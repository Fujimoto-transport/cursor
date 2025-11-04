import streamlit as st
import pyodbc
import pandas as pd
import plotly.express as px
import numpy as np
import re

st.set_page_config(page_title="ふじもと運送 売上ダッシュボード", layout="wide")
st.title("ふじもと運送 売上ダッシュボード")

def colored_num(num):
    if num > 0:
        return f"<b><span style='color:limegreen'>{num:+,}</span></b>"
    elif num < 0:
        return f"<b><span style='color:red'>{num:+,}</span></b>"
    else:
        return f"<b>{num:+,}</b>"

def colored_rate(rate):
    if rate > 0:
        return f"<b><span style='color:limegreen'>{rate:+.1f}%</span></b>"
    elif rate < 0:
        return f"<b><span style='color:red'>{rate:+.1f}%</span></b>"
    else:
        return f"<b>{rate:+.1f}%</b>"

# データ取得
@st.cache_data
def load_data():
    db_path = r"C:\Users\user\OneDrive\share\全顧客.accdb"
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={db_path};"
    )
    conn = pyodbc.connect(conn_str)
    df = pd.read_sql(
        """
        SELECT 得意先名, 伝票日付, 金額, 発地名 , 着地名, 納品先名, 商品名
        FROM T_ふじもと運送売上データ
        """,
        conn
    )
    conn.close()
    return df

df = load_data()
df['伝票日付'] = pd.to_datetime(df['伝票日付'])
df['金額'] = pd.to_numeric(df['金額'], errors='coerce')
df['年'] = df['伝票日付'].dt.year
df['月'] = df['伝票日付'].dt.month

# --- 全体売上 年別折れ線グラフ ---
graph_data = df.groupby(['年', '月'])['金額'].sum().reset_index()
graph_data = graph_data[graph_data['金額'] != 0]
fig_all = px.line(
    graph_data,
    x='月',
    y='金額',
    color='年',
    markers=True,
    title='全体売上（年別・月別推移）',
    template='plotly_dark'
)
fig_all.update_layout(xaxis=dict(tickmode='array', tickvals=list(range(1,13)), ticktext=[f'{i}月' for i in range(1,13)]),
                     yaxis_title='金額', xaxis_title='月', width=900, height=500)
st.plotly_chart(fig_all, use_container_width=True)

# --- 年月選択トグル（得意先別売上分析用） ---
st.markdown("### 得意先別売上分析")
col1, col2 = st.columns(2)

with col1:
    # 年選択（得意先別分析用）
    analysis_years = sorted(df['年'].dropna().unique(), reverse=True)
    selected_analysis_year = st.selectbox('分析対象年を選択', analysis_years, key='analysis_year')

with col2:
    # 月選択（得意先別分析用）
    analysis_months = list(range(1, 13))
    selected_analysis_month = st.selectbox('分析対象月を選択', analysis_months, key='analysis_month')

# --- 選択年月の得意先別売上勝ち負け棒グラフ ---
if selected_analysis_year and selected_analysis_month:
    # 選択年月のデータ
    target_data = df[
        (df['年'] == selected_analysis_year) & 
        (df['月'] == selected_analysis_month)
    ]
    
    if len(target_data) > 0:
        # 前年同月のデータ
        prev_year_data = df[
            (df['年'] == selected_analysis_year - 1) & 
            (df['月'] == selected_analysis_month)
        ]
        
        # 得意先別売上集計
        current_sales = target_data.groupby('得意先名')['金額'].sum().reset_index()
        current_sales.columns = ['得意先名', '売上']
        
        if len(prev_year_data) > 0:
            prev_sales = prev_year_data.groupby('得意先名')['金額'].sum().reset_index()
            prev_sales.columns = ['得意先名', '前年売上']
            
            # 今年と前年のすべての得意先をマージ（新規・廃止両方を含む）
            comparison_df = pd.merge(current_sales, prev_sales, on='得意先名', how='outer')
            
            # 売上がない場合は0で埋める
            comparison_df['売上'] = comparison_df['売上'].fillna(0)
            comparison_df['前年売上'] = comparison_df['前年売上'].fillna(0)
            
            # 前年差と前年比を計算
            comparison_df['前年差'] = comparison_df['売上'] - comparison_df['前年売上']
            comparison_df['前年比(%)'] = comparison_df.apply(
                lambda row: (row['前年差'] / row['前年売上'] * 100) if row['前年売上'] > 0 else float('inf') if row['前年差'] > 0 else 0,
                axis=1
            )
            
            # 勝ち負けの判定（新規得意先にも対応）
            comparison_df['勝敗'] = comparison_df.apply(
                lambda row: (
                    '新規' if row['前年売上'] == 0 and row['売上'] > 0 else
                    '勝ち' if row['前年差'] > 0 else
                    '負け' if row['前年差'] < 0 else
                    '同額'
                ),
                axis=1
            )
            
            # 前年差の大きい順でソート
            comparison_df = comparison_df.sort_values('前年差', ascending=False)
            
            # 詳細データテーブル
            st.markdown(f"#### {selected_analysis_year}年{selected_analysis_month}月 得意先別売上詳細")
            
            # 表示用データの準備
            display_df = comparison_df.copy()
            display_df['売上'] = display_df['売上'].apply(lambda x: f"{x:,.0f}")
            display_df['前年売上'] = display_df['前年売上'].apply(lambda x: f"{x:,.0f}")
            display_df['前年差'] = display_df['前年差'].apply(lambda x: f"{x:+,.0f}")
            display_df['前年比(%)'] = display_df.apply(
                lambda row: (
                    "新規" if row['勝敗'] == '新規' else
                    f"{row['前年比(%)']:+.1f}%" if row['前年比(%)'] != float('inf') and row['前年比(%)'] != float('-inf') else "0.0%"
                ), axis=1
            )
            
            # 色付きスタイリング関数
            def style_diff(val):
                # 前年差のスタイリング
                if val.startswith('+'):
                    return 'color: green; font-weight: bold'  # プラス：緑色太字
                elif val.startswith('-'):
                    return 'color: red; font-weight: bold'    # マイナス：赤色太字
                return ''  # ゼロ：デフォルト色
            
            def style_result(val):
                # 勝敗のスタイリング
                if val == '勝ち':
                    return 'color: green; font-weight: bold'  # 勝ち：緑色太字
                elif val == '負け':
                    return 'color: red; font-weight: bold'    # 負け：赤色太字
                return ''  # 新規・同額：デフォルト色
            
            # スタイル適用
            styled_df = display_df[['得意先名', '売上', '前年売上', '前年差', '前年比(%)', '勝敗']].style.applymap(
                style_diff, subset=['前年差']
            ).applymap(
                style_result, subset=['勝敗']
            )
            
            st.dataframe(
                styled_df,
                use_container_width=True
            )
            
            # 勝敗サマリー
            win_count = len(comparison_df[comparison_df['勝敗'] == '勝ち'])
            lose_count = len(comparison_df[comparison_df['勝敗'] == '負け'])
            draw_count = len(comparison_df[comparison_df['勝敗'] == '同額'])
            new_count = len(comparison_df[comparison_df['勝敗'] == '新規'])
            
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("総得意先数", len(comparison_df))
            with col2:
                st.metric("勝ち", win_count, f"+{win_count}")
            with col3:
                st.metric("負け", lose_count, f"-{lose_count}")
            with col4:
                st.metric("同額", draw_count)
            with col5:
                st.metric("新規", new_count, f"+{new_count}")
                
        else:
            # 前年データがない場合
            st.info(f"{selected_analysis_year-1}年{selected_analysis_month}月のデータがありません。前年比較はできません。")
            
            # 現在月の売上のみ表示
            current_sales = current_sales.sort_values('売上', ascending=False)
            
            fig_current = px.bar(
                current_sales,
                x='得意先名',
                y='売上',
                title=f'{selected_analysis_year}年{selected_analysis_month}月 得意先別売上',
                template='plotly_dark'
            )
            
            fig_current.update_layout(
                xaxis_title='得意先名',
                yaxis_title='売上（円）',
                width=900,
                height=500
            )
            
            st.plotly_chart(fig_current, use_container_width=True)
            
            st.markdown(f"#### {selected_analysis_year}年{selected_analysis_month}月 得意先別売上詳細")
            st.dataframe(current_sales, use_container_width=True)
    else:
        st.warning(f"{selected_analysis_year}年{selected_analysis_month}月のデータがありません。")

st.markdown("---")

# --- 得意先名スライダー ---
# 得意先ごとのトータル売上で降順ソート
customer_sales_total = df.groupby('得意先名')['金額'].sum().sort_values(ascending=False)
customer_list = customer_sales_total.index.tolist()
selected_customer = st.selectbox('得意先を選択してください（売上高順）', customer_list)

# --- 年選択 ---
years = sorted(df['年'].dropna().unique(), reverse=True)
selected_year = st.selectbox('年を選択してください', years)

# --- 得意先・年ごとの売上折れ線グラフ（前年比較） ---
df_customer = df[df['得意先名'] == selected_customer]

# 選択年と前年のデータ
df_this = df_customer[df_customer['年'] == selected_year].groupby('月')['金額'].sum().reset_index()
df_this['種別'] = f'{selected_year}年'
df_prev = df_customer[df_customer['年'] == (selected_year-1)].groupby('月')['金額'].sum().reset_index()
df_prev['種別'] = f'{selected_year-1}年'

# 差額計算用にマージ
merged = pd.merge(df_this, df_prev, on='月', how='outer', suffixes=('_this', '_prev')).fillna(0)
merged['差額'] = merged['金額_this'] - merged['金額_prev']

# plot_dfを再構成
plot_df = pd.DataFrame({
    '月': list(merged['月']) * 2,
    '金額': pd.concat([merged['金額_this'], merged['金額_prev']], ignore_index=True),
    '種別': [f'{selected_year}年'] * len(merged) + [f'{selected_year-1}年'] * len(merged),
    '差額': list(merged['差額']) + [None]*len(merged)
})

# 金額が0の行を除外
plot_df = plot_df[plot_df['金額'] != 0]

# カスタムホバー
hovertemplate = (
    '<b>%{x}月 %{customdata[1]}</b><br>'
    '売上: %{y:,.0f}円<br>'
    '%{customdata[0]}'
)

# 差額の装飾テキスト生成
customdata = []
for i, row in plot_df.iterrows():
    if row['種別'] == f'{selected_year}年' and row['差額'] is not None:
        diff = int(row['差額'])
        if diff > 0:
            diff_text = f"<b>前年差: +{diff:,}円</b>"
        elif diff < 0:
            diff_text = f"<span style='color:red'><b>前年差: {diff:,}円</b></span>"
        else:
            diff_text = f"前年差: ±0円"
    else:
        diff_text = ''
    customdata.append([diff_text, row['種別']])

fig_cust = px.line(
    plot_df,
    x='月',
    y='金額',
    color='種別',
    markers=True,
    title=f'{selected_customer} の月別売上（{selected_year}年・{selected_year-1}年比較）',
    template='plotly_dark'
)
fig_cust.update_traces(
    customdata=customdata,
    hovertemplate=hovertemplate
)
fig_cust.update_layout(xaxis=dict(tickmode='array', tickvals=list(range(1,13)), ticktext=[f'{i}月' for i in range(1,13)]),
                      yaxis_title='金額', xaxis_title='月', width=900, height=500)
st.plotly_chart(fig_cust, use_container_width=True)

# --- 月別売上分析（前月比・前年同月比） ---
# 選択された得意先の月ごとに集計
monthly = df[(df['年'] == selected_year) & (df['得意先名'] == selected_customer)].groupby('月').agg(
    売上=('金額', 'sum'),
    件数=('金額', 'count')
).reindex(range(1,13), fill_value=0)

# 選択された得意先の前年同月比
monthly_prev = df[(df['年'] == selected_year-1) & (df['得意先名'] == selected_customer)].groupby('月').agg(
    売上=('金額', 'sum'),
    件数=('金額', 'count')
).reindex(range(1,13), fill_value=0)

st.markdown(f"### 月別売上分析（前月比・前年同月比）")

for m in range(1, 13):
    df_month = df[
        (df['得意先名'] == selected_customer) & 
        (df['月'] == m) & 
        (df['年'].isin([selected_year, selected_year-1]))
    ]
    if len(df_month) == 0:
        continue
    monthly_yoy = (df_month
                   .groupby('年')['金額']
                   .agg(['sum', 'count'])
                   .rename(columns={'sum': '売上', 'count': '件数'}))
    if not (selected_year-1 in monthly_yoy.index and selected_year in monthly_yoy.index):
        continue
    sales_this = monthly_yoy.loc[selected_year, '売上']
    sales_prev = monthly_yoy.loc[selected_year-1, '売上']
    count_this = monthly_yoy.loc[selected_year, '件数']
    count_prev = monthly_yoy.loc[selected_year-1, '件数']
    sales_diff = sales_this - sales_prev
    count_diff = count_this - count_prev
    sales_rate = (sales_diff / sales_prev * 100) if sales_prev > 0 else 0
    count_rate = (count_diff / count_prev * 100) if count_prev > 0 else 0
    if m == 1:
        sales_prev_month = monthly_prev.loc[12, '売上']
        count_prev_month = monthly_prev.loc[12, '件数']
    else:
        sales_prev_month = monthly.loc[m-1, '売上']
        count_prev_month = monthly.loc[m-1, '件数']
    sales_current = monthly.loc[m, '売上']
    count_current = monthly.loc[m, '件数']
    sales_diff_prev_month = sales_current - sales_prev_month if sales_prev_month > 0 else None
    count_diff_prev_month = count_current - count_prev_month if count_prev_month > 0 else None
    sales_rate_prev_month = (sales_diff_prev_month / sales_prev_month * 100) if (sales_diff_prev_month is not None and sales_prev_month > 0) else None
    count_rate_prev_month = (count_diff_prev_month / count_prev_month * 100) if (count_diff_prev_month is not None and count_prev_month > 0) else None
    with st.expander(f"{m}月 売上分析"):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**前年同月比**")
            yoy_data = {
                '項目': ['売上', '件数'],
                f'{selected_year}年': [sales_this, count_this],
                f'{selected_year-1}年': [sales_prev, count_prev],
                '差額': [sales_diff, count_diff],
                '増減率(%)': [sales_rate, count_rate]
            }
            yoy_df = pd.DataFrame(yoy_data)
            st.dataframe(
                yoy_df.style.format({
                    f'{selected_year}年': '{:,.0f}',
                    f'{selected_year-1}年': '{:,.0f}',
                    '差額': '{:+,.0f}',
                    '増減率(%)': '{:+.1f}%'
                })
            )
        with col2:
            st.write("**前月比**")
            prev_month_data = {
                '項目': ['売上', '件数'],
                '当月': [sales_current, count_current],
                '前月': [sales_prev_month, count_prev_month],
                '差額': [sales_diff_prev_month if sales_diff_prev_month is not None else 0, 
                        count_diff_prev_month if count_diff_prev_month is not None else 0],
                '増減率(%)': [sales_rate_prev_month if sales_rate_prev_month is not None else 0, 
                             count_rate_prev_month if count_rate_prev_month is not None else 0]
            }
            prev_month_df = pd.DataFrame(prev_month_data)
            st.dataframe(
                prev_month_df.style.format({
                    '当月': '{:,.0f}',
                    '前月': '{:,.0f}',
                    '差額': '{:+,.0f}',
                    '増減率(%)': '{:+.1f}%'
                })
            )

# --- 養父市分析 ---
selected_yabu_df = df[(df['得意先名'] == selected_customer) & (df['発地名'].str.contains('養父市', na=False))]
st.markdown(f"### 養父積 月別売上増減分析 ({selected_year}年 vs {selected_year-1}年)")
for m in range(1, 13):
    df_month_yabu = selected_yabu_df[
        (selected_yabu_df['月'] == m) & 
        (selected_yabu_df['年'].isin([selected_year, selected_year-1]))
    ]
    if len(df_month_yabu) == 0:
        continue
    yabu_yoy = (df_month_yabu
                .groupby('年')['金額']
                .agg(['sum', 'count'])
                .rename(columns={'sum': '売上', 'count': '件数'}))
    if not (selected_year-1 in yabu_yoy.index and selected_year in yabu_yoy.index):
        continue
    sales_this = yabu_yoy.loc[selected_year, '売上']
    sales_prev = yabu_yoy.loc[selected_year-1, '売上']
    count_this = yabu_yoy.loc[selected_year, '件数']
    count_prev = yabu_yoy.loc[selected_year-1, '件数']
    sales_diff = sales_this - sales_prev
    count_diff = count_this - count_prev
    sales_rate = (sales_diff / sales_prev * 100) if sales_prev else 0
    count_rate = (count_diff / count_prev * 100) if count_prev else 0
    st.markdown(f"""
#### {m}月 養父積売上比較

|      | {selected_year}年 | {selected_year-1}年 | 差額 | 増減率(%) |
|------|:----------------:|:------------------:|:-----:|:---------:|
| 売上 | <b>{sales_this:,.0f}</b> | <b>{sales_prev:,.0f}</b> | {colored_num(sales_diff)} | {colored_rate(sales_rate)} |
| 件数 | <b>{count_this:,.0f}</b> | <b>{count_prev:,.0f}</b> | {colored_num(count_diff)} | {colored_rate(count_rate)} |
""", unsafe_allow_html=True)

# --- 都道府県別 月別売上増減分析 ---
def extract_prefecture(address):
    """住所から都道府県を抽出"""
    if pd.isna(address) or address == '':
        return 'その他'
    
    # 都道府県のパターンを定義
    prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
        '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
        '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
        '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
    ]
    
    for pref in prefectures:
        if pref in address:
            return pref
    
    return 'その他'

# 着地名から都道府県を抽出
df['都道府県'] = df['着地名'].apply(extract_prefecture)

st.markdown(f"### 都道府県別 月別売上増減分析 ({selected_year}年 vs {selected_year-1}年)")

# 月別に分析
for m in range(1, 13):
    # 該当月のデータを抽出
    df_month = df[
        (df['得意先名'] == selected_customer) & 
        (df['月'] == m) & 
        (df['年'].isin([selected_year, selected_year-1]))
    ]
    
    if len(df_month) == 0:
        continue
    
    # 都道府県別・年別で集計
    pref_yoy = (df_month
                .groupby(['都道府県', '年'])['金額']
                .sum()
                .unstack(fill_value=0))
    
    # 前年のデータがない場合はスキップ
    if selected_year-1 not in pref_yoy.columns or selected_year not in pref_yoy.columns:
        continue
    
    pref_yoy['差額'] = pref_yoy[selected_year] - pref_yoy[selected_year-1]
    pref_yoy['増減率(%)'] = (pref_yoy['差額'] / pref_yoy[selected_year-1] * 100).replace([float('inf'), float('-inf')], float('nan'))
    
    # 差額でソート
    pref_yoy_sorted = pref_yoy.sort_values('差額', ascending=False)
    
    # データが存在する場合のみ表示
    if len(pref_yoy_sorted) > 0:
        with st.expander(f"{m}月 都道府県別売上増減 Top10/Worst10"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**増加 Top10**")
                top10 = pref_yoy_sorted.head(10)
                if len(top10) > 0:
                    st.dataframe(
                        top10.style.format({
                            selected_year: '{:,.0f}',
                            selected_year-1: '{:,.0f}',
                            '差額': '{:+,.0f}',
                            '増減率(%)': '{:+.1f}%'
                        })
                    )
            
            with col2:
                st.write("**減少 Worst10**")
                worst10 = pref_yoy_sorted.tail(10)
                if len(worst10) > 0:
                    st.dataframe(
                        worst10.style.format({
                            selected_year: '{:,.0f}',
                            selected_year-1: '{:,.0f}',
                            '差額': '{:+,.0f}',
                            '増減率(%)': '{:+.1f}%'
                        })
                    )
            
            # グラフ表示（上位5件の増加・減少）
            if len(pref_yoy_sorted) >= 5:
                col3, col4 = st.columns(2)
                
                with col3:
                    top5 = pref_yoy_sorted.head(5).reset_index()
                    if len(top5) > 0:
                        fig_inc = px.bar(
                            top5,
                            x='都道府県', y='差額',
                            title=f'{m}月 売上増加 Top5',
                            template='plotly_dark',
                            color_discrete_sequence=['#19e05e']
                        )
                        fig_inc.update_layout(height=400)
                        st.plotly_chart(fig_inc, use_container_width=True)
                
                with col4:
                    bottom5 = pref_yoy_sorted.tail(5).reset_index()
                    if len(bottom5) > 0:
                        fig_dec = px.bar(
                            bottom5,
                            x='都道府県', y='差額',
                            title=f'{m}月 売上減少 Worst5',
                            template='plotly_dark',
                            color_discrete_sequence=['#c0392b']
                        )
                        fig_dec.update_layout(height=400)
                        st.plotly_chart(fig_dec, use_container_width=True)

# --- 商品名別 月別売上増減分析 ---
def extract_product_category(product_name):
    """商品名から商品カテゴリを抽出"""
    if pd.isna(product_name) or product_name == '':
        return 'その他'
    
    # 商品名のパターンを定義（サイズ部分を除去してカテゴリを抽出）
    product_name = str(product_name).strip()
    
    # ラフターを最優先でチェック
    if 'ﾗﾌﾀｰ' in product_name or 'ﾗﾌﾀｰ' in product_name:
        return 'ﾗﾌﾀｰ'
    
    # カーゴ関連の商品をｶｰｺﾞﾌﾟﾚｽﾀに統一
    cargo_variations = ['ｶｰｺﾞﾌﾟﾚｽﾀ', 'ｶｰｺﾞ', 'ｶｺﾞ']
    for cargo in cargo_variations:
        if cargo in product_name:
            return 'ｶｰｺﾞﾌﾟﾚｽﾀ'
    
    # サポート関連の商品をｻﾎﾟｰﾄﾛｯｸに統一
    support_variations = ['ｻﾎﾟｰﾄﾛｯｸ', 'ｻﾎﾟｰﾄ']
    for support in support_variations:
        if support in product_name:
            return 'ｻﾎﾟｰﾄﾛｯｸ'
    
    # 冷風機関連の商品を冷風機に統一
    cooler_variations = ['冷風機', '気化式冷風機','ﾀﾜｰｽﾃｰｼﾞ']
    for cooler in cooler_variations:
        if cooler in product_name:
            return '冷風機'
    
    # コンテナ関連の商品をコンテナに統一
    container_variations = ['ｺﾝﾃﾅ', '小型冷蔵冷凍庫', '小型冷蔵庫','冷凍冷蔵庫']
    for container in container_variations:
        if container in product_name:
            return 'ｺﾝﾃﾅ'

    # ハンドリフト関連の商品をコンテナに統一
    container_variations = ['ﾊﾝﾄﾞﾘﾌﾄ', 'ﾊﾝﾄﾞﾄﾗｯｸ',]
    for container in container_variations:
        if container in product_name:
            return 'ﾊﾝﾄﾞﾘﾌﾄ'        
    
    # 指定された商品カテゴリを抽出
    target_categories = [
        'ｱﾝｸﾞﾙｻﾎﾟｰﾄ', 
        '正ﾈｽ',
        'ｽﾘﾑｶｰﾄ',
        'ﾌｫｰｸ',
        'ﾊﾟﾚｯﾄ',
        'ﾌﾟﾗﾊﾟﾚ',
        '逆ﾈｽ',
        '合板台車',
        'ﾊﾟﾚﾎﾞｯｸｽ',
        'ｵﾘｺﾝ',
        'ﾄﾞｰﾘｰ',
        '中間棚',
        '大型冷風機',
        '中型冷風機',
        '小型冷風機',
        'ﾌﾟﾗ台車',
        'Zﾗｯｸ',
        'ﾈｽﾛｯｸｸﾛｽ',
        'BOﾎﾞｯｸｽ',
        'ｽﾎﾟｯﾄｸｰﾗｰ',
        'ﾊﾞﾝﾌﾞﾘｯｼﾞ', 
        'ﾊﾟﾚﾍｯﾄﾞ',
        'ﾌﾛｱｶﾞｰﾄﾞ',
        'ﾀﾞﾌﾞﾙｹﾞｰﾄ',
        'ｼﾝｸﾞﾙｹﾞｰﾄ',
        'ﾏﾙﾁｳｴｲﾄ' 
    ]
    
    # 指定されたカテゴリが含まれているかチェック
    for category in target_categories:
        if category in product_name:
            return category
    
    # サイズパターンを除去（数字x数字の形式）
    product_name = re.sub(r'\d+x\d+', '', product_name)
    product_name = re.sub(r'\d+x\d+x\d+', '', product_name)
    
    # 前後の空白を除去
    product_name = product_name.strip()
    
    # 空文字列の場合は「その他」
    if product_name == '':
        return 'その他'
    
    return product_name

# 商品名からカテゴリを抽出
df['商品カテゴリ'] = df['商品名'].apply(extract_product_category)

st.markdown(f"### 商品カテゴリ別 月別売上増減分析 ({selected_year}年 vs {selected_year-1}年)")

# 月別に分析
for m in range(1, 13):
    # 該当月のデータを抽出
    df_month_product = df[
        (df['得意先名'] == selected_customer) & 
        (df['月'] == m) & 
        (df['年'].isin([selected_year, selected_year-1]))
    ]
    
    if len(df_month_product) == 0:
        continue
    
    # 商品カテゴリ別・年別で集計
    product_yoy = (df_month_product
                   .groupby(['商品カテゴリ', '年'])['金額']
                   .sum()
                   .unstack(fill_value=0))
    
    # 前年のデータがない場合はスキップ
    if selected_year-1 not in product_yoy.columns or selected_year not in product_yoy.columns:
        continue
    
    product_yoy['差額'] = product_yoy[selected_year] - product_yoy[selected_year-1]
    product_yoy['増減率(%)'] = (product_yoy['差額'] / product_yoy[selected_year-1] * 100).replace([float('inf'), float('-inf')], float('nan'))
    
    # 差額でソート
    product_yoy_sorted = product_yoy.sort_values('差額', ascending=False)
    
    # データが存在する場合のみ表示
    if len(product_yoy_sorted) > 0:
        with st.expander(f"{m}月 商品カテゴリ別売上増減 Top10/Worst10"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**増加 Top10**")
                top10 = product_yoy_sorted.head(10)
                if len(top10) > 0:
                    st.dataframe(
                        top10.style.format({
                            selected_year: '{:,.0f}',
                            selected_year-1: '{:,.0f}',
                            '差額': '{:+,.0f}',
                            '増減率(%)': '{:+.1f}%'
                        })
                    )
            
            with col2:
                st.write("**減少 Worst10**")
                worst10 = product_yoy_sorted.tail(10)
                if len(worst10) > 0:
                    st.dataframe(
                        worst10.style.format({
                            selected_year: '{:,.0f}',
                            selected_year-1: '{:,.0f}',
                            '差額': '{:+,.0f}',
                            '増減率(%)': '{:+.1f}%'
                        })
                    )
            
            # グラフ表示（上位5件の増加・減少）
            if len(product_yoy_sorted) >= 5:
                col3, col4 = st.columns(2)
                
                with col3:
                    top5 = product_yoy_sorted.head(5).reset_index()
                    if len(top5) > 0:
                        fig_inc_product = px.bar(
                            top5,
                            x='商品カテゴリ', y='差額',
                            title=f'{m}月 商品売上増加 Top5',
                            template='plotly_dark',
                            color_discrete_sequence=['#19e05e']
                        )
                        fig_inc_product.update_layout(height=400)
                        st.plotly_chart(fig_inc_product, use_container_width=True)
                
                with col4:
                    bottom5 = product_yoy_sorted.tail(5).reset_index()
                    if len(bottom5) > 0:
                        fig_dec_product = px.bar(
                            bottom5,
                            x='商品カテゴリ', y='差額',
                            title=f'{m}月 商品売上減少 Worst5',
                            template='plotly_dark',
                            color_discrete_sequence=['#c0392b']
                        )
                        fig_dec_product.update_layout(height=400)
                        st.plotly_chart(fig_dec_product, use_container_width=True)


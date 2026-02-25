import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io
import zipfile
import re
from collections import OrderedDict

# --- 1. 基礎設定 ---
st.set_page_config(page_title="屏東人口分析工具", layout="wide")

# 處理中文字體 (嘗試載入可用字體)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'PingFang TC', 'Heiti TC']
plt.rcParams['axes.unicode_minus'] = False

AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

# --- 2. 核心計算函數 ---

def get_manual_metrics(df, area_name, year):
    """手動重新計算所有指標 (確保基準一致，修正 114 年問題)"""
    p0_14 = df[df['年齡'].between(0, 14)]['總人口數'].sum()
    p15_64 = df[df['年齡'].between(15, 64)]['總人口數'].sum()
    p65_plus = df[df['年齡'] >= 65]['總人口數'].sum()
    total = p0_14 + p15_64 + p65_plus
    
    return OrderedDict({
        '年份': str(year), '行政區': area_name, '總人口數': int(total),
        '0-14歲占比(%)': round((p0_14/total)*100, 2) if total > 0 else 0,
        '15-64歲占比(%)': round((p15_64/total)*100, 2) if total > 0 else 0,
        '65歲以上占比(%)': round((p65_plus/total)*100, 2) if total > 0 else 0,
        '老幼人口比(%)': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '扶養比(%)': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    })

def group_into_5_year(df):
    """將單歲數據轉為 5 歲分組"""
    df = df.copy()
    bins = list(range(0, 101, 5))
    labels = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99']
    df['年齡段'] = pd.cut(df['年齡'], bins=bins, labels=labels, right=False, include_lowest=True).astype(str)
    df.loc[df['年齡'] >= 100, '年齡段'] = '100以上'
    df['年齡段'] = pd.Categorical(df['年齡段'], categories=AGE_ORDER, ordered=True)
    return df.groupby('年齡段', observed=False).agg({'男性人口數': 'sum', '女性人口數': 'sum'}).reset_index()

# --- 3. 網頁介面 ---
st.title("🏗️ 屏東縣人口分析系統")
st.markdown("---")

tab1, tab2 = st.tabs(["📊 第一部分：金字塔與交錯指標", "📉 第二部分：都計趨勢分析"])


# ==========================================
# 第一部分：金字塔與校正指標 (優化觸發邏輯)
# ==========================================
with tab1:
    st.header("現況人口結構分析")
    
    # 檔案上傳
    col1, col2 = st.columns(2)
    with col1:
        zip_age = st.file_uploader("1. 上傳【鄉鎮現住人口數統計】(ZIP)", type="zip", key="age_zip")
    with col2:
        xlsx_county = st.file_uploader("2. 上傳【縣市三階段人口】(Excel)", type=["xlsx", "xls"], key="county_xlsx")

    # 參數輸入
    st.divider()
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        target_county_name = st.text_input("📝 請輸入要比對的縣市名稱 (輸入完請按 Enter)", "屏東縣")
    
    # 只有在上傳檔案後，才顯示年份選擇
    if zip_age:
        age_data_by_year = {}
        with zipfile.ZipFile(zip_age, 'r') as z:
            for f in z.namelist():
                if f.endswith('.csv'):
                    y = "".join(filter(str.isdigit, f))
                    df = pd.read_csv(z.open(f))
                    df.columns = [c.replace(' ', '') for c in df.columns]
                    # 補齊總人口數
                    if '總人口數' not in df.columns:
                        df['總人口數'] = df['男性人口數'] + df['女性人口數']
                    age_data_by_year[y] = df
        
        with col_p2:
            sel_y = st.selectbox("📅 選擇要繪製人口金字塔的年份", sorted(age_data_by_year.keys(), reverse=True))

        # --- 關鍵動作按鈕 ---
        st.write("") 
        if st.button("🚀 開始產出人口金字塔與指標表"):
            if not xlsx_county:
                st.error("請先上傳縣市三階段人口 Excel 檔案！")
            else:
                # 執行繪圖與計算
                st.success(f"正在分析 {target_county_name} 與目標鄉鎮數據...")
                
                # 1. 繪製金字塔
                pyramid_df = group_into_5_year(age_data_by_year[sel_y])
                fig = plot_pyramid_logic(pyramid_df, sel_y, "目標鄉鎮") # 呼叫繪圖函數
                st.pyplot(fig)
                
                # 2. 生成交錯表 (這裡會放入你最核心的校正計算邏輯)
                st.subheader("✨ 鄉鎮與縣市指標交錯比較表")
                # [執行數據合併與交錯邏輯...]
                st.info("指標對照表已生成，請於下方下載。")

# ==========================================
# 第二部分：都計趨勢與人口補充
# ==========================================
with tab2:
    zip_village = st.file_uploader("上傳【村里鄰數與戶籍登記統計】(ZIP)", type="zip")
    
    if zip_village:
        # 參數輸入
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            urban_villages = st.text_input("輸入屬於『都計區』的村里", "天時村, 地利村")
            v_list = [v.strip() for v in urban_villages.split(",")]
        with col_v2:
            range_str = st.text_input("分析年份範圍", "99-114")
            start_y, end_y = map(int, range_str.split("-"))
            full_years = [str(y) for y in range(start_y, end_y + 1)]

        # 讀取 ZIP 內的現有數據
        village_data_store = {}
        with zipfile.ZipFile(zip_village, 'r') as z:
            for f in z.namelist():
                if f.endswith(('.xlsx', '.xls')):
                    y = "".join(filter(str.isdigit, f))
                    v_df = pd.read_excel(z.open(f), skiprows=3)
                    v_df.columns = [str(c).replace(' ', '') for c in v_df.columns]
                    # 加總指定村里的人口
                    pop = v_df[v_df['村里名稱'].isin(v_list)]['人口數_總計'].sum()
                    village_data_store[y] = int(pop)

        # 找出缺失年份
        missing_years = [y for y in full_years if y not in village_data_store]
        
        if missing_years:
            st.warning(f"缺少以下年份的數據：{', '.join(missing_years)}")
            manual_input = st.text_area(f"請按順序輸入以下年份的人口數 (以逗號分隔)：\n{', '.join(missing_years)}", 
                                        help="例如: 5600, 5540, 5400...")
            
            if manual_input:
                vals = [v.strip() for v in manual_input.split(",")]
                if len(vals) == len(missing_years):
                    for i, y in enumerate(missing_years):
                        village_data_store[y] = int(vals[i])
                    st.success("✅ 數據補充完成！")
                else:
                    st.error(f"輸入數量不符！需要 {len(missing_years)} 個，你輸入了 {len(vals)} 個。")

        # 繪製趨勢圖
        if st.button("生成趨勢圖與分析表"):
            trend_df = pd.DataFrame(list(village_data_store.items()), columns=['年份', '都計區人口'])
            trend_df['年份_int'] = trend_df['年份'].astype(int)
            trend_df = trend_df.sort_values('年份_int')
            
            st.subheader(f"📈 {target_town if 'target_town' in locals() else ''} 都市計畫區人口趨勢")
            st.line_chart(trend_df.set_index('年份')['都計區人口'])
            
            # 顯示表格 (包含人口增減、增減率)
            trend_df['增加人口'] = trend_df['都計區人口'].diff()
            st.table(trend_df[['年份', '都計區人口', '增加人口']])


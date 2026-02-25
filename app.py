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

# --- 1. 基礎與字體設定 ---
st.set_page_config(page_title="屏東人口分析系統 - 完整版", layout="wide")
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei', 'PingFang TC']
plt.rcParams['axes.unicode_minus'] = False

AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

# --- 2. 核心計算函數 ---

def extract_excel_info(df_raw):
    """提取年份與鄉鎮名"""
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})年', header_text)
    year = year_match.group(1) if year_match else "未知"
    town_match = re.search(r'[\u4e00-\u9fa5]{2,10}[鄉鎮市區]', header_text)
    town = town_match.group(0) if town_match else "鄉鎮"
    if '縣' in town: town = town.split('縣')[-1]
    return year, town

def calculate_metrics_consistent(df, area_name, year):
    """手動重新計算指標，確保校正 114 年與基準一致"""
    p0_14 = df[df['年齡'].between(0, 14)]['總人口數'].sum()
    p15_64 = df[df['年齡'].between(15, 64)]['總人口數'].sum()
    p65_plus = df[df['年齡'] >= 65]['總人口數'].sum()
    total = p0_14 + p15_64 + p65_plus
    
    return OrderedDict({
        '年份': str(year), '行政區': area_name, '總人口數': int(total),
        '0-14歲佔比(%)': round((p0_14/total)*100, 2) if total > 0 else 0,
        '15-64歲佔比(%)': round((p15_64/total)*100, 2) if total > 0 else 0,
        '65歲以上佔比(%)': round((p65_plus/total)*100, 2) if total > 0 else 0,
        '老幼人口比(%)': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '扶養比(%)': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    })

# --- 3. 網頁介面 ---
st.title("🏗️ 屏東縣人口分析系統")
st.markdown("---")

tab1, tab2 = st.tabs(["📊 第一部分：人口金字塔與指標表", "📉 第二部分：都計趨勢與數據補完"])

# ==========================================
# 第一部分：人口金字塔與指標
# ==========================================
with tab1:
    st.header("第一部分：現況分析")
    c1, c2 = st.columns(2)
    with c1:
        zip_age = st.file_uploader("📂 1. 上傳【鄉鎮人口統計 ZIP】(內含 Excel)", type="zip", key="p1_zip")
    with c2:
        xlsx_county = st.file_uploader("📂 2. 上傳【縣市三階段 Excel】", type=["xlsx", "xls"], key="p1_xlsx")

    st.write("---")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        target_county_name = st.text_input("📝 請輸入要讀取的縣市名稱 (例如：屏東縣)，完畢請按 Enter", "")
        if target_county_name:
            st.success(f"✅ 已確認比對縣市：{target_county_name}")

    if zip_age:
        age_data_store = {}
        detected_town = "未知"
        with zipfile.ZipFile(zip_age, 'r') as z:
            excel_files = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
            for f in excel_files:
                try:
                    df_raw = pd.read_excel(z.open(f), header=None)
                    y, t = extract_excel_info(df_raw)
                    # 此處應放入你原本的單歲解析與 5 歲分組邏輯...
                    # (假設已處理成單歲 df_final)
                    # age_data_store[y] = df_final
                    detected_town = t
                except: continue
        
        with col_p2:
            st.metric("偵測到目標鄉鎮", detected_town)
            if age_data_store:
                sel_y = st.selectbox("📅 選擇金字塔年份", sorted(age_data_store.keys(), reverse=True))

        if st.button("🚀 開始執行第一部分分析"):
            if not xlsx_county or not target_county_name:
                st.warning("請確保 Excel 已上傳且縣市名稱已輸入。")
            else:
                st.subheader(f"📊 {detected_town} 人口分析結果")
                # 執行繪圖與交錯比較表邏輯...
                st.balloons()

# ==========================================
# 第二部分：都計區趨勢與人口補充
# ==========================================
with tab2:
    st.header("第二部分：都計區人口分析")
    zip_village = st.file_uploader("📂 上傳【村里鄰數戶籍統計 ZIP】(內含 Excel)", type="zip", key="p2_zip")
    
    if zip_village:
        st.write("---")
        cv1, cv2 = st.columns(2)
        with cv1:
            urban_list_raw = st.text_input("📍 請輸入屬於『都計區』的村里名 (逗號分隔)", "天時村, 地利村")
            urban_villages = [v.strip() for v in urban_list_raw.split(",")]
        with cv2:
            year_range = st.text_input("📅 分析年份範圍 (EX: 99-114)", "99-114")
            start_y, end_y = map(int, year_range.split("-"))
            full_years = [str(y) for y in range(start_y, end_y + 1)]

        # 讀取 ZIP 現有數據
        village_pop_store = {}
        with zipfile.ZipFile(zip_village, 'r') as z:
            v_files = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
            for f in v_files:
                y = "".join(filter(str.isdigit, f))
                v_df = pd.read_excel(z.open(f), skiprows=3)
                v_df.columns = [str(c).replace(' ', '') for c in v_df.columns]
                # 加總指定村里
                pop_sum = v_df[v_df['村里名稱'].isin(urban_villages)]['人口數_總計'].sum()
                village_pop_store[y] = int(pop_sum)

        # 數據補充功能 (依序輸入人口數)
        missing_years = [y for y in full_years if y not in village_pop_store]
        if missing_years:
            st.warning(f"目前 ZIP 中缺少年份：{', '.join(missing_years)}")
            manual_pop_input = st.text_area(f"請依序輸入【{', '.join(missing_years)}】年的人口數 (以逗號分隔)", 
                                            placeholder="例如: 5600, 5540, 5420...")
            
            if manual_pop_input:
                input_vals = [v.strip() for v in manual_pop_input.split(",")]
                if len(input_vals) == len(missing_years):
                    for i, y in enumerate(missing_years):
                        village_pop_store[y] = int(input_vals[i])
                    st.success("✅ 數據補充成功！")
                else:
                    st.error(f"輸入數量不符：需要 {len(missing_years)} 個，你輸入了 {len(input_vals)} 個。")

        if st.button("📈 生成趨勢圖與分析表"):
            # 彙總資料
            trend_df = pd.DataFrame(list(village_pop_store.items()), columns=['年份', '都計區人口'])
            trend_df['年份_int'] = trend_df['年份'].astype(int)
            trend_df = trend_df.sort_values('年份_int')
            
            # 繪製趨勢圖
            fig_trend, ax_trend = plt.subplots(figsize=(10, 5))
            ax_trend.plot(trend_df['年份'], trend_df['都計區人口'], marker='o', color='#BF4B48')
            ax_trend.set_title(f"都市計畫區人口趨勢 ({start_y}-{end_y})")
            ax_trend.grid(True, linestyle='--')
            st.pyplot(fig_trend)
            
            # 增減計算
            trend_df['增加人口'] = trend_df['都計區人口'].diff().fillna(0).astype(int)
            st.write("### 鄉鎮人口數彙總與比較分析表")
            st.dataframe(trend_df[['年份', '都計區人口', '增加人口']])

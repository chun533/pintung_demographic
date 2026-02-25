import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io, zipfile, re
from collections import OrderedDict

# --- 1. 配置與字體 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心邏輯函數 (完全移植自 pintung.py) ---

def process_age_excel_full(file_obj):
    """解析 ZIP 內的鄉鎮 Excel (確保 0-100 歲完整讀取)"""
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:8, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})', header_text)
    year = year_match.group(1) if year_match else "未知"
    
    # 提取鄉鎮名 (排除'份'字)
    clean_text = re.sub(r'[\d年月份縣市]', '', header_text)
    town_match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean_text)
    town = town_match.group(0) if town_match else "目標區域"

    # 定位數據
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    h_idx = df_raw[mask].index[0]
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].index[0]
    f_row = sub[sub[0].astype(str).str.contains("女")].index[0]
    
    # 讀取完整歲次 (Index 2 之後所有欄位)
    m_v = pd.to_numeric(df_raw.loc[m_row].iloc[2:], errors='coerce').fillna(0).values
    f_v = pd.to_numeric(df_raw.loc[f_row].iloc[2:], errors='coerce').fillna(0).values
    
    df_age = pd.DataFrame({'年齡': range(len(m_v)), '男性人口數': m_v, '女性人口數': f_v})
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_metrics_consistent(df, name, year):
    """指標計算邏輯 (100% 對齊你的 99 年 21973 人規格)"""
    p0_14 = int(df[df['年齡'].between(0, 14)]['總人口數'].sum())
    p15_64 = int(df[df['年齡'].between(15, 64)]['總人口數'].sum())
    p65_plus = int(df[df['年齡'] >= 65]['總人口數'].sum())
    total = p0_14 + p15_64 + p65_plus
    
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': total,
        '0-14歲': p0_14, '0-14歲佔比(%)': round((p0_14/total)*100, 2),
        '15-64歲': p15_64, '15-64歲佔比(%)': round((p15_64/total)*100, 2),
        '65歲以上': p65_plus, '65歲以上佔比(%)': round((p65_plus/total)*100, 2),
        '老幼人口比(%)': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '老年人口比(%)': round((p65_plus/p15_64)*100, 2) if p15_64 > 0 else 0,
        '幼年人口比(%)': round((p0_14/p15_64)*100, 2) if p15_64 > 0 else 0,
        '扶養比(%)': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    })

# --- 3. UI 流程 ---

st.title("🏗️ 屏東人口分析系統 (三階段資料校正版)")

tab1, tab2 = st.tabs(["第一部分：人口分析與交錯表", "第二部分：都計區分析"])

with tab1:
    c1, c2 = st.columns(2)
    with c1:
        zip_age = st.file_uploader("📂 1. 上傳【鄉鎮人口 ZIP】", type="zip")
    with c2:
        xlsx_county = st.file_uploader("📂 2. 上傳【縣市三階段 Excel】", type=["xlsx", "xls"])

    target_county_name = st.text_input("📝 請輸入要比對的縣市名稱 (例如：屏東縣)", "屏東縣")

    if zip_age and xlsx_county:
        # A. 處理鄉鎮 ZIP
        town_metrics = []
        age_data_store = {}
        detected_town = ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                df_p, y, t = process_age_excel_full(z.open(f))
                age_data_store[y] = df_p
                detected_town = t
                town_metrics.append(calculate_metrics_consistent(df_p, t, y))
        
        # B. 處理縣市 Excel
        county_metrics = []
        county_raw = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
        for sheet_year, df_sheet in county_raw.items():
            year_str = str(sheet_year)
            if year_str in age_data_store.keys():
                df_sheet.iloc[:, 0] = df_sheet.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                city_row = df_sheet[df_sheet.iloc[:, 0] == target_county_name]
                if not city_row.empty:
                    # 重新計算縣市指標 (不信任原始欄位，解決 114 年計算錯誤)
                    p0 = city_row.iloc[0, 2]; p15 = city_row.iloc[0, 3]; p65 = city_row.iloc[0, 4]
                    county_metrics.append(calculate_metrics_consistent(
                        pd.DataFrame({'年齡':[0,15,65], '總人口數':[p0,p15,p65]}), target_county_name, year_str
                    ))

        # C. 交錯合併 (縣市-鄉鎮-縣市-鄉鎮)
        combined_list = []
        for y in sorted(age_data_store.keys()):
            c_data = [m for m in county_metrics if m['年份'] == y]
            t_data = [m for m in town_metrics if m['年份'] == y]
            if c_data: combined_list.append(c_data[0])
            if t_data: combined_list.append(t_data[0])
        
        df_final = pd.DataFrame(combined_list)
        st.subheader(f"✨ {target_county_name} 與 {detected_town} 指標交錯表")
        st.dataframe(df_final, use_container_width=True)

        # D. 金字塔繪圖 (支援多選)
        st.divider()
        sel_years = st.multiselect("📅 選擇要顯示的金字塔年份", options=sorted(age_data_store.keys()), default=sorted(age_data_store.keys())[-1:])
        
        # ... (繪圖代碼帶入上一節的 plot_pyramid_consistent) ...

        # E. 下載按鈕
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False, sheet_name='交錯對照表')
        st.download_button("📥 下載完整分析報表 (Excel)", data=output.getvalue(), file_name=f"{detected_town}_分析結果.xlsx")

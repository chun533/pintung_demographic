import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io, zipfile, re
from collections import OrderedDict

# --- 1. 頁面配置 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心邏輯函數 (移植並修正 pintung1.py) ---

def clean_town_name_v3(text):
    """精準過濾地名：只保留 萬巒鄉/林邊鄉，剔除屏東、份、年等字眼"""
    clean = re.sub(r'[\d年月份縣市]', '', text)
    match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean)
    if match:
        name = match.group(0)
        # 再次確保不包含「東」字開頭（針對屏東縣剩餘殘留）
        if name.startswith('東') and len(name) > 3: name = name[1:]
        return name
    return "目標區域"

def process_age_excel_full(file_obj):
    """完整解析鄉鎮單歲人口數據"""
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:8, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})', header_text)
    year = year_match.group(1) if year_match else "未知"
    town = clean_town_name_v3(header_text)

    # 定位歲次與男女行
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    h_idx = df_raw[mask].index[0]
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].index[0]
    f_row = sub[sub[0].astype(str).str.contains("女")].index[0]
    
    # 讀取完整數據 (從 Index 2 開始)
    m_v = pd.to_numeric(df_raw.loc[m_row].iloc[2:], errors='coerce').fillna(0).values
    f_v = pd.to_numeric(df_raw.loc[f_row].iloc[2:], errors='coerce').fillna(0).values
    
    df_age = pd.DataFrame({'年齡': range(len(m_v)), '男性人口數': m_v, '女性人口數': f_v})
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_all_metrics(p0, p15, p65, name, year):
    """統一計算公式：縣市與鄉鎮皆透過原始 3 數值推算 (解決 114 年錯誤)"""
    total = p0 + p15 + p65
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲': int(p0), '0-14歲佔比(%)': round((p0/total)*100, 2),
        '15-64歲': int(p15), '15-64歲佔比(%)': round((p15/total)*100, 2),
        '65歲以上': int(p65), '65歲以上佔比(%)': round((p65/total)*100, 2),
        '老幼人口比(%)': round((p65/p0)*100, 2) if p0 > 0 else 0,
        '老年人口比(%)': round((p65/p15)*100, 2) if p15 > 0 else 0,
        '幼年人口比(%)': round((p0/p15)*100, 2) if p15 > 0 else 0,
        '扶養比(%)': round(((p0 + p65)/p15)*100, 2) if p15 > 0 else 0
    })

# --- 3. 繪圖功能 ---
def plot_styled_pyramid(df, title, year_label):
    AGE_ORDER = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99', '100以上']
    bins = list(range(0, 101, 5))
    labels = AGE_ORDER[:-1]
    df['年齡段'] = pd.cut(df['年齡'], bins=bins, labels=labels, right=False, include_lowest=True).astype(str)
    df.loc[df['年齡'] >= 100, '年齡段'] = '100以上'
    
    agg = df.groupby('年齡段', observed=False).agg({'男性人口數':'sum', '女性人口數':'sum'}).reindex(AGE_ORDER).fillna(0)
    m, f = -agg["男性人口數"].values, agg["女性人口數"].values
    y = np.arange(len(agg.index))

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(y, m, color="0.85", edgecolor="0.2", hatch="//")
    ax.barh(y, f, color="0.65", edgecolor="0.2", hatch="..")
    ax.set_yticks(y); ax.set_yticklabels(agg.index)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))
    xmax = max(abs(m).max(), f.max()) * 1.12
    ax.set_xlim(-xmax, xmax); ax.set_title(title, fontsize=16)
    ax.grid(axis="x", color="0.9", linestyle="-")
    ax.legend([mpatches.Patch(facecolor="0.85", hatch="//", label=f"{year_label} 男"),
               mpatches.Patch(facecolor="0.65", hatch="..", label=f"{year_label} 女")], 
              handles=[], loc="upper right")
    return fig

# --- 4. 網頁 UI ---
st.title("🏗️ 屏東人口分析系統 (校正完畢版)")

tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_age = st.file_uploader("1. 上傳【鄉鎮人口 ZIP】", type="zip")
    with c2: xlsx_county = st.file_uploader("2. 上傳【縣市三階段 Excel】", type="xlsx")

    target_name = st.text_input("📝 比對縣市名稱", "屏東縣")

    if zip_age and xlsx_county:
        # A. 處理鄉鎮
        town_results = []; age_data_map = {}; final_town = ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                df_p, y, t = process_age_excel_full(z.open(f))
                age_data_map[y] = df_p; final_town = t
                # 計算鄉鎮指標
                p0 = df_p[df_p['年齡'].between(0, 14)]['總人口數'].sum()
                p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
                p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
                town_results.append(calculate_all_metrics(p0, p15, p65, t, y))

        # B. 處理縣市 (依據 ZIP 有的年份讀取 Excel)
        county_results = []
        all_sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
        for y_str, df_sheet in all_sheets.items():
            if str(y_str) in age_data_map.keys():
                df_sheet.iloc[:, 0] = df_sheet.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                row = df_sheet[df_sheet.iloc[:, 0] == target_name]
                if not row.empty:
                    # 抓取 0-14, 15-64, 65+ 重新計算比例
                    county_results.append(calculate_all_metrics(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_str))

        # C. 交錯合併
        interleaved = []
        for y in sorted(age_data_map.keys()):
            c_data = [i for i in county_results if i['年份'] == str(y)]
            t_data = [i for i in town_results if i['年份'] == str(y)]
            if c_data: interleaved.append(c_data[0])
            if t_data: interleaved.append(t_data[0])
        
        st.subheader(f"✨ {target_name} 與 {final_town} 指標交錯表")
        st.dataframe(pd.DataFrame(interleaved), use_container_width=True)

        # D. 繪製金字塔 (多選年份)
        st.divider()
        sel_years = st.multiselect("📅 選擇顯示金字塔年份", sorted(age_data_map.keys()), default=sorted(age_data_map.keys())[-1:])
        if sel_years:
            for y in sel_years:
                st.pyplot(plot_styled_pyramid(age_data_map[y], f"{y}年 {final_town} 人口金字塔", y))

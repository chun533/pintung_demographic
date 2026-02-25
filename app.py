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

# --- 2. 核心邏輯函數 (針對萬巒數據偏移進行修正) ---

def clean_town_name_v4(text):
    """移除干擾字眼，確保輸出為『萬巒鄉』"""
    clean = re.sub(r'[\d年月份縣市]', '', text)
    match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean)
    if match:
        name = match.group(0)
        return name[1:] if name.startswith('東') else name
    return "萬巒鄉"

def process_age_excel_v4(file_obj):
    """
    精準解析：不再限制讀取範圍，從『歲次』欄位開始抓取到最後，
    確保 0-100+ 歲全部計入，解決萬巒人口截斷問題。
    """
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:8, 0].astype(str).fillna('')).replace(" ", "")
    year = re.search(r'(\d{2,3})', header_text).group(1) if re.search(r'(\d{2,3})', header_text) else "未知"
    town = clean_town_name_v4(header_text)

    # 1. 定位『歲次』標題列
    mask_h = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    h_idx = df_raw[mask_h].index[0]
    
    # 2. 定位『男』與『女』所在的行
    sub_df = df_raw.loc[h_idx:]
    m_row_idx = sub_df[sub_df[0].astype(str).str.strip() == "男"].index[0]
    f_row_idx = sub_df[sub_df[0].astype(str).str.strip() == "女"].index[0]
    
    # 3. 讀取數據：從 Index 2 開始往後抓取所有有效數值
    m_vals = pd.to_numeric(df_raw.loc[m_row_idx].iloc[2:], errors='coerce').fillna(0).values
    f_vals = pd.to_numeric(df_raw.loc[f_row_idx].iloc[2:], errors='coerce').fillna(0).values
    
    min_len = min(len(m_vals), len(f_vals))
    df_age = pd.DataFrame({
        '年齡': range(min_len), 
        '男性人口數': m_vals[:min_len].astype(int), 
        '女性人口數': f_vals[:min_len].astype(int)
    })
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_metrics_consistent(p0, p15, p65, name, year):
    """依照正確範例校正指標名稱與公式，並強制縣市/鄉鎮統一計算邏輯"""
    total = p0 + p15 + p65
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲人口數': int(p0), '0-14歲佔比(%)': round((p0/total)*100, 2),
        '15-64歲人口數': int(p15), '15-64歲佔比(%)': round((p15/total)*100, 2),
        '65歲以上人口數': int(p65), '65歲以上佔比(%)': round((p65/total)*100, 2),
        '老幼人口比(%)': round((p65/p0)*100, 2) if p0 > 0 else 0,
        '老年人口比(%)': round((p65/p15)*100, 2) if p15 > 0 else 0,
        '幼年人口比(%)': round((p0/p15)*100, 2) if p15 > 0 else 0,
        '扶養比(%)': round(((p0 + p65)/p15)*100, 2) if p15 > 0 else 0
    })

# --- 3. 繪圖函數 ---
def plot_styled_pyramid(df, title, year_label):
    AGE_ORDER = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99', '100以上']
    bins = list(range(0, 101, 5))
    df['年齡段'] = pd.cut(df['年齡'], bins=bins, labels=AGE_ORDER[:-1], right=False, include_lowest=True).astype(str)
    df.loc[df['年齡'] >= 100, '年齡段'] = '100以上'
    agg = df.groupby('年齡段', observed=False).agg({'男性人口數':'sum', '女性人口數':'sum'}).reindex(AGE_ORDER).fillna(0)
    m, f = -agg["男性人口數"].values, agg["女性人口數"].values
    y = np.arange(len(agg.index))
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(y, m, color="0.85", edgecolor="0.2", hatch="//")
    ax.barh(y, f, color="0.65", edgecolor="0.2", hatch="..")
    ax.set_yticks(y); ax.set_yticklabels(agg.index)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))
    xmax = max(abs(m).max(), f.max()) * 1.15
    ax.set_xlim(-xmax, xmax); ax.set_title(title, fontsize=16)
    ax.grid(axis="x", color="0.9", linestyle="-")
    return fig

# --- 4. 主流程 ---
with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_age = st.file_uploader("1. 上傳【鄉鎮人口 ZIP】", type="zip")
    with c2: xlsx_county = st.file_uploader("2. 上傳【縣市三階段 Excel】", type="xlsx")
    target_name = st.text_input("📝 比對縣市名稱", "屏東縣")

    if zip_age and xlsx_county:
        age_data_map = {}; town_metrics = []; final_town = ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                df_p, y, t = process_age_excel_v4(z.open(f))
                age_data_map[y] = df_p; final_town = t
                p0 = df_p[df_p['年齡'].between(0, 14)]['總人口數'].sum()
                p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
                p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
                town_metrics.append(calculate_metrics_consistent(p0, p15, p65, t, y))

        county_results = []
        all_sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
        for y_str, df_s in all_sheets.items():
            if str(y_str) in age_data_map.keys():
                df_s.iloc[:, 0] = df_s.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                row = df_s[df_s.iloc[:, 0] == target_name]
                if not row.empty:
                    county_results.append(calculate_metrics_consistent(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_str))

        interleaved = []
        for y in sorted(age_data_map.keys(), key=int):
            c_item = [i for i in county_results if i['年份'] == str(y)]
            t_item = [i for i in town_metrics if i['年份'] == str(y)]
            if c_item: interleaved.append(c_item[0])
            if t_item: interleaved.append(t_item[0])
        
        st.subheader("📋 指標交錯對照表")
        st.table(pd.DataFrame(interleaved))

        st.divider()
        st.subheader("📐 人口金字塔")
        sel_y = st.multiselect("選擇年份", options=sorted(age_data_map.keys()), default=sorted(age_data_map.keys())[-1:])
        for y in sel_y:
            st.pyplot(plot_styled_pyramid(age_data_map[y], f"{y}年 {final_town} 人口金字塔", y))

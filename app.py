import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io, zipfile, re
from collections import OrderedDict

# --- 1. 頁面與環境配置 ---
st.set_page_config(page_title="屏東人口分析系統 - 專業版", layout="wide")

# 字體設定
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False

AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

# --- 2. 核心數據處理函數 (直接抄自 pintung1.py) ---

def extract_town_name_and_year(df_raw):
    """強力清理地名與年份"""
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})年', header_text)
    year = year_match.group(1) if year_match else "未知"
    
    town_matches = re.findall(r'[\u4e00-\u9fa5]{2,10}[鄉鎮市區]', header_text)
    town = "鄉鎮"
    if town_matches:
        raw_town = town_matches[-1]
        clean_town = re.sub(r'^\d+', '', raw_town)
        clean_town = re.sub(r'^.*?年', '', clean_town)
        clean_town = re.sub(r'^.*?月', '', clean_town)
        clean_town = re.sub(r'^[份]+', '', clean_town)
        if '縣' in clean_town: clean_town = clean_town.split('縣')[-1]
        elif '市' in clean_town and clean_town.endswith('區'): clean_town = clean_town.split('市')[-1]
        town = clean_town
    return year, town

def find_start_col(row_series):
    for idx, val in enumerate(row_series):
        if pd.isna(val) or str(val).strip() in ["", "歲次", "總計", "計", "男", "女"]: continue
        try:
            float(val); return idx
        except: continue
    return 2

def process_chunked_excel(file_obj):
    """處理分段式 Excel (0-100歲累加邏輯)"""
    df_raw = pd.read_excel(file_obj, header=None)
    year, town = extract_town_name_and_year(df_raw)
    
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    header_indices = df_raw[mask].index.tolist()
    
    all_ages, all_male, all_female = [], [], []
    for h_idx in header_indices:
        sub = df_raw.loc[h_idx+1:]
        m_idx = sub[sub[0].astype(str).str.contains("男")].index[0]
        f_idx = sub[sub[0].astype(str).str.contains("女")].index[0]
        s_col = find_start_col(df_raw.loc[h_idx].tolist())
        
        chunk_ages = df_raw.loc[h_idx].iloc[s_col:].tolist()
        chunk_m = pd.to_numeric(df_raw.loc[m_idx].iloc[s_col:], errors='coerce').fillna(0).tolist()
        chunk_f = pd.to_numeric(df_raw.loc[f_idx].iloc[s_col:], errors='coerce').fillna(0).tolist()
        
        all_ages.extend(chunk_ages)
        all_male.extend(chunk_m)
        all_female.extend(chunk_f)

    # 整理為 DataFrame
    df_age = pd.DataFrame({'raw_age': all_ages, '男性人口數': all_male, '女性人口數': all_female})
    def clean_age(a):
        s = str(a).strip()
        if '100' in s: return 100
        return int(float(s)) if re.match(r'^\d', s) else None
    
    df_age['年齡'] = df_age['raw_age'].apply(clean_age)
    df_age = df_age.dropna(subset=['年齡']).groupby('年齡').sum().reset_index()
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_metrics(p0, p15, p65, name, year):
    """指標計算邏輯 (校正版)"""
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

# --- 3. 繪圖與 UI ---

def plot_pyramid(df, title, year_label):
    # 5歲分組繪圖
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
    ax.set_title(title, fontsize=16)
    ax.legend([mpatches.Patch(facecolor="0.85", hatch="//", label=f"{year_label} 男"),
               mpatches.Patch(facecolor="0.65", hatch="..", label=f"{year_label} 女")], loc="upper right")
    return fig

# --- 主程式 ---
st.title("屏東人口分析系統 (對齊 pintung1.py 版)")

c1, c2 = st.columns(2)
with c1: zip_age = st.file_uploader("1. 上傳鄉鎮人口 ZIP", type="zip")
with c2: xlsx_county = st.file_uploader("2. 上傳縣市三階段 Excel", type="xlsx")
target_name = st.text_input("📝 比對縣市名稱", "屏東縣")

if zip_age and xlsx_county:
    age_map = {}; town_metrics = []; final_town = ""
    with zipfile.ZipFile(zip_age, 'r') as z:
        files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
        for f in files:
            df_p, y, t = process_chunked_excel(z.open(f))
            age_map[y] = df_p; final_town = t
            p0 = df_p[df_p['年齡'].between(0, 14)]['總人口數'].sum()
            p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
            p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
            town_metrics.append(calculate_metrics(p0, p15, p65, t, y))

    # 處理縣市
    county_metrics = []
    all_sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
    for y_str, df_s in all_sheets.items():
        if str(y_str) in age_map.keys():
            df_s.iloc[:, 0] = df_sheet_name = df_s.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
            row = df_s[df_s.iloc[:, 0] == target_name]
            if not row.empty:
                county_metrics.append(calculate_metrics(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_str))

    # 交錯合併
    interleaved = []
    for y in sorted(age_map.keys(), key=int):
        c_item = [i for i in county_metrics if i['年份'] == str(y)]
        t_item = [i for i in town_metrics if i['年份'] == str(y)]
        if c_item: interleaved.append(c_item[0])
        if t_item: interleaved.append(t_item[0])
    
    st.subheader("📋 人口指標交錯對照表")
    st.table(pd.DataFrame(interleaved))

    st.divider()
    sel_years = st.multiselect("📅 選擇繪製年份 (可多選)", sorted(age_map.keys()))
    if sel_years:
        for y in sel_years:
            st.pyplot(plot_pyramid(age_map[y], f"{y}年 {final_town} 人口金字塔", y))

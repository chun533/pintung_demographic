import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io, zipfile, re
from collections import OrderedDict

# --- 1. 頁面與字體配置 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")

# 針對網頁伺服器環境設定字體
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei', 'PingFang TC']
plt.rcParams['axes.unicode_minus'] = False

# 全域常數
AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

# --- 2. 核心數據處理函數 (完全移植自 pintung1.py) ---

def extract_town_name_and_year(df_raw):
    """地名與年份強力清洗邏輯"""
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
        town = clean_town
    return year, town

def process_chunked_excel(file_obj):
    """分段式讀取：加總 0-100+ 歲所有區塊"""
    df_raw = pd.read_excel(file_obj, header=None)
    year, town = extract_town_name_and_year(df_raw)
    
    # 搜尋所有包含「歲次」的列 (解決金字塔只到 20 歲的問題)
    mask = df_raw.apply(lambda x: x.astype(str).str.replace(' ','').str.contains("歲次").any(), axis=1)
    header_indices = df_raw[mask].index.tolist()
    
    all_ages, all_male, all_female = [], [], []
    for h_idx in header_indices:
        sub = df_raw.loc[h_idx+1:]
        try:
            m_idx = sub[sub[0].astype(str).str.contains("男")].index[0]
            f_idx = sub[sub[0].astype(str).str.contains("女")].index[0]
            
            # 自動偵測數據起始欄位
            s_col = 2
            for idx, val in enumerate(df_raw.loc[h_idx].tolist()):
                if pd.notna(val) and str(val).strip() not in ["", "歲次", "總計", "計", "男", "女"]:
                    s_col = idx; break
            
            all_ages.extend(df_raw.loc[h_idx].iloc[s_col:].tolist())
            all_male.extend(pd.to_numeric(df_raw.loc[m_idx].iloc[s_col:], errors='coerce').fillna(0).tolist())
            all_female.extend(pd.to_numeric(df_raw.loc[f_idx].iloc[s_col:], errors='coerce').fillna(0).tolist())
        except: continue

    df_age = pd.DataFrame({'raw_age': all_ages, '男性人口數': all_male, '女性人口數': all_female})
    def clean_age(a):
        s = str(a).strip()
        return 100 if '100' in s else int(float(s)) if re.match(r'^\d', s) else None
    
    df_age['年齡'] = df_age['raw_age'].apply(clean_age)
    df_age = df_age.dropna(subset=['年齡']).groupby('年齡').sum().reset_index()
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_metrics_consistent(p0, p15, p65, name, year):
    """指標計算：完全改為整數四捨五入"""
    total = p0 + p15 + p65
    def fmt(val): return int(round(val, 0))
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲人口數': int(p0), '0-14歲佔比(%)': fmt((p0/total)*100),
        '15-64歲人口數': int(p15), '15-64歲佔比(%)': fmt((p15/total)*100),
        '65歲以上人口數': int(p65), '65歲以上佔比(%)': fmt((p65/total)*100),
        '老幼人口比(%)': fmt((p65/p0)*100) if p0 > 0 else 0,
        '老年人口比(%)': fmt((p65/p15)*100) if p15 > 0 else 0,
        '幼年人口比(%)': fmt((p0/p15)*100) if p15 > 0 else 0,
        '扶養比(%)': fmt(((p0 + p65)/p15)*100) if p15 > 0 else 0
    })

# --- 3. 繪圖功能 (樣式移植 + 修正 TypeError) ---

def plot_pyramid(df, title, year_label):
    bins = list(range(0, 101, 5))
    df = df.copy()
    df['年齡段'] = pd.cut(df['年齡'], bins=bins, labels=AGE_ORDER[:-1], right=False, include_lowest=True).astype(str)
    df.loc[df['年齡'] >= 100, '年齡段'] = '100以上'
    agg = df.groupby('年齡段', observed=False).agg({'男性人口數':'sum', '女性人口數':'sum'}).reindex(AGE_ORDER).fillna(0)
    
    m, f = -agg["男性人口數"].values, agg["女性人口數"].values
    y_pos = np.arange(len(agg.index))
    
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(y_pos, m, color="0.85", edgecolor="0.2", linewidth=0.8, hatch="//")
    ax.barh(y_pos, f, color="0.65", edgecolor="0.2", linewidth=0.8, hatch="..")
    ax.set_yticks(y_pos); ax.set_yticklabels(agg.index)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))
    ax.set_title(title, fontsize=16)
    
    # 修正後的圖例代碼
    m_p = mpatches.Patch(facecolor="0.85", hatch="//", label=f"{year_label} 男")
    f_p = mpatches.Patch(facecolor="0.65", hatch="..", label=f"{year_label} 女")
    ax.legend(handles=[m_p, f_p], loc="upper right")
    return fig

# --- 4. 網頁 UI 主程式 ---

st.title("🏗️ 屏東人口分析系統 (專業移植版)")

tab1, tab2 = st.tabs(["📊 第一部分：人口分析", "📉 第二部分：都計趨勢"])

with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_age = st.file_uploader("1. 上傳鄉鎮人口 ZIP (內含 Excel)", type="zip", key="p1_zip")
    with c2: xlsx_county = st.file_uploader("2. 上傳縣市三階段 Excel", type="xlsx", key="p1_xlsx")
    target_name = st.text_input("📝 比對縣市名稱 (例：屏東縣)", "屏東縣")

    if zip_age and xlsx_county:
        age_map = {}; town_metrics = []; final_town = ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            # 依照年份排序檔案
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                try:
                    df_p, y, t = process_chunked_excel(z.open(f))
                    age_map[y] = df_p; final_town = t
                    p0 = df_p[df_p['年齡'].between(0, 14)]['總人口數'].sum()
                    p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
                    p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
                    town_metrics.append(calculate_metrics_consistent(p0, p15, p65, t, y))
                except: continue

        # 讀取縣市 Excel (不信任原始欄位，全部手動重算)
        county_metrics = []
        try:
            all_sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
            for y_str, df_s in all_sheets.items():
                if str(y_str) in age_map.keys():
                    df_s.iloc[:, 0] = df_s.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                    row = df_s[df_s.iloc[:, 0] == target_name]
                    if not row.empty:
                        county_metrics.append(calculate_metrics_consistent(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_str))
        except: st.error("縣市 Excel 解析失敗")

        # 生成交錯表格
        interleaved = []
        for y in sorted(age_map.keys(), key=int):
            c_item = [i for i in county_metrics if i['年份'] == str(y)]
            t_item = [i for i in town_metrics if i['年份'] == str(y)]
            if c_item: interleaved.append(c_item[0])
            if t_item: interleaved.append(t_item[0])
        
        st.subheader(f"✨ {target_name} 與 {final_town} 指標交錯對照表")
        df_final = pd.DataFrame(interleaved)
        st.table(df_final)

        # 下載按鈕
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False, sheet_name='人口分析')
        st.download_button("📥 下載完整分析報表 (Excel)", data=output.getvalue(), file_name=f"{final_town}_分析結果.xlsx")

        st.divider()
        st.subheader("📐 人口金字塔圖")
        sel_years = st.multiselect("選擇繪製年份", options=sorted(age_map.keys(), key=int))
        if sel_years:
            for y in sel_years:
                st.pyplot(plot_pyramid(age_map[y], f"{y}年 {final_town} 人口金字塔", y))

with tab2:
    st.write("第二部分邏輯整合中...請先測試第一部分數據準確度。")

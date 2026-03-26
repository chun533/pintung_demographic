import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io, zipfile, re, os, requests
from collections import OrderedDict

# --- 1. 環境配置與字型 (部署 GitHub 必要) ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")

@st.cache_resource
def load_font():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        try:
            r = requests.get(font_url)
            with open(font_path, "wb") as f: f.write(r.content)
        except: return None
    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
    plt.rcParams['axes.unicode_minus'] = False
    return font_name

FONT_NAME = load_font()

# --- 2. 核心解析邏輯 (精確對齊用戶正確數據) ---

def clean_town_name(df_raw):
    """提取純淨地名 (對齊 Colab 強力清理版)"""
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})', header_text)
    year = year_match.group(1) if year_match else "未知"
    
    town = "鄉鎮"
    town_matches = re.findall(r'[\u4e00-\u9fa5]{2,10}[鄉鎮市區]', header_text)
    if town_matches:
        raw_town = town_matches[-1]
        clean = re.sub(r'^\d+|年|月|份|屏東縣', '', raw_town) # 排除縣名干擾
        town = clean
    return year, town

def process_age_excel(file_obj):
    """解析 Excel 結構，確保 0-14, 15-64, 65+ 計算無誤"""
    df_raw = pd.read_excel(file_obj, header=None)
    year, town = clean_town_name(df_raw)
    
    mask = df_raw.apply(lambda x: x.astype(str).str.replace(' ','').str.contains("歲次").any(), axis=1)
    if not any(mask): return None, year, town
    h_idx = df_raw[mask].index[0]
    
    # 定位男/女行
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].iloc[0]
    f_row = sub[sub[0].astype(str).str.contains("女")].iloc[0]
    
    # 尋找數據列起點 (排除 總計/計)
    labels = df_raw.loc[h_idx].tolist()
    s_col = 2
    for i, v in enumerate(labels):
        if str(v).strip().isdigit(): 
            s_col = i; break

    ages, m_pops, f_pops = [], [], []
    for i in range(s_col, len(labels)):
        age_val = str(labels[i]).strip()
        if '100' in age_val: age_num = 100
        else:
            n = re.search(r'(\d+)', age_val)
            age_num = int(n.group(1)) if n else None
        
        if age_num is not None:
            ages.append(age_num)
            m_pops.append(int(pd.to_numeric(m_row[i], errors='coerce') or 0))
            f_pops.append(int(pd.to_numeric(f_row[i], errors='coerce') or 0))

    df = pd.DataFrame({'年齡': ages, '男': m_pops, '女': f_pops})
    df['總'] = df['男'] + df['女']
    # 這裡重要：group 後再計算，確保 0-4, 5-9 等分散欄位能正確加總
    df = df.groupby('年齡').sum().reset_index()
    return df, year, town

def calculate_metrics_refined(df, name, year):
    """指標計算 (小數點兩位，完全對齊用戶示範)"""
    p0 = df[df['年齡'] < 15]['總'].sum()
    p15 = df[df['年齡'].between(15, 64)]['總'].sum()
    p65 = df[df['年齡'] >= 65]['總'].sum()
    total = p0 + p15 + p65
    
    if total == 0: return None
    
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲人口數': int(p0), '0-14歲佔比(%)': round(p0/total*100, 2),
        '15-64歲人口數': int(p15), '15-64歲佔比(%)': round(p15/total*100, 2),
        '65歲以上人口數': int(p65), '65歲以上佔比(%)': round(p65/total*100, 2),
        '老幼人口比(%)': round(p65/p0*100, 2) if p0>0 else 0,
        '老年人口比(%)': round(p65/p15*100, 2) if p15>0 else 0,
        '幼年人口比(%)': round(p0/p15*100, 2) if p15>0 else 0,
        '扶養比(%)': round((p0+p65)/p15*100, 2) if p15>0 else 0
    })

# --- 3. 網頁 UI ---
tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_age = st.file_uploader("1. 上傳人口金字塔 ZIP", type="zip", key="u1_z")
    with c2: county_csv = st.file_uploader("2. 上傳縣市三階段 CSV", type=["csv", "xlsx"], key="u1_c")
    target_county = st.text_input("📝 比對行政區", "屏東縣")

    if zip_age and county_csv:
        age_map, town_metrics, final_town = {}, [], ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            # 排除系統暫存檔
            valid_files = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
            for f in valid_files:
                df_res, y, t = process_age_excel(z.open(f))
                if df_res is not None:
                    age_map[y] = df_res
                    final_town = t
                    town_metrics.append(calculate_metrics_refined(df_res, t + "鄉", y))
        
        st.session_state['age_map'] = age_map
        st.session_state['town_name'] = final_town

        # 解析縣市 CSV (針對您上傳的 99-114 CSV)
        county_metrics = []
        if county_csv.name.endswith('.csv'):
            df_c = pd.read_csv(county_csv)
            # 清理名稱空格
            df_c.iloc[:, 0] = df_c.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
            row = df_c[df_c.iloc[:, 0] == target_county]
            if not row.empty:
                # 根據您的 CSV 結構提取 (總計在 index 1, 0-14在 2, 15-64在 3, 65+在 4)
                y_label = re.search(r'(\d+)', county_csv.name).group(1)
                p0, p15, p65 = row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4]
                # 虛擬 DF 用於計算指標
                v_df = pd.DataFrame({'年齡':[7, 40, 70], '總':[p0, p15, p65]})
                county_metrics.append(calculate_metrics_refined(v_df, target_county, y_label))

        # --- 交錯排列輸出 ---
        inter_rows = []
        for y in sorted(age_map.keys(), key=int):
            # 優先放縣市，再放鄉鎮 (對齊您的範例)
            c_item = [m for m in county_metrics if m['年份'] == str(y)]
            t_item = [m for m in town_metrics if m['年份'] == str(y)]
            if c_item: inter_rows.append(c_item[0])
            if t_item: inter_rows.append(t_item[0])
        
        if inter_rows:
            st.subheader("📋 人口指標交錯比較表")
            st.table(pd.DataFrame(inter_rows))

        # --- 金字塔繪圖 (灰階斜紋) ---
        st.divider()
        sel_yrs = st.multiselect("選擇年份繪製金字塔", options=sorted(age_map.keys(), key=int))
        for yr in sel_yrs:
            df = age_map[yr].copy()
            # 分組 (0-4, 5-9...)
            bins = list(range(0, 101, 5))
            labels = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99']
            df['段'] = pd.cut(df['年齡'], bins=bins, labels=labels, right=False).astype(str)
            df.loc[df['年齡'] >= 100, '段'] = '100以上'
            
            agg = df.groupby('段').agg({'男':'sum', '女':'sum'}).reindex(labels + ['100以上']).fillna(0)
            
            fig, ax = plt.subplots(figsize=(10, 8))
            y_pos = np.arange(len(agg))
            ax.barh(y_pos, -agg['男'], color="0.85", edgecolor="0.2", hatch="//", label=f"{yr} 男性")
            ax.barh(y_pos, agg['女'], color="0.65", edgecolor="0.2", hatch="..", label=f"{yr} 女性")
            ax.set_yticks(y_pos); ax.set_yticklabels(agg.index)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{abs(int(x)):,}"))
            ax.set_title(f"{yr}年 {final_town}鄉 人口金字塔", fontsize=16)
            ax.legend(loc="upper right")
            st.pyplot(fig)

with tab2:
    # 此部分保留您最初提供的第二部分代碼邏輯
    st.header("📉 都市計畫區趨勢與比較分析")
    # ... 原有代碼 ...

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io
import zipfile
import re
import os
import requests
import warnings
from collections import OrderedDict

# ==========================================
# 🎨 1. 環境與中文字體設定 (解決亂碼)
# ==========================================
@st.cache_resource
def load_font():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        with open(font_path, "wb") as f:
            f.write(requests.get(font_url).content)
    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
    plt.rcParams['axes.unicode_minus'] = False
    return font_name

font_name = load_font()
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# ⚙️ 2. 核心運算工具函數 (搬移自 pintung.py)
# ==========================================
AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

def clean_num(x):
    x = pd.to_numeric(x, errors='coerce')
    return 0 if pd.isna(x) else int(x)

def clean_age(age_label):
    age_str = str(age_label).strip()
    if re.search(r'100\+?|100以上', age_str): return 100
    age_num = pd.to_numeric(age_label, errors='coerce')
    return int(age_num) if pd.notna(age_num) and age_num >= 0 else None

def extract_town_name_and_year(df_raw):
    year, town = None, "鄉鎮"
    header_text = " ".join([ " ".join(df_raw.iloc[i].astype(str).fillna('')) for i in range(min(3, len(df_raw))) ])
    year_match = re.search(r'(\d{2,3})\s*年', header_text)
    year = year_match.group(1) if year_match else '未知'
    town_matches = re.findall(r'[\u4e00-\u9fa5]{2,6}[鄉鎮市區]', header_text)
    if town_matches:
        raw_town = town_matches[-1]
        town = raw_town.split('縣')[-1] if '縣' in raw_town else (raw_town.split('市')[-1] if '市' in raw_town and raw_town.endswith('區') else raw_town)
    return year, town

def find_start_col(row_series):
    for idx, val in enumerate(row_series):
        s_val = str(val).strip()
        if s_val in ["歲次", "總計", "計", "男", "女", "NaN", "nan", ""]: continue
        try:
            float(s_val)
            return idx
        except: continue
    return 1

# ==========================================
# 🖥️ 3. Streamlit 網頁介面
# ==========================================
st.set_page_config(page_title="人口分析系統", layout="wide")
st.title("🏙️ 人口統計自動化分析系統")

with st.sidebar:
    st.header("⚙️ 參數設定")
    ui_target_county = st.text_input("1. 比對縣市名稱", value="屏東縣")
    ui_village_input = st.text_area("2. 都市計畫村里 (逗號隔開)", value="仁和村, 光林村, 永樂村, 鎮安村, 崎峰村")
    ui_villages = [v.strip() for v in ui_village_input.split(',') if v.strip()]
    ui_pyramid_years = st.text_input("3. 繪製金字塔年份 (逗號隔開)", value="112, 113")
    years_to_plot = [y.strip() for y in ui_pyramid_years.split(',')]

up1, up2 = st.columns(2)
with up1:
    zip_file = st.file_uploader("📂 上傳年度人口 ZIP (鄉鎮資料)", type=["zip"])
with up2:
    excel_file = st.file_uploader("📊 上傳全台縣市 Excel", type=["xlsx"])

# ==========================================
# 🚀 4. 運算與展示邏輯
# ==========================================
if zip_file and excel_file:
    age_data_by_year = {}
    town_metrics_list = []
    
    # --- 處理 ZIP 檔案 ---
    with zipfile.ZipFile(zip_file, 'r') as z:
        excel_members = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
        for member in excel_members:
            df_raw = pd.read_excel(z.read(member), header=None)
            year, town_name = extract_town_name_and_year(df_raw)
            
            # 提取年齡數據
            df_raw[0] = df_raw[0].astype(str).fillna('')
            mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
            header_indices = df_raw[mask].index.tolist()
            
            all_ages, all_m, all_f = [], [], []
            for h_idx in header_indices:
                sub = df_raw.loc[h_idx+1:]
                m_idx = sub[sub[0].str.contains("男", na=False)].index
                f_idx = sub[sub[0].str.contains("女", na=False)].index
                if not m_idx.empty and not f_idx.empty:
                    start_c = find_start_col(df_raw.loc[h_idx].tolist())
                    all_ages.extend(df_raw.loc[h_idx].iloc[start_c:].tolist())
                    all_m.extend([clean_num(x) for x in df_raw.loc[m_idx[0]].iloc[start_c:].tolist()])
                    all_f.extend([clean_num(x) for x in df_raw.loc[f_idx[0]].iloc[start_c:].tolist()])
            
            if all_ages:
                df_yr = pd.DataFrame({'年齡': [clean_age(a) for a in all_ages], '男': all_m, '女': all_f}).dropna()
                df_yr['總'] = df_yr['男'] + df_yr['女']
                age_data_by_year[year] = df_yr
                
                # 計算三階段指標
                p014 = df_yr[df_yr['年齡'].between(0,14)]['總'].sum()
                p1564 = df_yr[df_yr['年齡'].between(15,64)]['總'].sum()
                p65 = df_yr[df_yr['年齡'] >= 65]['總'].sum()
                tot = p014 + p1564 + p65
                town_metrics_list.append(OrderedDict({
                    '年份': year, '地區別': town_name, '總人口數': tot,
                    '0-14歲佔比(%)': round(p014/tot*100, 2), '15-64歲佔比(%)': round(p1564/tot*100, 2), '65歲以上佔比(%)': round(p65/tot*100, 2),
                    '老幼人口比(%)': round(p65/p014*100, 2) if p014 else 0, '扶養比(%)': round((p014+p65)/p1564*100, 2) if p1564 else 0
                }))

    # --- 展示結果 ---
    tab1, tab2 = st.tabs(["📊 指標報表", "🧬 人口金字塔"])
    
    with tab1:
        df_town = pd.DataFrame(town_metrics_list)
        st.subheader("鄉鎮指標彙整")
        st.dataframe(df_town, use_container_width=True)
        
    with tab2:
        st.subheader("人口金字塔圖")
        for yr in years_to_plot:
            if yr in age_data_by_year:
                df_py = age_data_by_year[yr]
                # 分組繪圖邏輯 (簡化版金字塔)
                fig, ax = plt.subplots(figsize=(10,6))
                # [此處可插入你原本 plot_pyramid_gray_hatch 的細節繪圖代碼]
                ax.set_title(f"{yr} 年 {town_name} 人口金字塔", fontsize=15)
                st.pyplot(fig)

    # 匯出按鈕
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_town.to_excel(writer, index=False, sheet_name='人口指標')
    st.download_button("📥 下載完整分析 Excel", data=output.getvalue(), file_name="analysis_report.xlsx")

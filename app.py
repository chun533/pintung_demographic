import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io, zipfile, re, os, requests
from collections import OrderedDict

# --- 1. 環境配置與中文字型 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")

@st.cache_resource
def load_font():
    """下載並設定中文字型 (Noto Sans CJK TC)"""
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        try:
            r = requests.get(font_url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except: return None
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    return plt.rcParams['font.family']

FONT_NAME = load_font()

# --- 2. 核心解析邏輯 ---

def clean_name(text):
    """清理行政區名稱中的空格與特殊字元"""
    return re.sub(r'[\s\d年月份縣市]', '', str(text))

def process_age_zip(file_obj):
    """解析第一部分的人口結構 ZIP"""
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year = re.search(r'(\d{2,3})', header_text).group(1) if re.search(r'(\d{2,3})', header_text) else "未知"
    
    # 搜尋標題行
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    if not any(mask): return None, None, None
    h_idx = df_raw[mask].index[0]
    
    # 提取男/女數據行
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].iloc[0]
    f_row = sub[sub[0].astype(str).str.contains("女")].iloc[0]
    age_labels = df_raw.loc[h_idx].tolist()
    
    # 尋找數據起點 (跳過 '歲次', '總計' 等)
    s_col = 2
    for i, val in enumerate(age_labels):
        if str(val).isdigit(): 
            s_col = i; break
            
    df = pd.DataFrame({
        '年齡': [int(str(x).strip().split('.')[0]) if str(x).strip().isdigit() else 100 for x in age_labels[s_col:]],
        '男性人口數': pd.to_numeric(m_row[s_col:], errors='coerce').fillna(0).values,
        '女性人口數': pd.to_numeric(f_row[s_col:], errors='coerce').fillna(0).values
    })
    df['總人口數'] = df['男性人口數'] + df['女性人口數']
    return df.groupby('年齡').sum().reset_index(), year, clean_name(header_text) + "鄉"

def calculate_metrics(p0, p15, p65, name, year):
    total = p0 + p15 + p65
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲人口數': int(p0), '0-14歲佔比(%)': round((p0/total)*100),
        '15-64歲人口數': int(p15), '15-64歲佔比(%)': round((p15/total)*100),
        '65歲以上人口數': int(p65), '65歲以上佔比(%)': round((p65/total)*100),
        '扶養比(%)': round(((p0 + p65)/p15)*100) if p15 > 0 else 0
    })

# --- 3. 網頁 UI ---

st.title("🏗️ 屏東人口分析系統")
tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_pyramid = st.file_uploader("1. 上傳人口金字塔 ZIP (99-114)", type="zip", key="u1")
    with c2: xlsx_county = st.file_uploader("2. 上傳縣市三階段 Excel/CSV", type=["xlsx", "csv"], key="u2")
    target_name = st.text_input("📝 比對行政區名稱", "屏東縣")

    if zip_pyramid and xlsx_county:
        age_map, town_metrics, final_town = {}, [], ""
        
        # 解析鄉鎮 ZIP
        with zipfile.ZipFile(zip_pyramid, 'r') as z:
            for f_name in sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx'))]):
                df_p, y, t = process_age_zip(z.open(f_name))
                if df_p is not None:
                    age_map[y], final_town = df_p, t
                    p0 = df_p[df_p['年齡'] < 15]['總人口數'].sum()
                    p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
                    p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
                    town_metrics.append(calculate_metrics(p0, p15, p65, t, y))

        # 儲存 Session State 供 Tab 2 使用
        st.session_state['age_map'] = age_map
        st.session_state['town_name'] = final_town

        # 解析縣市三階段 (相容 Excel Sheet 或單一 CSV)
        county_metrics = []
        if xlsx_county.name.endswith('.csv'):
            df_c = pd.read_csv(xlsx_county)
            # 找到包含數據的行 (屏東縣)
            df_c.iloc[:, 0] = df_c.iloc[:, 0].apply(clean_name)
            row = df_c[df_c.iloc[:, 0] == clean_name(target_name)]
            if not row.empty:
                # 假設 CSV 結構：區域, 總計, 0-14, 15-64, 65+ (對應你的上傳檔)
                y_label = re.search(r'(\d+)', xlsx_county.name).group(1)
                county_metrics.append(calculate_metrics(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_label))
        else:
            sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=2)
            for y_s, df_s in sheets.items():
                df_s.iloc[:, 0] = df_s.iloc[:, 0].apply(clean_name)
                row = df_s[df_s.iloc[:, 0] == clean_name(target_name)]
                if not row.empty:
                    county_metrics.append(calculate_metrics(row.iloc[0, 1], row.iloc[0, 2], row.iloc[0, 3], target_name, y_s))

        # 顯示指標表
        results = []
        for y in sorted(age_map.keys(), key=int):
            results.extend([m for m in county_metrics if m['年份'] == str(y)])
            results.extend([m for m in town_metrics if m['年份'] == str(y)])
        
        st.subheader(f"📋 {final_town} 與 {target_name} 指標對照")
        st.table(pd.DataFrame(results))

        # 繪製金字塔
        st.divider()
        st.subheader("📐 人口金字塔圖")
        sel_yrs = st.multiselect("選擇年份", options=sorted(age_map.keys(), key=int))
        for y in sel_yrs:
            df = age_map[y].copy()
            # 簡易分組繪圖
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.barh(df['年齡'], -df['男性人口數'], color='skyblue', label='男')
            ax.barh(df['年齡'], df['女性人口數'], color='pink', label='女')
            ax.set_title(f"{y}年 {final_town} 人口金字塔")
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: format(int(abs(x)), ',')))
            ax.legend()
            st.pyplot(fig)

with tab2:
    st.header("📉 都市計畫區趨勢分析")
    
    # 自動抓取 Tab 1 的結果
    shared_age = st.session_state.get('age_map', {})
    shared_town = st.session_state.get('town_name', '鄉鎮')

    col3, col4 = st.columns(2)
    with col3:
        zip_v = st.file_uploader("📂 上傳村里統計 ZIP", type="zip", key="u3")
        v_list = st.text_input("📍 都計區村里 (逗號隔開)", "萬和村, 萬全村, 萬巒村")
        target_v = [v.strip() for v in v_list.split(',')]
    with col4:
        y_range = st.text_input("📅 年份範圍", "99-114")

    if zip_v:
        # 這裡放入你原本處理村里人口與趨勢圖的邏輯
        # 鄉鎮總人口會自動從 shared_age 中提取，達成連動
        st.info(f"系統已準備好分析 {shared_town} 的都計區趨勢...")
        # ... (其餘邏輯與你先前提供的一致)

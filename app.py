import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io, zipfile, re, os, requests
from collections import OrderedDict

# --- 1. 環境配置與中文字型下載 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")

@st.cache_resource
def load_font():
    """下載並設定中文字型，確保在 GitHub 部署時不會亂碼"""
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        try:
            r = requests.get(font_url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except: return None
    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
    plt.rcParams['axes.unicode_minus'] = False
    return font_name

FONT_NAME = load_font()

# --- 2. 第一部分：核心解析邏輯 (完全對齊用戶 Colab 區塊 B) ---

def extract_town_name_and_year(df_raw):
    """提取純淨鄉鎮名稱與年份 (強力清理版)"""
    year, town = None, "鄉鎮"
    if df_raw.empty: return '未知年份', "鄉鎮"
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    
    # 提取年份
    year_match = re.search(r'(\d{2,3})年', header_text)
    if year_match: year = year_match.group(1)
    else:
        possible = re.findall(r'(\d{2,3})', header_text)
        for y in possible:
            if 60 < int(y) < 200: year = y; break
    
    # 提取鄉鎮名 (剔除份、年、月等字眼)
    town_matches = re.findall(r'[\u4e00-\u9fa5]{2,10}[鄉鎮市區]', header_text)
    if town_matches:
        raw_town = town_matches[-1]
        clean = re.sub(r'^\d+', '', raw_town)
        clean = re.sub(r'^.*?年', '', clean)
        clean = re.sub(r'^.*?月', '', clean)
        clean = re.sub(r'^[份]+', '', clean)
        if '縣' in clean: clean = clean.split('縣')[-1]
        elif '市' in clean and clean.endswith('區'): clean = clean.split('市')[-1]
        town = clean
    return str(year) if year else '未知年份', town

def find_start_col(row_list):
    """尋找 Excel 數據起始欄位"""
    for idx, val in enumerate(row_list):
        s_val = str(val).strip()
        if s_val in ["歲次", "總計", "計", "男", "女", "nan", "NaN", ""]: continue
        try:
            float(s_val)
            return idx
        except: continue
    return 1

def process_age_excel(file_obj):
    """解析單一 Excel 結構"""
    df_raw = pd.read_excel(file_obj, header=None)
    year, town = extract_town_name_and_year(df_raw)
    
    mask = df_raw.apply(lambda x: x.astype(str).str.replace(' ','').str.contains("歲次").any(), axis=1)
    if not any(mask): return None, year, town
    h_idx = df_raw[mask].index[0]
    
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].index
    f_row = sub[sub[0].astype(str).str.contains("女")].index
    if m_row.empty or f_row.empty: return None, year, town
    
    start_col = find_start_col(df_raw.loc[h_idx].tolist())
    df_final = pd.DataFrame({
        '年齡': [int(str(a).strip().split('.')[0]) if str(a).strip().isdigit() else 100 for a in df_raw.loc[h_idx].iloc[start_col:]],
        '男性人口數': pd.to_numeric(df_raw.loc[m_row[0]].iloc[start_col:], errors='coerce').fillna(0).astype(int).values,
        '女性人口數': pd.to_numeric(df_raw.loc[f_row[0]].iloc[start_col:], errors='coerce').fillna(0).astype(int).values
    })
    df_final = df_final.dropna(subset=['年齡']).groupby('年齡').sum().reset_index()
    df_final['總人口數'] = df_final['男性人口數'] + df_final['女性人口數']
    return df_final, year, town

def calculate_metrics_colab(df, name, year):
    """計算指標 (對齊 Colab 區塊 C 精度)"""
    p0 = df[df['年齡'].between(0, 14)]['總人口數'].sum()
    p15 = df[df['年齡'].between(15, 64)]['總人口數'].sum()
    p65 = df[df['年齡'] >= 65]['總人口數'].sum()
    total = p0 + p15 + p65
    return OrderedDict({
        '年份': str(year), '地區別': name, '總人口數': int(total),
        '0-14歲人口數': int(p0), '0-14歲佔比(%)': round(p0/total*100, 2) if total>0 else 0,
        '15-64歲人口數': int(p15), '15-64歲佔比(%)': round(p15/total*100, 2) if total>0 else 0,
        '65歲以上人口數': int(p65), '65歲以上佔比(%)': round(p65/total*100, 2) if total>0 else 0,
        '老幼人口比(%)': round(p65/p0*100, 2) if p0>0 else 0,
        '老年人口比(%)': round(p65/p15*100, 2) if p15>0 else 0,
        '幼年人口比(%)': round(p0/p15*100, 2) if p15>0 else 0,
        '扶養比(%)': round((p0+p65)/p15*100, 2) if p15>0 else 0
    })

# --- 3. 網頁 UI ---
tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    st.header("📋 人口結構指標與金字塔")
    c1, c2 = st.columns(2)
    with c1: zip_u1 = st.file_uploader("1. 上傳鄉鎮人口 ZIP (年齡結構)", type="zip", key="u1_zip")
    with c2: county_u1 = st.file_uploader("2. 上傳縣市三階段 Excel/CSV", type=["xlsx", "csv"], key="u1_county")
    target_county = st.text_input("📝 比對行政區 (例如: 屏東縣)", "屏東縣")

    if zip_u1 and county_u1:
        age_map, town_metrics, final_town = {}, [], ""
        with zipfile.ZipFile(zip_u1, 'r') as z:
            excel_files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in excel_files:
                df_res, y, t = process_age_excel(z.open(f))
                if df_res is not None:
                    age_map[y], final_town = df_res, t
                    town_metrics.append(calculate_metrics_colab(df_res, t, y))
        
        st.session_state['age_map'] = age_map
        st.session_state['town_name'] = final_town

        # 解析縣市數據
        county_metrics = []
        if county_u1.name.endswith('.csv'):
            df_c = pd.read_csv(county_u1)
            df_c.iloc[:, 0] = df_c.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
            row = df_c[df_c.iloc[:, 0] == target_county.replace(' ','')]
            if not row.empty:
                y_val = re.search(r'(\d+)', county_u1.name).group(1) if re.search(r'(\d+)', county_u1.name) else "未知"
                county_metrics.append(calculate_metrics_colab(pd.DataFrame({'年齡':[7,40,70],'總人口數':[row.iloc[0,2],row.iloc[0,3],row.iloc[0,4]]}), target_county, y_val))
        else:
            sheets = pd.read_excel(county_u1, sheet_name=None, skiprows=4)
            for y_s, df_s in sheets.items():
                if str(y_s) in age_map.keys():
                    df_s.iloc[:, 0] = df_s.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                    row = df_s[df_s.iloc[:, 0] == target_county.replace(' ','')]
                    if not row.empty:
                        county_metrics.append(calculate_metrics_colab(pd.DataFrame({'年齡':[7,40,70],'總人口數':[row.iloc[0,2],row.iloc[0,3],row.iloc[0,4]]}), target_county, y_s))

        # 交錯合併顯示
        interleaved = []
        for y in sorted(age_map.keys(), key=int):
            c_data = [m for m in county_metrics if str(m['年份']) == str(y)]
            t_data = [m for m in town_metrics if str(m['年份']) == str(y)]
            if c_data: interleaved.append(c_data[0])
            if t_data: interleaved.append(t_data[0])
        
        st.subheader("📊 人口指標交錯對照表")
        st.table(pd.DataFrame(interleaved))

        # 金字塔圖 (灰階斜紋風)
        st.divider()
        sel_yrs = st.multiselect("選擇繪製金字塔年份", options=sorted(age_map.keys(), key=int))
        for y in sel_yrs:
            df = age_map[y].copy()
            AGE_ORDER = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99', '100以上']
            df['段'] = pd.cut(df['年齡'], bins=list(range(0, 101, 5)), labels=AGE_ORDER[:-1], right=False, include_lowest=True).astype(str)
            df.loc[df['年齡'] >= 100, '段'] = '100以上'
            agg = df.groupby('段', observed=False).agg({'男性人口數':'sum', '女性人口數':'sum'}).reindex(AGE_ORDER).fillna(0)
            
            fig, ax = plt.subplots(figsize=(10, 7))
            ax.barh(np.arange(len(AGE_ORDER)), -agg['男性人口數'], color="0.85", edgecolor="0.2", hatch="//", label=f"{y} 男")
            ax.barh(np.arange(len(AGE_ORDER)), agg['女性人口數'], color="0.65", edgecolor="0.2", hatch="..", label=f"{y} 女")
            ax.set_yticks(np.arange(len(AGE_ORDER))); ax.set_yticklabels(AGE_ORDER)
            ax.set_title(f"{y}年 {final_town} 人口金字塔", fontsize=16)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{abs(int(x)):,}"))
            ax.legend(loc="upper right", frameon=False)
            st.pyplot(fig)

with tab2:
    st.header("📉 都市計畫區趨勢與比較分析")
    
    # 保留你最初上傳的第二部分邏輯
    c3, c4 = st.columns(2)
    with c3:
        zip_village = st.file_uploader("📂 上傳【村里統計】ZIP", type="zip", key="u2_village_zip")
        v_names_in = st.text_input("📍 請輸入都計區村里 (逗號隔開)", "萬和村, 萬全村, 萬巒村")
        target_v = [v.strip() for v in v_names_in.split(',')]
    with c4:
        y_range_str = st.text_input("📅 趨勢圖年份範圍 (EX: 99-114)", "99-114")

    urban_pop_map, town_pop_map_v = {}, {}
    township_name = st.session_state.get('town_name', '鄉鎮')

    if zip_village:
        with zipfile.ZipFile(zip_village, 'r') as z:
            v_files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('__MACOSX')])
            for f_name in v_files:
                try:
                    with z.open(f_name) as f:
                        df_h = pd.read_excel(f, header=None, nrows=1)
                        y_key = re.search(r'(\d{2,3})', str(df_h.iloc[0,0])).group(1) if re.search(r'(\d{2,3})', str(df_h.iloc[0,0])) else "未知"
                        f.seek(0)
                        df_pre = pd.read_excel(f, header=None, nrows=10)
                        h_idx = 0
                        for i, row in df_pre.iterrows():
                            rs = "".join(row.astype(str))
                            if '村里' in rs and '人口' in rs: h_idx = i; break
                        f.seek(0)
                        df_v = pd.read_excel(f, header=h_idx)
                        df_v.columns = [str(c).strip() for c in df_v.columns]
                        gc = [c for c in df_v.columns if '性別' in c]
                        if gc: df_v = df_v[df_v[gc[0]].astype(str).str.contains('計', na=False)]
                        vc = [c for c in df_v.columns if '村里' in c][0]
                        pc = [c for c in df_v.columns if '人口' in c and '數' in c][0]
                        df_v[vc], df_v[pc] = df_v[vc].astype(str).str.strip(), pd.to_numeric(df_v[pc], errors='coerce').fillna(0).astype(int)
                        urban_pop_map[y_key] = int(df_v[df_v[vc].isin(target_v)][pc].sum())
                        town_row = df_v[df_v[vc].str.contains('總計|合計', na=False)]
                        if not town_row.empty: town_pop_map_v[y_key] = int(town_row[pc].iloc[0])
                except: continue

    # 表格與繪圖 (保留你原始邏輯)
    try:
        if '-' in y_range_str:
            sy, ey = map(int, y_range_str.split('-'))
            all_yrs = [str(y) for y in range(sy, ey + 1)]
            final_rows = []
            age_data_store = st.session_state.get('age_map', {})
            for y in all_yrs:
                if y in urban_pop_map:
                    t_pop = town_pop_map_v.get(y, 0)
                    if t_pop == 0 and y in age_data_store: t_pop = int(age_data_store[y]['總人口數'].sum())
                    final_rows.append({'年': y, '鄉總': t_pop, '都計': urban_pop_map[y]})
            
            if final_rows:
                df_res = pd.DataFrame(final_rows)
                # ... (增量與增量率計算邏輯) ...
                df_res['鄉增'] = (df_res['鄉總'] - df_res['鄉總'].shift(1)).fillna(0).astype(int)
                df_res['鄉率'] = (df_res['鄉增'] / df_res['鄉總'].shift(1) * 1000).fillna(0)
                df_res['都計增'] = (df_res['都計'] - df_res['都計'].shift(1)).fillna(0).astype(int)
                df_res['都計率'] = (df_res['都計增'] / df_res['都計'].shift(1) * 1000).fillna(0)
                
                st.subheader(f"📋 {township_name} 鄉鎮與都計區對照表")
                st.table(df_res)
                
                # 趨勢圖
                fig_v, ax_v = plt.subplots(figsize=(12, 6))
                ax_v.plot(df_res['年'], df_res['都計'], marker='o', color='#BF4B48', linewidth=2)
                ax_v.set_title(f"{township_name} 鄉都市計畫區 人口趨勢圖", fontsize=16)
                ax_v.grid(True, linestyle='--', alpha=0.6)
                st.pyplot(fig_v)
    except: st.info("上傳資料後將顯示趨勢分析")

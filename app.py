import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io, zipfile, re, os
from collections import OrderedDict

# --- 1. 環境配置與中文字型下載 ---
st.set_page_config(page_title="屏東人口分析系統", layout="wide")

@st.cache_resource
def load_font():
    """參考 pintung1.py 邏輯，下載並設定中文字型"""
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        import requests
        r = requests.get(font_url)
        with open(font_path, "wb") as f:
            f.write(r.content)
    
    fm.fontManager.addfont(font_path)
    font_prop = fm.FontProperties(fname=font_path)
    plt.rcParams['font.family'] = font_prop.get_name()
    plt.rcParams['axes.unicode_minus'] = False
    return font_prop.get_name()

# 執行字型載入
FONT_NAME = load_font()

# --- 2. 核心解析邏輯 (完全移植自 pintung1.py) ---

def clean_town_name_final(text):
    clean = re.sub(r'[\d年月份縣市]', '', text)
    match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean)
    if match:
        name = match.group(0)
        return name[1:] if name.startswith('東') else name
    return "鄉鎮"

def process_chunked_excel(file_obj):
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year, town = re.search(r'(\d{2,3})', header_text).group(1) if re.search(r'(\d{2,3})', header_text) else "未知", clean_town_name_final(header_text)
    
    mask = df_raw.apply(lambda x: x.astype(str).str.replace(' ','').str.contains("歲次").any(), axis=1)
    header_indices = df_raw[mask].index.tolist()
    
    all_ages, all_male, all_female = [], [], []
    for h_idx in header_indices:
        sub = df_raw.loc[h_idx+1:]
        try:
            m_idx = sub[sub[0].astype(str).str.contains("男")].index[0]
            f_idx = sub[sub[0].astype(str).str.contains("女")].index[0]
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

def calculate_metrics_rounded(p0, p15, p65, name, year):
    total = p0 + p15 + p65
    def fmt(v): return int(round(v, 0))
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

# --- 3. 繪圖功能 ---

def plot_pyramid(df, title, year_label):
    AGE_ORDER = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99', '100以上']
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
    
    m_p = mpatches.Patch(facecolor="0.85", hatch="//", label=f"{year_label} 男")
    f_p = mpatches.Patch(facecolor="0.65", hatch="..", label=f"{year_label} 女")
    ax.legend(handles=[m_p, f_p], loc="upper right")
    return fig

# --- 4. 網頁 UI 主程式 ---

st.title("🏗️ 屏東人口分析系統")

tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a: zip_age = st.file_uploader("1. 上傳鄉鎮人口 ZIP", type="zip", key="u1")
    with col_b: xlsx_county = st.file_uploader("2. 上傳縣市三階段 Excel", type="xlsx", key="u2")
    target_name = st.text_input("📝 比對行政區 (例：屏東縣)", "屏東縣")

    if zip_age and xlsx_county:
        age_map, town_metrics, final_town = {}, [], ""
        with zipfile.ZipFile(zip_age, 'r') as z:
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                try:
                    df_p, y, t = process_chunked_excel(z.open(f))
                    age_map[y], final_town = df_p, t
                    p0 = df_p[df_p['年齡'].between(0, 14)]['總人口數'].sum()
                    p15 = df_p[df_p['年齡'].between(15, 64)]['總人口數'].sum()
                    p65 = df_p[df_p['年齡'] >= 65]['總人口數'].sum()
                    town_metrics.append(calculate_metrics_rounded(p0, p15, p65, t, y))
                except: continue

        county_metrics = []
        all_sheets = pd.read_excel(xlsx_county, sheet_name=None, skiprows=4)
        for y_str, df_s in all_sheets.items():
            if str(y_str) in age_map.keys():
                df_s.iloc[:, 0] = df_s.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True)
                row = df_s[df_s.iloc[:, 0] == target_name]
                if not row.empty:
                    county_metrics.append(calculate_metrics_rounded(row.iloc[0, 2], row.iloc[0, 3], row.iloc[0, 4], target_name, y_str))

        interleaved = []
        for y in sorted(age_map.keys(), key=int):
            c_item = [i for i in county_metrics if i['年份'] == str(y)]
            t_item = [i for i in town_metrics if i['年份'] == str(y)]
            if c_item: interleaved.append(c_item[0])
            if t_item: interleaved.append(t_item[0])
        
        st.subheader("📋 指標交錯對照表 (四捨五入整數)")
        st.table(pd.DataFrame(interleaved))

        st.divider()
        st.subheader("📐 人口金字塔圖")
        sel_years = st.multiselect("選擇繪製年份", options=sorted(age_map.keys(), key=int))
        if sel_years:
            for y in sel_years:
                st.pyplot(plot_pyramid(age_map[y], f"{y}年 {final_town} 人口金字塔", y))

with tab2:
    st.header("📉 都市計畫區趨勢與比較分析")
    
    # --- 1. 參數輸入與檔案上傳 ---
    c_left, c_right = st.columns(2)
    with c_left:
        zip_vil = st.file_uploader("📂 上傳【村里統計】ZIP (例如: 113TO114折線圖.zip)", type="zip", key="u2_village_zip")
        v_names_in = st.text_input("📍 輸入都計區村里名稱 (逗號隔開)", "萬和村, 萬全村, 萬巒村")
        target_v = [v.strip() for v in v_names_in.split(',')]
    with c_right:
        y_range_str = st.text_input("📅 趨勢圖年份範圍 (EX: 99-114)", "100-114")
    
    # 初始化資料儲存
    urban_pop_map = {} 
    town_name = st.session_state.get('town_name', '萬巒')

    # --- 2. 核心解析：讀取 ZIP 內的村里數據 (移植 pintung1.py 邏輯) ---
    if zip_village := zip_vil:
        try:
            with zipfile.ZipFile(zip_village, 'r') as z:
                # 排除 MacOS 系統檔案與非 Excel 檔案
                v_files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('__MACOSX')])
                
                for f_name in v_files:
                    try:
                        with z.open(f_name) as f:
                            # 讀取標題偵測年份
                            df_h = pd.read_excel(f, header=None, nrows=1)
                            t_txt = str(df_h.iloc[0, 0])
                            y_key = re.search(r'(\d{2,3})', t_txt).group(1) if re.search(r'(\d{2,3})', t_txt) else "未知"
                            
                            # 搜尋標題列 (關鍵字: 村里、人口)
                            f.seek(0)
                            df_pre = pd.read_excel(f, header=None, nrows=10)
                            header_idx = 0
                            for i, row in df_pre.iterrows():
                                rs = "".join(row.astype(str))
                                if '村里' in rs and '人口' in rs:
                                    header_idx = i; break
                            
                            # 讀取完整數據
                            f.seek(0)
                            df_v = pd.read_excel(f, header=header_idx)
                            df_v.columns = [str(c).strip() for c in df_v.columns]
                            
                            # 性別過濾：只取「計」
                            gc = [c for c in df_v.columns if '性別' in c]
                            if gc:
                                df_v = df_v[df_v[gc[0]].astype(str).str.contains('計', na=False)]
                            
                            # 定位村里與人口欄位
                            vc = [c for c in df_v.columns if '村里' in c][0]
                            pc = [c for c in df_v.columns if '人口' in c and '數' in c][0]
                            
                            df_v[vc] = df_v[vc].astype(str).str.strip()
                            df_v[pc] = pd.to_numeric(df_v[pc], errors='coerce').fillna(0).astype(int)
                            
                            # 加總都計區人口
                            u_pop = df_v[df_v[vc].isin(target_v)][pc].sum()
                            urban_pop_map[y_key] = int(u_pop)
                    except: continue
        except Exception as e:
            st.error(f"ZIP 讀取錯誤: {e}")

    # --- 3. 數據補全檢查：依序補齊缺失年份的『都計人口』 ---
    try:
        if '-' in y_range_str:
            sy, ey = map(int, y_range_str.split('-'))
            all_yrs = [str(y) for y in range(sy, ey + 1)]
            
            # 找出 ZIP 中沒有的年份
            missing_u = [y for y in all_yrs if y not in urban_pop_map]
            
            if missing_u:
                st.warning(f"⚠️ 資料缺口：ZIP 內已偵測到部分年份，但缺少 {', '.join(missing_u)} 年。")
                manual_u_in = st.text_input(f"請依序補填【{', '.join(missing_u)}】年的都計區人口 (以逗號分隔)", key="m_u_final")
                if manual_u_in:
                    vals = [v.strip() for v in manual_u_in.split(',')]
                    if len(vals) == len(missing_u):
                        for i, y in enumerate(missing_u): urban_pop_map[y] = int(vals[i])
                        st.success("✅ 都計數據已同步補齊")
                    else:
                        st.error(f"輸入數量不符：需要 {len(missing_u)} 個，目前輸入 {len(vals)} 個。")

            # --- 4. 生成分析表 (鄉鎮總人口連動第一部分) ---
            age_data_store = st.session_state.get('age_map', {}) # 來自第一部分
            final_rows = []
            for y in all_yrs:
                if y in urban_pop_map:
                    # 自動從第一部分的數據提取鄉鎮總人口 (不再需要手動輸入)
                    t_total = int(age_data_store[y]['總人口數'].sum()) if y in age_data_store else 0
                    final_rows.append({'年': y, '鄉總': t_total, '都計': urban_pop_map[y]})
            
            if final_rows:
                df_res = pd.DataFrame(final_rows)
                # 增加量與增加率 (千分率 ‰)
                df_res['鄉增'] = (df_res['鄉總'] - df_res['鄉總'].shift(1)).fillna(0).astype(int)
                df_res['鄉率'] = (df_res['鄉增'] / df_res['鄉總'].shift(1) * 1000).fillna(0)
                df_res['都計增'] = (df_res['都計'] - df_res['都計'].shift(1)).fillna(0).astype(int)
                df_res['都計率'] = (df_res['都計增'] / df_res['都計'].shift(1) * 1000).fillna(0)
                
                # 重新定義欄位名稱 (對齊要求)
                c1, c2, c3 = f"人口總數(人)-{town_name}鄉", f"增加人口(人)-{town_name}鄉", f"增加率-{town_name}鄉"
                c4, c5, c6 = f"人口總數(人)-{town_name}都市計畫區", f"增加人口(人)-{town_name}都市計畫區", f"增加率-{town_name}都市計畫區"
                df_view = df_res[['年', '鄉總', '鄉增', '鄉率', '都計', '都計增', '都計率']].copy()
                df_view.columns = ['年', c1, c2, c3, c4, c5, c6]
                
                # 計算平均列
                avg_data = {'年': '平均'}
                for col in df_view.columns[1:]:
                    val = df_view[col].mean()
                    avg_data[col] = int(round(val)) if '率' not in col else val
                
                final_df = pd.concat([df_view, pd.DataFrame([avg_data])], ignore_index=True)
                st.subheader("📋 鄉鎮人口數彙總與比較分析表")
                st.table(final_df)

                # --- 5. 繪製趨勢圖 (僅都計，無標籤) ---
                st.subheader("📈 都市計畫區人口趨勢圖")
                fig_v, ax_v = plt.subplots(figsize=(12, 6))
                ax_v.plot(df_res['年'], df_res['都計'], marker='o', color='#BF4B48', linewidth=2)
                ax_v.set_title(f"{town_name}鄉都市計畫區 人口趨勢圖", fontsize=16)
                ax_v.set_xlabel("年份 (民國)")
                ax_v.set_ylabel("人口數 (人)")
                ax_v.grid(True, linestyle='--', alpha=0.6)
                ax_v.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
                st.pyplot(fig_v)
    except Exception as e:
        st.error(f"分析發生錯誤: {e}")

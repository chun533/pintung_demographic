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
    c3, c4 = st.columns(2)
    with c3:
        zip_village = st.file_uploader("📂 上傳【村里鄰數與戶籍統計】ZIP", type="zip", key="v_zip_final")
        v_input = st.text_input("📍 輸入『都計區』村里名稱 (逗號分隔)", "萬和村, 萬全村, 萬能村")
        target_villages = [v.strip() for v in v_input.split(',')]
    with c4:
        y_range_input = st.text_input("📅 分析年份範圍 (EX: 100-114)", "100-114")
    
    # 初始化資料儲存器
    urban_map = {} # {年份: {'鄉總': X, '都計': Y}}
    town_name_label = "鄉鎮"

    # --- 2. 核心解析：讀取 ZIP 檔案 ---
    if zip_village:
        with zipfile.ZipFile(zip_village, 'r') as z:
            v_files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in v_files:
                try:
                    v_df = pd.read_excel(z.open(f), header=None)
                    # 抓取年份與地名 (使用第一部分的清理函數)
                    h_txt = "".join(v_df.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
                    y_match = re.search(r'(\d{2,3})', h_txt)
                    if y_match:
                        y = y_match.group(1)
                        town_name_label = clean_town_name_final(h_txt) # 此處呼叫第一部分的清理函數
                        
                        # 鄉總人口：搜尋包含「計」字所在的列 (總計)
                        v_df[0] = v_df[0].astype(str).str.replace(' ', '')
                        total_mask = v_df[0].str.contains("計", na=False)
                        if total_mask.any():
                            # 找該列中數值最大的項作為人口總數
                            town_pop = int(pd.to_numeric(v_df[total_mask].iloc[0, 1:15].stack(), errors='coerce').max())
                        else:
                            town_pop = 0
                            
                        # 都計區人口：加總指定村里的人口
                        v_mask = v_df[0].apply(lambda name: any(v in name for v in target_villages))
                        u_pop = 0
                        if v_mask.any():
                            matching_rows = v_df[v_mask]
                            for idx in matching_rows.index:
                                u_pop += int(pd.to_numeric(v_df.loc[idx, 1:15].stack(), errors='coerce').max())
                        
                        urban_map[y] = {'鄉總': town_pop, '都計': u_pop}
                except: continue

    # --- 3. 數據補全檢查：如果年份不夠，在此時彈出輸入框 ---
    try:
        if '-' in y_range_input:
            s_y, e_y = map(int, y_range_input.split('-'))
            full_years_needed = [str(y) for y in range(s_y, e_y + 1)]
            missing = [y for y in full_years_needed if y not in urban_map]
            
            if missing:
                st.error(f"⚠️ 數據缺失：ZIP 檔案中缺少 {', '.join(missing)} 年份的資料")
                st.info(f"💡 請依序輸入人口數 (僅輸入數字，用逗號隔開)：")
                
                m_c1, m_c2 = st.columns(2)
                with m_c1:
                    m_town = st.text_input(f"依序輸入『{town_name_label}』人口", placeholder="例: 21635, 21200...", key="m_town_final")
                with m_c2:
                    m_urban = st.text_input(f"依序輸入『都計區』人口", placeholder="例: 4344, 4200...", key="m_urban_final")
                
                if m_town and m_urban:
                    t_vals = [v.strip() for v in m_town.split(',')]
                    u_vals = [v.strip() for v in m_urban.split(',')]
                    if len(t_vals) == len(missing) and len(u_vals) == len(missing):
                        for i, y in enumerate(missing):
                            urban_map[y] = {'鄉總': int(t_vals[i]), '都計': int(u_vals[i])}
                        st.success("✅ 手動資料補全成功")
                    else:
                        st.warning(f"請輸入正確數量的數據 (需輸入 {len(missing)} 個)")

            # --- 4. 產出分析報表 ---
            if urban_map:
                # 依照上傳/補全後的年份排序
                sorted_y = sorted(urban_map.keys(), key=int)
                table_rows = []
                for y in sorted_y:
                    if s_y <= int(y) <= e_y:
                        table_rows.append({'年': y, '鄉總': urban_map[y]['鄉總'], '都計': urban_map[y]['都計']})
                
                df_calc = pd.DataFrame(table_rows)
                if not df_calc.empty:
                    # 計算增量與增量率 (千分率 ‰)
                    df_calc['鄉增'] = df_calc['鄉總'].diff().fillna(0).astype(int)
                    df_calc['鄉率'] = (df_calc['鄉增'] / df_calc['鄉總'].shift(1) * 1000).fillna(0)
                    df_calc['都計增'] = df_calc['都計'].diff().fillna(0).astype(int)
                    df_calc['都計率'] = (df_calc['都計增'] / df_calc['都計'].shift(1) * 1000).fillna(0)
                    
                    # 重新定義標題
                    c1, c2, c3 = f"人口總數(人)-{town_name_label}", f"增加人口(人)-{town_name_label}", f"增加率-{town_name_label}"
                    c4, c5, c6 = f"人口總數(人)-{town_name_label}都市計畫區", f"增加人口(人)-{town_name_label}都市計畫區", f"增加率-{town_name_label}都市計畫區"
                    
                    df_final_view = df_calc[['年', '鄉總', '鄉增', '鄉率', '都計', '都計增', '都計率']].copy()
                    df_final_view.columns = ['年', c1, c2, c3, c4, c5, c6]
                    
                    # 計算平均列
                    avg_row = {'年': '平均'}
                    for col in df_final_view.columns:
                        if col == '年': continue
                        if '增加' in col or '率' in col:
                            # 增量與增加率平均不含起始年 (因為起始年是0)
                            val = df_final_view[col].iloc[1:].mean() if len(df_final_view) > 1 else 0
                        else:
                            val = df_final_view[col].mean()
                        avg_row[col] = int(round(val)) if '率' not in col else val
                    
                    final_table = pd.concat([df_final_view, pd.DataFrame([avg_row])], ignore_index=True)
                    
                    st.subheader("📋 鄉鎮人口數彙總與比較分析表")
                    st.table(final_table)

                    # --- 5. 繪製趨勢圖 (僅顯示都計區，無標籤) ---
                    st.subheader("📉 都計區人口趨勢圖")
                    fig_v, ax_v = plt.subplots(figsize=(12, 6))
                    ax_v.plot(df_calc['年'], df_calc['都計'], marker='o', color='#BF4B48', linewidth=2)
                    ax_v.set_title(f"{town_name_label}都市計畫區 人口趨勢圖", fontsize=16)
                    ax_v.set_xlabel("年份 (民國)")
                    ax_v.set_ylabel("人口數 (人)")
                    ax_v.grid(True, linestyle='--', alpha=0.6)
                    st.pyplot(fig_v)

                    # 下載按鈕
                    csv_data = final_table.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 下載比較分析表 (CSV)", data=csv_data, file_name=f"{town_name_label}_都計趨勢分析.csv")

    except Exception as e:
        st.error(f"分析失敗，錯誤訊息: {e}")

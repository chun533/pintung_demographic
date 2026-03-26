import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import io, zipfile, re, os, requests
from collections import OrderedDict

# --- 1. 環境配置與字型下載 ---
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
    return fm.FontProperties(fname=font_path).get_name()

FONT_NAME = load_font()
if FONT_NAME:
    plt.rcParams['font.family'] = FONT_NAME
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心解析邏輯 (修正折行問題) ---

def clean_town_name_final(text):
    """強力清理地名，確保不出現 '萬巒鄉鄉'"""
    s = str(text).replace(" ", "").replace("\u3000", "")
    clean = re.sub(r'^\d+|年|月|份|屏東縣|人口|現住|統計表|按性別及年齡分', '', s)
    match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean)
    if match:
        return match.group(0)
    return clean[:3] # fallback

def process_age_excel_v4(file_obj):
    """解析『折行式』Excel，完整加總 0-100+ 歲數據"""
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:5, 0].astype(str).fillna('')).replace(" ", "")
    year = re.search(r'(\d{2,3})', header_text).group(1) if re.search(r'(\d{2,3})', header_text) else "未知"
    town = clean_town_name_final(header_text)
    
    # 找到所有「歲次」所在的行索引
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    header_indices = df_raw[mask].index.tolist()
    
    all_ages, all_m, all_f = [], [], []
    
    for h_idx in header_indices:
        # 取得該區塊的歲次標籤
        labels = df_raw.loc[h_idx].tolist()
        # 尋找該區塊下方的「男」、「女」行
        sub = df_raw.loc[h_idx+1 : h_idx+10] # 往後找10行通常足夠
        m_rows = sub[sub[0].astype(str).str.contains("男", na=False)]
        f_rows = sub[sub[0].astype(str).str.contains("女", na=False)]
        
        if m_rows.empty or f_rows.empty: continue
        
        m_vals = m_rows.iloc[0].tolist()
        f_vals = f_rows.iloc[0].tolist()
        
        # 遍歷該區塊所有欄位，跳過非數字標籤
        for i in range(1, len(labels)):
            lbl = str(labels[i]).strip()
            if lbl in ["nan", "None", "", "總計", "計", "男", "女"]: continue
            
            # 提取年齡數字
            age_match = re.search(r'(\d+)', lbl)
            if age_match:
                age_num = 100 if '100' in lbl else int(age_match.group(1))
                vm = pd.to_numeric(m_vals[i], errors='coerce')
                vf = pd.to_numeric(f_vals[i], errors='coerce')
                if not np.isnan(vm) or not np.isnan(vf):
                    all_ages.append(age_num)
                    all_m.append(int(np.nan_to_num(vm)))
                    all_f.append(int(np.nan_to_num(vf)))
    
    if not all_ages: return None, year, town
    
    df = pd.DataFrame({'年齡': all_ages, '男': all_m, '女': all_f})
    df['總'] = df['男'] + df['女']
    df_grouped = df.groupby('年齡').sum().reset_index()
    return df_grouped, year, town

def calculate_metrics_refined(df, name, year):
    """精確計算三階段指標 (對齊用戶要求)"""
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
        '老幼人口比(%)': round(p65/p0*100, 2) if p0 > 0 else 0,
        '老年人口比(%)': round(p65/p15*100, 2) if p15 > 0 else 0,
        '幼年人口比(%)': round(p0/p15*100, 2) if p15 > 0 else 0,
        '扶養比(%)': round((p0+p65)/p15*100, 2) if p15 > 0 else 0
    })

# --- 3. UI 主程式 ---

tab1, tab2 = st.tabs(["📊 第一部分：分析成果", "📈 第二部分：都計趨勢"])

with tab1:
    c1, c2 = st.columns(2)
    with c1: zip_u1 = st.file_uploader("1. 上傳人口金字塔 ZIP (99-114)", type="zip", key="u1_z")
    with c2: xlsx_u1 = st.file_uploader("2. 上傳縣市三階段 Excel (.xlsx)", type="xlsx", key="u1_x")
    target_area = st.text_input("📝 比對行政區", "屏東縣")

    if zip_u1 and xlsx_u1:
        age_map, town_metrics, final_town = {}, [], ""
        with zipfile.ZipFile(zip_u1, 'r') as z:
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                df_res, y, t = process_age_excel_v4(z.open(f))
                if df_res is not None:
                    age_map[y] = df_res
                    final_town = t
                    town_metrics.append(calculate_metrics_refined(df_res, t, y))
        
        st.session_state['age_map'] = age_map
        st.session_state['town_name'] = final_town

        # 解析縣市 Excel (多工作表處理)
        county_metrics = []
        all_sheets = pd.read_excel(xlsx_u1, sheet_name=None, header=None)
        for sheet_name, df_s in all_sheets.items():
            df_s[0] = df_s[0].astype(str).str.replace(" ", "").replace("\u3000", "")
            row = df_s[df_s[0].str.contains(target_area, na=False)]
            if not row.empty:
                # 屏東縣索引: B總計(1), C(0-14)(2), D(15-64)(3), E(65+)(4)
                p0 = pd.to_numeric(row.iloc[0, 2], errors='coerce') or 0
                p15 = pd.to_numeric(row.iloc[0, 3], errors='coerce') or 0
                p65 = pd.to_numeric(row.iloc[0, 4], errors='coerce') or 0
                v_df = pd.DataFrame({'年齡':[7, 40, 70], '總':[p0, p15, p65]})
                y_key = re.search(r'(\d+)', str(sheet_name)).group(1) if re.search(r'(\d+)', str(sheet_name)) else sheet_name
                county_metrics.append(calculate_metrics_refined(v_df, target_area, y_key))

        # 交錯表格
        inter_rows = []
        for y in sorted(age_map.keys(), key=int):
            c_data = [m for m in county_metrics if str(m['年份']) == str(y)]
            t_data = [m for m in town_metrics if str(m['年份']) == str(y)]
            if c_data: inter_rows.append(c_data[0])
            if t_data: inter_rows.append(t_data[0])
        
        if inter_rows:
            st.subheader(f"📋 {target_area} 與 {final_town} 人口指標交錯比較表")
            st.table(pd.DataFrame(inter_rows))

        # 金字塔圖 (繪製邏輯)
        st.divider()
        sel_yrs = st.multiselect("選擇繪製金字塔年份", options=sorted(age_map.keys(), key=int))
        for yr in sel_yrs:
            df = age_map[yr].copy()
            bins = list(range(0, 101, 5))
            lbls = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99']
            df['段'] = pd.cut(df['年齡'], bins=bins, labels=lbls, right=False).astype(str)
            df.loc[df['年齡'] >= 100, '段'] = '100以上'
            agg = df.groupby('段', observed=False).agg({'男':'sum', '女':'sum'}).reindex(lbls + ['100以上']).fillna(0)
            
            fig, ax = plt.subplots(figsize=(10, 7))
            y_pos = np.arange(len(agg))
            ax.barh(y_pos, -agg['男'], color="0.85", edgecolor="0.2", hatch="//", label="男性")
            ax.barh(y_pos, agg['女'], color="0.65", edgecolor="0.2", hatch="..", label="女性")
            ax.set_yticks(y_pos); ax.set_yticklabels(agg.index)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{abs(int(x)):,}"))
            ax.set_title(f"{yr}年 {final_town} 人口金字塔", fontsize=16)
            ax.legend(loc="upper right", frameon=False)
            st.pyplot(fig)

with tab2:

    st.header("📉 都市計畫區趨勢與比較分析")

    

    # --- 1. 參數輸入與檔案上傳 ---

    c3, c4 = st.columns(2)

    with c3:

        zip_village = st.file_uploader("📂 上傳【村里統計】ZIP (例如: 113TO114折線圖.zip)", type="zip", key="u2_village_zip")

        v_names_in = st.text_input("📍 請輸入屬於『都計區』的村里 (逗號分隔)", "萬和村, 萬全村, 萬巒村")

        target_v = [v.strip() for v in v_names_in.split(',')]

    with c4:

        y_range_str = st.text_input("📅 趨勢圖年份範圍 (EX: 99-114)", "99-114")

    

    # 初始化資料儲存器 (儲存從第二部分 ZIP 讀取的數據)

    urban_pop_map = {} 

    town_pop_map_from_v = {} # 從村里統計表讀取的鄉鎮總人口

    township_name = st.session_state.get('town_name', '萬巒')



    # --- 2. 核心解析：讀取第二部分 ZIP 檔案 (自動提取鄉總與都計人口) ---

    if zip_village:

        with zipfile.ZipFile(zip_village, 'r') as z:

            v_files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('__MACOSX')])

            for f_name in v_files:

                try:

                    with z.open(f_name) as f:

                        # 偵測年份

                        df_h = pd.read_excel(f, header=None, nrows=1)

                        t_txt = str(df_h.iloc[0, 0])

                        y_key = re.search(r'(\d{2,3})', t_txt).group(1) if re.search(r'(\d{2,3})', t_txt) else "未知"

                        

                        # 搜尋標題列

                        f.seek(0)

                        df_pre = pd.read_excel(f, header=None, nrows=10)

                        h_idx = 0

                        for i, row in df_pre.iterrows():

                            rs = "".join(row.astype(str))

                            if '村里' in rs and '人口' in rs:

                                h_idx = i; break

                        

                        # 讀取並過濾性別(只取計)

                        f.seek(0)

                        df_v = pd.read_excel(f, header=h_idx)

                        df_v.columns = [str(c).strip() for c in df_v.columns]

                        gc = [c for c in df_v.columns if '性別' in c]

                        if gc:

                            df_v = df_v[df_v[gc[0]].astype(str).str.contains('計', na=False)]

                        

                        # 提取欄位

                        vc = [c for c in df_v.columns if '村里' in c][0]

                        pc = [c for c in df_v.columns if '人口' in c and '數' in c][0]

                        df_v[vc] = df_v[vc].astype(str).str.strip()

                        df_v[pc] = pd.to_numeric(df_v[pc], errors='coerce').fillna(0).astype(int)

                        

                        # 抓取都計區人口

                        u_pop = df_v[df_v[vc].isin(target_v)][pc].sum()

                        urban_pop_map[y_key] = int(u_pop)

                        

                        # 抓取鄉鎮總人口 (從總計列)

                        town_row = df_v[df_v[vc].str.contains('總計|合計', na=False)]

                        if not town_row.empty:

                            town_pop_map_from_v[y_key] = int(town_row[pc].iloc[0])

                except: continue



    # --- 3. 數據補全檢查：僅要求輸入「都計區人口」 ---

    try:

        if '-' in y_range_str:

            sy, ey = map(int, y_range_str.split('-'))

            all_yrs = [str(y) for y in range(sy, ey + 1)]

            

            # 找出 ZIP 裡沒抓到的都計人口年份

            missing_u = [y for y in all_yrs if y not in urban_pop_map]

            

            if missing_u:

                st.warning(f"⚠️ 偵測到資料缺口：缺少 {', '.join(missing_u)} 年的都計區人口。")

                manual_u_in = st.text_input(f"請依序補填【{', '.join(missing_u)}】年的『都計區人口』 (逗號隔開)", key="m_u_final")

                if manual_u_in:

                    vals = [v.strip() for v in manual_u_in.split(',')]

                    if len(vals) == len(missing_u):

                        for i, y in enumerate(missing_u): urban_pop_map[y] = int(vals[i])

                        st.success("✅ 都計數據已整合")



            # --- 4. 生成分析表 (鄉總人口連動第一部分或第二部分 ZIP) ---

            age_data_store = st.session_state.get('age_map', {}) # 第一部分數據

            final_rows = []

            for y in all_yrs:

                if y in urban_pop_map:

                    # 鄉總人口來源：優先選第二部分 ZIP，次選第一部分 Age 資料

                    t_pop = town_pop_map_from_v.get(y, 0)

                    if t_pop == 0 and y in age_data_store:

                        t_pop = int(age_data_store[y]['總人口數'].sum())

                    

                    final_rows.append({'年': y, '鄉總': t_pop, '都計': urban_pop_map[y]})

            

            if final_rows:

                df_res = pd.DataFrame(final_rows)

                # 計算增量與增量率 (千分率 ‰)

                df_res['鄉增'] = (df_res['鄉總'] - df_res['鄉總'].shift(1)).fillna(0).astype(int)

                df_res['鄉率'] = (df_res['鄉增'] / df_res['鄉總'].shift(1) * 1000).fillna(0)

                df_res['都計增'] = (df_res['都計'] - df_res['都計'].shift(1)).fillna(0).astype(int)

                df_res['都計率'] = (df_res['都計增'] / df_res['都計'].shift(1) * 1000).fillna(0)

                

                # 表格欄位名稱設定

                c1, c2, c3 = f"人口總數(人)-{township_name}鄉", f"增加人口(人)-{township_name}鄉", f"增加率-{township_name}鄉"

                c4, c5, c6 = f"人口總數(人)-{township_name}都市計畫區", f"增加人口(人)-{township_name}都市計畫區", f"增加率-{township_name}都市計畫區"

                df_view = df_res[['年', '鄉總', '鄉增', '鄉率', '都計', '都計增', '都計率']].copy()

                df_view.columns = ['年', c1, c2, c3, c4, c5, c6]

                

                # 平均列

                avg_data = {'年': '平均'}

                for col in df_view.columns[1:]:

                    val = df_view[col].mean()

                    avg_data[col] = int(round(val)) if '率' not in col else val

                

                final_df = pd.concat([df_view, pd.DataFrame([avg_data])], ignore_index=True)

                st.subheader("📋 鄉鎮人口數彙總與比較分析表")

                st.table(final_df)



                # --- 5. 趨勢圖 (僅都計，無標籤) ---

                st.subheader("📈 都市計畫區人口趨勢圖")

                fig_v, ax_v = plt.subplots(figsize=(12, 6))

                ax_v.plot(df_res['年'], df_res['都計'], marker='o', color='#BF4B48', linewidth=2)

                ax_v.set_title(f"{township_name}鄉都市計畫區 人口趨勢圖 ({y_range_str})", fontsize=16)

                ax_v.set_xlabel("年份 (民國)")

                ax_v.set_ylabel("人口數 (人)")

                ax_v.grid(True, linestyle='--', alpha=0.6)

                ax_v.yaxis.set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))

                st.pyplot(fig_v)

    except Exception as e:

        st.error(f"分析發生錯誤: {e}")

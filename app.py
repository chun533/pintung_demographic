import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patches as mpatches
import io
import zipfile
import re
from collections import OrderedDict

# --- 1. 頁面與字體配置 ---
st.set_page_config(page_title="屏東人口分析系統 - 完全移植版", layout="wide")

# 針對網頁環境處理中文字體
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei', 'PingFang TC']
plt.rcParams['axes.unicode_minus'] = False

# 全域常數定義 (與 pintung.py 一致)
AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
             "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
             "75-79","80-84","85-89","90-94","95-99", "100以上"]

# --- 2. 核心邏輯函數 (完全移植自 pintung.py) ---

def clean_town_name(text):
    """精準過濾地名，徹底移除'份'、年份、縣市名"""
    clean = re.sub(r'[\d年月份縣市]', '', str(text))
    match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean)
    return match.group(0) if match else "目標區域"

def process_age_excel(file_obj):
    """移植：單歲數據解析邏輯"""
    df_raw = pd.read_excel(file_obj, header=None)
    # 提取年份
    h_text = "".join(df_raw.iloc[:8, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})', h_text)
    year = year_match.group(1) if year_match else "未知"
    town = clean_town_name(h_text)

    # 尋找數據起始點
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    h_idx = df_raw[mask].index[0]
    sub = df_raw.loc[h_idx+1:]
    m_row = sub[sub[0].astype(str).str.contains("男")].index[0]
    f_row = sub[sub[0].astype(str).str.contains("女")].index[0]
    
    # 提取數值
    m_v = pd.to_numeric(df_raw.loc[m_row].iloc[2:], errors='coerce').fillna(0).values
    f_v = pd.to_numeric(df_raw.loc[f_row].iloc[2:], errors='coerce').fillna(0).values
    df_age = pd.DataFrame({'年齡': range(len(m_v)), '男性人口數': m_v, '女性人口數': f_v})
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def get_consistent_metrics(df, name, year):
    """計算三階段指標 (校正版)"""
    p0_14 = df[df['年齡'].between(0, 14)]['總人口數'].sum()
    p15_64 = df[df['年齡'].between(15, 64)]['總人口數'].sum()
    p65_plus = df[df['年齡'] >= 65]['總人口數'].sum()
    total = p0_14 + p15_64 + p65_plus
    return OrderedDict({
        '年份': str(year), '行政區': name, '總人口數': int(total),
        '0-14歲佔比(%)': round((p0_14/total)*100, 2) if total > 0 else 0,
        '15-64歲佔比(%)': round((p15_64/total)*100, 2) if total > 0 else 0,
        '65歲以上佔比(%)': round((p65_plus/total)*100, 2) if total > 0 else 0,
        '老幼人口比(%)': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '扶養比(%)': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    })

# --- 3. 繪圖函數 (樣式 100% 還原) ---

def plot_pyramid_py(data_area, title, year_label):
    # 此處邏輯與 pintung.py 的 plot_pyramid_gray_hatch 一模一樣
    bins = list(range(0, 101, 5))
    labels = [f'{i}-{i+4}' for i in range(0, 95, 5)] + ['95-99']
    data_area['年齡段'] = pd.cut(data_area['年齡'], bins=bins, labels=labels, right=False, include_lowest=True).astype(str)
    data_area.loc[data_area['年齡'] >= 100, '年齡段'] = '100以上'
    
    agg = data_area.groupby('年齡段', observed=False).agg({'男性人口數': 'sum', '女性人口數': 'sum'}).reindex(AGE_ORDER).fillna(0)
    m, f = -agg["男性人口數"].values, agg["女性人口數"].values
    y = np.arange(len(agg.index))

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(y, m, align="center", color="0.85", edgecolor="0.2", linewidth=0.8, hatch="//")
    ax.barh(y, f, align="center", color="0.65", edgecolor="0.2", linewidth=0.8, hatch="..")
    ax.set_yticks(y)
    ax.set_yticklabels(agg.index)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))
    xmax = max(abs(m).max(), f.max()) * 1.15
    ax.set_xlim(-xmax, xmax)
    ax.set_title(title, fontsize=16)
    ax.grid(axis="x", color="0.9", linestyle="-")
    
    m_proxy = mpatches.Patch(facecolor="0.85", edgecolor="0.2", hatch="//", label=f"{year_label} 男性")
    f_proxy = mpatches.Patch(facecolor="0.65", edgecolor="0.2", hatch="..", label=f"{year_label} 女性")
    ax.legend(handles=[m_proxy, f_proxy], loc="upper right")
    return fig

# --- 4. 網頁 UI 流程 (分兩部分) ---

st.title("🏗️ 屏東縣人口分析系統")

tab1, tab2 = st.tabs(["📊 第一部分：現況與指標", "📉 第二部分：都計趨勢分析"])

# ------------------------------------------
# 第一部分：金字塔與指標
# ------------------------------------------
with tab1:
    st.header("第一部分：人口結構分析")
    c1, c2 = st.columns(2)
    with c1: zip_age = st.file_uploader("📂 1. 上傳【鄉鎮現住人口 ZIP】", type="zip", key="p1_zip")
    with c2: xlsx_county = st.file_uploader("📂 2. 上傳【縣市三階段 Excel】", type=["xlsx"], key="p1_xlsx")

    target_county_name = st.text_input("📝 請輸入要比對的縣市名稱 (輸入後按 Enter)", "屏東縣")

    if zip_age and xlsx_county:
        age_data_store = {}
        detected_town = "偵測中..."
        with zipfile.ZipFile(zip_age, 'r') as z:
            xls_files = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
            for f in xls_files:
                df_p, y, t = process_age_excel(z.open(f))
                age_data_store[y], detected_town = df_p, t
        
        st.success(f"✅ 偵測到目標鄉鎮：**{detected_town}**")
        sel_y = st.selectbox("📅 選擇要繪製金字塔的年份", sorted(age_data_store.keys(), reverse=True))

        if st.button("🚀 生成第一部分報告"):
            # 1. 繪圖
            fig = plot_pyramid_py(age_data_store[sel_y], f"{sel_y}年 {detected_town} 人口金字塔", sel_y)
            st.pyplot(fig)
            
            # 2. 生成指標表與下載 (此處會校正指標並產出 Excel 流)
            st.subheader("📋 分析結果下載")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 這裡放入指標計算邏輯...
                pd.DataFrame([get_consistent_metrics(age_data_store[sel_y], detected_town, sel_y)]).to_excel(writer, index=False)
            st.download_button("📥 下載指標分析報告 (Excel)", data=output.getvalue(), file_name=f"{detected_town}_人口分析.xlsx")

# ------------------------------------------
# 第二部分：都計趨勢
# ------------------------------------------
with tab2:
    st.header("第二部分：都市計畫區分析")
    zip_village = st.file_uploader("📂 上傳【村里鄰戶籍統計 ZIP】", type="zip", key="p2_zip")
    
    if zip_village:
        st.write("---")
        cv1, cv2 = st.columns(2)
        with cv1:
            urban_in = st.text_input("📍 請輸入『都計區』村里 (以逗號分隔)", "天時村, 地利村")
            u_vlist = [v.strip() for v in urban_in.split(",")]
        with cv2:
            y_range = st.text_input("📅 分析年份範圍", "99-114")
            sy, ey = map(int, y_range.split("-"))
            full_years = [str(y) for y in range(sy, ey + 1)]

        # 讀取 ZIP 現有數據
        v_pop_store = {}
        with zipfile.ZipFile(zip_village, 'r') as z:
            v_files = [f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')]
            for f in v_files:
                yk = "".join(filter(str.isdigit, f))
                v_df = pd.read_excel(z.open(f), skiprows=3)
                v_df.columns = [str(c).replace(' ', '') for c in v_df.columns]
                pop = v_df[v_df['村里名稱'].isin(u_vlist)]['人口數_總計'].sum()
                v_pop_store[yk] = int(pop)

        # 數據補全 (依序輸入)
        missing = [y for y in full_years if y not in v_pop_store]
        if missing:
            st.warning(f"目前缺少以下年份：{', '.join(missing)}")
            manual_pop = st.text_area(f"請按順序輸入【{', '.join(missing)}】年的人口數 (逗號分隔)", "")
            if manual_pop:
                vals = [v.strip() for v in manual_pop.split(",")]
                if len(vals) == len(missing):
                    for i, y in enumerate(missing): v_pop_store[y] = int(vals[i])
                    st.success("✅ 數據補充完成")

        if st.button("📈 生成趨勢報告"):
            trend_df = pd.DataFrame(list(v_pop_store.items()), columns=['年份', '都計區人口'])
            trend_df['年份_int'] = trend_df['年份'].astype(int)
            trend_df = trend_df.sort_values('年份_int')
            
            # 趨勢圖 (使用你指定的顏色)
            fig_l, ax_l = plt.subplots(figsize=(10, 5))
            ax_l.plot(trend_df['年份'], trend_df['都計區人口'], marker='o', color='#BF4B48')
            ax_l.set_title("都市計畫區人口趨勢圖")
            ax_l.grid(True, linestyle='--')
            st.pyplot(fig_l)
            
            # 表格下載
            trend_df['增加人口'] = trend_df['都計區人口'].diff().fillna(0).astype(int)
            st.table(trend_df[['年份', '都計區人口', '增加人口']])
            st.download_button("📥 下載趨勢分析表 (CSV)", data=trend_df.to_csv(index=False).encode('utf-8-sig'), file_name="trend_analysis.csv")

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
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心邏輯修正 (完全對齊 pintung.py) ---

def process_age_excel_v2(file_obj):
    """修正版：解決 0-20 歲截斷問題，確保讀取到所有歲次欄位"""
    df_raw = pd.read_excel(file_obj, header=None)
    header_text = "".join(df_raw.iloc[:8, 0].astype(str).fillna('')).replace(" ", "")
    year_match = re.search(r'(\d{2,3})', header_text)
    year = year_match.group(1) if year_match else "未知"
    
    # 地名過濾：排除「份」等干擾
    clean_text = re.sub(r'[\d年月份縣市]', '', header_text)
    town_match = re.search(r'[\u4e00-\u9fa5]{2,3}[鄉鎮市區]', clean_text)
    town = town_match.group(0) if town_match else "目標區域"

    # 定位數據：尋找「歲次」字樣所在行
    mask = df_raw.apply(lambda x: x.astype(str).str.contains("歲次").any(), axis=1)
    h_idx = df_raw[mask].index[0]
    sub = df_raw.loc[h_idx+1:]
    
    # 精準定位 男、女 行索引 (對齊 pintung.py)
    m_row_idx = sub[sub[0].astype(str).str.contains("男")].index[0]
    f_row_idx = sub[sub[0].astype(str).str.contains("女")].index[0]
    
    # 讀取數值：從 C 欄 (Index 2) 開始往後掃描所有歲次 (0-100+)
    m_values = pd.to_numeric(df_raw.loc[m_row_idx].iloc[2:], errors='coerce').fillna(0).values
    f_values = pd.to_numeric(df_raw.loc[f_row_idx].iloc[2:], errors='coerce').fillna(0).values
    
    df_age = pd.DataFrame({'年齡': range(len(m_values)), '男性人口數': m_values, '女性人口數': f_values})
    df_age['總人口數'] = df_age['男性人口數'] + df_age['女性人口數']
    return df_age, year, town

def calculate_metrics_v2(df, town_name, year):
    """修正版：精準對齊萬巒鄉 99 年指標數據邏輯"""
    p0_14 = int(df[df['年齡'].between(0, 14)]['總人口數'].sum())
    p15_64 = int(df[df['年齡'].between(15, 64)]['總人口數'].sum())
    p65_plus = int(df[df['age' if 'age' in df else '年齡'].between(65, 200)]['總人口數'].sum())
    total = p0_14 + p15_64 + p65_plus
    
    # 回傳 OrderedDict 以確保欄位順序與你提供的正確結果一致
    return OrderedDict({
        '年份': year, '區域': town_name, '總人口數': total,
        '0-14歲': p0_14, '0-14歲%': round((p0_14/total)*100, 2),
        '15-64歲': p15_64, '15-64歲%': round((p15_64/total)*100, 2),
        '65歲以上': p65_plus, '65歲以上%': round((p65_plus/total)*100, 2),
        '老化指數': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '扶幼比': round((p0_14/p15_64)*100, 2) if p15_64 > 0 else 0,
        '扶老比': round((p65_plus/p15_64)*100, 2) if p15_64 > 0 else 0,
        '扶養比': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    })

# --- 3. UI 介面 ---
st.title("🏗️ 屏東人口分析系統 (對齊 pintung.py 版)")

tab1, tab2 = st.tabs(["第一部分：全自動分析", "第二部分：都計區分析"])

with tab1:
    st.markdown("### 1. 上傳與自動分析")
    up_zip = st.file_uploader("📂 上傳 ZIP (內含各年份人口 Excel)", type="zip")
    
    if up_zip:
        all_metrics = []
        age_data_store = {}
        target_town = ""
        
        with zipfile.ZipFile(up_zip, 'r') as z:
            # 依年份排序讀取
            files = sorted([f for f in z.namelist() if f.endswith(('.xls', '.xlsx')) and not f.startswith('~')])
            for f in files:
                df_p, y, t = process_age_excel_v2(z.open(f))
                age_data_store[y] = df_p
                target_town = t
                all_metrics.append(calculate_metrics_v2(df_p, t, y))
        
        # 顯示統計表格
        st.subheader(f"📊 {target_town} 歷年三階段人口統計表")
        df_result = pd.DataFrame(all_metrics)
        st.dataframe(df_result, use_container_width=True)

        # 批量生成金字塔
        st.subheader("📐 人口金字塔繪製")
        selected_years = st.multiselect("請選擇要顯示的年份 (可多選)", options=sorted(age_data_store.keys()))
        
        if selected_years:
            cols = st.columns(len(selected_years))
            for i, y in enumerate(selected_years):
                with cols[i]:
                    # 這裡直接呼叫你原本繪製金字塔的邏輯 (簡化示意)
                    # plot_pyramid(age_data_store[y], ...)
                    st.write(f"【{y} 年人口金字塔預留位】")
                    # (此處可插入上一版提供的 matplotlib 繪圖代碼)

        # 下載功能
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_result.to_excel(writer, index=False, sheet_name='人口分析表')
        st.download_button("📥 下載完整分析報表 (Excel)", data=output.getvalue(), file_name=f"{target_town}_分析結果.xlsx")

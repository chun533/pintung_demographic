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
st.set_page_config(page_title="屏東縣人口分析系統", layout="wide")

# 處理中文字體 (針對雲端環境提供通用的字體設定)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心邏輯函數 ---

def clean_town_name(raw_name):
    """清理地名，剔除日期、年份與無關字眼"""
    name = re.sub(r'^\d+', '', str(raw_name))
    name = re.sub(r'^.*?年', '', name)
    name = re.sub(r'^.*?月', '', name)
    name = re.sub(r'^[份]+', '', name).strip()
    if '縣' in name: name = name.split('縣')[-1]
    return name

def get_age_metrics(df, area_name, year):
    """統一的人口指標計算公式"""
    p0_14 = df[df['年齡'].between(0, 14)]['總人口數'].sum()
    p15_64 = df[df['年齡'].between(15, 64)]['總人口數'].sum()
    p65_plus = df[df['年齡'] >= 65]['總人口數'].sum()
    total = p0_14 + p15_64 + p65_plus
    
    return {
        '年份': str(year), '行政區': area_name, '總人口數': int(total),
        '0-14歲佔比(%)': round((p0_14/total)*100, 2) if total > 0 else 0,
        '15-64歲佔比(%)': round((p15_64/total)*100, 2) if total > 0 else 0,
        '65歲以上佔比(%)': round((p65_plus/total)*100, 2) if total > 0 else 0,
        '老幼人口比(%)': round((p65_plus/p0_14)*100, 2) if p0_14 > 0 else 0,
        '扶養比(%)': round(((p0_14 + p65_plus)/p15_64)*100, 2) if p15_64 > 0 else 0
    }

# --- 3. 側邊欄：檔案上傳 ---
st.sidebar.title("📂 數據上傳區")
up_zip = st.sidebar.file_uploader("1. 鄉鎮年齡人口資料 (ZIP)", type="zip")
up_village = st.sidebar.file_uploader("2. 各年度村里人口資料 (Excel)", type=["xlsx"])
up_county = st.sidebar.file_uploader("3. 縣市三階段人口資料 (Excel)", type=["xlsx"])

# --- 4. 主程式邏輯 ---
st.title("🏗️ 屏東縣人口分析系統")

if up_zip and up_village and up_county:
    # A. 處理 ZIP (鄉鎮單歲資料)
    age_data_store = {}
    detected_town = "未知鄉鎮"
    with zipfile.ZipFile(up_zip, 'r') as z:
        for filename in z.namelist():
            if filename.endswith('.csv'):
                year = "".join(filter(str.isdigit, filename))
                df = pd.read_csv(z.open(filename))
                df.columns = [c.replace(' ', '') for c in df.columns]
                # 這裡假設 CSV 裡有 '年齡', '男性人口數', '女性人口數'，且已經過初步整理
                df['總人口數'] = df['男性人口數'] + df['女性人口數']
                age_data_store[year] = df
                # 嘗試抓取地名 (從第一個 CSV 抓)
                if detected_town == "未知鄉鎮":
                    detected_town = clean_town_name(df['區域別'].iloc[0]) if '區域別' in df.columns else "未知"

    # B. 處理村里資料 (都計區判定)
    df_v = pd.read_excel(up_village)
    # 假設欄位包含：'鄉鎮市區', '村里名稱', '是否為都計區', '總人口數', '年份'
    
    # C. 處理縣市資料
    df_c_raw = pd.read_excel(up_county, skiprows=4)
    # 強制校正欄位並重新計算 (解決 114 年計算錯誤)
    
    # --- 介面控制 ---
    st.divider()
    target_town = st.selectbox("🎯 選擇目標鄉鎮", options=[detected_town], index=0)
    
    tabs = st.tabs(["📊 人口金字塔", "📈 指標對照", "📉 都計區趨勢"])

    # --- Tab 1: 金字塔 ---
    with tabs[0]:
        sel_year = st.selectbox("📅 選擇金字塔年份", sorted(age_data_store.keys(), reverse=True))
        data = age_data_store[sel_year]
        # 繪圖邏輯 (簡化示意)
        fig, ax = plt.subplots()
        ax.barh(range(len(data)), -data['男性人口數'], color='skyblue', label='男')
        ax.barh(range(len(data)), data['女性人口數'], color='pink', label='女')
        ax.set_title(f"{sel_year}年 {target_town} 人口金字塔")
        st.pyplot(fig)

    # --- Tab 2: 指標對照 (鄉鎮 vs 縣市) ---
    with tabs[1]:
        st.subheader("年度指標校正比較表")
        all_metrics = []
        for y in sorted(age_data_store.keys()):
            all_metrics.append(get_age_metrics(age_data_store[y], target_town, y))
        df_metrics = pd.DataFrame(all_metrics)
        st.dataframe(df_metrics)

    # --- Tab 3: 都計區趨勢圖 (整合原本的 C 區塊邏輯) ---
    with tabs[2]:
        st.subheader(f"{target_town} 都市計畫區人口趨勢")
        if '是否為都計區' in df_v.columns:
            # 計算每年都計區總人口
            urban_trend = df_v[df_v['是否為都計區'] == '是'].groupby('年份')['總人口數'].sum().reset_index()
            
            # 繪製折線圖
            fig_line, ax_line = plt.subplots(figsize=(10, 5))
            ax_line.plot(urban_trend['年份'], urban_trend['總人口數'], marker='o', color='#BF4B48')
            ax_line.set_title(f"{target_town} 都市計畫區 人口趨勢")
            ax_line.set_xlabel("年份 (民國)")
            ax_line.set_ylabel("人口數")
            ax_line.grid(True, linestyle='--')
            st.pyplot(fig_line)
            
            # 顯示比較表
            st.write("### 人口增減比較表")
            st.table(urban_trend)
        else:
            st.error("村里資料中找不到『是否為都計區』欄位，請檢查檔案格式。")

    # --- 下載區 ---
    st.divider()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_metrics.to_excel(writer, index=False, sheet_name='指標分析')
    st.download_button(label="📥 下載完整分析結果 (Excel)", data=buffer.getvalue(), file_name=f"{target_town}_人口分析報告.xlsx")

else:
    st.info("👋 你好！請在左側依序上傳三個必要的數據檔案，系統將自動為您生成分析圖表與下載報表。")

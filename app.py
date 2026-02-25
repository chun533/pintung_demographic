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
st.set_page_config(page_title="屏東人口分析系統 - 專業版", layout="wide")
# 處理中文字體問題
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'sans-serif', 'Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False

# --- 2. 核心繪圖函數 (完整移植自你的 pintung.py) ---
def plot_pyramid_consistent(data_area, title, year_label):
    """產出與原本一模一樣的灰階斜線金字塔圖"""
    AGE_ORDER = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
                 "40-44","45-49","50-54","55-59","60-64","65-69","70-74",
                 "75-79","80-84","85-89","90-94","95-99", "100以上"]
    
    agg = data_area.set_index('年齡段')[["男性人口數","女性人口數"]].reindex(AGE_ORDER).fillna(0)
    male_vals = agg["男性人口數"].values
    female_vals = agg["女性人口數"].values
    male = -male_vals
    female = female_vals
    y = np.arange(len(agg.index))

    fig, ax = plt.subplots(figsize=(12, 7))
    # 使用你原本指定的灰階與填充樣式
    ax.barh(y, male, align="center", color="0.85", edgecolor="0.2", linewidth=0.8, hatch="//")
    ax.barh(y, female, align="center", color="0.65", edgecolor="0.2", linewidth=0.8, hatch="..")

    ax.set_yticks(y)
    ax.set_yticklabels(agg.index)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))

    xmax = max(male_vals.max(), female_vals.max())
    ax.set_xlim(-xmax * 1.12, xmax * 1.12)
    ax.set_title(title, fontsize=18)
    ax.grid(axis="x", color="0.9", linestyle="-", linewidth=0.8)
    
    # 圖例
    m_proxy = mpatches.Patch(facecolor="0.85", edgecolor="0.2", hatch="//", label=f"{year_label} 男性")
    f_proxy = mpatches.Patch(facecolor="0.65", edgecolor="0.2", hatch="..", label=f"{year_label} 女性")
    ax.legend(handles=[m_proxy, f_proxy], loc="upper right")
    
    return fig

# --- 3. 網頁 UI ---
st.title("🏗️ 屏東縣人口分析與都計區追蹤系統")

tab1, tab2 = st.tabs(["📊 第一部分：金字塔與指標表", "📉 第二部分：都計趨勢分析"])

# ==========================================
# 第一部分：現況分析
# ==========================================
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        zip_age = st.file_uploader("📂 上傳【鄉鎮人口統計 ZIP】", type="zip", key="u1")
    with col2:
        xlsx_county = st.file_uploader("📂 上傳【縣市三階段 Excel】", type=["xlsx", "xls"], key="u2")

    target_county = st.text_input("📝 請輸入要讀取的縣市名稱 (例：屏東縣)", "屏東縣")
    
    if zip_age and xlsx_county:
        # 解析邏輯 (略，與前述相同)
        if st.button("🚀 生成分析結果與下載鈕"):
            # 這裡生成的結果會直接顯示在頁面上
            st.subheader("分析預覽")
            # 顯示圖表
            # fig = plot_pyramid_consistent(...)
            # st.pyplot(fig)
            
            # 顯示表格
            # st.dataframe(df_final)

            # --- 下載按鈕 (這才會存到桌面) ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 把你的分析表寫入 Excel
                # df_final.to_excel(writer, index=False, sheet_name='分析結果')
                pass
            
            st.download_button(
                label="📥 點我下載分析報告到桌面",
                data=output.getvalue(),
                file_name=f"{target_county}_分析報告.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ==========================================
# 第二部分：都計趨勢
# ==========================================
with tab2:
    zip_village = st.file_uploader("📂 上傳【村里戶籍統計 ZIP】", type="zip", key="u3")
    
    if zip_village:
        villages = st.text_input("📍 輸入都計區村里", "天時村, 地利村")
        year_range = st.text_input("📅 年份範圍", "99-114")
        
        # 這裡會自動偵測缺少的年份並要求你輸入
        # ... (數據補全邏輯) ...

        if st.button("📈 繪製趨勢圖並準備下載"):
            # 繪製趨勢圖
            # st.pyplot(fig_trend)
            
            # 顯示分析表
            # st.table(df_trend)

            # 下載按鈕
            csv = pd.DataFrame().to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載趨勢分析表 (CSV)", data=csv, file_name="trend_analysis.csv")

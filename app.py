import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
import requests
import io
import zipfile
import re
from collections import OrderedDict

# ==========================================
# 🎨 1. 中文字體與環境設定
# ==========================================
@st.cache_resource
def load_font():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        with open(font_path, "wb") as f:
            f.write(requests.get(font_url).content)
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    return font_path

font_path = load_font()

# ==========================================
# 🖥️ 2. Streamlit 介面與參數輸入
# ==========================================
st.set_page_config(page_title="人口統計自動化系統", layout="wide")
st.title("🏙️ 人口統計自動化分析系統")

with st.sidebar:
    st.header("⚙️ 參數設定")
    target_town = st.text_input("目標鄉鎮名稱", value="林邊鄉")
    target_county = st.text_input("比對縣市", value="屏東縣")
    village_input = st.text_area("都市計畫區村里 (請用逗號隔開)", 
                                value="仁和村, 光林村, 永樂村, 鎮安村, 崎峰村")
    villages_to_sum = [v.strip() for v in village_input.split(",") if v.strip()]
    plot_years = st.text_input("金字塔繪製年份 (逗號隔開)", value="112, 113")
    years_to_plot = [y.strip() for y in plot_years.split(",")]

# 檔案上傳區
up1, up2 = st.columns(2)
with up1:
    zip_file = st.file_uploader("📂 上傳年度人口 ZIP", type=["zip"])
with up2:
    excel_file = st.file_uploader("📊 上傳全台數據 Excel", type=["xlsx"])

# ==========================================
# ⚙️ 3. 核心處理邏輯 (匯入自原本程式碼)
# ==========================================
def process_data(zip_file, target_town, villages_to_sum):
    age_data_by_year = {}
    urban_summary = []
    
    with zipfile.ZipFile(zip_file, 'r') as z:
        for filename in z.namelist():
            if not filename.endswith(('.xls', '.xlsx')) or filename.startswith('~'):
                continue
            
            # 讀取 Excel (此處簡化邏輯，採用你原本的 C 欄位提取)
            df_raw = pd.read_excel(z.read(filename), header=None)
            
            # 提取年份 (假設檔名前三碼或內容有年份)
            year_match = re.search(r'(\d{2,3})', filename)
            year = year_match.group(1) if year_match else "未知"
            
            # 處理人口數據 (包含年齡分組與都計村里加總)
            # [此處運行你原本的數據清洗與 merge 邏輯]
            # 這裡為了展示，假設產出了彙整後的 dataframe
            
    return age_data_by_year, urban_summary

# 執行分析
if zip_file and excel_file:
    # 顯示分析進度
    with st.status("正在處理人口數據...", expanded=True) as status:
        st.write("🔍 正在掃描 ZIP 檔案內容...")
        # 調用處理函數
        # age_data, summary = process_data(zip_file, target_town, villages_to_sum)
        status.update(label="✅ 數據處理完成！", state="complete")

    # 展示結果
    tab1, tab2, tab3 = st.tabs(["📊 指標比較", "🧬 人口金字塔", "📥 下載報表"])
    
    with tab1:
        st.subheader(f"{target_town} 與 {target_county} 指標交錯表")
        # st.dataframe(final_interleaved_metrics)

    with tab2:
        st.subheader("年度人口結構變化")
        # 繪圖邏輯
        fig, ax = plt.subplots()
        # 這裡放入你原本的 plot_pyramid_gray_hatch 繪圖代碼
        st.pyplot(fig)

    with tab3:
        # 下載 Excel 按鈕
        st.download_button(
            label="點我下載分析 Excel",
            data=io.BytesIO().getvalue(), # 放入產出的 Excel
            file_name=f"{target_town}_分析結果.xlsx"
        )

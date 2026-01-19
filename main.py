import streamlit as st
import pandas as pd
from modules.db import init_db, get_all_tickers, save_company_meta, get_financial_records, get_company_meta
from modules.data_entry import render_entry_tab
from modules.charts import render_charts_tab
from modules.valuation_PE import render_valuation_PE_tab
from modules.valuation_DCF import render_valuation_DCF_tab
from modules.wacc import render_wacc_module

st.set_page_config(page_title="Valuation Pro (SQLite)", layout="wide")
st.title("📊 企业估值系统 (SQLite Integrated)")

# 初始化数据库
init_db()

# --- 侧边栏 ---
st.sidebar.header("🏢 公司管理")

# 1. 新建公司
with st.sidebar.form("add_company"):
    new_ticker = st.text_input("Ticker (e.g. AAPL)").upper()
    new_name = st.text_input("公司名称 (e.g. Apple)")
    new_unit = st.selectbox("单位", ["Billion", "Million"])
    if st.form_submit_button("添加/更新公司"):
        if new_ticker:
            save_company_meta(new_ticker, new_name, new_unit)
            st.success(f"已添加 {new_ticker}")
            st.rerun()

# 2. 选择公司
tickers = get_all_tickers()
if not tickers:
    st.info("请先添加公司")
    st.stop()

selected_company = st.sidebar.selectbox("选择公司", tickers)
meta = get_company_meta(selected_company)
current_unit = meta.get('unit', 'Billion')

st.sidebar.markdown(f"**当前单位**: {current_unit}")

# Proxy 设置
proxy = st.sidebar.text_input("Proxy URL", value="http://127.0.0.1:10808", key="proxy_url")

# 读取财务数据
raw_records = get_financial_records(selected_company)
df_raw = pd.DataFrame(raw_records)

# --- 主界面 ---
tab1, tab2, tab3 = st.tabs(["📝 数据录入", "📈 趋势分析", "🧮 估值模型"])

with tab1:
    render_entry_tab(selected_company, current_unit)

with tab2:
    render_charts_tab(df_raw, current_unit)

with tab3:
    # PE 和 DCF 模块需要 calculator 处理后的数据，我们在模块内部调用 process_financial_data
    # 所以直接传 df_raw 即可
    
    val_tab1, val_tab2 = st.tabs(["📉 PE 估值", "🚀 DCF 估值"])
    
    with val_tab1:
        render_valuation_PE_tab(df_raw, current_unit)
        
    with val_tab2:
        wacc, rf = render_wacc_module(df_raw)
        render_valuation_DCF_tab(df_raw, wacc, rf, current_unit)
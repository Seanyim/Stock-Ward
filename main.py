import streamlit as st
import pandas as pd
from modules.db import init_db, get_all_companies, get_company_records, save_company_metadata
from modules.data_entry import render_entry_tab
from modules.charts import render_charts_tab
from modules.valuation_PE import render_valuation_PE_tab
from modules.valuation_DCF import render_valuation_DCF_tab # [修复] 引入 DCF
from modules.data_fetcher import get_fetcher
from modules.data_processor import DataProcessor

# 初始化
init_db()
st.set_page_config(page_title="Valuation Pro", layout="wide")
st.title("📊 企业财务分析与估值软件 (DB Integrated)")

# --- Sidebar ---
st.sidebar.header("🏢 公司管理")
companies_data = get_all_companies()

# 添加公司
with st.sidebar.form("add_company_form"):
    new_ticker = st.text_input("添加 Ticker (如 MSFT)").upper()
    if st.form_submit_button("添加"):
        if new_ticker:
            save_company_metadata(new_ticker, {}, "Billion")
            st.success(f"已添加 {new_ticker}")
            st.rerun()

# 自动获取
st.sidebar.markdown("---")
st.sidebar.header("☁️ 数据同步")
proxy = st.sidebar.text_input("Proxy", key="proxy_input")
if proxy: st.session_state['proxy_url'] = proxy

fetch_ticker = st.sidebar.text_input("Fetch Ticker", "NVDA").upper()
if st.sidebar.button("🚀 Fetch Data", key="btn_fetch"):
    fetcher = get_fetcher()
    with st.spinner("Fetching..."):
        raw_data, err = fetcher.fetch_all(fetch_ticker)
        if err:
            st.error(err)
        else:
            cnt = DataProcessor.process_and_save(raw_data)
            st.success(f"更新成功！包含 {len(cnt)} 条记录")
            st.rerun()

# 选择公司
company_list = list(companies_data.keys())
if not company_list:
    st.info("请添加公司")
    st.stop()

selected_company = st.sidebar.selectbox("选择分析标的", company_list)
current_unit = companies_data[selected_company]['meta'].get('unit', 'Billion')

# --- 主界面 ---
records = get_company_records(selected_company)
df = pd.DataFrame(records)

# [修复] 增加 DCF 选项卡
tab1, tab2, tab3, tab4 = st.tabs([
    "📂 数据概览 (Entry)", 
    "📈 财务分析 (Charts)", 
    "⚖️ PE/PEG 估值", 
    "💎 DCF 估值"
])

with tab1:
    render_entry_tab(selected_company, current_unit)

with tab2:
    if not df.empty:
        # 此时 df 中的 H1/Q9 已由 DataProcessor 生成
        # Calculator 能够正确计算出 single quarter diff
        render_charts_tab(df, current_unit)
    else:
        st.warning("暂无数据")

with tab3:
    if not df.empty:
        render_valuation_PE_tab(df, current_unit)
    else:
        st.warning("暂无数据")

# ... (前文代码不变)

with tab4:
    if not df.empty:
        st.subheader("DCF 估值参数设置")
        
        # [修复] 增加 WACC 和 Rf 的输入交互
        # 因为 valuation_DCF.py 需要这两个参数才能运行
        col_dcf_1, col_dcf_2 = st.columns(2)
        with col_dcf_1:
            wacc_input = st.number_input("WACC (加权平均资本成本) %", value=10.0, step=0.1, key="dcf_wacc_input") / 100
        with col_dcf_2:
            rf_input = st.number_input("Rf (无风险利率) %", value=3.0, step=0.1, key="dcf_rf_input") / 100
            
        st.markdown("---")
        
        # [修复] 传递所有 4 个必要参数: df, wacc, rf, unit_label
        render_valuation_DCF_tab(df, wacc_input, rf_input, current_unit)
    else:
        st.warning("暂无数据")
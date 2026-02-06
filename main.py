import streamlit as st
import pandas as pd
from modules.core.db import init_db, get_all_tickers, save_company_meta, get_financial_records, get_company_meta
from modules.ui.data_entry import render_entry_tab
from modules.ui.charts import render_charts_tab
from modules.valuation.valuation_PE import render_valuation_PE_tab
from modules.valuation.valuation_DCF import render_valuation_DCF_tab
from modules.valuation.valuation_analyst import render_analyst_tab
from modules.valuation.valuation_advanced import render_advanced_valuation_tab
from modules.core.wacc import render_wacc_module

st.set_page_config(page_title="Valuation Pro v2.0", layout="wide")
st.title("📊 企业估值系统 v2.0")

# 初始化数据库
init_db()

# --- 侧边栏 ---
st.sidebar.header("🏢 公司管理")

# 1. 新建公司 (v2.0 - 添加地区选择)
with st.sidebar.form("add_company"):
    new_ticker = st.text_input("Ticker (e.g. AAPL)").upper()
    new_name = st.text_input("公司名称 (e.g. Apple)")
    new_region = st.selectbox(
        "地区/市场", 
        ["US", "CN", "HK", "JP", "TW"],
        format_func=lambda x: {
            "US": "🇺🇸 美国",
            "CN": "🇨🇳 中国大陆",
            "HK": "🇭🇰 香港",
            "JP": "🇯🇵 日本",
            "TW": "🇹🇼 台湾"
        }.get(x, x)
    )
    new_unit = st.selectbox("单位", ["Billion", "Million"])
    if st.form_submit_button("添加/更新公司"):
        if new_ticker:
            save_company_meta(new_ticker, new_name, new_unit, new_region)
            st.success(f"已添加 {new_ticker} ({new_region})")
            st.rerun()

# 2. 选择公司
tickers = get_all_tickers()
if not tickers:
    st.info("请先添加公司")
    st.stop()

selected_company = st.sidebar.selectbox("选择公司", tickers)
meta = get_company_meta(selected_company)
current_unit = meta.get('unit', 'Billion')
current_region = meta.get('region', 'US')

# 显示公司信息
region_flags = {
    "US": "🇺🇸", "CN": "🇨🇳", "HK": "🇭🇰", "JP": "🇯🇵", "TW": "🇹🇼"
}
st.sidebar.markdown(f"**当前单位**: {current_unit} | **地区**: {region_flags.get(current_region, '')} {current_region}")

st.sidebar.markdown("---")

# 3. API 配置区域
st.sidebar.subheader("⚙️ API 配置")

# Proxy 设置
proxy = st.sidebar.text_input("Proxy URL", value="http://127.0.0.1:10808", key="proxy_url")

st.sidebar.caption("💡 Proxy 用于 yfinance 数据获取")

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
    # WACC 模块（在顶部，供所有子 Tab 使用）
    wacc, rf = render_wacc_module(df_raw)
    
    st.divider()
    
    # 估值模型子 Tab
    val_tab1, val_tab2, val_tab3, val_tab4 = st.tabs([
        "📉 PE 估值", 
        "🚀 DCF 估值",
        "🔬 高级模型",
        "📊 分析师预测"
    ])
    
    with val_tab1:
        render_valuation_PE_tab(df_raw, current_unit)
        
    with val_tab2:
        render_valuation_DCF_tab(df_raw, wacc, rf, current_unit)
    
    with val_tab3:
        render_advanced_valuation_tab(df_raw, current_unit, wacc, rf)
    
    with val_tab4:
        render_analyst_tab(selected_company, df_raw)


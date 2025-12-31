# main.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_manager import load_data, save_data
from modules.data_entry import render_entry_tab
from modules.charts import render_charts_tab
from modules.valuation_PE import render_valuation_PE_tab
from modules.valuation_DCF import render_valuation_DCF_tab
from modules.wacc import render_wacc_module


st.set_page_config(page_title="公司估值工具", layout="wide")
st.title("📊 企业财务分析与估值软件 (Pro Ver 1.15)")

# --- 侧边栏逻辑 ---
st.sidebar.header("🏢 公司管理")
data_store = load_data()

# 1. 新建公司 (增加了单位选择)
with st.sidebar.form("add_company_form"):
    new_name = st.text_input("新建公司名称 (例如: Apple)")
    # 让用户选择该公司的记账单位
    selected_unit = st.selectbox("金额单位", ["Billion (十亿)", "Million (百万)"]) 
    submitted = st.form_submit_button("添加公司")

    if submitted and new_name:
        if new_name not in data_store:
            # 【重要】新的数据结构：包含元数据(meta)和记录(records)
            data_store[new_name] = {
                "meta": {"unit": selected_unit},
                "records": []
            }
            save_data(data_store)
            st.success(f"已添加 {new_name}")
            st.rerun()
        else:
            st.warning("公司已存在")

# 2. 选择公司
company_list = list(data_store.keys())
if not company_list:
    st.info("请在左侧添加公司。")
    st.stop()

selected_company = st.sidebar.selectbox("选择公司", company_list)

# 【重要】读取数据的逻辑变了
company_obj = data_store[selected_company]

# 兼容性处理：防止读取旧JSON报错（如果是旧格式，默认为Billion）
if isinstance(company_obj, list):
    st.error("检测到旧版数据格式，请删除 json 文件重置，或手动迁移数据。")
    st.stop()

company_records = company_obj.get("records", [])
company_meta = company_obj.get("meta", {"unit": "Billion"})
current_unit = company_meta.get("unit", "Billion")

# 在侧边栏显示当前单位
st.sidebar.markdown(f"**当前单位:** `{current_unit}`")

# 定义周期排序映射 (用于数据排序)
PERIOD_ORDER = {"Q1": 1, "H1": 2, "Q9": 3, "FY": 4}

# 预处理数据 #使用累计季报方式
if company_records:
    df = pd.DataFrame(company_records)
    # 添加辅助列用于排序
    df['Period_Order'] = df['Period'].map(PERIOD_ORDER)
    # 按 年份 + 周期 排序
    df = df.sort_values(by=['Year', 'Period_Order'])
else:
    df = pd.DataFrame()

# --- 主界面逻辑 ---
tab1, tab2, tab3 = st.tabs(["📝 数据录入", "📈 PE&PEG", "🧮 估值计算"])

with tab1:
    # 传入 records 和 current_unit
    render_entry_tab(selected_company, data_store, current_unit)
    render_charts_tab(df, current_unit)


with tab2:
    render_valuation_PE_tab(df, current_unit)
with tab3:
    wacc_value, rf_value = render_wacc_module(df)
    render_valuation_DCF_tab(df, wacc_value, rf_value, current_unit)
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from modules.config import FINANCIAL_METRICS
from modules.db import get_financial_records, save_financial_record, save_company_meta, get_company_meta, get_market_history
from modules.data_fetcher import get_fetcher

def render_entry_tab(selected_company, unit_label):
    st.subheader(f"📝 {selected_company} - 财务数据录入 (SQLite 版)")
    
    # --- 1. 市场数据管理 (自动同步 & 可视化) ---
    with st.expander("☁️ 市场数据管理 (Market Data)", expanded=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info("包含: 每日收盘价, 市值, PE TTM (需结合财报), EPS TTM")
        with c2:
            if st.button("🚀 同步/更新市场数据"):
                with st.spinner("Syncing..."):
                    fetcher = get_fetcher()
                    res = fetcher.sync_market_data(selected_company)
                    if "Error" in res["msg"]:
                        st.error(res["msg"])
                    else:
                        st.success(f"同步成功! {res['msg']}")
                        st.rerun()

        # 展示已录入的市场数据详情
        df_market = get_market_history(selected_company)
        if not df_market.empty:
            st.markdown("#### 📊 已录入市场数据概览")
            latest = df_market.iloc[-1]
            earliest = df_market.iloc[0]
            
            # 数据统计
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("数据条数", f"{len(df_market)}")
            
            # Safe date formatting
            try:
                if not pd.api.types.is_datetime64_any_dtype(df_market['date']):
                    df_market['date'] = pd.to_datetime(df_market['date'])
                earliest_date = earliest['date'].strftime('%Y-%m')
                latest_date = latest['date'].strftime('%Y-%m')
                m2.metric("时间跨度", f"{earliest_date} ~ {latest_date}")
            except:
                m2.metric("时间跨度", "N/A")
            
            m3.metric("最新股价", f"{latest['close']:.2f}")
            
            # Safe PE formatting
            pe_value = latest.get('pe_ttm', None)
            if pe_value is not None and not pd.isna(pe_value):
                m4.metric("最新 PE (TTM)", f"{pe_value:.2f}")
            else:
                m4.metric("最新 PE (TTM)", "N/A")
            
            # 图表化展示
            tab_chart1, tab_chart2, tab_chart3 = st.tabs(["📉 股价历史", "📊 PE Band / TTM", "📈 市值趋势"])
            
            with tab_chart1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_market['date'], y=df_market['close'], name='Close'))
                fig.update_layout(title="历史股价 (Close)", height=300, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)
                
            with tab_chart2:
                # 只有当 PE 数据存在时才展示
                df_pe = df_market.dropna(subset=['pe_ttm'])
                if not df_pe.empty:
                    fig_pe = go.Figure()
                    fig_pe.add_trace(go.Scatter(x=df_pe['date'], y=df_pe['pe_ttm'], name='PE TTM', line=dict(color='orange')))
                    fig_pe.update_layout(title="PE Ratio (TTM) 历史走势", height=300, margin=dict(l=0,r=0,t=30,b=0))
                    st.plotly_chart(fig_pe, use_container_width=True)
                else:
                    st.caption("暂无 PE 数据 (需先录入财报以计算 EPS)")
            
            with tab_chart3:
                 if 'market_cap' in df_market.columns and df_market['market_cap'].notna().any():
                    fig_mc = go.Figure()
                    fig_mc.add_trace(go.Scatter(x=df_market['date'], y=df_market['market_cap']/1e9, name='Market Cap (B)'))
                    fig_mc.update_layout(title="市值历史 (Billion)", height=300, margin=dict(l=0,r=0,t=30,b=0))
                    st.plotly_chart(fig_mc, use_container_width=True)
        else:
            st.warning("暂无市场数据，请点击右上角‘同步’按钮获取 (需科学上网)")

    st.markdown("---")

    # --- 2. 财务数据录入 (Input Grouping) ---
    st.markdown("#### ➕ 录入/编辑 财务报告")
    st.caption("系统将根据以下规则自动计算单季度数据：Q2=H1-Q1, Q3=Q9-H1, Q4=FY-Q9")
    
    # 基础选择
    c_base1, c_base2, c_base3 = st.columns(3)
    with c_base1:
        year_input = st.number_input("财年 (Year)", 2000, 2030, 2025)
    with c_base2:
        period_input = st.selectbox("累计周期", ["Q1", "H1", "Q9", "FY"])
    with c_base3:
        report_date_input = st.date_input("财报披露日", value=date.today())

    # 自动检测是否已有数据
    existing_records = get_financial_records(selected_company)
    existing_data = {}
    
    # 查找匹配记录
    for r in existing_records:
        if r['year'] == year_input and r['period'] == period_input:
            existing_data = r
            break
            
    if existing_data:
        st.info(f"💡 检测到 {year_input} {period_input} 已有数据，已自动回填。")

    # 动态表单 (按 Category 分组)
    with st.form("financial_form"):
        # 1. Group metrics by category
        grouped_metrics = {}
        for m in FINANCIAL_METRICS:
            cat = m.get('category', 'Other')
            if cat not in grouped_metrics:
                grouped_metrics[cat] = []
            grouped_metrics[cat].append(m)
        
        # 2. Render Expanders
        input_values = {}
        
        # Define category order (optional)
        cat_order = ["Income Statement", "Balance Sheet", "Cash Flow", "Manual Market Data", "Other"]
        # Sort keys based on order
        sorted_cats = sorted(grouped_metrics.keys(), key=lambda x: cat_order.index(x) if x in cat_order else 99)
        
        for cat in sorted_cats:
            with st.expander(f"📌 {cat}", expanded=(cat=="Income Statement")):
                cols = st.columns(3)
                metrics = grouped_metrics[cat]
                for i, m in enumerate(metrics):
                    default_val = existing_data.get(m['id'], m['default'])
                    # Ensure default_val is not None
                    if default_val is None:
                        default_val = m['default']
                    with cols[i % 3]:
                        val = st.number_input(
                            f"{m['label']}", 
                            value=float(default_val),
                            format=m['format'],
                            key=f"in_{m['id']}"
                        )
                        input_values[m['id']] = val
        
        st.markdown("---")
        submitted = st.form_submit_button("💾 保存/更新数据", use_container_width=True)
        
        if submitted:
            record = {
                "ticker": selected_company,
                "year": int(year_input),
                "period": period_input,
                "report_date": report_date_input.strftime("%Y-%m-%d")
            }
            record.update(input_values)
            
            if save_financial_record(record):
                st.success(f"已保存 {selected_company} {year_input} {period_input}")
                st.rerun()
            else:
                st.error("保存失败")

    # 3. 历史数据表格展示
    if existing_records:
        st.markdown("### 📋 已录入历史数据列表")
        df_show = pd.DataFrame(existing_records)
        # 简单排序展示
        p_map = {"Q1":1, "H1":2, "Q9":3, "FY":4}
        df_show['s'] = df_show['period'].map(p_map)
        df_show = df_show.sort_values(['year', 's'], ascending=[False, False])
        
        # 动态展示所有配置的列
        all_metric_ids = [m['id'] for m in FINANCIAL_METRICS]
        # 过滤掉 df 中不存在的列 (防止报错)
        valid_cols = [c for c in all_metric_ids if c in df_show.columns]
        
        cols_to_show = ['year', 'period', 'report_date'] + valid_cols
        st.dataframe(df_show[cols_to_show], use_container_width=True)
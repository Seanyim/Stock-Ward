import streamlit as st
import pandas as pd
import plotly.express as px
from modules.db import get_company_records, get_price_history, get_report_dates

def format_large_number(num):
    if pd.isna(num): return "-"
    if abs(num) >= 1e9: return f"{num/1e9:.2f}B"
    if abs(num) >= 1e6: return f"{num/1e6:.2f}M"
    return f"{num:,.2f}"

def render_entry_tab(selected_company, unit_label):
    st.subheader(f"{selected_company} - 财务数据")
    
    # ... (图表代码保持不变, 参考上一轮) ...
    # 这里仅展示表格部分的修改

    records = get_company_records(selected_company)
    if records:
        df = pd.DataFrame(records)
        st.markdown("### 📋 详细数据 (Raw)")
        
        # 显示列包含财报年/周期
        core_cols = ["report_date", "fiscal_year", "fiscal_period", "Revenue", "Profit", "EPS", "market_cap", "pe_static"]
        view_cols = [c for c in core_cols if c in df.columns]
        
        # 格式化
        df_show = df[view_cols].copy()
        for c in df_show.columns:
            if pd.api.types.is_numeric_dtype(df_show[c]) and c not in ["fiscal_year"]:
                df_show[c] = df_show[c].apply(lambda x: format_large_number(x) if x!=0 else "-")
                
        st.dataframe(df_show, use_container_width=True)

    # 2. 交互式数据表
    records = get_company_records(selected_company)
    if records:
        df = pd.DataFrame(records)
        st.markdown("### 📋 详细财务报表 (Raw Data)")
        
        c1, c2 = st.columns(2)
        with c1:
            all_years = sorted(df['year'].unique(), reverse=True)
            sel_years = st.multiselect("筛选年份", all_years, default=all_years[:5])
        with c2:
            all_periods = sorted(df['period'].unique())
            sel_periods = st.multiselect("筛选周期", all_periods, default=all_periods)
        
        if sel_years and sel_periods:
            mask = (df['year'].isin(sel_years)) & (df['period'].isin(sel_periods))
            df_view = df[mask].copy()
            
            # 排序
            p_map = {"Q1":1, "Q2":2, "Q3":3, "Q4":4, "H1":5, "Q9":6, "FY":7}
            df_view['p_sort'] = df_view['period'].map(p_map).fillna(0)
            df_view = df_view.sort_values(['year', 'p_sort'], ascending=[False, False]).drop(columns=['p_sort'])
            
            # 显示列选择
            core_cols = ["year", "period", "Revenue", "Profit", "EPS", "pe_ttm", "pe_static", "stock_price"]
            other_cols = [c for c in df_view.columns if c not in core_cols and c not in ['ticker', 'report_date']]
            view_cols = [c for c in core_cols if c in df_view.columns] + other_cols
            
            # [核心优化] 应用大数格式化
            df_display = df_view[view_cols].copy()
            for c in df_display.columns:
                if c in ["year", "period"]: continue
                # 如果是数值型，应用格式化
                if pd.api.types.is_numeric_dtype(df_display[c]):
                    df_display[c] = df_display[c].apply(lambda x: format_large_number(x))
            
            st.dataframe(df_display, use_container_width=True)
        else:
            st.info("请选择筛选条件。")
    else:
        st.warning("暂无数据。")
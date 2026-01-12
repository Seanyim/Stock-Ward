import streamlit as st
import pandas as pd
from modules.calculator import process_financial_data

def render_valuation_PE_tab(df, unit_label):
    st.subheader("📊 PE 估值模型")
    if df.empty: return

    df_cum, df_single = process_financial_data(df)
    
    # 获取最新数据
    df_single_sorted = df_single.sort_values(by=['year', 'Sort_Key'])
    latest = df_single_sorted.iloc[-1]
    
    # --- 1. 股价选择 ---
    col_p1, col_p2 = st.columns(2)
    latest_close = latest.get('stock_price', 0)
    
    with col_p1:
        price_mode = st.radio("股价基准", ["最新收盘价", "手动输入"], horizontal=True)
    with col_p2:
        if price_mode == "最新收盘价":
            price_input = st.number_input("股价", value=float(latest_close), disabled=True)
        else:
            price_input = st.number_input("股价", value=float(latest_close))

    # --- 2. 关键指标 ---
    ttm_eps = latest.get('EPS_TTM', 0)
    g_rate = latest.get('EPS_TTM_YoY', 0.0)
    
    # --- 3. 公司特定税率计算 ---
    # 逻辑：取最近一个完整财年(FY)的 Income_Tax / Pre_Tax_Income (Profit + Tax)
    # 或者 Sum(4Q Tax) / Sum(4Q PreTax)
    ttm_tax = latest.get('Income_Tax_TTM', 0)
    ttm_profit = latest.get('Profit_TTM', 0)
    calc_tax_rate = 0.21 # 默认
    tax_calc_msg = "默认 (21%)"
    
    if ttm_profit > 0 and ttm_tax > 0:
        ttm_pre_tax = ttm_profit + ttm_tax
        calc_tax_rate = ttm_tax / ttm_pre_tax
        tax_calc_msg = f"{calc_tax_rate:.1%} (基于 TTM: 税 {ttm_tax/1e9:.2f}B / 税前 {ttm_pre_tax/1e9:.2f}B)"
        
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        rf_rate = st.number_input("无风险利率 (%)", value=4.0, step=0.1) / 100
    with c2:
        st.metric("有效税率 (公司实际)", tax_calc_msg)

    # --- 4. PE 计算 ---
    col1, col2, col3 = st.columns(3)
    
    # Static PE (基于上个 FY EPS)
    last_fy = df_cum[df_cum['period'] == 'FY'].sort_values('year').iloc[-1] if not df_cum[df_cum['period'] == 'FY'].empty else None
    static_eps = last_fy['EPS'] if last_fy is not None else 0
    with col1:
        pe = price_input / static_eps if static_eps > 0 else 0
        st.metric("Static PE", f"{pe:.2f}x" if pe>0 else "N/A", f"EPS (FY): {static_eps:.2f}")

    # TTM PE
    with col2:
        pe_ttm = price_input / ttm_eps if ttm_eps > 0 else 0
        st.metric("TTM PE", f"{pe_ttm:.2f}x" if pe_ttm>0 else "N/A", f"EPS (TTM): {ttm_eps:.2f}")
            
    # Forward PE (需要 Forward EPS)
    # 这里我们简单估算：Forward EPS = TTM EPS * (1 + Growth)
    # 或者如果有 analyst estimates (需要 fetcher 支持获取 info['forwardEps'])
    # 假设 g_rate 是可持续的
    with col3:
        fwd_eps = ttm_eps * (1 + g_rate)
        pe_fwd = price_input / fwd_eps if fwd_eps > 0 else 0
        st.metric("Forward PE (Est.)", f"{pe_fwd:.2f}x" if pe_fwd>0 else "N/A", f"Growth: {g_rate:.1%}")
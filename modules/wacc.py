import streamlit as st
from modules.calculator import process_financial_data
from modules.db import get_company_meta

def render_wacc_module(df_raw):
    st.markdown("### WACC 计算器")
    
    if df_raw.empty: return 0.1, 0.04
    
    # 1. 自动获取财务数据 (债务, 利息)
    _, df_single = process_financial_data(df_raw)
    latest = df_single.iloc[-1]
    
    interest = latest.get('Interest_Expense_TTM', 0)
    debt = latest.get('Total_Debt', 0) # 存量指标直接取最新
    
    # 2. 自动获取市值 (从数据库快照)
    ticker = df_raw.iloc[0]['ticker']
    meta = get_company_meta(ticker)
    market_cap = meta.get('last_market_cap', 0)
    
    if market_cap == 0:
        market_cap = st.number_input("未获取到市值，请手动输入", value=100.0)
    
    # 3. 计算权重
    total_val = debt + market_cap
    if total_val == 0: total_val = 1
    
    we = market_cap / total_val
    wd = debt / total_val
    
    # 4. 成本估算
    cost_debt = (interest / debt) if debt > 0 else 0.05
    tax_rate = 0.21 # 简化
    
    c1, c2 = st.columns(2)
    rf = c1.number_input("无风险利率 (%)", value=4.0) / 100
    beta = c2.number_input("Beta", value=1.2)
    erp = 0.055
    
    cost_equity = rf + beta * erp
    wacc = we * cost_equity + wd * cost_debt * (1 - tax_rate)
    
    st.info(f"👉 WACC: {wacc:.2%}")
    
    with st.expander("Show Calculation Details (计算过程)"):
        st.markdown(r"""
        $$
        WACC = \frac{E}{V} \times Re + \frac{D}{V} \times Rd \times (1 - T)
        $$
        """)
        
        c_d1, c_d2, c_d3 = st.columns(3)
        with c_d1:
            st.markdown("**1. 资本结构**")
            st.write(f"- 市值 (E): {market_cap/1e9:.2f} B")
            st.write(f"- 债务 (D): {debt/1e9:.2f} B")
            st.write(f"- 总价值 (V): {total_val/1e9:.2f} B")
            st.write(f"- 权益占比 (E/V): {we:.1%}")
            st.write(f"- 债务占比 (D/V): {wd:.1%}")
            
        with c_d2:
            st.markdown("**2. 权益成本 (Re)**")
            st.write(f"- 无风险 (Rf): {rf:.1%}")
            st.write(f"- Beta: {beta}")
            st.write(f"- ERP: {erp:.1%}")
            st.write(f"- Re = {rf:.1%} + {beta} * {erp:.1%} = **{cost_equity:.1%}**")

        with c_d3:
            st.markdown("**3. 债务成本 (Rd)**")
            st.write(f"- 利息支出: {interest/1e9:.2f} B")
            st.write(f"- 债务总额: {debt/1e9:.2f} B")
            st.write(f"- Rd (Int/Debt): {cost_debt:.1%}")
            st.write(f"- 税率 (T): {tax_rate:.0%}")
            st.write(f"- After-Tax Rd: {cost_debt * (1-tax_rate):.1%}")

    return wacc, rf
import streamlit as st
import pandas as pd
from modules.calculator import process_financial_data

def render_wacc_module(df):
    st.markdown("## 🧮 WACC 自动化计算引擎")
    prefix = "wacc"

    # --- 1. 自动从财报获取关键参数 ---
    df_cum, df_single = process_financial_data(df)
    
    # 确保按时间排序并取最新 TTM 数据
    df_single = df_single.sort_values(by=['Year', 'Sort_Key'])
    if not df_single.empty:
        latest = df_single.iloc[-1]
        
        # A. 自动计算有效税率 (Tax Rate) = TTM 所得税 / TTM 税前利润
        st.latex(r"Tax\ Rate = \frac{Income\ Tax_{TTM}}{Pre\ Tax\ Income_{TTM}}")
        tax_expense = latest.get('Income_Tax_TTM', 0)
        pre_tax_income = latest.get('Pre_Tax_Income_TTM', 0)
        
        if pre_tax_income > 0:
            auto_tax_rate = tax_expense / pre_tax_income
            tax_source = f"财报自动计算 ({tax_expense:.2f}/{pre_tax_income:.2f})"
        else:
            auto_tax_rate = 0.21 # 默认 21%
            tax_source = "默认值 (数据缺失)"

        # B. 自动计算资本结构 (Capital Structure)
        # 注意：债务和市值通常是存量概念，我们取单季度数据的最新值（非累计）
        # 假设用户在录入 Q4/FY 时录入了期末债务和市值
        total_debt = latest.get('Total_Debt_Single', 0) 
        market_cap = latest.get('Market_Cap_Single', 0)
        
        total_capital = total_debt + market_cap
        if total_capital > 0:
            auto_equity_ratio = market_cap / total_capital
            struct_source = f"财报自动计算 (市值:{market_cap:.1f} / 债务:{total_debt:.1f})"
        else:
            auto_equity_ratio = 0.85 # 默认 85%
            struct_source = "默认值 (数据缺失)"
    else:
        auto_tax_rate = 0.21
        auto_equity_ratio = 0.85
        tax_source = "无数据"
        struct_source = "无数据"

    # --- 2. 宏观参数 (仍需手动，因随市场变动) ---
    with st.expander("🌍 宏观与市场风险参数 (点击修改)", expanded=True):
        col1, col2 = st.columns(2)
        rf = col1.number_input("无风险利率 Rf (%) - 10Y / 20Y / 30Y 美国国债收益率 同币种长期国债", value=4.0, step=0.1, key=f"{prefix}_rf") / 100
        beta = col2.number_input("Beta 系数 - 5Y monthly 行业β → 去杠杆 → 目标D/E加杠杆", value=1.1, step=0.05, key=f"{prefix}_beta")
        
        col3, col4 = st.columns(2)
        erp = col3.number_input("市场风险溢价 ERP (%) - 股票相对于无风险资产的长期超额收益", value=5.5, step=0.1, key=f"{prefix}_erp") / 100
        credit_spread = col4.number_input("信用利差 (Credit Spread) (%) - 公司债 or ICR映射", value=1.5, step=0.1, key=f"{prefix}_spread") / 100

    # --- 3. 资本结构与税率 (自动填充 + 可修正) ---
    st.markdown("### 🏗 资本结构 & 税率 (自动抓取)")
    
    col_c1, col_c2 = st.columns(2)
    
    # 使用自动计算值作为默认值
    tax_rate = col_c1.number_input(
        "有效税率 (%)", 
        value=float(auto_tax_rate * 100), 
        format="%.2f",
        help=f"来源: {tax_source}",
        key=f"{prefix}_tax"
    ) / 100
    
    equity_weight = col_c2.number_input(
        "权益占比 (E/V) (%)",         
        value=float(auto_equity_ratio * 100), 
        format="%.2f",
        help=f"来源: {struct_source}",
        key=f"{prefix}_equity"
    ) / 100

    # --- 4. WACC 最终计算 ---
    st.markdown("### 🧮 WACC 计算公式")
    st.latex(r"\frac{Equity}{Equity + Debt} \quad Equity = Market\ Cap \qquad \frac{Debt}{Equity + Debt} \quad Debt = Total\ Debt")
    st.latex(r"权益成本\quad Re = Rf + \beta \times ERP \qquad \qquad 债务成本\quad Rd = (Rf + Spread) \times (1 - Tax)")
    # 计算权益成本 re = Rf + Beta * ERP
    cost_of_equity = rf + (beta * erp)

    # 计算税后债务成本 rd = (Rf + Spread) * (1 - Tax)
    pre_tax_cost_of_debt = rf + credit_spread
    cost_of_debt = pre_tax_cost_of_debt * (1 - tax_rate)
    
    debt_weight = 1 - equity_weight
    
    # 计算 WACC
    st.latex(r"WACC = \frac{E}{V} \times Re + \frac{D}{V} \times Rd")
    wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt)

    # --- 5. 结果展示 ---
    st.markdown("### 📊 WACC 结果")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("权益成本 (Re)", f"{cost_of_equity:.2%}")
    c2.metric("税后债务成本 (Rd)", f"{cost_of_debt:.2%}", help=f"税前: {pre_tax_cost_of_debt:.2%}")
    c3.metric("权益/债务比例", f"{equity_weight*100:.0f}/{debt_weight*100:.0f}")
    c4.metric("WACC (折现率)", f"{wacc:.2%}", delta="用于DCF计算")

    return wacc, rf # 返回 Rf 供终端永续增长率参考
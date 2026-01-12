import streamlit as st
import pandas as pd
import numpy as np
from modules.calculator import process_financial_data

def render_valuation_DCF_tab(df, wacc, rf_rate, unit_label):
    st.subheader("💎 现金流折现模型 (DCF)")
    
    if df.empty:
        st.warning("暂无数据")
        return

    # 1. 准备数据
    df_cum, df_single = process_financial_data(df)
    # [修复] 小写 year
    df_fy = df_cum[df_cum['period'] == 'FY'].sort_values(by='year')
    
    if df_fy.empty:
        st.error("DCF 需要年度数据 (FY)")
        return
        
    last_record = df_fy.iloc[-1]
    
    # 2. 自动提取参数
    # [修复] 优先使用 Free_Cash_Flow，如果没有则计算
    base_fcf = last_record.get('Free_Cash_Flow', 0)
    if base_fcf == 0:
        base_fcf = last_record.get('Operating_Cash_Flow', 0) - abs(last_record.get('Capex', 0))
        
    # 获取增长率 (使用 calculator 算好的 YoY)
    # 如果 calculator 没算 FCF YoY，则尝试算 Revenue YoY 作为替代参考
    g_rate_hist = last_record.get('Free_Cash_Flow_YoY', 0.05)
    if pd.isna(g_rate_hist): g_rate_hist = 0.05
    
    # 3. 参数设置
    c1, c2, c3 = st.columns(3)
    with c1:
        initial_fcf = st.number_input("基准 FCF (初始值)", value=float(base_fcf))
    with c2:
        growth_stage1 = st.number_input("第一阶段增长率 (%)", value=float(g_rate_hist*100), step=0.1) / 100
    with c3:
        terminal_growth = st.number_input("永续增长率 (%)", value=2.0, step=0.1, max_value=rf_rate*100) / 100

    c4, c5 = st.columns(2)
    with c4:
        years_stage1 = st.slider("第一阶段时长 (年)", 3, 10, 5)
    with c5:
        # 显示传入的 WACC
        st.metric("WACC (折现率)", f"{wacc*100:.1f}%")

    # 4. 计算过程
    st.markdown("---")
    st.markdown("#### 📅 现金流预测")
    
    future_fcfs = []
    discount_factors = []
    pv_fcfs = []
    
    cols = st.columns(years_stage1)
    
    current_fcf = initial_fcf
    total_pv_stage1 = 0
    
    for i in range(1, years_stage1 + 1):
        current_fcf *= (1 + growth_stage1)
        disc = (1 + wacc) ** i
        pv = current_fcf / disc
        
        future_fcfs.append(current_fcf)
        discount_factors.append(disc)
        pv_fcfs.append(pv)
        total_pv_stage1 += pv
        
        # 简单显示
        with cols[i-1]:
            st.metric(f"Y{i}", f"{current_fcf/1e9:.2f}B", f"PV: {pv/1e9:.2f}B")

    # 5. 终值计算
    terminal_val = future_fcfs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_val / ((1 + wacc) ** years_stage1)
    
    total_value = total_pv_stage1 + pv_terminal
    
    # 6. 结果展示
    # 尝试获取股本数来计算每股价值
    # [修复] 假设 stock_price 和 market_cap 存在
    price = last_record.get('stock_price', 0)
    mcap = last_record.get('market_cap', 0)
    shares = 0
    if price > 0 and mcap > 0:
        shares = mcap / price
    elif price > 0 and last_record.get('EPS', 0) > 0:
        # 估算: Market Cap 也可以通过 Profit * PE 估算，或者直接从 raw data 获取 shares
        # 这里如果没有 shares 数据，就只显示总市值
        pass
        
    st.markdown("#### 💰 估值结果")
    res_c1, res_c2, res_c3 = st.columns(3)
    
    with res_c1:
        st.metric("第一阶段现值", f"{total_pv_stage1/1e9:.2f} B")
    with res_c2:
        st.metric("终值现值", f"{pv_terminal/1e9:.2f} B")
    with res_c3:
        st.metric("企业总价值 (EV)", f"{total_value/1e9:.2f} B", delta_color="normal")
        
    # 如果能算出每股价值
    net_debt = last_record.get('Total_Debt', 0) - last_record.get('Cash', 0)
    equity_value = total_value - net_debt
    
    st.caption(f"减去净债务: {net_debt/1e9:.2f} B -> 股权价值: {equity_value/1e9:.2f} B")
    
    if shares > 0:
        fair_price = equity_value / shares
        upside = (fair_price - price) / price
        st.success(f"### 合理股价: ${fair_price:.2f} (Upside: {upside:.1%})")
    elif price > 0:
        # 粗略反推
        implied_upside = (equity_value - mcap) / mcap if mcap > 0 else 0
        st.info(f"当前市值: {mcap/1e9:.2f} B | 理论股权价值: {equity_value/1e9:.2f} B")
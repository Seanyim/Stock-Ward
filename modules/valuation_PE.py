import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from modules.calculator import process_financial_data
from modules.db import get_market_history

def render_valuation_PE_tab(df_raw, unit_label):
    st.subheader("📊 PE 估值模型 (SQLite 版)")
    
    if df_raw.empty:
        st.warning("暂无财务数据")
        return

    # 1. 获取单季数据 (为了获得 EPS TTM)
    _, df_single = process_financial_data(df_raw)
    
    if df_single.empty or 'EPS_TTM' not in df_single.columns:
        st.warning("无法计算 EPS TTM，请检查是否录入了利润/EPS数据")
        return

    # 2. 结合股价历史
    # 从 df_raw 中提取 ticker (假设是同一家公司)
    ticker = df_raw.iloc[0]['ticker']
    df_price = get_market_history(ticker) # 获取每日股价
    
    if df_price.empty:
        st.info("⚠️ 暂无历史股价数据，请在数据录入页面点击【开始同步】。")
        return

    # 3. 匹配股价与财报 (以财报日期为准，找最近的股价)
    # 确保 report_date 是 datetime
    df_single['report_date'] = pd.to_datetime(df_single['report_date'])
    df_price['date'] = pd.to_datetime(df_price['date'])
    
    # 排序
    df_price = df_price.sort_values('date')
    df_single = df_single.sort_values('report_date')
    
    # 使用 merge_asof 模糊匹配最近的股价
    df_merge = pd.merge_asof(
        df_single, 
        df_price, 
        left_on='report_date', 
        right_on='date', 
        direction='backward'
    )
    
    # 计算历史 PE
    df_merge['PE_TTM'] = df_merge['close'] / df_merge['EPS_TTM']
    
    # 过滤异常值
    valid_pe = df_merge[(df_merge['PE_TTM'] > 0) & (df_merge['PE_TTM'] < 200)]
    
    if valid_pe.empty:
        st.warning("有效 PE 数据不足 (需 EPS>0 且有对应股价)")
        return
        
    # 4. 统计分析
    pe_median = valid_pe['PE_TTM'].median()
    pe_20 = valid_pe['PE_TTM'].quantile(0.2)
    pe_80 = valid_pe['PE_TTM'].quantile(0.8)
    
    latest = valid_pe.iloc[-1]
    current_pe_ttm = latest['PE_TTM']
    current_price = latest['close']
    current_eps_ttm = latest['EPS_TTM']
    
    # --- 增加详细 PE 指标计算 ---
    # 1. 静态 PE (Static PE) = Price / Last FY EPS
    fy_data = df_raw[df_raw['period'] == 'FY']
    if not fy_data.empty:
        fy_data_sorted = fy_data.sort_values('year')
        last_fy_record = fy_data_sorted.iloc[-1]
        eps_static = last_fy_record.get('EPS', None) if isinstance(last_fy_record, pd.Series) else None
    else:
        eps_static = None
    
    pe_static = (current_price / eps_static) if eps_static and eps_static > 0 else None
    
    # 2. 动态 PE & PEG (需输入增长率)
    st.markdown("#### 📐 详细估值指标")
    g_col, _ = st.columns([1, 2])
    growth_input = g_col.number_input("预期盈利增长率 (%) for PEG/Forward", value=15.0, min_value=0.1)
    
    # Forward EPS = EPS_TTM * (1 + g)
    eps_forward = current_eps_ttm * (1 + growth_input/100)
    pe_forward = current_price / eps_forward if eps_forward > 0 else 0
    
    # PEG = PE_TTM / Growth (Rate)
    peg = current_pe_ttm / growth_input
    
    # Display Grid
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("PE (TTM)", f"{current_pe_ttm:.2f}", help="当前股价 / 过去12个月每股收益")
    m2.metric("PE (Static)", f"{pe_static:.2f}" if pe_static else "N/A", help="当前股价 / 上一财年每股收益")
    m3.metric("PE (Forward)", f"{pe_forward:.2f}", help=f"当前股价 / 预期每股收益 (Based on {growth_input}% growth)")
    m4.metric("PEG", f"{peg:.2f}", help="PE (TTM) / 预期增长率 (理想值 < 1)")
    m5.metric("中位 PE (Hist)", f"{pe_median:.2f}", help="历史上 PE 的中位数")

    st.markdown("---")
    
    # 5. 绘制 PE Band
    st.markdown("#### 📉 PE Band 通道图")
    # ... (Keep existing chart code)
    fig = go.Figure()
    
    # 真实股价
    fig.add_trace(go.Scatter(x=valid_pe['report_date'], y=valid_pe['close'], name="股价", line=dict(color='black', width=2)))
    
    # 理论股价线
    fig.add_trace(go.Scatter(x=valid_pe['report_date'], y=valid_pe['EPS_TTM']*pe_80, name=f"高估 ({pe_80:.1f}x)", line=dict(dash='dot', color='red')))
    fig.add_trace(go.Scatter(x=valid_pe['report_date'], y=valid_pe['EPS_TTM']*pe_median, name=f"中枢 ({pe_median:.1f}x)", line=dict(dash='dash', color='blue')))
    fig.add_trace(go.Scatter(x=valid_pe['report_date'], y=valid_pe['EPS_TTM']*pe_20, name=f"低估 ({pe_20:.1f}x)", line=dict(dash='dot', color='green')))
    
    st.plotly_chart(fig, use_container_width=True)
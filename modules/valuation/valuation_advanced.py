# modules/valuation_advanced.py
# 高级估值模型模块
# v1.1 - 修复 None 值处理

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from modules.core.calculator import process_financial_data
from modules.core.db import get_company_meta, get_market_history
from modules.core.risk_free_rate import get_risk_free_rate
from modules.data.industry_data import get_industry_benchmarks

def safe_get(row, key, default=0):
    """安全获取 DataFrame 行的值，处理 None 和 NaN"""
    val = row.get(key, default)
    if val is None:
        return default
    if isinstance(val, float) and np.isnan(val):
        return default
    return val


def render_advanced_valuation_tab(df_raw, unit_label, wacc, rf):
    """渲染高级估值模型 Tab"""
    st.subheader("🔬 高级估值模型")
    
    if df_raw.empty:
        st.warning("请先录入财务数据")
        return
    
    # 获取基础数据
    _, df_single = process_financial_data(df_raw)
    if df_single.empty:
        st.warning("财务数据不足")
        return
    
    latest = df_single.iloc[-1]
    ticker = df_raw.iloc[0]['ticker']
    meta = get_company_meta(ticker)
    
    # 子 Tab
    sub_tabs = st.tabs([
        "🔄 DCF 倒推",
        "📊 PEG 倒推", 
        "💹 EV/EBITDA",
        "📈 增长率透视",
        "🎲 Monte Carlo",
        "📉 ROIC/ROA/ROE"
    ])
    
    with sub_tabs[0]:
        _render_dcf_reverse(df_single, latest, meta, wacc, rf, unit_label)
    
    with sub_tabs[1]:
        _render_peg_analysis(df_single, latest, meta, unit_label)
    
    with sub_tabs[2]:
        _render_ev_ebitda(df_single, latest, meta, unit_label)
    
    with sub_tabs[3]:
        _render_growth_analysis(df_single, unit_label)
    
    with sub_tabs[4]:
        _render_monte_carlo(df_single, latest, meta, wacc, unit_label)
    
    with sub_tabs[5]:
        _render_profitability_analysis(df_single, unit_label)


def _render_dcf_reverse(df_single, latest, meta, wacc, rf, unit_label):
    """DCF 倒推 - 从股价反推隐含增长率"""
    st.markdown("#### 🔄 DCF 倒推分析")
    st.caption("从当前股价反推市场隐含的增长率预期")
    
    # 获取当前市值
    market_cap = meta.get('last_market_cap', 0)
    
    # 尝试多种 FCF 数据源
    fcf = safe_get(latest, 'FreeCashFlow_TTM', 0)
    fcf_source = "FreeCashFlow_TTM"
    
    # 备选：使用 FreeCashFlow（非TTM）
    if fcf == 0:
        fcf = safe_get(latest, 'FreeCashFlow', 0)
        fcf_source = "FreeCashFlow"
    
    # 备选：使用经营现金流 - 资本支出
    if fcf == 0:
        ocf = safe_get(latest, 'OperatingCashFlow_TTM', 0)
        if ocf == 0:
            ocf = safe_get(latest, 'OperatingCashFlow', 0)
        capex = abs(safe_get(latest, 'CapEx', 0))  # CapEx 通常为负
        if ocf > 0:
            fcf = ocf - capex
            fcf_source = "OCF - CapEx"
    
    if market_cap == 0:
        st.warning("⚠️ 需要市值数据，请先同步市场数据")
        return
    
    if fcf == 0:
        st.warning("⚠️ 需要 FCF 数据")
        st.info("💡 尝试的数据源：FreeCashFlow_TTM, FreeCashFlow, OCF-CapEx 均无有效数据")
        # 显示可用的现金流字段
        cf_cols = [c for c in latest.index if 'CashFlow' in c or 'FCF' in c or 'CapEx' in c]
        if cf_cols:
            st.caption(f"可用现金流字段：{cf_cols}")
        return
    
    # === 单位转换 ===
    # 财务数据单位：十亿美元 (B)
    # 市值单位：美元
    # 需要将财务数据转换为美元
    if fcf < 10000:  # 如果 FCF < 10000，说明是以十亿美元为单位
        fcf_dollars = fcf * 1e9
        unit_note = "(数据已从 B 转换为 $)"
    else:
        fcf_dollars = fcf
        unit_note = ""
    
    st.info(f"📊 当前市值: {market_cap/1e9:.2f}B | FCF: {fcf:.2f}B ({fcf_source}) {unit_note} | WACC: {wacc:.2%}")
    
    # 倒推隐含增长率
    perp_rate = st.slider("永续增长率 (%)", 1.0, 4.0, 2.5) / 100
    
    # 使用二分法求解隐含增长率
    def calc_ev(growth_rate):
        """计算给定增长率下的企业价值（使用转换后的美元单位）"""
        curr = fcf_dollars  # 使用转换后的美元单位
        total_pv = 0
        for i in range(1, 6):
            curr = curr * (1 + growth_rate)
            pv = curr / ((1 + wacc) ** i)
            total_pv += pv
        term_val = curr * (1 + perp_rate) / (wacc - perp_rate)
        term_pv = term_val / ((1 + wacc) ** 5)
        return total_pv + term_pv
    
    # 二分法求解
    low, high = -0.2, 0.5
    implied_growth = 0
    
    for _ in range(50):
        mid = (low + high) / 2
        ev = calc_ev(mid)
        if abs(ev - market_cap) < market_cap * 0.001:
            implied_growth = mid
            break
        if ev < market_cap:
            low = mid
        else:
            high = mid
        implied_growth = mid
    
    # 显示结果
    col1, col2, col3 = st.columns(3)
    col1.metric("隐含增长率", f"{implied_growth:.1%}")
    col2.metric("隐含 FCF (Y5)", f"{fcf_dollars * (1 + implied_growth)**5 / 1e9:.2f}B")
    col3.metric("验证 EV", f"{calc_ev(implied_growth) / 1e9:.2f}B")
    
    # === DCF 计算过程展示 ===
    with st.expander("📐 DCF 计算过程"):
        st.markdown("**输入参数：**")
        st.markdown(f"""
| 参数 | 值 |
|------|------|
| 当前 FCF | {fcf:.2f}B |
| WACC | {wacc:.2%} |
| 永续增长率 | {perp_rate:.2%} |
| 隐含增长率 | {implied_growth:.1%} |
        """)
        
        st.markdown("**5年现金流预测：**")
        fcf_projections = []
        curr_fcf = fcf_dollars
        for i in range(1, 6):
            curr_fcf = curr_fcf * (1 + implied_growth)
            pv = curr_fcf / ((1 + wacc) ** i)
            fcf_projections.append({
                "年份": f"Y{i}",
                "FCF (B)": f"{curr_fcf/1e9:.2f}",
                "PV (B)": f"{pv/1e9:.2f}"
            })
        
        st.dataframe(pd.DataFrame(fcf_projections), use_container_width=True)
        
        # 终值计算
        term_val = curr_fcf * (1 + perp_rate) / (wacc - perp_rate)
        term_pv = term_val / ((1 + wacc) ** 5)
        total_pv = sum([fcf_dollars * (1 + implied_growth)**i / ((1 + wacc)**i) for i in range(1, 6)])
        
        st.markdown(f"""
**终值计算：**
- 终值 = FCF₅ × (1 + g) / (WACC - g) = {curr_fcf/1e9:.2f} × (1 + {perp_rate:.2%}) / ({wacc:.2%} - {perp_rate:.2%}) = **{term_val/1e9:.2f}B**
- 终值现值 = {term_val/1e9:.2f} / (1 + {wacc:.2%})⁵ = **{term_pv/1e9:.2f}B**

**企业价值：**
- 5年现金流 PV = {total_pv/1e9:.2f}B
- 终值 PV = {term_pv/1e9:.2f}B
- **总计 EV = {(total_pv + term_pv)/1e9:.2f}B**
        """)
    
    # 敏感性分析
    st.markdown("**敏感性分析**")
    growth_rates = np.arange(-0.1, 0.31, 0.05)
    evs = [calc_ev(g) / 1e9 for g in growth_rates]
    
    fig = go.Figure()
    
    # 1. 估值曲线
    fig.add_trace(go.Scatter(
        x=[f"{g:.0%}" for g in growth_rates],
        y=evs,
        mode='lines+markers',
        name='企业价值 (预测)',
        line=dict(color='#3B82F6', width=3),
        marker=dict(size=6)
    ))
    
    # 2. 当前市值线
    fig.add_hline(y=market_cap/1e9, line_dash="dash", line_color="#EF4444",
                  annotation_text=f"当前市值 {market_cap/1e9:.1f}B", 
                  annotation_position="bottom right")

    # 3. 隐含增长率标记点
    if -0.1 <= implied_growth <= 0.3:
        fig.add_trace(go.Scatter(
            x=[f"{implied_growth:.1%}"], 
            y=[market_cap/1e9],
            mode='markers',
            name=f'隐含增长率 {implied_growth:.1%}',
            marker=dict(color='#EF4444', size=12, symbol='star'),
            text=[f"隐含点: {implied_growth:.1%}"],
            textposition="top center"
        ))

    fig.update_layout(
        title="DCF 倒推: 增长率 vs 企业价值",
        xaxis_title="永续/长期增长率假设",
        yaxis_title="企业价值 (Billion USD)",
        height=350,
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_peg_analysis(df_single, latest, meta, unit_label):
    """PEG 倒推分析"""
    st.markdown("#### 📊 PEG 倒推分析")
    st.caption("基于 PEG=1 反推合理股价")
    
    eps_ttm = safe_get(latest, 'EPS_TTM', 0)
    
    # 从财务数据计算增长率
    cagr = 0.15  # 默认值
    growth_source = "默认"
    
    # 优先使用 EPS_TTM_YoY
    if 'EPS_TTM_YoY' in df_single.columns:
        latest_yoy = safe_get(latest, 'EPS_TTM_YoY', None)
        if latest_yoy is not None and latest_yoy > 0:
            cagr = latest_yoy
            growth_source = "EPS TTM 同比"
    
    # 备选：使用历史 EPS 计算 CAGR
    if growth_source == "默认" and 'EPS_TTM' in df_single.columns and len(df_single) >= 5:
        eps_series = df_single['EPS_TTM'].dropna()
        if len(eps_series) >= 5:
            eps_old = eps_series.iloc[-5]
            eps_new = eps_series.iloc[-1]
            if eps_old > 0 and eps_new > 0:
                cagr = (eps_new / eps_old) ** (1/4) - 1
                growth_source = "EPS 4年 CAGR"
    
    # 获取最新股价
    ticker = df_single.iloc[0].get('ticker', '') if len(df_single) > 0 else ''
    df_price = get_market_history(ticker) if ticker else pd.DataFrame()
    
    current_price = 0
    if not df_price.empty:
        current_price = df_price.iloc[-1].get('close', 0) or 0
    
    # 数据验证
    if eps_ttm <= 0:
        st.warning("⚠️ EPS TTM 数据无效或为负数，无法计算 PEG")
        st.info(f"当前 EPS TTM: {eps_ttm}")
        return
    
    if current_price <= 0:
        st.warning("⚠️ 缺少股价数据，请先同步市场数据")
        return
    
    # 计算 PE 和 PEG
    current_pe = current_price / eps_ttm
    growth_pct = cagr * 100  # 转为百分比
    current_peg = current_pe / growth_pct if growth_pct > 0 else float('inf')
    
    # ===== 费雪利率修正 PEG (Fisher Adjusted PEG) =====
    # 费雪提出：考虑到利率环境，PEG 应调整为 PEG / (无风险利率 * 2)
    # 当利率较高时，相同的 PEG 代表更高的估值
    # Fisher Adjusted PEG = PE / (G + 2*rf) 其中 G 为增长率%，rf 为无风险利率%
    from modules.core.risk_free_rate import get_risk_free_rate
    
    rf_rate = get_risk_free_rate(use_cache=True)
    rf_pct = rf_rate * 100  # 转为百分比
    
    # Fisher 修正公式: 合理 PE = 增长率 + 2*无风险利率
    fisher_denominator = growth_pct + 2 * rf_pct
    fisher_peg = current_pe / fisher_denominator if fisher_denominator > 0 else float('inf')
    
    # ===== 完整计算过程展示 =====
    st.markdown("##### 📐 计算过程")
    
    with st.expander("🔍 查看详细计算", expanded=False):
        st.markdown(f"""
**1. 基础数据:**
- 最新股价: **${current_price:.2f}**
- EPS TTM: **${eps_ttm:.2f}**
- 增长率 (G): **{growth_pct:.2f}%** (来源: {growth_source})
- 无风险利率 (rf): **{rf_pct:.2f}%**

**2. 传统 PEG 计算:**
PE = {current_pe:.2f}, PEG = {current_peg:.2f}

**3. 费雪利率修正 PEG:**
Fisher PEG = PE / (G + 2×rf) = {current_pe:.2f} / ({growth_pct:.2f} + 2×{rf_pct:.2f}) = {fisher_peg:.2f}
        """)
    
    # 用户输入
    st.markdown("##### ⚙️ 参数调整")
    col1, col2 = st.columns(2)
    growth_input = col1.number_input("预期 EPS 增长率 (%)", value=float(growth_pct), step=1.0, min_value=0.1)
    target_peg = col2.number_input("目标 PEG (传统=1, 费雪修正<1)", value=1.0, step=0.1, min_value=0.1)
    
    # 计算合理价格
    fair_pe = target_peg * growth_input
    fair_price = fair_pe * eps_ttm
    upside = (fair_price / current_price - 1) * 100 if current_price > 0 else 0
    
    # 费雪修正合理价格
    fisher_fair_pe = growth_input + 2 * rf_pct
    fisher_fair_price = fisher_fair_pe * eps_ttm
    fisher_upside = (fisher_fair_price / current_price - 1) * 100 if current_price > 0 else 0
    
    # ===== 估值指标展示 =====
    st.markdown("##### 📊 估值指标")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("当前 PE", f"{current_pe:.1f}")
    m2.metric("传统 PEG", f"{current_peg:.2f}" if current_peg < 100 else "∞", 
              help="<1 低估")
    m3.metric("费雪修正 PEG", f"{fisher_peg:.2f}" if fisher_peg < 100 else "∞",
              help="考虑利率后 <1 低估")
    
    m4, m5, m6 = st.columns(3)
    m4.metric("合理股价 (PEG=1)", f"${fair_price:.2f}", f"{upside:+.1f}%")
    m5.metric("费雪合理股价", f"${fisher_fair_price:.2f}", f"{fisher_upside:+.1f}%")
    m6.metric("合理 PE (费雪)", f"{fisher_fair_pe:.1f}")
    
    # 估值判断
    if current_peg < 1:
        st.success("✅ 传统 PEG < 1，根据 Peter Lynch 标准可能被低估")
    elif current_peg > 2:
        st.warning("⚠️ PEG > 2，估值偏高")
    
    if fisher_peg < 1:
        st.success("✅ 费雪修正 PEG < 1，考虑利率环境后仍被低估")

    st.markdown("---")
    st.markdown("#### 📐 PEG 倒推可视化")
    
    # 可视化：增长率 vs 合理 PE (Implied PE)
    
    growth_range = np.arange(5, 50, 1)
    
    # 传统 PEG=1 时的合理 PE = G
    fair_pe_traditional = growth_range * 1.0 
    
    # 费雪 PEG=1 时的合理 PE = G + 2*rf
    fair_pe_fisher = growth_range + 2 * rf_pct
    
    fig = go.Figure()
    
    # 费雪合理 PE 线
    fig.add_trace(go.Scatter(
        x=growth_range, y=fair_pe_fisher, mode='lines', name='Fisher 合理 PE (PEG=1)',
        line=dict(color='green', width=3)
    ))
    
    # 传统合理 PE 线
    fig.add_trace(go.Scatter(
        x=growth_range, y=fair_pe_traditional, mode='lines', name='传统合理 PE (PEG=1)',
        line=dict(color='gray', width=2, dash='dash')
    ))
    
    # 当前 PE 线
    fig.add_hline(y=current_pe, line_dash="dash", line_color="orange", annotation_text=f"当前 PE {current_pe:.1f}")
    
    # 标记当前增长率点
    # 找到当前 PE 在 Fisher 线上对应的增长率 (反推)
    # PE = G_implied + 2*rf  => G_implied = PE - 2*rf
    implied_growth_fisher = current_pe - 2 * rf_pct
    
    if implied_growth_fisher > 0:
        fig.add_trace(go.Scatter(
            x=[implied_growth_fisher], y=[current_pe], mode='markers', 
            name=f"市场隐含增长率 {implied_growth_fisher:.1f}%",
            marker=dict(size=12, color='red', symbol='x')
        ))
    
    fig.update_layout(
        title=f"PEG 倒推：当前股价隐含增长率约 {implied_growth_fisher:.1f}% (Fisher Model)",
        xaxis_title="预期增长率 (%)",
        yaxis_title="合理 PE 倍数",
        height=400,
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    if implied_growth_fisher < growth_pct:
        st.success(f"✅ 市场隐含增长率 ({implied_growth_fisher:.1f}%) < 实际/预期增长率 ({growth_pct:.1f}%)，意味着当前价格未充分计入增长预期 (低估)")
    else:
        st.warning(f"⚠️ 市场隐含增长率 ({implied_growth_fisher:.1f}%) > 实际/预期增长率 ({growth_pct:.1f}%)，意味着当前价格透支了过高的增长预期 (高估)")


def _render_ev_ebitda(df_single, latest, meta, unit_label):
    """EV/EBITDA 分析 (含行业对比)"""
    st.markdown("#### 💹 EV/EBITDA 分析")
    
    # 获取参数
    market_cap = meta.get('last_market_cap', 0)
    debt = safe_get(latest, 'TotalDebt', 0)
    if debt == 0: debt = safe_get(latest, 'LongTermDebt', 0)
    cash = safe_get(latest, 'CashAndEquivalents', 0)
    if cash == 0: cash = safe_get(latest, 'CashEndOfPeriod', 0)
    
    # EBITDA
    ebitda = safe_get(latest, 'EBITDA_TTM', 0)
    if ebitda == 0: ebitda = safe_get(latest, 'OperatingProfit_TTM', 0)
    if ebitda == 0: ebitda = safe_get(latest, 'OperatingProfit', 0)
    if ebitda == 0: 
        gp = safe_get(latest, 'GrossProfit_TTM', 0) or safe_get(latest, 'GrossProfit', 0)
        opex = safe_get(latest, 'OperatingExpenses_TTM', 0) or safe_get(latest, 'OperatingExpenses', 0)
        ebitda = gp - opex
    
    if market_cap == 0 or ebitda == 0:
        st.warning("⚠️ 缺少市值或 EBITDA 数据")
        return
        
    # 计算 EV (Scaling)
    if ebitda < 10000 and ebitda != 0: 
        scale_input = 1e9
    else:
        scale_input = 1.0
        
    ebitda_dollars = ebitda * scale_input
    debt_dollars = debt * scale_input
    cash_dollars = cash * scale_input
    
    ev = market_cap + debt_dollars - cash_dollars
    ev_ebitda = ev / ebitda_dollars if ebitda_dollars > 0 else 0
    
    # 行业对比 (自动 + 手动)
    # 优先使用数据库中存储的真实 Sector
    meta_sector = meta.get('sector', 'Unknown')
    # 如果数据库没有，尝试尝试从 meta 中获取 (兼容旧逻辑)
    if meta_sector == 'Unknown' or not meta_sector:
         meta_sector = 'Technology' # 默认回退
         
    st.info(f"所属行业识别: {meta_sector}")
    
    bench = get_industry_benchmarks(meta_sector)
    industry_median = bench.get('ev_ebitda', 15.0)
    
    col1, col2 = st.columns(2)
    input_sector_median = col1.number_input("行业中位数 (手动调整)", value=float(industry_median))
    
    # 展示
    m1, m2, m3 = st.columns(3)
    m1.metric("EV/EBITDA (公司)", f"{ev_ebitda:.1f}x")
    m2.metric(f"EV/EBITDA (行业)", f"{input_sector_median:.1f}x")
    diff_pct = (ev_ebitda / input_sector_median - 1) * 100
    m3.metric("相对溢价", f"{diff_pct:+.1f}%", delta_color="inverse") # 越低越好，所以inverse
    
    # 可视化对比
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=['EV/EBITDA'], x=[ev_ebitda], orientation='h', name='公司 (Current)', marker_color='blue',
        text=f"{ev_ebitda:.1f}x", textposition='auto'
    ))
    fig.add_trace(go.Bar(
        y=['EV/EBITDA'], x=[input_sector_median], orientation='h', name=f'行业中位 ({meta_sector})', marker_color='gray',
        text=f"{input_sector_median:.1f}x", textposition='auto'
    ))
    fig.update_layout(
        title="公司 EV/EBITDA vs 行业中位数 (越低越好)", 
        height=250, 
        barmode='group',
        xaxis_title="倍数 (x)",
        legend=dict(orientation="h", y=-0.2)
    )
    st.plotly_chart(fig, use_container_width=True)



def _render_growth_analysis(df_single, unit_label):
    """增长率透视 (全方位: 营收/利润/现金流/债务)"""
    st.markdown("#### 📈 增长率透视 (Growth Perspective)")
    
    if len(df_single) < 4:
        st.warning("数据不足，无法计算增长趋势")
        return
        
    metrics = {
        '业务规模': [('TotalRevenue_TTM', '营收'), ('GrossProfit_TTM', '毛利')],
        '盈利能力': [('NetIncome_TTM', '净利'), ('EPS_TTM', 'EPS')],
        '现金流': [('OperatingCashFlow_TTM', 'OCF'), ('FreeCashFlow_TTM', 'FCF')],
        '资产负债': [('TotalAssets', '总资产'), ('TotalDebt', '总债务'), ('TotalEquity', '股东权益')]
    }
    
    # 汇总数据
    rows = []
    analysis_points = []
    
    for category, items in metrics.items():
        for col, name in items:
            if col in df_single.columns:
                s = df_single[col].dropna()
                if len(s) >= 4:
                    val_new = s.iloc[-1]
                    
                    cagr = 0
                    if len(s) >= 5: 
                        val_old_4y = s.iloc[-5] 
                        if val_old_4y != 0 and val_new != 0:
                            # 能够处理负数的简单CAGR逻辑 (取绝对值计算幅度，保留方向符号)
                            cagr = (abs(val_new) / abs(val_old_4y))**(1/4) - 1
                            if val_new < 0 and val_old_4y > 0: cagr = -abs(cagr)
                            elif val_new > 0 and val_old_4y < 0: cagr = abs(cagr)
                            elif val_new < 0 and val_old_4y < 0: 
                                if val_new > val_old_4y: cagr = abs(cagr) # 亏损收窄
                                else: cagr = -abs(cagr) # 亏损扩大
                    
                    # QoQ
                    qoq = 0
                    if len(s) >= 2 and s.iloc[-2] != 0:
                        qoq = (s.iloc[-1] / s.iloc[-2] - 1)
                    
                    # 记录用于分析
                    if category == '业务规模' and name == '营收':
                        analysis_points.append(f"营收 4年复合增速为 {cagr:.1%}")
                    if category == '盈利能力' and name == '净利':
                        analysis_points.append(f"净利润 4年复合增速为 {cagr:.1%}")
                    
                    rows.append({
                        "类别": category,
                        "指标": name,
                        "最新值": f"{val_new/1e9:.2f}B" if abs(val_new)>1e6 else f"{val_new:.2f}",
                        "QoQ": f"{qoq:+.1%}",
                        "CAGR (4Y)": f"{cagr:+.1%}",
                        "_cagr_raw": cagr
                    })
    
    if rows:
        st.dataframe(pd.DataFrame(rows).drop(columns=['_cagr_raw']), use_container_width=True)
        
    # === 自动文本分析 ===
    st.markdown("##### 📝 增长趋势分析")
    if analysis_points:
        summary = "、".join(analysis_points) + "。"
        
        # 查找主要矛盾
        df_rows = pd.DataFrame(rows)
        rev_growth = df_rows[df_rows['指标']=='营收']['_cagr_raw'].values
        prof_growth = df_rows[df_rows['指标']=='净利']['_cagr_raw'].values
        rev_g = rev_growth[0] if len(rev_growth)>0 else 0
        prof_g = prof_growth[0] if len(prof_growth)>0 else 0
        
        if prof_g > rev_g + 0.05:
            summary += " 净利增速显著快于营收，显示**盈利能力提升**或成本控制有效。"
        elif prof_g < rev_g - 0.05:
            summary += " 净利增速落后于营收，可能面临**毛利下滑**或费用增加压力。"
        else:
            summary += " 营收与利润虽然同步增长，经营质量维持稳定。"
            
        st.info(summary)

    # === 可视化: 历史趋势折线图 ===
    st.markdown("##### 📅 核心指标趋势 (5年)")
    
    metric_keys = ['TotalRevenue_TTM', 'NetIncome_TTM', 'FreeCashFlow_TTM']
    labels = ['营收', '净利', 'FCF']
    colors = ['#3B82F6', '#10B981', '#F59E0B']
    
    fig_ts = go.Figure()
    
    has_data = False
    for k, label, color in zip(metric_keys, labels, colors):
        if k in df_single.columns:
            s_plot = df_single.dropna(subset=[k]).tail(20) # 5年 (4*5=20个季度)
            if not s_plot.empty:
                fig_ts.add_trace(go.Scatter(
                    x=s_plot['report_date'], y=s_plot[k], name=label,
                    mode='lines', line=dict(color=color, width=2)
                ))
                has_data = True
    
    if has_data:
        fig_ts.update_layout(title="核心财务指标趋势 (TTM)", height=350, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_ts, use_container_width=True)
        
    # === 增长率对比 (Bar) ===
    df_chart = pd.DataFrame(rows)
    if not df_chart.empty:
        fig = go.Figure()
        df_chart['cagr_val'] = df_chart['_cagr_raw'] * 100
        
        colors_map = {'业务规模': 'blue', '盈利能力': 'green', '现金流': 'orange', '资产负债': 'red'}
        
        for cat in metrics.keys():
            df_sub = df_chart[df_chart['类别'] == cat]
            if not df_sub.empty:
                fig.add_trace(go.Bar(
                    x=df_sub['指标'], y=df_sub['cagr_val'],
                    name=cat, marker_color=colors_map.get(cat, 'gray'),
                    text=[f"{v:.1f}%" for v in df_sub['cagr_val']],
                    textposition='auto'
                ))
                
        fig.update_layout(title="各维度复合增长率对比 (4Y CAGR)", yaxis_title="CAGR (%)", height=300, legend=dict(orientation="h", y=1.2))
        st.plotly_chart(fig, use_container_width=True)




def _render_monte_carlo(df_single, latest, meta, wacc, unit_label):
    """Monte Carlo 模拟"""
    st.markdown("#### 🎲 Monte Carlo 模拟")
    st.caption("使用概率分布模拟估值区间")
    
    fcf = safe_get(latest, 'FreeCashFlow_TTM', 0)
    if fcf == 0:
        fcf = safe_get(latest, 'FreeCashFlow', 0)
    
    if fcf == 0:
        st.warning("需要 FCF 数据")
        return
    
    # 单位转换
    if fcf < 10000:
        fcf_dollars = fcf * 1e9
    else:
        fcf_dollars = fcf
    
    market_cap = meta.get('last_market_cap', 0)
    
    # 自动计算历史增长率均值和标准差
    hist_growth_mean = 0.10
    hist_growth_std = 0.05
    source_msg = "默认值"
    
    if 'FreeCashFlow_TTM_YoY' in df_single.columns:
        growth_series = df_single['FreeCashFlow_TTM_YoY'].dropna()
        # 剔除极端异动值 (超过 +/- 100%)
        growth_series = growth_series[(growth_series > -0.5) & (growth_series < 1.0)]
        if len(growth_series) >= 4:
            hist_growth_mean = growth_series.mean()
            hist_growth_std = growth_series.std()
            source_msg = f"基于历史 {len(growth_series)} 个季度的 FCF 同比数据计算 (Mean={hist_growth_mean:.1%}, Std={hist_growth_std:.1%})"
    
    st.info(f"💡 自动参数推断: {source_msg}")
    
    # 参数设置
    col1, col2, col3 = st.columns(3)
    growth_mean = col1.number_input("增长率均值 (%)", value=float(hist_growth_mean * 100)) / 100
    growth_std = col2.number_input("增长率标准差 (%)", value=float(hist_growth_std * 100)) / 100
    n_sims = col3.number_input("模拟次数", value=1000, step=100)
    
    if st.button("🎲 运行模拟"):
        np.random.seed(42)
        evs = []
        
        for _ in range(int(n_sims)):
            # 随机增长率 (正态分布)
            growth = np.random.normal(growth_mean, growth_std)
            # 限制范围避免极端值破坏模拟结果
            growth = max(-0.3, min(0.6, growth))
            
            # 计算 EV
            curr = fcf_dollars
            total_pv = 0
            for i in range(1, 6):
                curr = curr * (1 + growth)
                pv = curr / ((1 + wacc) ** i)
                total_pv += pv
            
            term_val = curr * 1.025 / (wacc - 0.025)
            term_pv = term_val / ((1 + wacc) ** 5)
            evs.append((total_pv + term_pv) / 1e9)
        
        evs = np.array(evs)
        
        # 显示结果
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("P10 (保守)", f"{np.percentile(evs, 10):.1f}B")
        col2.metric("P50 (中性)", f"{np.percentile(evs, 50):.1f}B")
        col3.metric("P90 (乐观)", f"{np.percentile(evs, 90):.1f}B")
        col4.metric("平均值", f"{np.mean(evs):.1f}B")
        
        # 与当前市值对比
        upside_p50 = (np.percentile(evs, 50) * 1e9 / market_cap - 1) * 100 if market_cap > 0 else 0
        
        # 结论文本分析
        st.markdown("##### 📝 模拟结果分析")
        if upside_p50 > 15:
            st.success(f"📈 **结论**: Monte Carlo 模拟中位数 (P50) 显示潜在上涨空间 {upside_p50:+.1f}%。即使在较保守情境 (P10) 下，估值为 {np.percentile(evs, 10):.1f}B。")
        elif upside_p50 < -15:
            st.error(f"📉 **结论**: 模拟结果显示当前价格可能高估 (溢价 {abs(upside_p50):.1f}%)。建议关注增长率假设的合理性。")
        else:
            st.info(f"⚖️ **结论**: 模拟结果支持当前估值合理性，差异在正常波动范围内 ({upside_p50:+.1f}%)。")
        
        # 分布图
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=evs, nbinsx=50, name='EV 分布概率', 
            marker_color='rgba(100, 149, 237, 0.7)', opacity=0.7
        ))
        
        # 垂直辅助线
        fig.add_vline(x=market_cap/1e9, line_dash="dash", line_color="orange", 
                      annotation_text=f"当前市值 {market_cap/1e9:.1f}B")
        
        fig.add_vline(x=np.percentile(evs, 50), line_dash="solid", line_color="green",
                     annotation_text="P50 (中位)")
                     
        fig.update_layout(
            title=f"企业价值概率分布 (基于 {int(n_sims)} 次随机模拟)", 
            xaxis_title="企业价值 (Billion USD)",
            yaxis_title="频次",
            height=350,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_profitability_analysis(df_single, unit_label):
    """ROIC/ROA/ROE 分析 (含行业对比)"""
    st.markdown("#### 📉 盈利能力透视 (ROIC/ROA/ROE)")
    
    if len(df_single) < 2:
        st.warning("数据不足")
        return
    
    latest = df_single.iloc[-1]
    
    # 行业对比
    ticker = df_single.iloc[0].get('ticker', '')
    meta = get_company_meta(ticker)
    sector = meta.get('sector', 'General')
    st.info(f"所属行业: **{sector}** | Ticker: {ticker}")
    
    bench = get_industry_benchmarks(sector)
    
    # 辅助函数：安全获取数值
    def safe_val(row, key):
        val = row.get(key, 0)
        return val if val is not None and not (isinstance(val, float) and np.isnan(val)) else 0
    
    # 计算指标
    net_income = safe_val(latest, 'NetIncome_TTM')
    total_assets = safe_val(latest, 'TotalAssets')
    total_equity = safe_val(latest, 'TotalEquity')
    total_debt = safe_val(latest, 'TotalDebt')
    invested_capital = total_equity + total_debt
    
    roa = (net_income / total_assets * 100) if total_assets > 0 else 0
    roe = (net_income / total_equity * 100) if total_equity > 0 else 0
    roic = (net_income / invested_capital * 100) if invested_capital > 0 else 0
    
    # 行业基准
    ind_roe = bench.get('roe', 15.0)
    ind_roa = bench.get('roa', 5.0)
    ind_roic = bench.get('roic', 10.0)
    
    # 指标卡片
    c1, c2, c3 = st.columns(3)
    c1.metric("ROE (净资产回报)", f"{roe:.1f}%", f"行业 {ind_roe}%", delta_color="normal")
    c2.metric("ROA (总资产回报)", f"{roa:.1f}%", f"行业 {ind_roa}%", delta_color="normal")
    c3.metric("ROIC (投入资本回报)", f"{roic:.1f}%", f"行业 {ind_roic}%", delta_color="normal")
    
    # 杜邦分析
    revenue = safe_val(latest, 'TotalRevenue_TTM')
    npm = (net_income / revenue * 100) if revenue > 0 else 0
    asset_turnover = revenue / total_assets if total_assets > 0 else 0
    equity_multiplier = total_assets / total_equity if total_equity > 0 else 0
    
    st.info(f"💡 杜邦拆解: ROE {roe:.1f}% ≈ 净利率 {npm:.1f}% × 资产周转率 {asset_turnover:.2f} × 权益乘数 {equity_multiplier:.2f}")
    
    # 可视化: 公司 vs 行业
    metric_names = ['ROE', 'ROA', 'ROIC']
    company_vals = [roe, roa, roic]
    industry_vals = [ind_roe, ind_roa, ind_roic]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=metric_names, y=company_vals, name='公司', marker_color='#3B82F6', text=[f"{v:.1f}%" for v in company_vals], textposition='auto'
    ))
    fig.add_trace(go.Bar(
        x=metric_names, y=industry_vals, name=f'行业 ({sector})', marker_color='#9CA3AF', text=[f"{v:.1f}%" for v in industry_vals], textposition='auto'
    ))
    
    fig.update_layout(
        title="盈利能力对比: 公司 vs 行业",
        yaxis_title="百分比 (%)",
        barmode='group',
        height=300,
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # 历史趋势图
    st.markdown("##### 📅 历史趋势")
    fig2 = go.Figure()
    
    # 添加 ROE 趋势
    if 'NetIncome_TTM' in df_single.columns and 'TotalEquity' in df_single.columns:
        df_plot = df_single.dropna(subset=['NetIncome_TTM', 'TotalEquity']).tail(12)
        if not df_plot.empty:
            roe_series = df_plot['NetIncome_TTM'] / df_plot['TotalEquity'] * 100
            fig2.add_trace(go.Scatter(
                x=df_plot['report_date'], y=roe_series, mode='lines+markers', name='ROE 历史',
                line=dict(width=2)
            ))
            
    # 添加 ROIC 趋势
    if 'NetIncome_TTM' in df_single.columns and 'TotalDebt' in df_single.columns:
        df_plot_roic = df_single.dropna(subset=['NetIncome_TTM', 'TotalEquity', 'TotalDebt']).tail(12)
        if not df_plot_roic.empty:
            capital = df_plot_roic['TotalEquity'] + df_plot_roic['TotalDebt']
            roic_series = df_plot_roic['NetIncome_TTM'] / capital * 100
            fig2.add_trace(go.Scatter(
                x=df_plot_roic['report_date'], y=roic_series, mode='lines+markers', name='ROIC 历史',
                line=dict(dash='dash', width=2)
            ))
            
    fig2.update_layout(title="盈利能力历史趋势 (ROE vs ROIC)", yaxis_title="百分比 (%)", height=300, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig2, use_container_width=True)


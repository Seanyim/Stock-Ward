import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from modules.core.calculator import process_financial_data

def render_valuation_DCF_tab(df_raw, wacc, rf, unit_label):
    st.subheader("🚀 DCF 现金流折现 (SQLite 版)")
    
    if df_raw.empty: return
    
    # 1. 自动计算基准数据
    _, df_single = process_financial_data(df_raw)
    
    if df_single.empty:
        st.warning("缺少财务数据")
        return
        
    latest = df_single.iloc[-1]
    
    # 尝试多种 FCF 数据源
    base_fcf = latest.get('FreeCashFlow_TTM', 0)
    if base_fcf == 0:
        base_fcf = latest.get('FreeCashFlow', 0)
    
    # 自定义处理: OCF - CapEx
    if base_fcf == 0:
        ocf = latest.get('OperatingCashFlow_TTM', 0)
        if ocf == 0: ocf = latest.get('OperatingCashFlow', 0)
        capex = abs(latest.get('CapEx', 0))
        if ocf > 0:
            base_fcf = ocf - capex
            
    if base_fcf == 0:
        st.warning("缺少 FCF 数据，请录入自由现金流 (FreeCashFlow / OperatingCashFlow)")
        st.info("提示：系统会自动计算 OCF - CapEx 作为备选 FCF")
        return
    
    # 2. 自动计算历史增长率 (CAGR & YoY)
    hist_growth_defaults = 10.0
    growth_source_msg = "默认值"
    
    # 尝试计算 FCF 历史增长率 (5年窗口)
    try:
        # 获取年度 FCF 数据
        df_fy = df_raw[df_raw['period'] == 'FY'].sort_values('year')
        if len(df_fy) >= 5:
            # 使用最近5年数据计算 CAGR
            series_fcf = []
            for _, row in df_fy.tail(5).iterrows():
                val = row.get('FreeCashFlow') or (row.get('OperatingCashFlow', 0) - abs(row.get('CapEx', 0)))
                series_fcf.append(val)
            
            if len(series_fcf) >= 2 and series_fcf[0] > 0 and series_fcf[-1] > 0:
                # CAGR 公式: (End/Start)^(1/n) - 1
                years = len(series_fcf) - 1
                cagr = (series_fcf[-1] / series_fcf[0]) ** (1/years) - 1
                cagr_pct = cagr * 100
                
                # 限制在合理范围
                if -20 < cagr_pct < 50:
                    hist_growth_defaults = cagr_pct
                    growth_source_msg = f"基于过去5年 FY FCF CAGR ({cagr_pct:.1f}%)"
    except Exception as e:
        print(f"Growth Calc Error: {e}")

    # 3. 参数输入
    st.markdown("#### ⚙️ DCF 参数设置")
    c1, c2, c3 = st.columns(3)
    
    # 强制优先使用 TTM 数据作为基准，若无则使用由于估值模型通常基于当前时点
    init_fcf = c1.number_input("基准 FCF (TTM/FY)", value=float(base_fcf), help="默认取 TTM 数据，若无则取最新 FY")
    
    growth_rate = c2.number_input(
        "前5年增长率 (%)", 
        value=float(hist_growth_defaults), 
        step=0.5,
        help=f"建议参考历史增速。来源: {growth_source_msg}"
    ) / 100
    
    # 永续增长率通常不应超过无风险利率或 GDP 增速
    # 默认给一个相对保守的值，例如 min(2.0, Rf/2)
    # 用户反馈: 0.04% 过小。说明之前可能是 0.04 (4%) 的理解偏差。
    # 这里我们显示百分比输入，代码除以 100。
    # 修正逻辑：考虑无风险利率，通常永续增长率 <= Rf
    perp_cap = float(rf) if rf else 3.0
    perp_default = min(2.0, perp_cap * 0.8) # 默认取 Rf 的 80% 或 2.0%
    
    perp_rate = c3.number_input(
        "永续增长率 (%)", 
        value=float(perp_default),
        min_value=0.0,
        max_value=perp_cap,
        step=0.1,
        help=f"修正: 不应超过无风险利率 ({rf}%)，通常为 2%-3%"
    ) / 100
    
    if wacc <= perp_rate:
        st.error("❌ WACC 必须大于永续增长率 (数学上无法收敛)")
        return
        
    # 4. 计算与展示
    # 详细过程展开
    with st.expander("📝 查看详细计算过程 (5 Year Projection)", expanded=True):
        flows = []
        curr = init_fcf
        total_pv = 0
        
        # 表头
        cols = st.columns(6)
        cols[0].markdown("**年份**")
        for i in range(1, 6):
            cols[i].markdown(f"**Y{i}**")
            
        # 现金流行
        row_cf = st.columns(6)
        row_cf[0].write("FCF 预测")
        
        # 现值行
        row_pv = st.columns(6)
        row_pv[0].write("折现值 (PV)")
        
        for i in range(1, 6):
            curr = curr * (1 + growth_rate)
            pv = curr / ((1 + wacc) ** i)
            total_pv += pv
            
            flows.append(curr)
            row_cf[i].write(f"{curr:,.2f}")
            row_pv[i].write(f"{pv:,.2f}")
            
    # 终值
    term_val = flows[-1] * (1 + perp_rate) / (wacc - perp_rate)
    term_pv = term_val / ((1 + wacc) ** 5)
    
    enterprise_value = total_pv + term_pv
    
    st.divider()
    
    # 结果展示
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("企业价值 (EV)", f"{enterprise_value:,.2f} {unit_label}")
    rc2.metric("阶段1 现值 (1-5Y)", f"{total_pv:,.2f}", f"占比 {total_pv/enterprise_value:.1%}")
    rc3.metric("终值 现值 (Terminal)", f"{term_pv:,.2f}", f"占比 {term_pv/enterprise_value:.1%}")
    
    st.info(f"💡 永续增长率修正: 已参考无风险利率 {rf}% 进行限制。")
    
    # --- 5. 可视化展示 (Wiki style) ---
    st.markdown("#### 📊 估值构成可视化")
    
    # A. 估值构成 瀑布图/堆叠图
    fig_dcf = go.Figure()
    
    # x 轴
    x_labels = [f"Y{i} ({y:,.0f})" for i, y in enumerate(flows, 1)] + ["Terminal (终值)"]
    y_values = [curr / ((1 + wacc) ** i) for i, curr in enumerate(flows, 1)] + [term_pv]
    
    # 瀑布图展示各部分贡献
    fig_dcf.add_trace(go.Bar(
        x=x_labels, 
        y=y_values,
        text=[f"{v:,.0f}" for v in y_values],
        textposition='auto',
        marker_color=['#60A5FA']*5 + ['#34D399'], # 前5年蓝色，终值绿色
        name="现值贡献"
    ))
    
    fig_dcf.update_layout(
        title=f"DCF 估值构成 (企业价值: {enterprise_value:,.0f})",
        yaxis_title="现值 (PV)",
        showlegend=False,
        height=400
    )
    st.plotly_chart(fig_dcf, use_container_width=True)
    
    # B. 分析报告
    st.markdown("#### 📝 估值分析报告")
    
    term_mix = term_pv / enterprise_value
    
    analysis_md = f"""
    **1. 估值结果**
    基于 **DCF 模型**，{latest.get('ticker', '公司')} 的推算企业价值 (Enterprise Value) 为 **{enterprise_value:,.2f} {unit_label}**。
    
    **2. 核心假设**
    - **基准现金流**: {init_fcf:,.2f} (来源: {'TTM' if base_fcf == latest.get('FreeCashFlow_TTM') else 'FY'})
    - **折现率 (WACC)**: {wacc*100:.2f}%
    - **增长阶段**: 前5年 CAGR 为 {growth_rate*100:.1f}%，永续增长率为 {perp_rate*100:.1f}%。
    
    **3. 结构分析**
    - **前5年增长**: 贡献了 {total_pv:,.2f} ({1-term_mix:.1%}) 的价值。
    - **永续阶段**: 终值折现后贡献了 {term_pv:,.2f} ({term_mix:.1%}) 的价值。
    
    """
    
    if term_mix > 0.7:
        analysis_md += """
        > [!NOTE]
        > **终值依赖度较高**: 超过 70% 的价值来自于永续阶段 (Terminal Value)。
        > 这意味着估值对 **永续增长率** 和 **WACC** 的微小变化非常敏感，需谨慎评估这些长期假设。
        """
        
    st.markdown(analysis_md)

    # C. 敏感性分析 (WACC vs Terminal Growth)
    st.markdown("#### 🎯 敏感性分析 (Enterprise Value)")
    
    # 构造矩阵
    wacc_range = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
    g_range = [perp_rate - 0.005, perp_rate, perp_rate + 0.005]
    
    # 确保 g < wacc
    valid_g = [g for g in g_range if g < min(wacc_range)]
    if not valid_g: valid_g = [perp_rate]
    
    res_matrix = []
    for g in valid_g:
        row_vals = []
        for w in wacc_range:
             # 重新计算
            term_val_sense = flows[-1] * (1 + g) / (w - g)
            term_pv_sense = term_val_sense / ((1 + w) ** 5)
            
            # 前5年PV受WACC影响
            pv_5y_sense = 0
            curr_s = init_fcf
            for i in range(1, 6):
                curr_s = curr_s * (1 + growth_rate)
                pv_5y_sense += curr_s / ((1 + w) ** i)
            
            ev_sense = pv_5y_sense + term_pv_sense
            row_vals.append(ev_sense)
        res_matrix.append(row_vals)
        
    # Heatmap
    # Heatmap
    fig_sense = go.Figure(data=go.Heatmap(
        z=res_matrix,
        x=[f"{w*100:.1f}%" for w in wacc_range],
        y=[f"{g*100:.1f}%" for g in valid_g],
        colorscale='Viridis',
        texttemplate="%{z:,.0f}",
        hoverongaps=False
    ))
    
    fig_sense.update_layout(
        title="敏感性分析: WACC (X轴) vs 永续增长率 (Y轴)",
        xaxis_title="WACC",
        yaxis_title="永续增长率",
        height=350
    )
    
    st.plotly_chart(fig_sense, use_container_width=True)

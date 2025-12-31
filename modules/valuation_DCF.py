import streamlit as st
import pandas as pd
import numpy as np
from modules.calculator import process_financial_data

def render_valuation_DCF_tab(df, wacc, rf, unit_label):
    prefix = "dcf"
    st.subheader("🚀 自动 DCF 估值模型 (动态联动版)")
    
    if df.empty:
        st.warning("暂无财务数据，请先录入。")
        return

    # 1. 获取 TTM 数据
    df_cum, df_single = process_financial_data(df)
    df_single = df_single.sort_values(by=['Year', 'Sort_Key'])
    
    if len(df_single) < 4:
        st.error("数据不足 4 个季度，无法生成 TTM 数据，DCF 模型暂停使用。")
        return
    
    latest_data = df_single.iloc[-1]

    # --- 自动参数 1: 基准 FCF (锁定) ---
    # 严格使用 TTM FCF，如果未录入 FCF 则降级使用 TTM Profit
    if pd.notna(latest_data.get('FCF_TTM')) and latest_data['FCF_TTM'] != 0:
        base_fcf = latest_data['FCF_TTM']
        fcf_source = "TTM 自由现金流 (滚动4季)"
    else:
        base_fcf = latest_data.get('Profit_TTM', 0)
        fcf_source = "TTM 净利润 (替代值，未检测到FCF)"

    # --- 自动参数 2: 历史增长率 (CAGR) ---
    # 计算逻辑：(最新TTM / N年前TTM)^(1/N) - 1
    st.latex(r"CAGR = \left(\frac{FCF_{TTM\ 最新}}{FCF_{TTM\ N年前}}\right)^{\frac{1}{N}} - 1")
    # 尝试寻找 3 年前的 TTM 数据来计算 CAGR
    cagr_label = "默认 (10%)"
    auto_growth_rate = 0.10
    
    if len(df_single) >= 12: # 至少3年数据
        try:
            past_data = df_single.iloc[-9] # 2年前 (8个季度前)
            past_fcf = past_data.get('FCF_TTM', past_data.get('Profit_TTM', 1))
            if past_fcf > 0 and base_fcf > 0:
                cagr = (base_fcf / past_fcf) ** (1/2) - 1
                auto_growth_rate = cagr
                cagr_label = "2年复合增速 (CAGR)"
        except:
            pass
    elif pd.notna(latest_data.get('FCF_TTM_YoY')):
        auto_growth_rate = latest_data['FCF_TTM_YoY']
        cagr_label = "最新 TTM 同比增速"

    # --- 界面交互 ---
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    # 1. 基准 FCF (只读)
    col_p1.metric(
        label="基准现金流 (Base FCF)",
        value=f"{base_fcf:.2f} {unit_label}",
        help=f"数据来源: {fcf_source} (不可手动修改，请更新财报)"
    )

    # 2. 预期增长率 (自动填充但可修)
    growth_rate_input = col_p2.number_input(
        "未来 5 年增长率 (%)",
        value=float(auto_growth_rate * 100),
        format="%.2f",
        help=f"系统建议: {cagr_label} ({auto_growth_rate:.1%})",
        key=f"{prefix}_growth"
    ) / 100

    # 3. 永续增长率 (自动建议)
    # 理论上限通常是无风险利率或 GDP 增速
    terminal_g_input = col_p3.number_input(
        "永续增长率 (%)",
        value=2.5, # 默认 2.5%
        max_value=float(rf * 100), # 不超过无风险利率
        step=0.1,
        format="%.2f",
        help=f"通常不应超过无风险利率 ({rf:.1%})",
        key=f"{prefix}_term_g"
    ) / 100

    # --- 计算引擎 ---
    if wacc <= terminal_g_input:
        st.error(f"❌ 错误：WACC ({wacc:.2%}) 必须大于永续增长率 ({terminal_g_input:.2%})，否则模型发散。")
        return

    # 预测期
    cash_flows = []
    years_label = []
    
    # 动态显示年份
    current_year = latest_data['Year']
    
    for i in range(1, 6):
        fcf_future = base_fcf * ((1 + growth_rate_input) ** i)
        discounted_fcf = fcf_future / ((1 + wacc) ** i)
        cash_flows.append(discounted_fcf)
        years_label.append(f"{int(current_year)+i}E")

    sum_pv_growth = sum(cash_flows)

    # 终值
    fcf_year_5 = base_fcf * ((1 + growth_rate_input) ** 5)
    terminal_value = fcf_year_5 * (1 + terminal_g_input) / (wacc - terminal_g_input)
    pv_terminal = terminal_value / ((1 + wacc) ** 5)

    total_value = sum_pv_growth + pv_terminal

    # --- 结果可视化 ---
    st.markdown("---")
    res_c1, res_c2, res_c3 = st.columns(3)
    
    res_c1.metric("预测期现值 (5年)", f"{sum_pv_growth:.2f} {unit_label}")
    res_c2.metric("终值折现 (PV TV)", f"{pv_terminal:.2f} {unit_label}")
    res_c3.metric(
        "🚀 DCF 估值 (内在价值)", 
        f"{total_value:.2f} {unit_label}", 
        delta=f"WACC: {wacc:.1%} | g: {growth_rate_input:.1%}"
    )
    
    # 增加一个小表格显示未来流
    with st.expander("查看现金流预测详情"):
        future_df = pd.DataFrame({
            "年份": years_label,
            "折现因子": [f"1/{(1+wacc)**i:.2f}" for i in range(1, 6)],
            "折现后现值": [f"{cf:.2f}" for cf in cash_flows]
        })
        st.table(future_df)
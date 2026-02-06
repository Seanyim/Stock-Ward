import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from modules.core.calculator import process_financial_data
from modules.core.db import get_market_history, get_company_meta
from modules.data.industry_data import get_industry_benchmarks


def _calculate_percentile(data: pd.Series, value: float) -> float:
    """计算给定值在数据序列中的百分位（纯numpy实现，无需scipy）"""
    if len(data) == 0:
        return 0.0
    sorted_data = np.sort(data.values)
    # 计算小于等于该值的数据占比
    count_below = np.sum(sorted_data <= value)
    return (count_below / len(sorted_data)) * 100


def render_valuation_PE_tab(df_raw, unit_label):
    st.subheader("📊 PE 估值模型 (SQLite 版)")
    
    if df_raw.empty:
        st.warning("暂无财务数据")
        return

    # 1. 获取单季数据 (为了获得 EPS TTM 和增长率)
    _, df_single = process_financial_data(df_raw)
    
    if df_single.empty or 'EPS_TTM' not in df_single.columns:
        st.warning("无法计算 EPS TTM，请检查是否录入了利润/EPS数据")
        return

    # 2. 结合股价历史
    ticker = df_raw.iloc[0]['ticker']
    df_price = get_market_history(ticker)
    
    if df_price.empty:
        st.info("⚠️ 暂无历史股价数据，请在数据录入页面点击【开始同步】。")
        return

    # 3. 匹配股价与财报
    df_single['report_date'] = pd.to_datetime(df_single['report_date'])
    df_price['date'] = pd.to_datetime(df_price['date'])
    
    df_price = df_price.sort_values('date')
    df_single = df_single.sort_values('report_date')
    
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
        
    # 4. 统计分析 - 多分位数
    pe_percentiles = {
        '10%': valid_pe['PE_TTM'].quantile(0.1),
        '20%': valid_pe['PE_TTM'].quantile(0.2),
        '25%': valid_pe['PE_TTM'].quantile(0.25),
        '50%': valid_pe['PE_TTM'].quantile(0.5),
        '75%': valid_pe['PE_TTM'].quantile(0.75),
        '80%': valid_pe['PE_TTM'].quantile(0.8),
        '90%': valid_pe['PE_TTM'].quantile(0.9),
    }
    
    pe_median = pe_percentiles['50%']
    pe_20 = pe_percentiles['20%']
    pe_80 = pe_percentiles['80%']
    
    # 获取最新 EPS TTM (来自财报)
    latest_financial = valid_pe.iloc[-1]
    current_eps_ttm = latest_financial['EPS_TTM']
    
    # 获取最新股价 (来自市场数据最新日期)
    current_price = df_price.iloc[-1]['close']
    
    # 使用最新股价计算当前 PE TTM (解决 PE TTM 不匹配问题)
    current_pe_ttm = current_price / current_eps_ttm if current_eps_ttm > 0 else 0
    
    # 计算当前 PE 所处历史百分位
    current_percentile = _calculate_percentile(valid_pe['PE_TTM'], current_pe_ttm)
    
    # --- 静态 PE (使用最近完整财年 EPS) ---
    # PE Static 使用最近完整财年的 EPS，而不是滚动 TTM
    # 对于美股：Q4 = 财年结束，取上一个 Q4 的累计 EPS
    
    eps_static = None
    static_source = None
    
    # 方法1：查找 FY 数据
    fy_data = df_raw[df_raw['period'] == 'FY']
    if not fy_data.empty:
        fy_data_sorted = fy_data.sort_values('year')
        last_fy_record = fy_data_sorted.iloc[-1]
        eps_static = last_fy_record.get('EPS', None) if isinstance(last_fy_record, pd.Series) else None
        if eps_static:
            static_source = f"FY{last_fy_record.get('year', '')}"
    
    # 方法2：查找最近的 Q4 数据 (美股财年结束)
    if eps_static is None:
        q4_data = df_raw[df_raw['period'] == 'Q4']
        if not q4_data.empty:
            q4_sorted = q4_data.sort_values('year', ascending=False)
            # 取上一个完整财年的 Q4 (不是最新的)
            for _, q4_row in q4_sorted.iterrows():
                # 检查是否有完整4个季度数据
                year = q4_row.get('year')
                year_data = df_raw[(df_raw['year'] == year) & (df_raw['period'].isin(['Q1', 'Q2', 'Q3', 'Q4']))]
                if len(year_data) == 4 and 'EPS' in year_data.columns:
                    eps_static = year_data['EPS'].sum()
                    static_source = f"FY{year} (Q1-Q4累加)"
                    break
    
    # 方法3：如果都没有，显示 N/A 而不是使用 TTM
    pe_static = (current_price / eps_static) if eps_static and eps_static > 0 else None
    
    # --- PEG 自动计算 (基于财报数据) ---
    st.markdown("#### 🚀 PEG 估值模型 (含费雪利率修正)")
    
    # 1. 确定增长率
    growth_rate = None
    growth_source = None
    
    # 优先使用归母净利润增长率，其次使用 EPS 增长率
    if 'NetIncomeToParent_TTM_YoY' in df_single.columns:
        latest_growth = df_single.iloc[-1].get('NetIncomeToParent_TTM_YoY', None)
        if pd.notna(latest_growth) and latest_growth > 0:
            growth_rate = latest_growth * 100
            growth_source = "归母净利润 TTM 同比"
    
    if growth_rate is None and 'EPS_TTM_YoY' in df_single.columns:
        latest_growth = df_single.iloc[-1].get('EPS_TTM_YoY', None)
        if pd.notna(latest_growth) and latest_growth > 0:
            growth_rate = latest_growth * 100
            growth_source = "EPS TTM 同比"
            
    # 让用户可以调整增长率
    col_g1, col_g2, col_g3 = st.columns(3)
    input_growth = col_g1.number_input("预期增长率 G (%)", value=float(growth_rate if growth_rate else 15.0), min_value=0.1)
    
    # 费雪修正：输入无风险利率 (影响 PEG 阈值)
    # 彼得·林奇认为 PEG=1 合理，但在高利率环境下 PEG < 1 才合理，低利率下可稍高
    # 或者使用 PEG = PE / (Growth + Yield)
    rf_rate = col_g2.number_input("无风险利率/通胀 (%)", value=4.0, help="用于费雪效应修正")
    
    # 计算
    peg = current_pe_ttm / input_growth
    
    # 修正后的评估标准 (假设 Benchmark PEG = 1)
    # Fisher修正思路：高利率下资金成本高，Growth价值打折
    # 简单修正公式：Adjusted G = G - Rf
    # Adjusted PEG = PE / (G - Rf) (如果 G > Rf)
    
    adjusted_growth = input_growth - rf_rate
    if adjusted_growth > 0:
        peg_adjusted = current_pe_ttm / adjusted_growth
    else:
        peg_adjusted = float('inf')
    
    # 展示结果
    col_g3.metric("PEG (原始)", f"{peg:.2f}")
    
    st.info(f"💡 原始增长率来源: {growth_source if growth_rate else '默认值'}")
    
    with st.expander("📝 完整计算过程 & 费雪修正"):
        st.markdown(f"""
        **1. 基础公式**
        $$ PEG = \\frac{{P/E}}{{Growth}} = \\frac{{{current_pe_ttm:.2f}}}{{{input_growth:.2f}}} = {peg:.2f} $$
        
        **2. 费雪利率修正 (Fisher Effect)**
        考虑资金成本/通胀对增长价值的侵蚀，修正后的有效增长率 (Real Growth)：
        $$ G_{{real}} = G_{{nominal}} - R_{{risk\_free}} = {input_growth:.2f}\\% - {rf_rate:.2f}\\% = {adjusted_growth:.2f}\\% $$
        
        **3. 修正后 PEG**
        $$ PEG_{{adjusted}} = \\frac{{P/E}}{{G_{{real}}}} = \\frac{{{current_pe_ttm:.2f}}}{{{adjusted_growth:.2f}}} = {peg_adjusted:.2f} $$
        
        **4. 评价**
        - PEG (原始): {peg:.2f} {"✅ 低估" if peg < 1 else "⚠️ 合理/高估" if peg < 1.5 else "❌ 高估"}
        - PEG (修正): {peg_adjusted:.2f} (考虑 {rf_rate}% 利率成本后)
        """)
        
    # --- PEG 可视化分析 ---
    st.markdown("#### 📊 PEG 分析可视化")
    fig_peg = go.Figure()

    # 绘制 PEG 仪表盘
    fig_peg.add_trace(go.Indicator(
        mode = "gauge+number+delta",
        value = peg,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "PEG (原始)", 'font': {'size': 24}},
        delta = {'reference': 1.0, 'increasing': {'color': "red"}, 'decreasing': {'color': "green"}},
        gauge = {
            'axis': {'range': [0, max(3.0, peg * 1.2)], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 0.8], 'color': 'rgba(0, 255, 0, 0.3)'},
                {'range': [0.8, 1.2], 'color': 'rgba(255, 255, 0, 0.3)'},
                {'range': [1.2, 3.0], 'color': 'rgba(255, 0, 0, 0.3)'}],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': peg}}))
    
    fig_peg.update_layout(height=300)
    st.plotly_chart(fig_peg, use_container_width=True)

    # 文本分析
    peg_status = "低估" if peg < 1 else "合理" if peg < 1.5 else "高估"
    st.info(f"📊 **数据分析**: 当前 PEG 为 {peg:.2f}，处于 **{peg_status}** 区间。基于 {growth_rate:.1f}% 的预期增长率，市场给予的估值倍数为 {current_pe_ttm:.1f}x。")
        
    eps_forward = current_eps_ttm * (1 + input_growth / 100)
    pe_forward = current_price / eps_forward if eps_forward > 0 else None
    
    # --- UI: 详细估值指标 ---
    st.markdown("#### 📐 详细估值指标")
    
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("PE (TTM)", f"{current_pe_ttm:.2f}", help="当前股价 / 过去12个月每股收益")
    m2.metric("PE (Static)", f"{pe_static:.2f}" if pe_static else "N/A", help="当前股价 / 上一财年每股收益")
    m3.metric("PE (Forward)", f"{pe_forward:.2f}" if pe_forward else "N/A", 
              help=f"当前股价 / 预期每股收益 (增长率: {growth_rate:.1f}%)" if growth_rate else "需要有效增长率")
    m4.metric("PEG", f"{peg:.2f}" if peg else "N/A", 
              help=f"PE(TTM) / 增长率 ({growth_source})" if growth_source else "需要正增长率才能计算")
    m5.metric("中位 PE (Hist)", f"{pe_median:.2f}", help="历史 PE 的中位数")
    
    # --- 需求1: PE TTM 区间分析 ---
    st.markdown("---")
    st.markdown("#### 📊 PE TTM 历史区间分析")
    
    # 当前PE百分位进度条
    st.markdown(f"**当前 PE {current_pe_ttm:.2f} 处于历史 {current_percentile:.1f}% 分位**")
    st.progress(min(current_percentile / 100, 1.0))
    
    # 分位数表格
    percentile_df = pd.DataFrame({
        '分位': list(pe_percentiles.keys()),
        'PE值': [f"{v:.2f}" for v in pe_percentiles.values()]
    })
    
    # 水平布局展示分位数
    cols = st.columns(len(pe_percentiles))
    for i, (pct, pe_val) in enumerate(pe_percentiles.items()):
        with cols[i]:
            # 高亮当前PE接近的分位
            is_close = abs(pe_val - current_pe_ttm) < (pe_percentiles['90%'] - pe_percentiles['10%']) * 0.1
            color = "🔵" if is_close else ""
            st.metric(f"{color}{pct}", f"{pe_val:.2f}")
    
    # 估值判断提示
    if current_percentile <= 20:
        st.success("📉 当前估值处于历史低位区间 (≤20%分位)，可能被低估")
    elif current_percentile >= 80:
        st.warning("📈 当前估值处于历史高位区间 (≥80%分位)，可能被高估")
    else:
        st.info("📊 当前估值处于历史正常区间")

    st.markdown("---")
    
    # --- PE Band 图 (含财报发布日标线) ---
    st.markdown("#### 📉 PE Band 通道图")
    
    # === 优化: 准备每日级别的数据用于绘图 ===
    # 1. 确保 df_price 是每日连续的
    df_price_daily = df_price.set_index('date').resample('D').ffill().reset_index()
    
    # 2. 将 EPS 数据合并到每日股价数据中 (ffill)
    # 先处理 df_single 只保留需要的列
    df_eps = df_single[['report_date', 'EPS_TTM']].sort_values('report_date')
    
    # merge_asof 需要 keys 有序
    df_price_daily = df_price_daily.sort_values('date')
    
    df_chart_data = pd.merge_asof(
        df_price_daily,
        df_eps,
        left_on='date',
        right_on='report_date',
        direction='backward'  # 使用最近一次已发布的 EPS
    )
    
    # 移除没有 EPS 处理的早期数据
    df_chart_data = df_chart_data.dropna(subset=['EPS_TTM'])
    
    # 3. 计算通道价格 (使用平滑处理)
    # 计算平滑窗口 (例如 90天)
    window = 90
    df_chart_data['band_80'] = (df_chart_data['EPS_TTM'] * pe_80).rolling(window=window, min_periods=1).mean()
    df_chart_data['band_mid'] = (df_chart_data['EPS_TTM'] * pe_median).rolling(window=window, min_periods=1).mean()
    df_chart_data['band_20'] = (df_chart_data['EPS_TTM'] * pe_20).rolling(window=window, min_periods=1).mean()
    
    # 历史 PE TTM 平滑
    # 先计算每日 PE
    df_chart_data['pe_ttm'] = df_chart_data['close'] / df_chart_data['EPS_TTM']
    df_chart_data['pe_ttm_smooth'] = df_chart_data['pe_ttm'].rolling(window=window, min_periods=1).mean()

    # 获取行业平均 PE
    meta = get_company_meta(ticker)
    sector = meta.get('sector', 'General')
    industry_benchmarks = get_industry_benchmarks(sector)
    industry_pe = industry_benchmarks.get('pe_ttm', 20.0)
    
    fig = go.Figure()
    
    # === 改进的 PE Band 可视化 ===
    # 使用蓝色填充通道，加粗股价线，添加数值标注
    
    # 高估区域上沿 (80分位) - 平滑
    fig.add_trace(go.Scatter(
        x=df_chart_data['date'], 
        y=df_chart_data['band_80'], 
        name=f"PE {pe_80:.1f}x (80%分位)", 
        line=dict(color='rgba(239, 68, 68, 0.8)', width=1),
        mode='lines'
    ))
    
    # 中枢线 (50分位) - 平滑
    fig.add_trace(go.Scatter(
        x=df_chart_data['date'], 
        y=df_chart_data['band_mid'], 
        name=f"PE {pe_median:.1f}x (中枢)", 
        line=dict(color='rgba(59, 130, 246, 1)', width=2, dash='dash'),
        mode='lines'
    ))
    
    # 低估区域下沿 (20分位) - 平滑
    fig.add_trace(go.Scatter(
        x=df_chart_data['date'], 
        y=df_chart_data['band_20'], 
        name=f"PE {pe_20:.1f}x (20%分位)", 
        line=dict(color='rgba(34, 197, 94, 0.8)', width=1),
        mode='lines'
    ))

    # --- 改进: 行业平均 PE 线 (灰色, 平滑) ---
    # 新增灰色线代表公司所在行业的平均市盈率走势（平滑曲线）
    # 平滑窗口 90天
    df_chart_data['industry_line'] = (df_chart_data['EPS_TTM'] * industry_pe).rolling(window=90, min_periods=1).mean()
    
    fig.add_trace(go.Scatter(
        x=df_chart_data['date'],
        y=df_chart_data['industry_line'],
        name=f"行业平均趋势 ({industry_pe}x)",
        line=dict(color='rgba(128, 128, 128, 0.8)', width=1.5, dash='dot'),
        hovertemplate="行业平均: $%{y:.2f}<extra></extra>"
    ))

    # --- 改进: 历史 PE TTM 平滑曲线 (用户可选择时间窗口) ---
    st.markdown("##### ⚙️ 图表设置")
    c_h1, c_h2 = st.columns(2)
    with c_h1:
        hist_window_opt = st.selectbox(
            "历史 PE 均值参考窗口", 
            ["1年 (1Y)", "3年 (3Y)", "5年 (5Y)"], 
            index=1,
            help="计算'历史PE平滑均价'线时使用的移动平均窗口大小"
        )
    
    window_map = {"1年 (1Y)": 252, "3年 (3Y)": 252*3, "5年 (5Y)": 252*5}
    rolling_window = window_map.get(hist_window_opt, 252*3)
    
    # 计算移动平均 PE
    df_chart_data['pe_rolling_avg'] = df_chart_data['pe_ttm'].rolling(window=rolling_window, min_periods=int(rolling_window*0.5)).mean()
    # 历史 PE 平滑均价 = Rolling Avg PE * EPS
    df_chart_data['hist_pe_line'] = df_chart_data['pe_rolling_avg'] * df_chart_data['EPS_TTM']
    
    # 对最终结果再做个短期平滑 (30天) 使曲线美观
    df_chart_data['hist_pe_line'] = df_chart_data['hist_pe_line'].rolling(window=30, min_periods=1).mean()

    fig.add_trace(go.Scatter(
        x=df_chart_data['date'],
        y=df_chart_data['hist_pe_line'],
        name=f"历史 {hist_window_opt} PE均价",
        line=dict(color='rgba(192, 192, 192, 0.9)', width=2),
        visible=True,
        hovertemplate=f"历史{hist_window_opt}: $%{str('y:.2f')}<extra></extra>"
    ))
    
    # 填充蓝色通道（20%-80%区间）
    fig.add_trace(go.Scatter(
        x=pd.concat([df_chart_data['date'], df_chart_data['date'][::-1]]),
        y=pd.concat([df_chart_data['band_80'], df_chart_data['band_20'][::-1]]),
        fill='toself',
        fillcolor='rgba(59, 130, 246, 0.15)',
        line=dict(color='rgba(0,0,0,0)'),
        name='估值通道 (20%-80%)',
        hoverinfo='skip',
        showlegend=True
    ))
    
    # 股价线 (加粗，橙色，最后添加以显示在顶层)
    fig.add_trace(go.Scatter(
        x=df_chart_data['date'], 
        y=df_chart_data['close'], 
        name="股价", 
        line=dict(color='#FF6B00', width=3),  # 橙色
        mode='lines',
        hovertemplate="股价: $%{y:.2f}<extra></extra>"
    ))
    
    # 添加当前价格和通道边界数值标注
    if not df_chart_data.empty:
        last_item = df_chart_data.iloc[-1]
        last_date_chart = last_item['date']
        
        # 统一 helper
        def add_label(y_val, color, text_val=None):
            if pd.isna(y_val): return
            txt = text_val if text_val else f"${y_val:.0f}"
            fig.add_annotation(
                x=last_date_chart, y=y_val,
                text=txt, 
                showarrow=False, xshift=40,
                font=dict(size=10, color=color)
            )

        add_label(last_item['band_80'], 'red')
        add_label(last_item['band_mid'], 'blue')
        add_label(last_item['band_20'], 'green')
        add_label(last_item['close'], '#FF6B00')
    
    # 需求3: 添加财报发布日垂直虚线
    for _, row in valid_pe.iterrows():
        report_date = row['report_date']
        if pd.isna(report_date): continue
        
        period = row.get('period', '')
        year = row.get('year', '')
        # 简化标签，避免遮挡
        label = f"{period}" if period else ""
        
        fig.add_shape(
            type="line", x0=report_date, x1=report_date, y0=0, y1=1, yref="paper",
            line=dict(color="rgba(128, 128, 128, 0.3)", width=1, dash="dot")
        )
    
    fig.update_layout(
        title="PE Band 估值通道图",
        xaxis_title="日期",
        yaxis_title="股价 ($)",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.95)",
            font_size=12,
            font_family="sans-serif"
        ),
        legend=dict(orientation="h", y=1.1, x=0),
        height=500,
        margin=dict(r=50) # 增加右边距以显示标签
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 增长率信息展示
    if growth_rate:
        st.caption(f"💡 PEG 使用的增长率：{growth_rate:.2f}% (来源: {growth_source})")
    else:
        st.caption("⚠️ 无法自动计算 PEG：需要正的利润增长率数据")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from modules.calculator import process_financial_data
from modules.db import get_market_history


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
    
    latest = valid_pe.iloc[-1]
    current_pe_ttm = latest['PE_TTM']
    current_price = latest['close']
    current_eps_ttm = latest['EPS_TTM']
    
    # 计算当前 PE 所处历史百分位
    current_percentile = _calculate_percentile(valid_pe['PE_TTM'], current_pe_ttm)
    
    # --- 静态 PE ---
    fy_data = df_raw[df_raw['period'] == 'FY']
    if not fy_data.empty:
        fy_data_sorted = fy_data.sort_values('year')
        last_fy_record = fy_data_sorted.iloc[-1]
        eps_static = last_fy_record.get('EPS', None) if isinstance(last_fy_record, pd.Series) else None
    else:
        eps_static = None
    
    pe_static = (current_price / eps_static) if eps_static and eps_static > 0 else None
    
    # --- PEG 自动计算 (基于财报数据) ---
    # 优先使用归母净利润增长率，其次使用 EPS 增长率
    growth_rate = None
    growth_source = None
    
    # 新指标名称：NetIncomeToParent_TTM_YoY（归母净利润TTM同比）
    if 'NetIncomeToParent_TTM_YoY' in df_single.columns:
        latest_growth = df_single.iloc[-1].get('NetIncomeToParent_TTM_YoY', None)
        if pd.notna(latest_growth) and latest_growth > 0:
            growth_rate = latest_growth * 100  # 转为百分比
            growth_source = "归母净利润 TTM 同比"
    
    # 备选：使用 NetIncome_TTM_YoY（旧版兼容）
    if growth_rate is None and 'NetIncome_TTM_YoY' in df_single.columns:
        latest_growth = df_single.iloc[-1].get('NetIncome_TTM_YoY', None)
        if pd.notna(latest_growth) and latest_growth > 0:
            growth_rate = latest_growth * 100
            growth_source = "净利润 TTM 同比"
    
    # 备选：使用 EPS_TTM_YoY
    if growth_rate is None and 'EPS_TTM_YoY' in df_single.columns:
        latest_growth = df_single.iloc[-1].get('EPS_TTM_YoY', None)
        if pd.notna(latest_growth) and latest_growth > 0:
            growth_rate = latest_growth * 100
            growth_source = "EPS TTM 同比"
    
    # 计算 PEG 和 Forward PE
    if growth_rate and growth_rate > 0:
        peg = current_pe_ttm / growth_rate
        eps_forward = current_eps_ttm * (1 + growth_rate / 100)
        pe_forward = current_price / eps_forward if eps_forward > 0 else None
    else:
        peg = None
        pe_forward = None
        growth_rate = None
    
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
    fig = go.Figure()
    
    # 真实股价
    fig.add_trace(go.Scatter(
        x=valid_pe['report_date'], 
        y=valid_pe['close'], 
        name="股价", 
        line=dict(color='black', width=2)
    ))
    
    # 理论股价线
    fig.add_trace(go.Scatter(
        x=valid_pe['report_date'], 
        y=valid_pe['EPS_TTM'] * pe_80, 
        name=f"高估 ({pe_80:.1f}x)", 
        line=dict(dash='dot', color='red')
    ))
    fig.add_trace(go.Scatter(
        x=valid_pe['report_date'], 
        y=valid_pe['EPS_TTM'] * pe_median, 
        name=f"中枢 ({pe_median:.1f}x)", 
        line=dict(dash='dash', color='blue')
    ))
    fig.add_trace(go.Scatter(
        x=valid_pe['report_date'], 
        y=valid_pe['EPS_TTM'] * pe_20, 
        name=f"低估 ({pe_20:.1f}x)", 
        line=dict(dash='dot', color='green')
    ))
    
    # 需求3: 添加财报发布日垂直虚线（使用shape避免Timestamp兼容性问题）
    for _, row in valid_pe.iterrows():
        report_date = row['report_date']
        period = row.get('period', '')
        year = row.get('year', '')
        label = f"{year} {period}" if year and period else ""
        
        # 使用 add_shape 绘制垂直线
        fig.add_shape(
            type="line",
            x0=report_date,
            x1=report_date,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(color="rgba(128, 128, 128, 0.3)", width=1, dash="dash")
        )
        
        # 单独添加注释
        if label:
            fig.add_annotation(
                x=report_date,
                y=1,
                yref="paper",
                text=label,
                showarrow=False,
                font=dict(size=8, color="gray"),
                yshift=5
            )
    
    fig.update_layout(
        title="PE Band 通道图 (虚线标记财报发布日)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 增长率信息展示
    if growth_rate:
        st.caption(f"💡 PEG 使用的增长率：{growth_rate:.2f}% (来源: {growth_source})")
    else:
        st.caption("⚠️ 无法自动计算 PEG：需要正的利润增长率数据")

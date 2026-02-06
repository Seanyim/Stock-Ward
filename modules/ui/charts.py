import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from modules.core.calculator import process_financial_data
from modules.core.config import FINANCIAL_METRICS

def format_large_number(num):
    if pd.isna(num) or num is None: return "-"
    abs_num = abs(num)
    if abs_num >= 1e9: return f"{num/1e9:.2f}B"
    if abs_num >= 1e6: return f"{num/1e6:.2f}M"
    return f"{num:,.2f}"

def render_charts_tab(df_raw, unit_label="Raw"):
    st.subheader("📊 全维财务趋势分析")
    
    if df_raw.empty:
        st.warning("暂无数据，请先录入财务信息。")
        return

    # 1. 调用计算引擎
    df_cum, df_single = process_financial_data(df_raw)
    from modules.core.calculator import get_view_data

    # 2. 控件布局
    c1, c2 = st.columns(2)
    with c1:
        # 筛选出当前数据中存在的列
        available_metrics = [m for m in FINANCIAL_METRICS if m['id'] in df_raw.columns]
        if not available_metrics:
            st.error("数据列缺失")
            return
            
        selected_metric = st.selectbox(
            "选择财务指标", 
            available_metrics, 
            format_func=lambda x: f"{x['label']}"
        )
        metric_key = selected_metric['id']
        
    with c2:
        # 统一视图选项
        view_label_map = {
            "单季度 (Q1-Q4)": "single",
            "累积季度 (Q1/H1/Q9/FY)": "cumulative",
            "年度数据 (FY Only)": "annual"
        }
        
        view_label = st.radio(
            "视角", 
            list(view_label_map.keys()),
            horizontal=True
        )
        view_mode = view_label_map[view_label]

    # 3. 准备数据
    # 3. 准备数据
    plot_data = get_view_data(df_single, view_mode)
    
    val_col = metric_key
    yoy_col = f"{metric_key}_YoY"
    # QoQ 只在单季度视角下有意义，get_view_data 暂未返回 QoQ
    # 如果需要 QoQ，可以在这里补算，或者只显示 YoY
    
    # 兼容性处理：如果 metric_key 是 TTM 的（旧代码遗留），应去掉 _TTM 后缀
    # 但这里 metric_key 来自 selector，它是原始 key (e.g. TotalRevenue)
    # get_view_data 返回的也是原始 key，所以 val_col = metric_key 是对的。

    if plot_data.empty:
        st.info("数据不足以生成图表")
        return
    
    # 检查所需列是否存在
    if val_col not in plot_data.columns:
        st.warning(f"⚠️ 列 '{val_col}' 不存在，该指标可能不支持此视角")
        st.info("💡 提示：百分比指标（如毛利率、ROE）通常不支持 TTM 滚动计算")
        return

    # 4. 构造 X 轴标签
    # 累计原始值保持 Q1/H1/Q9/FY 格式
    plot_data = plot_data.sort_values(['year', 'period'], ascending=[True, True])
    plot_data['x_label'] = plot_data['year'].astype(str) + "/" + plot_data['period']
    
    x = plot_data['x_label']
    y = plot_data[val_col]

    # 5. 创建混合图表（柱状图 + 折线图 + 增长率）
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 柱状图 - 数值
    fig.add_trace(
        go.Bar(
            x=x, 
            y=y, 
            name=selected_metric['label'],
            text=y.apply(format_large_number),
            textposition='outside',
            marker_color='rgba(59, 130, 246, 0.7)'
        ),
        secondary_y=False
    )
    
    # 折线图 - 数值趋势
    fig.add_trace(
        go.Scatter(
            x=x, 
            y=y, 
            name="趋势线",
            mode='lines+markers',
            line=dict(color='#1E40AF', width=2),
            marker=dict(size=6)
        ),
        secondary_y=False
    )
    
    # 同比增长率曲线 (YoY)
    if yoy_col and yoy_col in plot_data.columns:
        yoy_data = plot_data[yoy_col]
        fig.add_trace(
            go.Scatter(
                x=x, 
                y=yoy_data, 
                name="同比 YoY",
                mode='lines+markers',
                line=dict(color='#F97316', width=2, dash='dot'),
                marker=dict(size=5)
            ),
            secondary_y=True
        )
    
    # 环比增长率曲线 (QoQ) - 暂不支持
    # if qoq_col and qoq_col in plot_data.columns:
    #    ...
    
    # 布局设置
    fig.update_layout(
        title=f"{selected_metric['label']} 趋势分析",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.15),
        height=450,
        bargap=0.3
    )
    
    fig.update_yaxes(title_text=selected_metric['label'], secondary_y=False)
    fig.update_yaxes(title_text="增长率", tickformat=".1%", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 6. 数据表（按时间倒序显示）
    with st.expander("📋 查看详细数据"):
        display_data = plot_data.iloc[::-1].copy()  # 最新在前
        cols = ['year', 'period']
        
        if val_col in display_data.columns:
            cols.append(val_col)
        if yoy_col and yoy_col in display_data.columns:
            cols.append(yoy_col)
        
        valid_cols = [c for c in cols if c in display_data.columns]
        if valid_cols:
            # 格式化增长率列
            df_display = display_data[valid_cols].copy()
            for col in [yoy_col]:
                if col and col in df_display.columns:
                    df_display[col] = df_display[col].apply(
                        lambda x: f"{x:.1%}" if pd.notna(x) else "-"
                    )
            st.dataframe(df_display, use_container_width=True)
        else:
            st.info("无可显示数据")
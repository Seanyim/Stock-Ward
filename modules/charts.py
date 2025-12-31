import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from modules.calculator import process_financial_data
from modules.config import GROWTH_METRIC_KEYS

def render_charts_tab(df, unit_label):
    st.subheader("📊 财务趋势交互分析")
    
    if df.empty:
        st.warning("暂无数据，请先在数据录入页添加数据。")
        return

    # 1. 获取清洗后的数据
    df_cum, df_single = process_financial_data(df)

    col_ctrl1, col_ctrl2 = st.columns([1, 1])
    
    with col_ctrl1:
        # [修改点] 这里的下拉菜单将只显示 Revenue, Profit, EPS, FCF
        # 不会显示 Pre_Tax_Income, Tax 等不需要绘图的指标
        available_metrics = GROWTH_METRIC_KEYS
        valid_metrics = [m for m in available_metrics if m in df.columns]
        
        selected_metric = st.selectbox(
            "选择财务指标", 
            valid_metrics, 
            index=0
        )

    with col_ctrl2:
        # 视图模式选择
        view_mode = st.radio(
            "分析视角", 
            ["单季度 (拐点分析)", "TTM (长期趋势)", "累计 (年度分析)"], 
            horizontal=True
        )

    # 次级控制：仅在“单季度”模式下显示增长率类型选择
    growth_metric_type = "QoQ"
    if view_mode == "单季度 (拐点分析)":
        st.caption("📈 选择折线图增长指标：")
        growth_metric_type = st.radio(
            "增长率类型", 
            ["环比增长 (QoQ)", "同比增长 (YoY)"], 
            horizontal=True,
            label_visibility="collapsed",
            key="single_growth_select"
        )

    # 2. 调用绘图
    fig = _create_metric_chart(
        df_cum, 
        df_single, 
        selected_metric, 
        view_mode, 
        growth_metric_type,
        unit_label
    )

    st.plotly_chart(fig, use_container_width=True)

    # 3. 底部展示对应的数据表
    with st.expander(f"查看 {selected_metric} 详细数据表"):
        _show_data_table(df_cum, df_single, selected_metric, view_mode)


# ==========================================
#           内部通用核心函数
# ==========================================

def _create_metric_chart(df_cum, df_single, metric, view_mode, growth_type, unit_label):
    """
    通用绘图函数
    """
    # 定义映射关系 (通用)
    p_map = {"Q1": "Q1", "H1": "Q2", "Q9": "Q3", "FY": "Q4"}

    # --- A. 数据准备 ---
    if view_mode == "单季度 (拐点分析)":
        # === 模式1: 单季度 ===
        df_plot = df_single.sort_values(by=['Year', 'Sort_Key']).copy()
        df_plot['Display_Period'] = df_plot['Period'].map(p_map)
        df_plot['X_Label'] = df_plot['Year'].astype(str) + " " + df_plot['Display_Period']
        
        col_bar = f"{metric}_Single"
        
        if growth_type == "同比增长 (YoY)":
            col_line = f"{metric}_Single_YoY"
            line_name = "单季同比 (YoY)"
            title_text = f"{metric} - 单季度趋势 (关注 YoY 实质增长)"
        else:
            col_line = f"{metric}_Single_QoQ"
            line_name = "单季环比 (QoQ)"
            title_text = f"{metric} - 单季度趋势 (关注 QoQ 短期动能)"
            
        bar_name = f"单季{metric} ({unit_label})"
        hover_template_bar = f"<b>%{{x}}</b><br>单季数值: %{{y:.3f}} {unit_label}<extra></extra>"

    elif view_mode == "TTM (长期趋势)":
        # === 模式2: TTM ===
        df_plot = df_single.sort_values(by=['Year', 'Sort_Key']).copy()
        
        # [修改点] 恢复成 Q1/Q2/Q3/Q4 显示，利于观察连续趋势
        df_plot['Display_Period'] = df_plot['Period'].map(p_map)
        df_plot['X_Label'] = df_plot['Year'].astype(str) + " " + df_plot['Display_Period']
        
        col_bar = f"{metric}_TTM"
        col_line = f"{metric}_TTM_YoY"
        
        bar_name = f"TTM {metric} ({unit_label})"
        line_name = "TTM 同比增长"
        title_text = f"{metric} - TTM 滚动年化趋势 (熨平季节性)"
        
        # 增加提示：解释为何有些点没有增长率
        hover_template_bar = f"<b>%{{x}}</b><br>TTM数值: %{{y:.3f}} {unit_label}<br><i>(过去4个单季之和)</i><extra></extra>"
        
    else: 
        # === 模式3: 累计 ===
        df_plot = df_cum.sort_values(by=['Year', 'Sort_Key']).copy()
        df_plot['X_Label'] = df_plot['Year'].astype(str) + " " + df_plot['Period']
        
        col_bar = metric
        col_line = f"{metric}_YoY"
        
        bar_name = f"累计{metric} ({unit_label})"
        line_name = "累计同比增长"
        title_text = f"{metric} - 累计/年度完成进度"
        hover_template_bar = f"<b>%{{x}}</b><br>累计数值: %{{y:.3f}} {unit_label}<extra></extra>"

    # --- B. 绘图逻辑 (Plotly) ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. 柱状图
    fig.add_trace(
        go.Bar(
            x=df_plot['X_Label'],
            y=df_plot[col_bar],
            name=bar_name,
            marker_color='rgba(55, 128, 191, 0.7)',
            hovertemplate=hover_template_bar
        ),
        secondary_y=False,
    )

    # 2. 折线图
    if col_line in df_plot.columns:
        # 检查是否有有效数据，如果没有有效数据(全NaN)，Plotly不会画线，这解释了为何红点缺失
        valid_data_count = df_plot[col_line].notna().sum()
        
        fig.add_trace(
            go.Scatter(
                x=df_plot['X_Label'],
                y=df_plot[col_line],
                name=line_name,
                mode='lines+markers',
                marker=dict(size=8, color='crimson'),
                line=dict(width=3),
                hovertemplate=f"<b>%{{x}}</b><br>增长率: %{{y:.2%}}<extra></extra>"
            ),
            secondary_y=True,
        )

    # --- C. 布局美化 ---
    fig.update_layout(
        title=dict(text=title_text, x=0.05),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    fig.update_yaxes(
        title_text=f"金额 ({unit_label})", 
        secondary_y=False, 
        showgrid=True, 
        gridcolor='rgba(200,200,200,0.2)'
    )
    fig.update_yaxes(
        title_text="增长率 (%)", 
        secondary_y=True, 
        tickformat=".1%", 
        showgrid=False
    )
    
    return fig

def _show_data_table(df_cum, df_single, metric, view_mode):
    """显示表格"""
    # 表格展示也同步使用排序后的数据
    df_single_view = df_single.sort_values(by=['Year', 'Sort_Key'])
    df_cum_view = df_cum.sort_values(by=['Year', 'Sort_Key'])

    if view_mode == "单季度 (拐点分析)":
        cols = ['Year', 'Period', f'{metric}_Single']
        qoq, yoy = f'{metric}_Single_QoQ', f'{metric}_Single_YoY'
        if qoq in df_single.columns: cols.append(qoq)
        if yoy in df_single.columns: cols.append(yoy)
        
        st.dataframe(df_single_view[cols].style.format({
            f'{metric}_Single': "{:.3f}", 
            qoq: "{:.3%}",
            yoy: "{:.3%}"
        }, na_rep="-"))
        
    elif view_mode == "TTM (长期趋势)":
        cols = ['Year', 'Period', f'{metric}_TTM', f'{metric}_TTM_YoY']
        # 为了方便验证数据，保留单季度数据作为参考
        if f'{metric}_Single' in df_single.columns:
             cols.insert(2, f'{metric}_Single')
             
        st.dataframe(df_single_view[cols].style.format({
            f'{metric}_Single': "{:.3f}",
            f'{metric}_TTM': "{:.3f}", 
            f'{metric}_TTM_YoY': "{:.3%}"
        }, na_rep="-"))
        
    else:
        # 累计模式
        col_yoy = f'{metric}_YoY'
        cols = ['Year', 'Period', metric, col_yoy]
        st.dataframe(df_cum_view[cols].style.format({
            metric: "{:.3f}", 
            col_yoy: "{:.3%}"
        }, na_rep="-"))
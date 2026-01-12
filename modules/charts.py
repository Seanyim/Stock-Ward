import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from modules.calculator import process_financial_data
from modules.config import METRIC_MAPPING

def format_large_number(num):
    if pd.isna(num) or num is None: return "-"
    abs_num = abs(num)
    if abs_num >= 1e12: return f"{num/1e12:.2f}T"
    if abs_num >= 1e9: return f"{num/1e9:.2f}B"
    if abs_num >= 1e6: return f"{num/1e6:.2f}M"
    if abs_num >= 1e3: return f"{num/1e3:.2f}K"
    return f"{num:,.2f}"

def render_charts_tab(df, unit_label="Raw"):
    st.subheader("📊 全维财务趋势分析")
    if df.empty: return

    df_cum, df_single = process_financial_data(df)

    c1, c2 = st.columns(2)
    with c1:
        label_map = {m['id']: m['label'] for m in METRIC_MAPPING}
        available_cols = [c for c in label_map.keys() if c in df.columns]
        selected_metric_key = st.selectbox("选择财务指标", available_cols, format_func=lambda x: f"{label_map[x]} ({x})")
    with c2:
        view_mode = st.radio("视角", ["单季度 (QoQ/YoY)", "TTM (长期趋势)", "年度 (FY)"], horizontal=True)

    metric_label = label_map[selected_metric_key]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 数据准备 & 过滤空值
    plot_data = pd.DataFrame()
    val_col = ""
    yoy_col = ""
    qoq_col = ""

    if view_mode == "单季度 (QoQ/YoY)":
        plot_data = df_single[df_single['period'].isin(['Q1','Q2','Q3','Q4'])].copy()
        val_col = f"{selected_metric_key}_Single"
        yoy_col = f"{selected_metric_key}_Single_YoY"
        qoq_col = f"{selected_metric_key}_Single_QoQ"
    elif view_mode == "TTM (长期趋势)":
        plot_data = df_single.copy()
        val_col = f"{selected_metric_key}_TTM"
        yoy_col = f"{selected_metric_key}_TTM_YoY" # [新增] TTM YoY
    elif view_mode == "年度 (FY)":
        plot_data = df_cum[df_cum['period'] == 'FY'].copy()
        val_col = selected_metric_key
        yoy_col = f"{selected_metric_key}_YoY" # [新增] FY YoY

    # [优化] 过滤掉数值为 0 或 NaN 的行，防止图表断裂或显示无效点
    if not plot_data.empty and val_col in plot_data.columns:
        plot_data = plot_data[plot_data[val_col].notna() & (plot_data[val_col] != 0)].sort_values('report_date')
        
        x = plot_data['year'].astype(str) + " " + plot_data['period']
        y_bar = plot_data[val_col]
        
        # 绘制主数值
        if view_mode == "TTM (长期趋势)":
             fig.add_trace(go.Scatter(x=x, y=y_bar, name=f"{metric_label}", fill='tozeroy'), secondary_y=False)
        else:
             fig.add_trace(go.Bar(x=x, y=y_bar, name=f"{metric_label}", text=y_bar.apply(format_large_number), textposition='auto'), secondary_y=False)

        # 绘制增长率 (YoY)
        if yoy_col in plot_data.columns:
            y_yoy = plot_data[yoy_col]
            fig.add_trace(go.Scatter(x=x, y=y_yoy, name="同比增速 (YoY)", mode='lines+markers', line=dict(color='orange')), secondary_y=True)

        # 绘制增长率 (QoQ - 仅单季)
        if view_mode == "单季度 (QoQ/YoY)" and qoq_col in plot_data.columns:
            y_qoq = plot_data[qoq_col]
            fig.add_trace(go.Scatter(x=x, y=y_qoq, name="环比增速 (QoQ)", mode='lines+markers', line=dict(color='green', dash='dot')), secondary_y=True)

    fig.update_layout(title=f"{metric_label} 趋势", hovermode="x unified", legend=dict(orientation="h", y=1.02))
    fig.update_yaxes(title_text="金额", secondary_y=False)
    fig.update_yaxes(title_text="增长率", tickformat=".1%", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)
    
    # 详细数据表
    if not plot_data.empty:
        cols = ['year', 'period', val_col]
        if yoy_col in plot_data.columns: cols.append(yoy_col)
        if view_mode == "单季度 (QoQ/YoY)" and qoq_col in plot_data.columns: cols.append(qoq_col)
        
        df_show = plot_data[cols].copy()
        # 格式化
        if val_col in df_show.columns:
            df_show[val_col] = df_show[val_col].apply(format_large_number)
        
        fmt_dict = {c: "{:.2%}" for c in df_show.columns if 'YoY' in c or 'QoQ' in c}
        st.dataframe(df_show.style.format(fmt_dict, na_rep="-"), use_container_width=True)
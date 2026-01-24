import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from modules.config import FINANCIAL_METRICS
from modules.db import get_financial_records, save_financial_record, save_company_meta, get_company_meta, get_market_history
from modules.data_fetcher import get_fetcher


def _filter_by_time_window(df: pd.DataFrame, time_window: str, date_col: str = 'date') -> pd.DataFrame:
    """根据时间窗口过滤数据"""
    if time_window == "全部历史" or df.empty:
        return df
    
    window_map = {
        "1年": 365,
        "3年": 3 * 365,
        "5年": 5 * 365,
        "10年": 10 * 365
    }
    
    if time_window in window_map:
        cutoff_date = datetime.now() - timedelta(days=window_map[time_window])
        # 确保日期列是 datetime 类型
        if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
            df[date_col] = pd.to_datetime(df[date_col])
        return df[df[date_col] >= cutoff_date]
    
    return df


def _add_report_date_vlines(fig: go.Figure, records: list, df_date_range: pd.DataFrame, date_col: str = 'date'):
    """在图表中添加财报发布日垂直虚线（使用shape避免Timestamp兼容性问题）"""
    if not records or df_date_range.empty:
        return
    
    # 获取图表的日期范围
    min_date = df_date_range[date_col].min()
    max_date = df_date_range[date_col].max()
    
    # 获取 y 轴范围用于标注位置
    y_col = [c for c in df_date_range.columns if c not in [date_col, 'ticker', 'volume']]
    if y_col:
        y_max = df_date_range[y_col[0]].max() if y_col[0] in df_date_range.columns else 100
    else:
        y_max = 100
    
    for r in records:
        report_date_str = r.get('report_date', '')
        if not report_date_str:
            continue
        
        report_date = pd.to_datetime(report_date_str)
        
        # 只添加在图表日期范围内的标线
        if min_date <= report_date <= max_date:
            year = r.get('year', '')
            period = r.get('period', '')
            label = f"{year} {period}" if year and period else ""
            
            # 使用 add_shape 绘制垂直线（避免 add_vline 的 annotation 兼容性问题）
            fig.add_shape(
                type="line",
                x0=report_date,
                x1=report_date,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="rgba(128, 128, 128, 0.4)", width=1, dash="dash")
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


def render_entry_tab(selected_company, unit_label):
    st.subheader(f"📝 {selected_company} - 财务数据录入 (SQLite 版)")
    
    # --- 1. 市场数据管理 (自动同步 & 可视化) ---
    with st.expander("☁️ 市场数据管理 (Market Data)", expanded=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.info("包含: 每日收盘价, 市值, PE TTM (需结合财报), EPS TTM")
        with c2:
            if st.button("🚀 同步/更新市场数据"):
                with st.spinner("Syncing..."):
                    fetcher = get_fetcher()
                    res = fetcher.sync_market_data(selected_company)
                    if "Error" in res["msg"]:
                        st.error(res["msg"])
                    else:
                        st.success(f"同步成功! {res['msg']}")
                        st.rerun()

        # 展示已录入的市场数据详情
        df_market = get_market_history(selected_company)
        
        # 获取财报记录（用于添加垂直虚线）
        financial_records = get_financial_records(selected_company)
        
        if not df_market.empty:
            st.markdown("#### 📊 已录入市场数据概览")
            
            # 确保日期列是 datetime 类型
            if not pd.api.types.is_datetime64_any_dtype(df_market['date']):
                df_market['date'] = pd.to_datetime(df_market['date'])
            
            # --- 需求2: 时间窗口选择 ---
            time_window = st.selectbox(
                "📅 选择时间窗口",
                ["1年", "3年", "5年", "10年", "全部历史"],
                index=4,  # 默认全部历史
                key="market_time_window"
            )
            
            # 过滤数据
            df_filtered = _filter_by_time_window(df_market.copy(), time_window)
            
            if df_filtered.empty:
                st.warning(f"所选时间窗口 ({time_window}) 内无数据")
            else:
                latest = df_filtered.iloc[-1]
                earliest = df_filtered.iloc[0]
                
                # 数据统计
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("数据条数", f"{len(df_filtered)}")
                
                try:
                    earliest_date = earliest['date'].strftime('%Y-%m')
                    latest_date = latest['date'].strftime('%Y-%m')
                    m2.metric("时间跨度", f"{earliest_date} ~ {latest_date}")
                except:
                    m2.metric("时间跨度", "N/A")
                
                m3.metric("最新股价", f"{latest['close']:.2f}")
                
                # Safe PE formatting
                pe_value = latest.get('pe_ttm', None)
                if pe_value is not None and not pd.isna(pe_value):
                    m4.metric("最新 PE (TTM)", f"{pe_value:.2f}")
                else:
                    m4.metric("最新 PE (TTM)", "N/A")
                
                # 图表化展示
                tab_chart1, tab_chart2, tab_chart3 = st.tabs(["📉 股价历史", "📊 PE Band / TTM", "📈 市值趋势"])
                
                with tab_chart1:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df_filtered['date'], y=df_filtered['close'], name='Close'))
                    
                    # 需求3: 添加财报发布日垂直虚线
                    _add_report_date_vlines(fig, financial_records, df_filtered)
                    
                    fig.update_layout(
                        title="历史股价 (Close) - 虚线标记财报发布日", 
                        height=300, 
                        margin=dict(l=0, r=0, t=30, b=0)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                with tab_chart2:
                    # 只有当 PE 数据存在时才展示
                    df_pe = df_filtered.dropna(subset=['pe_ttm'])
                    if not df_pe.empty:
                        fig_pe = go.Figure()
                        fig_pe.add_trace(go.Scatter(x=df_pe['date'], y=df_pe['pe_ttm'], name='PE TTM', line=dict(color='orange')))
                        
                        # 需求3: 添加财报发布日垂直虚线
                        _add_report_date_vlines(fig_pe, financial_records, df_pe)
                        
                        fig_pe.update_layout(
                            title="PE Ratio (TTM) 历史走势 - 虚线标记财报发布日", 
                            height=300, 
                            margin=dict(l=0, r=0, t=30, b=0)
                        )
                        st.plotly_chart(fig_pe, use_container_width=True)
                    else:
                        st.caption("暂无 PE 数据 (需先录入财报以计算 EPS)")
                
                with tab_chart3:
                    if 'market_cap' in df_filtered.columns and df_filtered['market_cap'].notna().any():
                        fig_mc = go.Figure()
                        fig_mc.add_trace(go.Scatter(x=df_filtered['date'], y=df_filtered['market_cap']/1e9, name='Market Cap (B)'))
                        
                        # 需求3: 添加财报发布日垂直虚线
                        _add_report_date_vlines(fig_mc, financial_records, df_filtered)
                        
                        fig_mc.update_layout(
                            title="市值历史 (Billion) - 虚线标记财报发布日", 
                            height=300, 
                            margin=dict(l=0, r=0, t=30, b=0)
                        )
                        st.plotly_chart(fig_mc, use_container_width=True)
                    else:
                        st.caption("暂无市值数据")
        else:
            st.warning("暂无市场数据，请点击右上角'同步'按钮获取 (需科学上网)")

    st.markdown("---")

    # --- 2. 财务数据录入 (Input Grouping) ---
    st.markdown("#### ➕ 录入/编辑 财务报告")
    st.caption("系统将根据以下规则自动计算单季度数据：Q2=H1-Q1, Q3=Q9-H1, Q4=FY-Q9")
    
    # 自动检测是否已有数据 (先获取)
    existing_records = get_financial_records(selected_company)
    
    # 基础选择 - 不使用 form，这样可以实时响应变化
    c_base1, c_base2, c_base3 = st.columns(3)
    with c_base1:
        year_input = st.number_input("财年 (Year)", 2000, 2030, 2025, key="year_select")
    with c_base2:
        period_input = st.selectbox("累计周期", ["Q1", "H1", "Q9", "FY"], key="period_select")
    
    # 检测年份/周期是否发生变化，如果变化则清除表单缓存
    current_selection = f"{selected_company}_{year_input}_{period_input}"
    if 'last_selection' not in st.session_state:
        st.session_state.last_selection = current_selection
    
    if st.session_state.last_selection != current_selection:
        # 清除所有输入字段的缓存
        for m in FINANCIAL_METRICS:
            key_name = f"in_{m['id']}"
            if key_name in st.session_state:
                del st.session_state[key_name]
        if 'report_date_input' in st.session_state:
            del st.session_state['report_date_input']
        st.session_state.last_selection = current_selection
        st.rerun()  # 重新运行以应用新值
    
    # 查找匹配的已有数据
    existing_data = {}
    default_report_date = date.today()
    
    for r in existing_records:
        if r['year'] == year_input and r['period'] == period_input:
            existing_data = r
            # 回填财报披露日
            if r.get('report_date'):
                try:
                    default_report_date = pd.to_datetime(r['report_date']).date()
                except:
                    pass
            break
    
    with c_base3:
        # 使用动态 key 确保切换年份/周期时日期能正确回填
        report_date_key = f"{selected_company}_{year_input}_{period_input}_report_date"
        report_date_input = st.date_input("财报披露日", value=default_report_date, key=report_date_key)
    
    # 需求2: 自动获取市值快照
    df_market_for_snapshot = get_market_history(selected_company)
    auto_market_cap = None
    auto_close_price = None
    
    if not df_market_for_snapshot.empty:
        if not pd.api.types.is_datetime64_any_dtype(df_market_for_snapshot['date']):
            df_market_for_snapshot['date'] = pd.to_datetime(df_market_for_snapshot['date'])
        
        report_month = report_date_input.strftime('%Y-%m')
        month_data = df_market_for_snapshot[df_market_for_snapshot['date'].dt.strftime('%Y-%m') == report_month]
        
        if not month_data.empty:
            last_day = month_data.iloc[-1]
            auto_market_cap = last_day.get('market_cap', None)
            auto_close_price = last_day.get('close', None)
            
            if auto_market_cap is not None and auto_close_price is not None:
                try:
                    mc_display = float(auto_market_cap) / 1e9
                    price_display = float(auto_close_price)
                    st.success(f"📊 已自动获取 {report_month} 月末市值: {mc_display:.2f}B，收盘价: {price_display:.2f}")
                except (TypeError, ValueError):
                    pass
            
    if existing_data:
        st.info(f"💡 检测到 {year_input} {period_input} 已有数据，已自动回填（含财报披露日）。")

    # 动态 key 前缀：包含年份和周期，确保切换时刷新数据
    key_prefix = f"{selected_company}_{year_input}_{period_input}"

    # 动态表单 (按新的 Category 分组)
    with st.form(f"financial_form_{key_prefix}"):
        # 1. 按类别分组
        grouped_metrics = {}
        for m in FINANCIAL_METRICS:
            cat = m.get('category', '其他')
            if cat not in grouped_metrics:
                grouped_metrics[cat] = []
            grouped_metrics[cat].append(m)
        
        # 2. 渲染表单 - 使用新的类别顺序
        input_values = {}
        
        # 导入类别顺序
        from modules.config import CATEGORY_ORDER
        sorted_cats = sorted(grouped_metrics.keys(), 
                            key=lambda x: CATEGORY_ORDER.index(x) if x in CATEGORY_ORDER else 99)
        
        for cat in sorted_cats:
            is_expanded = (cat == "关键指标")
            with st.expander(f"📌 {cat}", expanded=is_expanded):
                cols = st.columns(3)
                metrics = grouped_metrics[cat]
                for i, m in enumerate(metrics):
                    # 获取默认值并确保是有效数值
                    default_val = existing_data.get(m['id'])
                    
                    # 处理 None 和 NaN 值
                    if default_val is None:
                        default_val = m.get('default', 0.0)
                    
                    # 安全转换为 float，处理 NaN
                    try:
                        default_val = float(default_val)
                        if pd.isna(default_val) or np.isnan(default_val):
                            default_val = 0.0
                    except (TypeError, ValueError):
                        default_val = 0.0
                    
                    with cols[i % 3]:
                        # 使用动态 key 包含年份和周期
                        val = st.number_input(
                            f"{m['label']}", 
                            value=default_val,
                            format=m.get('format', '%.2f'),
                            key=f"{key_prefix}_{m['id']}",
                            help=m.get('help', '')
                        )
                        input_values[m['id']] = val
        
        st.markdown("---")
        submitted = st.form_submit_button("💾 保存/更新数据", use_container_width=True)
        
        if submitted:
            record = {
                "ticker": selected_company,
                "year": int(year_input),
                "period": period_input,
                "report_date": report_date_input.strftime("%Y-%m-%d")
            }
            record.update(input_values)
            
            # 注意：不再添加 AutoMarketCap/AutoClosePrice 到数据库
            # 市值快照信息通过关联 market_daily 表获取
            
            if save_financial_record(record):
                st.success(f"已保存 {selected_company} {year_input} {period_input}")
                st.rerun()
            else:
                st.error("保存失败")

    # 3. 历史数据表格展示
    if existing_records:
        st.markdown("### 📋 已录入历史数据列表")
        df_show = pd.DataFrame(existing_records)
        p_map = {"Q1":1, "H1":2, "Q9":3, "FY":4}
        df_show['s'] = df_show['period'].map(p_map)
        df_show = df_show.sort_values(['year', 's'], ascending=[False, False])
        
        # 动态展示所有配置的列
        all_metric_ids = [m['id'] for m in FINANCIAL_METRICS]
        valid_cols = [c for c in all_metric_ids if c in df_show.columns]
        
        cols_to_show = ['year', 'period', 'report_date'] + valid_cols
        st.dataframe(df_show[cols_to_show], use_container_width=True)
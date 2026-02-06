import streamlit as st
import os
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from modules.core.config import FINANCIAL_METRICS, CATEGORY_ORDER
from modules.core.db import get_financial_records, save_financial_record, delete_financial_record, save_company_meta, get_company_meta, get_market_history
from modules.data.data_fetcher import get_fetcher
from modules.data.json_importer import parse_financial_json, validate_json_structure, import_json_to_database


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
                index=2,  # 默认 5年
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
                    st.plotly_chart(fig, width="stretch")
                    
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
                        st.plotly_chart(fig_pe, width="stretch")
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
                        st.plotly_chart(fig_mc, width="stretch")
                    else:
                        st.caption("暂无市值数据")
        else:
            st.warning("暂无市场数据，请点击右上角'同步'按钮获取 (需科学上网)")

    st.markdown("---")

    # --- 2. 财务数据录入 (Input Grouping) ---
    st.markdown("#### ➕ 录入/编辑 财务报告")
    
    # 获取公司元数据（用于判断地区）
    meta = get_company_meta(selected_company)
    region = meta.get('region', 'US')
    sector = meta.get('sector', 'Unknown')
    industry = meta.get('industry', 'Unknown')
    
    st.info(f"📍 公司信息: {meta.get('name', selected_company)} | 地区: {region} | 行业: {sector} / {industry}")
    
    # 地区化说明
    if region == 'US':
        st.caption("🇺🇸 美国股市：使用单季度数据录入 (Q1, Q2, Q3, Q4)")
    else:
        st.caption(f"{'🇨🇳' if region == 'CN' else '🇭🇰' if region == 'HK' else '🇯🇵' if region == 'JP' else '🇹🇼'} 累积季度数据：Q2=H1-Q1, Q3=Q9-H1, Q4=FY-Q9")
    
    # --- 批量导入选项 ---
    with st.expander("📋 批量导入 (JSON)", expanded=False):
        st.markdown("**从 JSON 文件批量导入财务数据**")
        st.caption("💡 系统自动识别报表类型和数据单位（亿/万），支持利润表、资产负债表、现金流量表、关键指标的混合导入")
        
        json_input = st.text_area(
            "粘贴 JSON 数据",
            height=300,
            placeholder='{\n  "headers": ["2024/Q1", "2024/Q2", ...],\n  "data": [\n    {"metric": "总收入", "values": ["565.17亿", ...]},\n    {"metric": "截止日期", "values": ["2023/09/30", ...]}\n  ]\n}',
            key="json_import_input"
        )
        
        # Template Download Button
        template_path = os.path.join("upload", "financial_data_template.json")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template_data = f.read()
            st.download_button(
                label="📥 下载 JSON 模版文件",
                data=template_data,
                file_name="financial_data_template.json",
                mime="application/json",
                help="点击下载标准 JSON 格式模版，填写后粘贴到上框"
            )

        
        col_preview, col_import = st.columns(2)
        
        with col_preview:
            if st.button("🔍 预览数据", key="btn_preview"):
                if json_input:
                    try:
                        json_data = json.loads(json_input)
                        is_valid, msg = validate_json_structure(json_data)
                        
                        if is_valid:
                            records = parse_financial_json(json_data, selected_company)
                            st.success(f"✅ {msg}，解析到 {len(records)} 条记录")
                            
                            # 显示预览表格
                            if records:
                                preview_df = pd.DataFrame(records[:5])
                                st.dataframe(preview_df, use_container_width=True)
                        else:
                            st.error(f"❌ {msg}")
                    except json.JSONDecodeError as e:
                        st.error(f"❌ JSON 格式错误: {e}")
                else:
                    st.warning("请先粘贴 JSON 数据")
        
        with col_import:
            if st.button("💾 导入数据库", key="btn_import", type="primary"):
                if json_input:
                    try:
                        json_data = json.loads(json_input)
                        success_count, errors = import_json_to_database(
                            json_data, selected_company
                        )
                        
                        if success_count > 0:
                            st.success(f"✅ 成功导入 {success_count} 条记录")
                        
                        if errors:
                            for err in errors[:5]:
                                st.warning(err)
                        
                        if success_count > 0:
                            st.rerun()
                    except json.JSONDecodeError as e:
                        st.error(f"❌ JSON 格式错误: {e}")
                else:
                    st.warning("请先粘贴 JSON 数据")
    
    # --- 批量管理选项 ---
    with st.expander("🛠️ 批量管理/修正数据 (Batch Editor)", expanded=False):
        st.caption("💡 可在此直接修改或删除历史数据。勾选 'delete' 列并点击保存即可删除对应行。")
        
        batch_records = get_financial_records(selected_company)
        
        if batch_records:
            # 准备数据供编辑器使用
            df_edit = pd.DataFrame(batch_records)
            
            if 'year' in df_edit.columns:
                # 确保关键列在最前
                key_cols = ['year', 'period', 'report_date']
                metric_col_ids = [m['id'] for m in FINANCIAL_METRICS if m['id'] in df_edit.columns]
                
                # 初始化 delete 列
                df_edit['delete'] = False
                
                column_config = {
                    "year": st.column_config.NumberColumn("年份", disabled=True),
                    "period": st.column_config.TextColumn("期间", disabled=True),
                    "delete": st.column_config.CheckboxColumn("删除?", help="勾选以删除此记录"),
                    "report_date": st.column_config.TextColumn("披露日期"),
                }
                
                # 动态添加指标列配置
                for m in FINANCIAL_METRICS:
                    if m['id'] in metric_col_ids:
                        column_config[m['id']] = st.column_config.NumberColumn(
                            m['label'],
                            format=m.get('format', "%.2f")
                        )
                
                # 列排序
                col_order = ['delete'] + [k for k in key_cols if k in df_edit.columns] + metric_col_ids
                
                edited_df = st.data_editor(
                    df_edit,
                    column_config=column_config,
                    column_order=col_order,
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed", 
                    key="batch_editor"
                )
                
                if st.button("💾 保存批量修改", type="primary"):
                    # 1. 处理删除
                    to_delete = edited_df[edited_df['delete'] == True]
                    del_count = 0
                    for _, row in to_delete.iterrows():
                        if delete_financial_record(row['ticker'], row['year'], row['period']):
                            del_count += 1
                    
                    # 2. 处理修改 (排除已删除的行)
                    to_update = edited_df[edited_df['delete'] == False]
                    
                    update_count = 0
                    for _, row in to_update.iterrows():
                        record = row.to_dict()
                        if 'delete' in record: del record['delete']
                        save_financial_record(record)
                        update_count += 1
                    
                    st.success(f"操作完成: 删除 {del_count} 条, 更新 {update_count} 条")
                    st.rerun()
            else:
                 st.error("数据异常：缺失年份列")
        else:
            st.info("暂无数据可编辑")

    # 自动检测是否已有数据 (先获取)
    existing_records = get_financial_records(selected_company)
    
    # 基础选择 - 不使用 form，这样可以实时响应变化
    c_base1, c_base2, c_base3 = st.columns(3)
    with c_base1:
        year_input = st.number_input("财年 (Year)", 2000, 2030, 2025, key="year_select")
    with c_base2:
        # 根据地区选择周期选项
        if region == 'US':
            # 美国：单季度输入 (Q1, Q2, Q3, Q4)
            period_options = ["Q1", "Q2", "Q3", "Q4"]
            period_label = "季度 (Quarter)"
        else:
            # 中国/香港等：累积季度输入 (Q1, H1, Q9, FY)
            period_options = ["Q1", "H1", "Q9", "FY"]
            period_label = "累计周期"
        
        period_input = st.selectbox(period_label, period_options, key="period_select")
    
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
        default_date_str = default_report_date.strftime("%Y-%m-%d")
        
        # 支持手动输入日期 (YYYY-MM-DD)
        date_str = st.text_input(
            "财报披露日 (YYYY-MM-DD)", 
            value=default_date_str, 
            key=report_date_key,
            help="格式: 2024-01-15"
        )
        
        # 解析日期
        try:
            report_date_input = pd.to_datetime(date_str).date()
        except:
            st.warning(f"日期格式错误，请使用 YYYY-MM-DD 格式")
            report_date_input = default_report_date
    
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
        from modules.core.config import CATEGORY_ORDER
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
        submitted = st.form_submit_button("💾 保存/更新数据", width="stretch")
        
        if submitted:
            record = {
                "ticker": selected_company,
                "year": int(year_input),
                "period": period_input,
                "report_date": report_date_input.strftime("%Y-%m-%d")
            }
            
            # 处理比率类指标：将 0 值视为数据缺失 (None)
            ratio_metrics = [
                'GrossMargin', 'OperatingMargin', 'EBITMargin', 'NetProfitMargin',
                'EBITDAMargin', 'EffectiveTaxRate', 'ROE', 'ROA', 'ROIC',
                'FCFToRevenue', 'FCFToNetIncome'
            ]
            
            for key, val in input_values.items():
                if key in ratio_metrics and val == 0.0:
                    # 比率类指标：0 表示未填写，保存为 None
                    record[key] = None
                else:
                    record[key] = val
            
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
        # 扩展排序映射以支持单季度和累积季度
        p_map = {
            "Q1": 1, 
            "Q2": 2, "H1": 2, 
            "Q3": 3, "Q9": 3, 
            "Q4": 4, "FY": 4
        }
        # 使用 map 时处理未知 key (设为 0)
        df_show['s'] = df_show['period'].map(p_map).fillna(0)
        df_show = df_show.sort_values(['year', 's'], ascending=[False, False])
        
        # 动态展示所有配置的列
        all_metric_ids = [m['id'] for m in FINANCIAL_METRICS]
        valid_cols = [c for c in all_metric_ids if c in df_show.columns]
        
        cols_to_show = ['year', 'period', 'report_date'] + valid_cols
        st.dataframe(df_show[cols_to_show], width="stretch")
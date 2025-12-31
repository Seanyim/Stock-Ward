import streamlit as st
import pandas as pd
from data_manager import save_data
from modules.config import FINANCIAL_METRICS

def render_entry_tab(selected_company, data_store, unit_label):
    st.subheader(f"{selected_company} - 累计季报数据录入")
    
    records = data_store[selected_company]["records"]
    
    # --- 1. 基础字段选择 ---
    c_base1, c_base2 = st.columns(2)
    with c_base1:
        year_input = st.number_input("财年 (Year)", 2000, 2030, 2025, key="entry_year")
    with c_base2:
        period_input = st.selectbox("报告周期 (累计)", ["Q1", "H1", "Q9", "FY"], key="entry_period")
    
    st.markdown("---")
    
    # --- 自动查找现有数据 (回显) ---
    existing_record = {}
    for r in records:
        if r['Year'] == int(year_input) and r['Period'] == period_input:
            existing_record = r
            break
            
    if existing_record:
        st.info(f"💡 检测到 {year_input} {period_input} 已有数据，已自动加载。")
    
    # --- 2. 动态生成输入框 ---
    input_values = {}
    cols = st.columns(3)
    
    for i, metric in enumerate(FINANCIAL_METRICS):
        current_col = cols[i % 3]
        metric_id = metric['id']
        
        current_val = existing_record.get(metric_id, metric['default'])
        
        with current_col:
            label_text = f"{metric['label']} ({unit_label})" if "EPS" not in metric_id and "Rate" not in metric_id else metric['label']
            
            widget_key = f"input_{metric_id}_{year_input}_{period_input}"
            
            # 输入框继续使用 config 中的 %.3f 格式
            val = st.number_input(
                label_text,
                min_value=0.0,
                value=float(current_val),
                format=metric.get('format', '%.3f'), 
                help=metric.get('help', ''),
                key=widget_key
            )
            input_values[metric_id] = val

    st.markdown("---")

    # --- 3. 保存逻辑 ---
    if st.button("保存数据", type="primary"):
        new_rec = {
            "Year": int(year_input),
            "Period": period_input,
        }
        new_rec.update(input_values)
        
        updated = [r for r in records if not (r['Year'] == int(year_input) and r['Period'] == period_input)]
        updated.append(new_rec)
        
        data_store[selected_company]["records"] = updated
        save_data(data_store)
        st.success(f"已保存 {year_input} {period_input}")
        st.rerun()
        
    # --- 4. 表格展示 (修复显示Bug) ---
    if records:
        df = pd.DataFrame(records)
        p_map = {"Q1":1, "H1":2, "Q9":3, "FY":4}
        df['s'] = df['Period'].map(p_map)
        df = df.sort_values(['Year', 's'], ascending=[False, False]).drop(columns=['s'])
        
        # 动态列
        base_cols = ["Year", "Period"]
        metric_cols = [m["id"] for m in FINANCIAL_METRICS if m["id"] in df.columns]
        
        # [修复核心] 构建 pandas 专用的格式化字典
        # 将 config 中的 "%.3f" 转换为 "{:.3f}"
        pandas_format_dict = {}
        for m in FINANCIAL_METRICS:
            if m["id"] in df.columns:
                # 获取配置的格式，例如 "%.3f"
                fmt = m.get("format", "%.3f")
                # 替换为 python 格式: "{:.3f}"
                pandas_fmt = fmt.replace("%", "{:") + "}"
                pandas_format_dict[m["id"]] = pandas_fmt
        
        st.dataframe(
            df[base_cols + metric_cols].style.format(pandas_format_dict),
            use_container_width=True
        )
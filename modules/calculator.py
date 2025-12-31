import pandas as pd
import numpy as np
from modules.config import GROWTH_METRIC_KEYS # [修改点] 只导入需要计算增长的 Key
# 常量定义
PERIOD_MAP_SORT = {"Q1": 1, "H1": 2, "Q9": 3, "FY": 4}
PERIOD_MAP_DISPLAY = {"Q1": "Q1", "H1": "Q2", "Q9": "Q3", "FY": "Q4"}

def process_financial_data(df):
    if df.empty:
        return df, df

    df = df.copy()
    df['Sort_Key'] = df['Period'].map(PERIOD_MAP_SORT)
    df = df.sort_values(by=['Year', 'Sort_Key']).reset_index(drop=True)
    
    df_single = df.copy()
    df_single['Quarter_Name'] = df_single['Period'].map(PERIOD_MAP_DISPLAY)

    # [关键修改] 只遍历需要计算增长率的指标
    # 那些 calc_growth=False 的指标（如 Tax, Debt）将不会生成 _Single, _YoY, _TTM 列
    # 从而节省计算资源，也不会污染图表选项
    target_metrics = GROWTH_METRIC_KEYS 
    valid_metrics = [m for m in target_metrics if m in df.columns]

    for metric in valid_metrics:
        # A. 单季值
        df_single = _calculate_single_quarter_value(df_single, metric)
        # B. 累计 YoY
        df = _calculate_yoy(df, metric, is_single=False)
        # C. 单季 YoY
        df_single = _calculate_yoy(df_single, f"{metric}_Single", is_single=True)
        # D. 单季 QoQ
        df_single = _calculate_qoq(df_single, f"{metric}_Single")
        
        # E. TTM 计算
        ttm_col = f"{metric}_TTM"
        df_single[ttm_col] = df_single[f"{metric}_Single"].rolling(window=4).sum()
        df_single = _calculate_yoy(df_single, ttm_col, is_single=True)
    
    # [新增] 对于不需要计算增长率的指标 (如 Total_Debt)，我们也需要把它们保留在 df_single 里
    # 方便 WACC 模块调用 "Total_Debt_Single" (虽然对于存量数据 Single=Cumulative)
    from modules.config import ALL_METRIC_KEYS
    non_growth_metrics = [m for m in ALL_METRIC_KEYS if m not in GROWTH_METRIC_KEYS and m in df.columns]
    
    for metric in non_growth_metrics:
        # 对于存量数据(债务/市值)，单季度数值 = 当期报告数值 (不需要 diff)
        # 我们简单地把原值复制过去，统一命名格式方便调用
        df_single[f"{metric}_Single"] = df_single[metric]
        # TTM 对存量数据通常取平均或期末值，这里简化处理取期末值
        df_single[f"{metric}_TTM"] = df_single[metric]

    return df, df_single
# ==========================================
#           内部通用核心函数 (封装)
# ==========================================

def _calculate_single_quarter_value(df, metric_name):
    """
    通用函数：将累计数据拆解为单季度数据
    逻辑：在同一年内，当前周期累计值 - 上个周期累计值 = 单季值
    利用 GroupBy + Diff 实现向量化计算，无需手写 if/else
    """
    target_col = f"{metric_name}_Single"
    
    # 1. 按年分组，计算差分 (Diff)
    # diff() 会计算当前行与上一行的差。
    # Q1 行因为没有上一行，会变成 NaN，H1 行会变成 H1-Q1
    df[target_col] = df.groupby('Year')[metric_name].diff()
    
    # 2. 修正 Q1 数据
    # Q1 的单季值就是累计值本身，diff() 造成的 NaN 需要用原始值填充
    mask_q1 = df['Period'] == 'Q1'
    df.loc[mask_q1, target_col] = df.loc[mask_q1, metric_name]
    
    return df

def _calculate_yoy(df, col_name, is_single=False):
    """
    通用函数：计算同比 (Year-over-Year)
    逻辑：通过 Self-Merge (自连接) 匹配去年的同周期数据
    """
    # 构造用于匹配去年的临时表
    prev_year_df = df.copy()
    prev_year_df['Year'] = prev_year_df['Year'] + 1  # 变成了"明年"的年份，用于和当前年份匹配
    
    # 匹配键：年份 + (Period 或 Quarter_Name)
    join_keys = ['Year', 'Quarter_Name'] if is_single else ['Year', 'Period']
    
    # 只取需要的列进行合并，减少内存消耗
    prev_year_subset = prev_year_df[join_keys + [col_name]]
    
    # 合并
    merged = pd.merge(
        df, 
        prev_year_subset, 
        on=join_keys, 
        how='left', 
        suffixes=('', '_PrevYear')
    )
    
    # 计算增长率公式: (Current - Prev) / |Prev|
    # 使用 abs() 处理分母，防止负利润导致的增长率符号错误（可选，视财务偏好而定）
    prev_val = merged[f'{col_name}_PrevYear']
    curr_val = merged[col_name]
    
    growth_col = f"{col_name}_YoY"
    df[growth_col] = (curr_val - prev_val) / prev_val.abs()
    
    return df

def _calculate_qoq(df, col_name):
    """
    通用函数：计算环比 (Quarter-over-Quarter)
    逻辑：直接利用 pandas 的 pct_change()
    """
    # 确保按时间绝对顺序排序 (2023 Q4 -> 2024 Q1)
    df = df.sort_values(by=['Year', 'Sort_Key'])
    
    # 计算环比
    growth_col = f"{col_name}_QoQ"
    df[growth_col] = df[col_name].pct_change()
    
    return df
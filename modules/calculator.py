import pandas as pd
import numpy as np
from modules.config import METRIC_MAPPING

PERIOD_MAP_SORT = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "H1": 2, "Q9": 3, "FY": 5}

def process_financial_data(df):
    if df.empty: return df, df

    df = df.copy()
    df = df[df['period'].isin(PERIOD_MAP_SORT.keys())]
    df['Sort_Key'] = df['period'].map(PERIOD_MAP_SORT)
    df = df.sort_values(by=['year', 'Sort_Key']).reset_index(drop=True)
    
    df_single = df.copy()
    
    valid_metrics = [m['id'] for m in METRIC_MAPPING if m['id'] in df.columns]

    for metric in valid_metrics:
        # 1. 单季值
        df_single[f"{metric}_Single"] = df_single[metric]
        
        # 2. TTM 计算
        ttm_col = f"{metric}_TTM"
        is_flow = metric not in ["Total_Assets", "Total_Liabilities", "Total_Equity", "Cash", "Total_Debt"]
        mask_q = df_single['period'].isin(['Q1', 'Q2', 'Q3', 'Q4'])
        
        if is_flow:
            df_single.loc[mask_q, ttm_col] = df_single.loc[mask_q, metric].rolling(window=4, min_periods=4).sum()
        else:
            df_single.loc[mask_q, ttm_col] = df_single.loc[mask_q, metric]

        # 3. YoY 计算 (对 Single, TTM 和 原始df(年度) 都计算)
        df = _calculate_yoy(df, metric) # 年度 YoY
        df_single = _calculate_yoy(df_single, f"{metric}_Single") # 单季 YoY
        if is_flow:
            df_single = _calculate_yoy(df_single, ttm_col) # TTM YoY

        # 4. QoQ 计算
        df_single = _calculate_qoq(df_single, f"{metric}_Single")

    return df, df_single

def _calculate_yoy(df, col_name):
    prev_df = df.copy()
    prev_df['year'] = prev_df['year'] + 1
    # 匹配键：year + period (确保 Q1 对 Q1, FY 对 FY)
    if col_name not in df.columns: return df
    
    merged = pd.merge(df, prev_df[['year', 'period', col_name]], on=['year', 'period'], how='left', suffixes=('', '_Prev'))
    curr = merged[col_name]
    prev = merged[f'{col_name}_Prev']
    df[f"{col_name}_YoY"] = (curr - prev) / prev.replace(0, np.nan).abs()
    return df

def _calculate_qoq(df, col_name):
    if col_name not in df.columns: return df
    df_sorted = df.sort_values(by=['year', 'Sort_Key'])
    mask = df_sorted['period'].isin(['Q1', 'Q2', 'Q3', 'Q4'])
    subset = df_sorted.loc[mask].copy()
    
    subset[f'{col_name}_PrevQ'] = subset[col_name].shift(1)
    # 只有当上一行确实是上个季度时才算有效 (简单处理: 均视为连续)
    curr = subset[col_name]
    prev = subset[f'{col_name}_PrevQ']
    subset[f"{col_name}_QoQ"] = (curr - prev) / prev.replace(0, np.nan).abs()
    
    df[f"{col_name}_QoQ"] = np.nan
    df.loc[subset.index, f"{col_name}_QoQ"] = subset[f"{col_name}_QoQ"]
    return df
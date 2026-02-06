import pandas as pd
import numpy as np
from modules.core.config import GROWTH_METRIC_KEYS, ALL_METRIC_KEYS

# 数据库存储的周期映射
PERIOD_SORT_MAP_CUMULATIVE = {"Q1": 1, "H1": 2, "Q9": 3, "FY": 4}  # 累积季度 (CN/HK)
PERIOD_SORT_MAP_SINGLE = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}  # 单季度 (US)


def detect_data_format(df: pd.DataFrame) -> str:
    """检测数据格式是单季度还是累积季度
    
    Returns:
        "single" - 单季度格式 (Q1, Q2, Q3, Q4)
        "cumulative" - 累积季度格式 (Q1, H1, Q9, FY)
    """
    if 'period' not in df.columns:
        return "unknown"
    
    periods = set(df['period'].unique())
    
    # 检测是否包含 H1, Q9, FY (累积季度特征)
    cumulative_markers = {'H1', 'Q9', 'FY'}
    if periods & cumulative_markers:
        return "cumulative"
    
    # 检测是否包含 Q2, Q3, Q4 (单季度特征)
    single_markers = {'Q2', 'Q3', 'Q4'}
    if periods & single_markers:
        return "single"
    
    # 只有 Q1，无法判断，默认单季度
    return "single"


def process_financial_data(df_raw):
    """
    核心计算引擎：处理财务数据
    
    自动检测数据格式：
    - 单季度格式 (US): 直接使用 Q1-Q4 数据
    - 累积季度格式 (CN/HK): 转换 Q1/H1/Q9/FY → Q1/Q2/Q3/Q4
    
    输入: df_raw (包含 year, period, Revenue 等值)
    输出: df_cum (原始数据), df_single (单季度数据 Q1-Q4)
    """
    if df_raw.empty:
        return df_raw, df_raw

    df = df_raw.copy()
    
    # 检测数据格式
    data_format = detect_data_format(df)
    
    # 根据格式选择排序映射
    if data_format == "cumulative":
        sort_map = PERIOD_SORT_MAP_CUMULATIVE
    else:
        sort_map = PERIOD_SORT_MAP_SINGLE
    
    # 1. 基础清理与排序
    if 'period' in df.columns:
        df['Sort_Key'] = df['period'].map(sort_map)
        df = df.sort_values(by=['year', 'Sort_Key'])
    
    # df_cum 就是原始数据
    df_cum = df.copy()
    
    # --- 根据数据格式处理 ---
    if data_format == "single":
        # 单季度格式：直接使用，只需计算 TTM 和 YoY
        df_single = _process_single_quarter_data(df)
    else:
        # 累积季度格式：需要转换为单季度
        df_single = _process_cumulative_data(df)
    
    return df_cum, df_single


def _process_single_quarter_data(df: pd.DataFrame) -> pd.DataFrame:
    """处理单季度格式数据 (US)"""
    df_single = df.copy()
    
    # 排序
    df_single['Sort_Key'] = df_single['period'].apply(
        lambda x: int(x[1]) if isinstance(x, str) and len(x) > 1 and x[1].isdigit() else 0
    )
    df_single = df_single.sort_values(by=['year', 'Sort_Key']).reset_index(drop=True)
    
    # 计算 TTM 和 YoY
    for metric in GROWTH_METRIC_KEYS:
        if metric not in df_single.columns:
            continue
        
        # 确保数值列是 numeric 类型，None 值转为 NaN
        df_single[metric] = pd.to_numeric(df_single[metric], errors='coerce')
        
        # TTM (滚动4季求和)
        df_single[f"{metric}_TTM"] = df_single[metric].rolling(4, min_periods=1).sum()
        
        # YoY (同比去年) - 使用 where 避免除以0或 NaN
        prev_val = df_single[metric].shift(4)
        prev_abs = prev_val.abs().replace(0, np.nan)  # 避免除以0
        df_single[f"{metric}_YoY"] = (df_single[metric] - prev_val) / prev_abs
        
        # TTM YoY
        prev_ttm = df_single[f"{metric}_TTM"].shift(4)
        prev_ttm_abs = prev_ttm.abs().replace(0, np.nan)
        df_single[f"{metric}_TTM_YoY"] = (df_single[f"{metric}_TTM"] - prev_ttm) / prev_ttm_abs
    
    return df_single


def _process_cumulative_data(df: pd.DataFrame) -> pd.DataFrame:
    """处理累积季度格式数据 (CN/HK) - 转换为单季度"""
    single_records = []
    
    if 'year' not in df.columns:
        return pd.DataFrame()
    
    years = df['year'].unique()
    
    for year in years:
        year_data = df[df['year'] == year].set_index('period')
        
        def get_val(p, m):
            return year_data.loc[p, m] if p in year_data.index else np.nan

        # 准备4个季度的容器
        q_data = {
            'Q1': {'period': 'Q1', 'year': year},
            'Q2': {'period': 'Q2', 'year': year},
            'Q3': {'period': 'Q3', 'year': year},
            'Q4': {'period': 'Q4', 'year': year}
        }
        
        # 填充日期 (若存在)
        if 'report_date' in df.columns:
            if 'Q1' in year_data.index: q_data['Q1']['report_date'] = year_data.loc['Q1', 'report_date']
            if 'H1' in year_data.index: q_data['Q2']['report_date'] = year_data.loc['H1', 'report_date']
            if 'Q9' in year_data.index: q_data['Q3']['report_date'] = year_data.loc['Q9', 'report_date']
            if 'FY' in year_data.index: q_data['Q4']['report_date'] = year_data.loc['FY', 'report_date']

        for metric in ALL_METRIC_KEYS:
            # 兼容性检查：确保列存在
            if metric not in df.columns:
                continue

            val_q1 = get_val('Q1', metric)
            val_h1 = get_val('H1', metric)
            val_q9 = get_val('Q9', metric)
            val_fy = get_val('FY', metric)
            
            if metric in GROWTH_METRIC_KEYS:
                # 流量指标 (营收/利润): 做减法
                q_data['Q1'][metric] = val_q1
                
                # Q2 = H1 - Q1
                if pd.notna(val_h1) and pd.notna(val_q1):
                    q_data['Q2'][metric] = val_h1 - val_q1
                else:
                    q_data['Q2'][metric] = np.nan
                    
                # Q3 = Q9 - H1
                if pd.notna(val_q9) and pd.notna(val_h1):
                    q_data['Q3'][metric] = val_q9 - val_h1
                else:
                    q_data['Q3'][metric] = np.nan
                    
                # Q4 = FY - Q9
                if pd.notna(val_fy) and pd.notna(val_q9):
                    q_data['Q4'][metric] = val_fy - val_q9
                else:
                    q_data['Q4'][metric] = np.nan
            else:
                # 存量指标 (债务/现金): 直接取期末值
                q_data['Q1'][metric] = val_q1
                q_data['Q2'][metric] = val_h1
                q_data['Q3'][metric] = val_q9
                q_data['Q4'][metric] = val_fy

        # 收集有效数据
        for q in ['Q1', 'Q2', 'Q3', 'Q4']:
            # 只要有一个关键指标非空，就认为该季度有效
            if any(pd.notna(q_data[q].get(m)) for m in GROWTH_METRIC_KEYS if m in df.columns):
                single_records.append(q_data[q])

    # 转换为 DataFrame
    df_single = pd.DataFrame(single_records)
    
    if df_single.empty:
        return df_single
    
    # 排序
    df_single['Sort_Key'] = df_single['period'].apply(lambda x: int(x[1]) if isinstance(x, str) and len(x) > 1 else 0)
    df_single = df_single.sort_values(by=['year', 'Sort_Key']).reset_index(drop=True)
    
    # 计算 TTM 和 YoY
    for metric in GROWTH_METRIC_KEYS:
        if metric not in df_single.columns:
            continue
        
        # TTM (滚动4季求和)
        df_single[f"{metric}_TTM"] = df_single[metric].rolling(4, min_periods=1).sum()
        
        # YoY (同比去年)
        prev_val = df_single[metric].shift(4)
        df_single[f"{metric}_YoY"] = (df_single[metric] - prev_val) / prev_val.abs()
        
        # TTM YoY
        prev_ttm = df_single[f"{metric}_TTM"].shift(4)
        df_single[f"{metric}_TTM_YoY"] = (df_single[f"{metric}_TTM"] - prev_ttm) / prev_ttm.abs()

    return df_single


# ==========================================
# V2.0 扩展：高级视图数据处理 (年度/累积/比率重算)
# ==========================================

# 比率计算公式映射 (分子, 分母, 乘数)
RATIO_DEFINITIONS = {
    "GrossMargin": ("GrossProfit", "TotalRevenue", 100),
    "OperatingMargin": ("OperatingProfit", "TotalRevenue", 100),
    "NetProfitMargin": ("NetIncomeToParent", "TotalRevenue", 100),
    "EBITMargin": ("OperatingProfit", "TotalRevenue", 100),  # 近似
    "EBITDAMargin": ("EBITDA", "TotalRevenue", 100),
    "EffectiveTaxRate": ("IncomeTaxExpense", "PreTaxIncome", 100),
    "ROE": ("NetIncomeToParent", "TotalEquity", 100),
    "ROA": ("NetIncome", "TotalAssets", 100),
    "FCFToRevenue": ("FreeCashFlow", "TotalRevenue", 100),
    "FCFToNetIncome": ("FreeCashFlow", "NetIncomeToParent", 100),
}

def recalculate_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """基于聚合后的绝对值重新计算比率指标"""
    cols = df.columns
    
    # 辅助：计算 EBITDA (如果缺失)
    # EBITDA = OperatingProfit + DepreciationAmortization (如果可用)
    # 这里简单近似 EBITDA = OperatingProfit for now unless we add D&A field
    if 'EBITDA' not in cols and 'OperatingProfit' in cols:
         # 如果有 D&A 字段则加上，否则暂用 OperatingProfit
         pass

    for ratio_name, (num, den, scale) in RATIO_DEFINITIONS.items():
        if num in cols and den in cols:
            # 避免除以 0, 并处理 NaN
            def calc_ratio(row):
                n = row.get(num, 0)
                d = row.get(den, 0)
                if pd.notna(d) and d != 0 and pd.notna(n):
                    return (n / d) * scale
                return np.nan
            df[ratio_name] = df.apply(calc_ratio, axis=1)
    return df

def get_view_data(df_single: pd.DataFrame, view_mode: str) -> pd.DataFrame:
    """
    根据视图模式处理数据
    view_mode: "single" (单季度), "cumulative" (累积季度), "annual" (年度)
    """
    if df_single.empty:
        return pd.DataFrame()

    if view_mode == "single":
        # 单季度：直接返回 (已包含 YoY)
        return df_single.copy()

    elif view_mode == "annual":
        # 年度数据：按 Year 聚合
        # 流量指标求和，存量指标取期末值
        agg_rules = {}
        
        # 识别基于 single df 的列
        # 注意：df_single 包含 TTM 列，聚合时应忽略 TTM 列，只聚合原始值
        base_cols = [c for c in df_single.columns if not str(c).endswith('_TTM') and not str(c).endswith('_YoY')]
        
        for col in base_cols:
            if col in ['year', 'period', 'report_date', 'Sort_Key']:
                continue
            if col in GROWTH_METRIC_KEYS: # 流量
                agg_rules[col] = 'sum'
            elif col in ALL_METRIC_KEYS: # 存量
                agg_rules[col] = 'last'
            
        # 确保包含 report_date
        if 'report_date' in df_single.columns:
            agg_rules['report_date'] = 'max' # 取年度最后一天
        
        if not agg_rules:
            return pd.DataFrame()

        # 聚合
        df_annual = df_single.groupby('year')[list(agg_rules.keys())].agg(agg_rules).reset_index()
        
        # 重新计算比率
        df_annual = recalculate_ratios(df_annual)
        
        # 设置 period 为 FY
        df_annual['period'] = 'FY'
        
        # 计算 YoY (基于年度)
        df_annual = df_annual.sort_values('year')
        for col in df_annual.columns:
            if (col in GROWTH_METRIC_KEYS or col in RATIO_DEFINITIONS or col in ALL_METRIC_KEYS) and pd.api.types.is_numeric_dtype(df_annual[col]):
                prev = df_annual[col].shift(1)
                div = prev.abs().replace(0, np.nan)
                df_annual[f"{col}_YoY"] = (df_annual[col] - prev) / div

        return df_annual

    elif view_mode == "cumulative":
        # 累积季度 (Q1 -> H1 -> Q9 -> FY)
        cumulative_rows = []
        
        for year, group in df_single.groupby('year'):
            group = group.sort_values('Sort_Key') # Q1, Q2, Q3, Q4
            
            # 累积容器
            acc_flow = {k: 0.0 for k in GROWTH_METRIC_KEYS if k in group.columns}
            
            for _, row in group.iterrows():
                p = row['period']
                target_p_map = {"Q1": "Q1", "Q2": "H1", "Q3": "Q9", "Q4": "FY"}
                target_p = target_p_map.get(p)
                if not target_p: continue
                
                new_row = row.copy()
                new_row['period'] = target_p
                
                # 流量累加
                for k in acc_flow:
                    val = row.get(k)
                    if pd.notna(val):
                        acc_flow[k] += val
                    new_row[k] = acc_flow[k]
                
                cumulative_rows.append(new_row)
        
        df_cum_view = pd.DataFrame(cumulative_rows)
        if not df_cum_view.empty:
            df_cum_view = recalculate_ratios(df_cum_view)
            
            # 重新计算 YoY
            p_sort = {"Q1": 1, "H1": 2, "Q9": 3, "FY": 4}
            df_cum_view['s'] = df_cum_view['period'].map(p_sort)
            df_cum_view = df_cum_view.sort_values(['year', 's'])
            
            for col in df_cum_view.columns:
                 if (col in GROWTH_METRIC_KEYS or col in RATIO_DEFINITIONS or col in ALL_METRIC_KEYS) and pd.api.types.is_numeric_dtype(df_cum_view[col]):
                      df_cum_view[f"{col}_YoY"] = df_cum_view.groupby('period')[col].pct_change()

        return df_cum_view

    return pd.DataFrame()
# modules/industry_data.py
# 行业数据助手模块
# 提供各行业的估值和财务基准数据 (模拟数据或从外部获取)

import pandas as pd

# 模拟的行业基准数据字典
# Key: 行业名称 (Sector)
# Value: 各项指标的中位数
INDUSTRY_BENCHMARKS = {
    "Technology": {
        "pe_ttm": 25.0,
        "peg": 1.2,
        "ev_ebitda": 18.0,
        "profit_margin": 15.0,
        "roe": 18.0,
        "roa": 8.0,
        "roic": 12.0
    },
    "Healthcare": {
        "pe_ttm": 22.0,
        "peg": 1.5,
        "ev_ebitda": 16.0,
        "profit_margin": 12.0,
        "roe": 15.0,
        "roa": 7.0,
        "roic": 10.0
    },
    "Financial Services": {
        "pe_ttm": 12.0,
        "peg": 1.0,
        "ev_ebitda": 10.0,
        "profit_margin": 20.0,
        "roe": 10.0,
        "roa": 1.0,
        "roic": 8.0
    },
    "Consumer Cyclical": {
        "pe_ttm": 18.0,
        "peg": 1.1,
        "ev_ebitda": 12.0,
        "profit_margin": 8.0,
        "roe": 14.0,
        "roa": 6.0,
        "roic": 9.0
    },
    "Industrials": {
        "pe_ttm": 20.0,
        "peg": 1.3,
        "ev_ebitda": 14.0,
        "profit_margin": 9.0,
        "roe": 16.0,
        "roa": 6.5,
        "roic": 11.0
    },
    # 默认兜底
    "General": {
        "pe_ttm": 20.0,
        "peg": 1.2,
        "ev_ebitda": 14.0,
        "profit_margin": 10.0,
        "roe": 12.0,
        "roa": 5.0,
        "roic": 9.0
    }
}

def get_industry_benchmarks(sector: str = None) -> dict:
    """获取指定行业的基准数据
    
    Args:
        sector: 行业名称 (如 'Technology')
        
    Returns:
        包含各项指标基准值的字典
    """
    if not sector:
        return INDUSTRY_BENCHMARKS["General"]
    
    # 简单的模糊匹配
    for key in INDUSTRY_BENCHMARKS:
        if key.lower() in sector.lower() or sector.lower() in key.lower():
            return INDUSTRY_BENCHMARKS[key]
            
    return INDUSTRY_BENCHMARKS["General"]

def get_industry_pe_history(sector: str = None, periods: int = 12) -> pd.Series:
    """获取行业历史 PE 走势 (模拟)
    
    Args:
        sector: 行业名称
        periods: 数据点数量
        
    Returns:
        pd.Series: 历史 PE 值
    """
    base = get_industry_benchmarks(sector)["pe_ttm"]
    
    # 模拟一个随时间微小波动的序列
    import numpy as np
    
    # 假设最近 periods 个月/季度的走势
    # 生成随机波动
    volatility = 0.05  # 5% 波动
    random_walk = np.random.normal(0, volatility, periods)
    
    # 构造序列
    trend = np.linspace(base * 0.9, base * 1.05, periods) # 假设有个轻微上涨趋势
    history = trend * (1 + random_walk)
    
    return pd.Series(history)

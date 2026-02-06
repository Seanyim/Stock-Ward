# modules/risk_free_rate.py
# 无风险利率自动获取模块
# v1.0 - 使用 yfinance 获取美国 10 年期国债收益率

import streamlit as st
import yfinance as yf
from datetime import datetime, timedelta


def get_risk_free_rate(use_cache: bool = True) -> float:
    """获取无风险利率 (美国 10 年期国债收益率)
    
    Args:
        use_cache: 是否使用缓存（24小时有效）
    
    Returns:
        无风险利率 (小数形式，如 0.045 表示 4.5%)
    """
    cache_key = 'risk_free_rate_cache'
    cache_time_key = 'risk_free_rate_cache_time'
    
    # 检查缓存
    if use_cache:
        cached_rate = st.session_state.get(cache_key)
        cached_time = st.session_state.get(cache_time_key)
        
        if cached_rate is not None and cached_time is not None:
            # 缓存 24 小时有效
            if datetime.now() - cached_time < timedelta(hours=24):
                return cached_rate
    
    # 获取 10 年期国债收益率
    try:
        # ^TNX 是 CBOE 10-Year Treasury Note Yield Index
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        
        if not hist.empty:
            # 收益率以百分比形式返回，需要除以 100
            rate = hist['Close'].iloc[-1] / 100
            
            # 缓存结果
            st.session_state[cache_key] = rate
            st.session_state[cache_time_key] = datetime.now()
            
            return rate
    except Exception as e:
        st.warning(f"获取无风险利率失败: {e}")
    
    # 默认值
    return 0.045  # 4.5%


def get_risk_free_rate_with_ui(default: float = None) -> float:
    """获取无风险利率（带 UI 显示）
    
    Returns:
        无风险利率 (小数形式)
    """
    # 尝试自动获取
    auto_rate = get_risk_free_rate()
    
    if default is None:
        default = auto_rate
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        rf_input = st.number_input(
            "无风险利率 (%)", 
            value=auto_rate * 100,
            min_value=0.0,
            max_value=20.0,
            step=0.1,
            help="自动获取美国 10 年期国债收益率"
        )
    
    with col2:
        if st.button("🔄", help="刷新无风险利率"):
            # 清除缓存，强制重新获取
            if 'risk_free_rate_cache' in st.session_state:
                del st.session_state['risk_free_rate_cache']
            if 'risk_free_rate_cache_time' in st.session_state:
                del st.session_state['risk_free_rate_cache_time']
            st.rerun()
    
    st.caption(f"📊 10年期国债收益率 (自动): {auto_rate:.2%}")
    
    return rf_input / 100


def render_risk_free_rate_info():
    """渲染无风险利率信息面板"""
    rf = get_risk_free_rate()
    
    st.metric(
        "无风险利率 (Rf)",
        f"{rf:.2%}",
        help="美国 10 年期国债收益率"
    )
    
    return rf

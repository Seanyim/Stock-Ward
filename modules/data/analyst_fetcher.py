# modules/analyst_fetcher.py
# 分析师数据获取器 - 基于 yfinance
# v1.0 - 替代 Finnhub，使用 yfinance 作为主要数据源

import yfinance as yf
import streamlit as st
import pandas as pd
from datetime import datetime
from modules.core.db import (
    save_price_target, get_price_target,
    save_analyst_estimates, get_analyst_estimates,
    save_recommendation_trends, get_recommendation_trends
)


class AnalystDataFetcher:
    """分析师数据获取器 (基于 yfinance)
    
    优势：
    - 免费，无需 API Key
    - 稳定可靠
    - 支持目标价、推荐趋势、EPS 预估
    """
    
    def __init__(self, proxy: str = None):
        """初始化
        
        Args:
            proxy: 代理地址（可选）
        """
        self.proxy = proxy
        # yfinance 通过环境变量设置代理
        if proxy:
            import os
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy
    
    def fetch_price_target(self, symbol: str) -> dict:
        """获取分析师目标价
        
        Returns:
            包含 current, high, low, mean, median 的字典
        """
        try:
            ticker = yf.Ticker(symbol)
            targets = ticker.analyst_price_targets
            
            if targets and isinstance(targets, dict):
                # 转换为标准格式（与 db.py 中的 save_price_target 兼容）
                result = {
                    'symbol': symbol,
                    'targetHigh': targets.get('high'),
                    'targetLow': targets.get('low'),
                    'targetMean': targets.get('mean'),
                    'targetMedian': targets.get('median'),
                    'currentPrice': targets.get('current'),
                    'lastUpdated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                save_price_target(symbol, result)
                return result
        except Exception as e:
            st.warning(f"获取目标价失败 ({symbol}): {e}")
        return None
    
    def fetch_recommendations(self, symbol: str) -> list:
        """获取分析师推荐趋势
        
        Returns:
            包含各期推荐分布的列表
        """
        try:
            ticker = yf.Ticker(symbol)
            recs = ticker.recommendations
            
            if recs is not None and not recs.empty:
                # 转换为标准格式
                result = []
                for idx, row in recs.iterrows():
                    period = row.get('period', '')
                    # 将相对期间转换为日期
                    if period:
                        try:
                            # period 格式如 "0m", "-1m", "-2m"
                            months_ago = int(period.replace('m', ''))
                            from dateutil.relativedelta import relativedelta
                            date = datetime.now() + relativedelta(months=months_ago)
                            period_str = date.strftime('%Y-%m-01')
                        except:
                            period_str = period
                    else:
                        period_str = datetime.now().strftime('%Y-%m-01')
                    
                    rec_data = {
                        'period': period_str,
                        'strong_buy': int(row.get('strongBuy', 0)),
                        'buy': int(row.get('buy', 0)),
                        'hold': int(row.get('hold', 0)),
                        'sell': int(row.get('sell', 0)),
                        'strong_sell': int(row.get('strongSell', 0))
                    }
                    result.append(rec_data)
                
                # 保存到缓存
                if result:
                    save_recommendation_trends(symbol, result)
                return result
        except Exception as e:
            st.warning(f"获取推荐趋势失败 ({symbol}): {e}")
        return None
    
    def fetch_earnings_estimate(self, symbol: str) -> list:
        """获取 EPS 预估
        
        Returns:
            包含各期 EPS 预估的列表
        """
        try:
            ticker = yf.Ticker(symbol)
            est = ticker.earnings_estimate
            
            if est is not None and not est.empty:
                # 转换为标准格式
                result = []
                for period in est.columns:
                    try:
                        row_data = {
                            'period': str(period),
                            'epsAvg': float(est.loc['avg', period]) if 'avg' in est.index else None,
                            'epsHigh': float(est.loc['high', period]) if 'high' in est.index else None,
                            'epsLow': float(est.loc['low', period]) if 'low' in est.index else None,
                            'numberAnalysts': int(est.loc['numberOfAnalysts', period]) if 'numberOfAnalysts' in est.index else None
                        }
                        result.append(row_data)
                    except:
                        continue
                
                # 保存到缓存
                if result:
                    save_analyst_estimates(symbol, 'eps', 'mixed', result)
                return result
        except Exception as e:
            st.warning(f"获取 EPS 预估失败 ({symbol}): {e}")
        return None
    
    def fetch_revenue_estimate(self, symbol: str) -> list:
        """获取收入预估
        
        Returns:
            包含各期收入预估的列表
        """
        try:
            ticker = yf.Ticker(symbol)
            est = ticker.revenue_estimate
            
            if est is not None and not est.empty:
                result = []
                for period in est.columns:
                    try:
                        row_data = {
                            'period': str(period),
                            'revenueAvg': float(est.loc['avg', period]) if 'avg' in est.index else None,
                            'revenueHigh': float(est.loc['high', period]) if 'high' in est.index else None,
                            'revenueLow': float(est.loc['low', period]) if 'low' in est.index else None,
                            'numberAnalysts': int(est.loc['numberOfAnalysts', period]) if 'numberOfAnalysts' in est.index else None
                        }
                        result.append(row_data)
                    except:
                        continue
                
                if result:
                    save_analyst_estimates(symbol, 'revenue', 'mixed', result)
                return result
        except Exception as e:
            st.warning(f"获取收入预估失败 ({symbol}): {e}")
        return None
    
    def fetch_all_analyst_data(self, symbol: str) -> dict:
        """一次性获取所有分析师数据
        
        Returns:
            包含所有数据类型的字典
        """
        results = {
            'price_target': None,
            'recommendations': None,
            'eps_estimate': None,
            'revenue_estimate': None,
            'errors': []
        }
        
        # 目标价
        try:
            results['price_target'] = self.fetch_price_target(symbol)
        except Exception as e:
            results['errors'].append(f"目标价: {e}")
        
        # 推荐趋势
        try:
            results['recommendations'] = self.fetch_recommendations(symbol)
        except Exception as e:
            results['errors'].append(f"推荐趋势: {e}")
        
        # EPS 预估
        try:
            results['eps_estimate'] = self.fetch_earnings_estimate(symbol)
        except Exception as e:
            results['errors'].append(f"EPS预估: {e}")
        
        # 收入预估
        try:
            results['revenue_estimate'] = self.fetch_revenue_estimate(symbol)
        except Exception as e:
            results['errors'].append(f"收入预估: {e}")
        
        return results


def get_analyst_fetcher() -> AnalystDataFetcher:
    """获取分析师数据获取器实例"""
    proxy = st.session_state.get('proxy_url', None)
    return AnalystDataFetcher(proxy)


# --- 缓存数据读取辅助函数 ---

def get_cached_price_target(ticker: str) -> dict:
    """获取缓存的目标价数据"""
    return get_price_target(ticker)


def get_cached_recommendations(ticker: str) -> list:
    """获取缓存的推荐趋势"""
    return get_recommendation_trends(ticker)


def get_cached_eps_estimates(ticker: str) -> dict:
    """获取缓存的 EPS 预估"""
    return get_analyst_estimates(ticker, 'eps', 'mixed')


def get_cached_revenue_estimates(ticker: str) -> dict:
    """获取缓存的收入预估"""
    return get_analyst_estimates(ticker, 'revenue', 'mixed')

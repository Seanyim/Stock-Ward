import yfinance as yf
import pandas as pd
import os

class YFinanceFetcher:
    def __init__(self, proxy=None):
        self.proxy = proxy
        if self.proxy:
            os.environ['HTTP_PROXY'] = self.proxy
            os.environ['HTTPS_PROXY'] = self.proxy

    def fetch_all(self, ticker_symbol):
        try:
            ticker = yf.Ticker(ticker_symbol)
            
            # [优化点3] 获取最大历史股价
            history = ticker.history(period="max")
            
            # 获取财务报表 (yfinance通常返回过去4-5年，如果需要更长可能需要其他源，但这里已尽力获取最大)
            fin_q = ticker.quarterly_financials
            bs_q = ticker.quarterly_balance_sheet
            cf_q = ticker.quarterly_cashflow
            
            fin_a = ticker.financials
            bs_a = ticker.balance_sheet
            cf_a = ticker.cashflow
            
            info = ticker.info

            if history.empty and fin_a.empty:
                return None, "未找到有效数据 (No history or financials)"

            raw_data = {
                "ticker": ticker_symbol,
                "history": history,
                "quarterly": {"income": fin_q, "balance": bs_q, "cashflow": cf_q},
                "annual": {"income": fin_a, "balance": bs_a, "cashflow": cf_a},
                "info": info
            }
            return raw_data, None

        except Exception as e:
            return None, f"Fetch Error: {str(e)}"

def get_fetcher():
    import streamlit as st
    proxy = st.session_state.get('proxy_url', None)
    return YFinanceFetcher(proxy)
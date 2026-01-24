import yfinance as yf
import pandas as pd
import streamlit as st
import os
import time
import numpy as np
from modules.db import save_market_history, update_company_snapshot, get_financial_records
from modules.calculator import process_financial_data

class MarketDataFetcher:
    def __init__(self, proxy=None):
        self.proxy = proxy
        if self.proxy:
            os.environ['HTTP_PROXY'] = self.proxy
            os.environ['HTTPS_PROXY'] = self.proxy

    def _safe_call(self, func, context_name="unknown"):
        try:
            return func(), None
        except Exception as e:
            error_msg = f"Error in {context_name}: {str(e)}"
            print(error_msg)
            return None, error_msg

    def sync_market_data(self, ticker_symbol):
        """
        高级同步：
        1. 获取 Yahoo 每日股价 (History)
        2. 获取 股本 (Shares Outstanding)
        3. 读取 本地手动财报 -> 计算每日 EPS TTM
        4. 合并计算 -> 每日 PE, 每日 Market Cap
        5. 存入数据库
        """
        status = {"history": False, "snapshot": False, "msg": ""}
        errors = []
        
        st.write(f"🔄 正在执行高级同步: {ticker_symbol} ...")
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            
            # --- 1. 获取股价历史 (Max) ---
            st.write("1. 下载股价历史...")
            hist, err = self._safe_call(lambda: ticker.history(period="max"), "fetch_history")
            
            if err or hist is None or hist.empty:
                st.error("❌ 无法获取股价历史，同步终止。")
                return {"msg": f"Fetch failed: {err}"}
            
            # 清理时区
            if hasattr(hist.index, 'tz_localize'):
                hist.index = hist.index.tz_localize(None)
            
            # --- 2. 获取当前股本 (Shares) ---
            # 历史股本很难获取，我们使用当前股本估算历史市值 (近似法)
            st.write("2. 获取股本信息...")
            shares = 0
            try:
                shares = ticker.fast_info.shares
            except:
                info, _ = self._safe_call(lambda: ticker.info, "fetch_shares")
                if info: shares = info.get('sharesOutstanding', 0)
            
            if shares == 0:
                st.warning("⚠️ 无法获取股本(Shares)，市值计算将跳过。")
            else:
                st.caption(f"当前股本: {shares:,.0f}")

            # --- 3. 计算 每日市值 ---
            if shares > 0:
                hist['market_cap'] = hist['Close'] * shares
            else:
                hist['market_cap'] = None

            # --- 4. 计算 每日 PE (核心逻辑) ---
            st.write("3. 结合财报计算每日 PE...")
            
            # A. 读取手动录入的财报
            raw_records = get_financial_records(ticker_symbol)
            
            if raw_records:
                # B. 使用 calculator 计算单季度/TTM 数据
                df_raw = pd.DataFrame(raw_records)
                _, df_single = process_financial_data(df_raw)
                
                if not df_single.empty and 'EPS_TTM' in df_single.columns:
                    # C. 构建 EPS 时间序列表
                    # 我们需要一个 DataFrame: [report_date, EPS_TTM]
                    # 注意：db.py 读取时已经按 report_date 排序
                    eps_data = df_single[['report_date', 'EPS_TTM']].dropna().copy()
                    eps_data['report_date'] = pd.to_datetime(eps_data['report_date'])
                    eps_data = eps_data.sort_values('report_date')
                    
                    # D. 将 EPS 数据合并到 股价数据中 (Merge Asof)
                    # 我们使用 merge_asof，direction='backward'
                    # 含义：对于每一天的股价，找到“之前最近一次”发布的财报的 EPS
                    
                    hist = hist.sort_index()
                    hist['date_temp'] = hist.index # 辅助列
                    
                    # 确保类型一致
                    eps_data['report_date'] = pd.to_datetime(eps_data['report_date'])
                    
                    # 合并
                    hist_merged = pd.merge_asof(
                        hist,
                        eps_data,
                        left_on='date_temp',
                        right_on='report_date',
                        direction='backward'
                    )
                    
                    # E. 计算 PE
                    # PE = Close / EPS_TTM
                    # 注意：如果 EPS <= 0，通常 PE 无意义或显示为负
                    hist_merged['pe_ttm'] = hist_merged['Close'] / hist_merged['EPS_TTM']
                    
                    # 处理除以0或空值
                    hist_merged['pe_ttm'] = hist_merged['pe_ttm'].replace([np.inf, -np.inf], None)
                    
                    # 将计算结果回填到 hist (方便后续保存)
                    hist['pe_ttm'] = hist_merged['pe_ttm'].values
                    hist['eps_ttm'] = hist_merged['EPS_TTM'].values
                    # 静态 PE 类似，暂略，PE Forward 无法历史回溯
                    hist['pe_static'] = None 
                    
                    st.success(f"✅ 成功计算 {len(hist_merged.dropna(subset=['pe_ttm']))} 个交易日的 PE 数据")
                else:
                    st.warning("⚠️ 财报数据不足以计算 EPS TTM (需至少4个季度数据)")
                    hist['pe_ttm'] = None
                    hist['eps_ttm'] = None
                    hist['pe_static'] = None
            else:
                st.warning("⚠️ 未找到手动录入的财报，无法计算 PE。请先录入财报。")
                hist['pe_ttm'] = None
                hist['eps_ttm'] = None
                hist['pe_static'] = None

            # --- 5. 保存入库 ---
            st.write("4. 保存至数据库...")
            save_market_history(ticker_symbol, hist)
            
            # 更新快照
            latest = hist.iloc[-1]
            update_company_snapshot(
                ticker_symbol, 
                latest.get('market_cap', 0), 
                latest.get('eps_ttm', 0)
            )
            
            status["history"] = True
            
            # 安全格式化，处理 None 值
            close_price = latest.get('Close', 0) or 0
            market_cap = latest.get('market_cap', 0) or 0
            pe_ttm_val = latest.get('pe_ttm')
            pe_str = f"{pe_ttm_val:.2f}" if pe_ttm_val is not None and not pd.isna(pe_ttm_val) else "N/A"
            
            status["msg"] = f"同步完成。最新股价: {close_price:.2f}, 市值: {market_cap/1e9:.2f}B, PE(TTM): {pe_str}"
            return status

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"msg": f"Critical Error: {str(e)}"}

def get_fetcher():
    proxy = st.session_state.get('proxy_url', None)
    return MarketDataFetcher(proxy)
import pandas as pd
import numpy as np
from datetime import timedelta
from modules.db import save_company_metadata, save_prices_to_db, save_financial_records
from modules.config import METRIC_MAPPING

class DataProcessor:
    @staticmethod
    def process_and_save(raw_data):
        ticker = raw_data['ticker']
        history = raw_data['history']
        
        save_company_metadata(ticker, raw_data['info'])
        
        if hasattr(history.index, 'tz_localize'):
            history.index = history.index.tz_localize(None)
        save_prices_to_db(ticker, history)
        
        records = DataProcessor._process_financials(ticker, raw_data, history)
        save_financial_records(records)
        return records

    @staticmethod
    def _process_financials(ticker, raw_data, history):
        records = []
        
        def get_delayed_price(report_date):
            if pd.isna(report_date): return 0
            target_date = pd.to_datetime(report_date) + timedelta(days=30)
            try:
                idx = history.index.get_indexer([target_date], method='nearest')[0]
                if abs((history.index[idx] - target_date).days) > 10: return 0
                return float(history.iloc[idx]['Close'])
            except: return 0

        def get_val(df, date, keys):
            if date not in df.columns: return 0.0
            for k in keys:
                if k in df.index:
                    val = df.loc[k, date]
                    if not pd.isna(val): return float(val)
            return 0.0

        q_dfs = [raw_data['quarterly']['income'], raw_data['quarterly']['balance'], raw_data['quarterly']['cashflow']]
        a_dfs = [raw_data['annual']['income'], raw_data['annual']['balance'], raw_data['annual']['cashflow']]
        
        # --- 处理季度数据 ---
        q_dates = set()
        for df in q_dfs: q_dates.update(df.columns)
        q_dates = sorted(list(q_dates))
        
        q_records_temp = []
        
        for date in q_dates:
            # [优化] 数据有效性检查：如果营收和利润都为0，视为无效数据（YF有时会返回空列）
            rev_check = 0
            for df in q_dfs: rev_check += get_val(df, date, ["Total Revenue", "Operating Revenue"])
            if rev_check == 0:
                continue

            # 推算财报周期
            f_year = date.year
            q_num = (date.month - 1) // 3 + 1
            f_period = f"Q{q_num}"
            
            # 获取股本 (用于计算市值)
            shares = 0
            for df in q_dfs:
                s = get_val(df, date, ["Basic Average Shares", "Ordinary Shares Number", "Share Issued"])
                if s > 0: shares = s; break
            
            stock_price = get_delayed_price(date)
            
            rec = {
                "ticker": ticker,
                "report_date": date.strftime("%Y-%m-%d"),
                "year": date.year,
                "period": f"Q{q_num}",
                "fiscal_year": f_year,     # [新增] 财报年
                "fiscal_period": f_period, # [新增] 财报周期
                "stock_price": stock_price,
                "shares": shares,
                "market_cap": stock_price * shares if shares > 0 else 0, # [新增] 历史市值
            }
            
            for m in METRIC_MAPPING:
                val = 0.0
                for df in q_dfs:
                    v = get_val(df, date, m['yf_keys'])
                    if v != 0: val = v; break
                rec[m['id']] = val
            
            if rec.get('Free_Cash_Flow', 0) == 0:
                 rec['Free_Cash_Flow'] = rec.get('Operating_Cash_Flow', 0) - abs(rec.get('Capex', 0))

            q_records_temp.append(rec)

        # 计算 TTM & PE TTM
        df_q = pd.DataFrame(q_records_temp).sort_values('report_date')
        if not df_q.empty:
            numeric_cols = [m['id'] for m in METRIC_MAPPING if m['id'] in df_q.columns]
            # 流量指标 TTM = Sum(4Q), 存量指标 TTM = Last
            # 简单起见，先全部 rolling sum，后续在 calculator 里可以精细化
            # 这里主要为了计算 PE TTM
            df_ttm = df_q[numeric_cols].rolling(4, min_periods=4).sum()
            
            for idx, row in df_q.iterrows():
                eps_ttm = df_ttm.loc[idx, 'EPS'] if 'EPS' in df_ttm.columns else 0
                rec = q_records_temp[idx]
                
                # PE TTM
                if row['stock_price'] > 0 and eps_ttm > 0:
                    rec['pe_ttm'] = row['stock_price'] / eps_ttm
                else:
                    rec['pe_ttm'] = 0
                
                # 更新回 records
                records.append(rec)

        # --- 处理年度数据 ---
        a_dates = set()
        for df in a_dfs: a_dates.update(df.columns)
        a_dates = sorted(list(a_dates))
        
        for date in a_dates:
            rev_check = 0
            for df in a_dfs: rev_check += get_val(df, date, ["Total Revenue", "Operating Revenue"])
            if rev_check == 0: continue

            shares = 0
            for df in a_dfs:
                s = get_val(df, date, ["Basic Average Shares", "Ordinary Shares Number"])
                if s > 0: shares = s; break

            stock_price = get_delayed_price(date)
            
            rec = {
                "ticker": ticker,
                "report_date": date.strftime("%Y-%m-%d"),
                "year": date.year,
                "period": "FY",
                "fiscal_year": date.year,
                "fiscal_period": "FY",
                "stock_price": stock_price,
                "shares": shares,
                "market_cap": stock_price * shares if shares > 0 else 0,
                "pe_ttm": 0
            }
            
            for m in METRIC_MAPPING:
                val = 0.0
                for df in a_dfs:
                    v = get_val(df, date, m['yf_keys'])
                    if v != 0: val = v; break
                rec[m['id']] = val
                
            if rec.get('Free_Cash_Flow', 0) == 0:
                 rec['Free_Cash_Flow'] = rec.get('Operating_Cash_Flow', 0) - abs(rec.get('Capex', 0))
            
            # Static PE
            eps = rec.get('EPS', 0)
            if stock_price > 0 and eps > 0:
                rec['pe_static'] = stock_price / eps
            else:
                rec['pe_static'] = 0
                
            records.append(rec)
            
        return records
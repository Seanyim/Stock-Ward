import sqlite3
import pandas as pd
import os
import streamlit as st
from modules.core.config import FINANCIAL_METRICS

DB_DIR = "data"
DB_FILE = "financial_data.db"
DB_PATH = os.path.join(DB_DIR, DB_FILE)

def init_db():
    """初始化数据库：创建独立的财务表和市场表，支持自动新增列"""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. 公司基础信息表 (v2.1 - 添加 sector, industry 字段)
        c.execute('''CREATE TABLE IF NOT EXISTS companies (
                        ticker TEXT PRIMARY KEY,
                        name TEXT,
                        region TEXT DEFAULT 'US',
                        unit TEXT DEFAULT 'Billion',
                        last_market_cap REAL,
                        last_eps_ttm REAL,
                        last_update TEXT,
                        sector TEXT DEFAULT 'Unknown',
                        industry TEXT DEFAULT 'Unknown'
                    )''')
        
        # 1.1 自动迁移：添加 region 字段（如果不存在）
        c.execute("PRAGMA table_info(companies)")
        company_cols = [row[1] for row in c.fetchall()]
        
        if 'region' not in company_cols:
            print("Migrating DB: Adding column region to companies")
            c.execute("ALTER TABLE companies ADD COLUMN region TEXT DEFAULT 'US'")
            
        if 'sector' not in company_cols:
            print("Migrating DB: Adding column sector to companies")
            c.execute("ALTER TABLE companies ADD COLUMN sector TEXT DEFAULT 'Unknown'")
            
        if 'industry' not in company_cols:
            print("Migrating DB: Adding column industry to companies")
            c.execute("ALTER TABLE companies ADD COLUMN industry TEXT DEFAULT 'Unknown'")
        
        # 2. 财务数据表 (手动录入)
        # 动态构建列定义，但 CREATE TABLE 只能用一次。后续需要 ALTER TABLE。
        metric_cols_def = [f"{m['id']} REAL" for m in FINANCIAL_METRICS]
        cols_sql = ", ".join(metric_cols_def)
        
        c.execute(f'''CREATE TABLE IF NOT EXISTS financial_records (
                        ticker TEXT,
                        year INTEGER,
                        period TEXT,
                        report_date TEXT,
                        {cols_sql},
                        PRIMARY KEY (ticker, year, period)
                    )''')
        
        # 2.1 自动迁移：检查是否有新增加的指标字段，如果没有则添加
        c.execute("PRAGMA table_info(financial_records)")
        existing_cols = [row[1] for row in c.fetchall()]
        
        for m in FINANCIAL_METRICS:
            col_name = m['id']
            if col_name not in existing_cols:
                print(f"Migrating DB: Adding column {col_name} to financial_records")
                try:
                    c.execute(f"ALTER TABLE financial_records ADD COLUMN {col_name} REAL")
                except Exception as e:
                    print(f"Migration Error for {col_name}: {e}")

        # 3. [升级] 市场行情表 (增加市值、PE等字段)
        c.execute('''CREATE TABLE IF NOT EXISTS market_daily (
                        ticker TEXT,
                        date TEXT,
                        close REAL,
                        volume REAL,
                        market_cap REAL,
                        pe_ttm REAL,
                        pe_static REAL,
                        eps_ttm REAL,
                        PRIMARY KEY (ticker, date)
                    )''')
        
        # 4. 分析师目标价缓存表
        c.execute('''CREATE TABLE IF NOT EXISTS analyst_price_targets (
                        ticker TEXT PRIMARY KEY,
                        symbol TEXT,
                        target_high REAL,
                        target_low REAL,
                        target_mean REAL,
                        target_median REAL,
                        last_updated TEXT,
                        raw_data TEXT
                    )''')
        
        # 5. EPS/Revenue 预测缓存表
        c.execute('''CREATE TABLE IF NOT EXISTS analyst_estimates (
                        ticker TEXT,
                        estimate_type TEXT,
                        freq TEXT,
                        data TEXT,
                        last_updated TEXT,
                        PRIMARY KEY (ticker, estimate_type, freq)
                    )''')
        
        # 6. 推荐趋势表
        c.execute('''CREATE TABLE IF NOT EXISTS recommendation_trends (
                        ticker TEXT,
                        period TEXT,
                        strong_buy INTEGER,
                        buy INTEGER,
                        hold INTEGER,
                        sell INTEGER,
                        strong_sell INTEGER,
                        PRIMARY KEY (ticker, period)
                    )''')
        
        conn.commit()
    except Exception as e:
        st.error(f"DB Init Error: {e}")
    finally:
        conn.close()

# --- 财务数据操作 ---

def get_financial_records(ticker):
    """获取某公司的所有财务记录"""
    conn = sqlite3.connect(DB_PATH)
    try:
        # 按发布日期排序，这对每日 PE 计算至关重要
        query = "SELECT * FROM financial_records WHERE ticker = ? ORDER BY report_date ASC"
        df = pd.read_sql(query, conn, params=(ticker,))
        return df.to_dict('records')
    except:
        return []
    finally:
        conn.close()

def save_financial_record(record):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    clean_record = {k: v for k, v in record.items() if v is not None}
    cols = ", ".join(clean_record.keys())
    placeholders = ", ".join(["?"] * len(clean_record))
    values = tuple(clean_record.values())
    sql = f"INSERT OR REPLACE INTO financial_records ({cols}) VALUES ({placeholders})"
    try:
        c.execute(sql, values)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False
    finally:
        conn.close()

def delete_financial_record(ticker, year, period):
    """删除特定的财务记录"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM financial_records WHERE ticker = ? AND year = ? AND period = ?",
                  (ticker, year, period))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Delete Error: {e}")
        return False
    finally:
        conn.close()

# --- [升级] 市场数据操作 ---

def save_market_history(ticker, df_history):
    """
    保存包含 PE/市值 的全量市场数据
    df_history 需包含: Close, Volume, market_cap, pe_ttm, pe_static, eps_ttm
    """
    if df_history.empty: return
    conn = sqlite3.connect(DB_PATH)
    
    data = []
    # 确保 DataFrame 有我们需要的列，没有则补 None
    req_cols = ['Close', 'Volume', 'market_cap', 'pe_ttm', 'pe_static', 'eps_ttm']
    for c in req_cols:
        if c not in df_history.columns:
            df_history[c] = None

    for date, row in df_history.iterrows():
        date_str = date.strftime('%Y-%m-%d')
        data.append((
            ticker, 
            date_str, 
            row['Close'], 
            row['Volume'],
            row['market_cap'],
            row['pe_ttm'],
            row['pe_static'],
            row['eps_ttm']
        ))
        
    try:
        c = conn.cursor()
        c.executemany('''INSERT OR REPLACE INTO market_daily 
                         (ticker, date, close, volume, market_cap, pe_ttm, pe_static, eps_ttm) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', data)
        conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        conn.close()

def get_market_history(ticker):
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM market_daily WHERE ticker = ? ORDER BY date ASC", 
                         conn, params=(ticker,), parse_dates=['date'])
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

# --- 公司元数据操作 ---
def update_company_snapshot(ticker, market_cap, eps_ttm, sector=None, industry=None):
    """更新公司信息快照，含 sector 和 industry"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 构建 UPDATE 语句
        update_fields = ["last_market_cap = ?", "last_eps_ttm = ?", "last_update = date('now')"]
        params = [market_cap, eps_ttm]
        
        if sector:
            update_fields.append("sector = ?")
            params.append(sector)
        if industry:
            update_fields.append("industry = ?")
            params.append(industry)
            
        params.append(ticker)
        
        sql = f"UPDATE companies SET {', '.join(update_fields)} WHERE ticker = ?"
        c.execute(sql, tuple(params))
        
        if c.rowcount == 0:
            # Insert logic simplified: only core fields, ignoring industry for insert if not present
            # But better to insert what we have
            cols = ["ticker", "last_market_cap", "last_eps_ttm"]
            vals = [ticker, market_cap, eps_ttm]
            placeholders = ["?", "?", "?"]
            if sector:
                cols.append("sector")
                vals.append(sector)
                placeholders.append("?")
            if industry:
                cols.append("industry")
                vals.append(industry)
                placeholders.append("?")
                
            c.execute(f"INSERT INTO companies ({', '.join(cols)}) VALUES ({', '.join(placeholders)})", tuple(vals))
            
        conn.commit()
    finally:
        conn.close()

def get_company_meta(ticker):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM companies WHERE ticker = ?", (ticker,))
    row = c.fetchone()
    conn.close()
    if row:
        col_names = [d[0] for d in c.description]
        return dict(zip(col_names, row))
    return {}

def save_company_meta(ticker, name, unit, region='US'):
    """保存公司元数据，支持地区字段"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO companies (ticker, name, unit, region) VALUES (?, ?, ?, ?)
                 ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, unit=excluded.unit, region=excluded.region""", 
              (ticker, name, unit, region))
    conn.commit()
    conn.close()


# --- 分析师数据操作 ---

def save_price_target(ticker, data):
    """保存分析师目标价数据"""
    import json
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''INSERT OR REPLACE INTO analyst_price_targets 
                     (ticker, symbol, target_high, target_low, target_mean, target_median, last_updated, raw_data)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (ticker, data.get('symbol', ticker),
                   data.get('targetHigh'), data.get('targetLow'),
                   data.get('targetMean'), data.get('targetMedian'),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   json.dumps(data)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Save price target error: {e}")
        return False
    finally:
        conn.close()


def get_price_target(ticker):
    """获取缓存的分析师目标价数据"""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM analyst_price_targets WHERE ticker = ?", (ticker,))
    row = c.fetchone()
    conn.close()
    if row:
        col_names = ['ticker', 'symbol', 'target_high', 'target_low', 'target_mean', 
                     'target_median', 'last_updated', 'raw_data']
        result = dict(zip(col_names, row))
        if result.get('raw_data'):
            result['raw_data'] = json.loads(result['raw_data'])
        return result
    return None


def save_analyst_estimates(ticker, estimate_type, freq, data):
    """保存 EPS/Revenue 预测数据"""
    import json
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''INSERT OR REPLACE INTO analyst_estimates 
                     (ticker, estimate_type, freq, data, last_updated)
                     VALUES (?, ?, ?, ?, ?)''',
                  (ticker, estimate_type, freq, json.dumps(data),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True
    except Exception as e:
        print(f"Save estimates error: {e}")
        return False
    finally:
        conn.close()


def get_analyst_estimates(ticker, estimate_type, freq):
    """获取缓存的预测数据"""
    import json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT data, last_updated FROM analyst_estimates WHERE ticker = ? AND estimate_type = ? AND freq = ?",
              (ticker, estimate_type, freq))
    row = c.fetchone()
    conn.close()
    if row:
        return {'data': json.loads(row[0]), 'last_updated': row[1]}
    return None


def save_recommendation_trends(ticker, trends):
    """保存推荐趋势历史数据"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        for trend in trends:
            c.execute('''INSERT OR REPLACE INTO recommendation_trends 
                         (ticker, period, strong_buy, buy, hold, sell, strong_sell)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (ticker, trend.get('period', ''),
                       trend.get('strongBuy', 0), trend.get('buy', 0),
                       trend.get('hold', 0), trend.get('sell', 0),
                       trend.get('strongSell', 0)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Save recommendation trends error: {e}")
        return False
    finally:
        conn.close()


def get_recommendation_trends(ticker):
    """获取推荐趋势历史"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM recommendation_trends WHERE ticker = ? ORDER BY period ASC",
                         conn, params=(ticker,))
        return df.to_dict('records')
    except:
        return []
    finally:
        conn.close()

def get_all_tickers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ticker FROM companies")
    tickers = [row[0] for row in c.fetchall()]
    conn.close()
    return tickers
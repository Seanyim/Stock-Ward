import sqlite3
import pandas as pd
import os
from modules.config import METRIC_MAPPING

DB_DIR = "data"
DB_FILE = "financial_data.db"
DB_PATH = os.path.join(DB_DIR, DB_FILE)

def init_db():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS companies (
                    ticker TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    currency TEXT,
                    unit TEXT DEFAULT 'Raw' 
                )''')
    
    # [优化] 增加 fiscal_year, fiscal_period, shares
    cols_def = [
        "ticker TEXT",
        "report_date TEXT",
        "year INTEGER",      # 自然年 (用于排序)
        "period TEXT",       # 自然周期 (Q1/Q2...)
        "fiscal_year INTEGER", # 财报年
        "fiscal_period TEXT",  # 财报周期
        "stock_price REAL",
        "shares REAL",       # 股本
        "market_cap REAL",
        "pe_ttm REAL",
        "pe_static REAL"
    ]
    
    for m in METRIC_MAPPING:
        if m['id'] not in ["stock_price", "pe_ttm", "pe_static", "market_cap", "shares"]:
            cols_def.append(f"{m['id']} REAL")
        
    sql = f"CREATE TABLE IF NOT EXISTS financials ({', '.join(cols_def)}, PRIMARY KEY (ticker, report_date))"
    c.execute(sql)

    c.execute('''CREATE TABLE IF NOT EXISTS stock_prices (
                    ticker TEXT,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (ticker, date)
                )''')
    
    conn.commit()
    conn.close()

def get_all_companies():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT ticker, unit FROM companies")
        data = {row[0]: {"meta": {"unit": row[1]}} for row in c.fetchall()}
    except: data = {}
    conn.close()
    return data

def save_company_metadata(ticker, info):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO companies (ticker, name, sector, currency, unit)
                 VALUES (?, ?, ?, ?, 'Raw')''', 
              (ticker, info.get('shortName', ticker), info.get('sector', 'Unknown'), info.get('currency', 'USD')))
    conn.commit()
    conn.close()

def save_prices_to_db(ticker, df_history):
    if df_history.empty: return
    conn = sqlite3.connect(DB_PATH)
    df = df_history.reset_index()
    data = []
    for _, row in df.iterrows():
        date_val = row['Date']
        date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val).split(" ")[0]
        data.append((ticker, date_str, row['Open'], row['High'], row['Low'], row['Close'], row['Volume']))
    conn.executemany('''INSERT OR REPLACE INTO stock_prices (ticker, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', data)
    conn.commit()
    conn.close()

def save_financial_records(records):
    if not records: return
    conn = sqlite3.connect(DB_PATH)
    keys = list(records[0].keys())
    placeholders = ",".join(["?"] * len(keys))
    cols = ",".join(keys)
    data_tuples = [tuple(r[k] for k in keys) for r in records]
    sql = f"INSERT OR REPLACE INTO financials ({cols}) VALUES ({placeholders})"
    conn.executemany(sql, data_tuples)
    conn.commit()
    conn.close()

def get_company_records(ticker):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # 按报告日期倒序
    c.execute("SELECT * FROM financials WHERE ticker = ? ORDER BY report_date DESC", (ticker,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_price_history(ticker):
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT date, close, volume FROM stock_prices WHERE ticker = ? ORDER BY date ASC", 
                        conn, params=(ticker,), parse_dates=['date'])
    except: df = pd.DataFrame()
    conn.close()
    return df

def get_report_dates(ticker):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 获取财报日和对应的周期标签
        c.execute("SELECT report_date, fiscal_year, fiscal_period FROM financials WHERE ticker = ? ORDER BY report_date ASC", (ticker,))
        rows = c.fetchall() # [(date, 2024, Q3), ...]
    except: rows = []
    conn.close()
    return rows
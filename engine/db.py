# engine/db.py — SQLite layer (Streamlit-free port of modules/core/db.py)
import sqlite3
import os
import json
import threading
from datetime import datetime

import pandas as pd

from modules.core.config import FINANCIAL_METRICS

# Absolute DB path (project root /data/financial_data.db).
# When frozen (PyInstaller), store the DB next to the executable so it is
# writable and persists across launches (not inside the temporary _MEIPASS).
import sys as _sys
if getattr(_sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.abspath(_sys.executable))
else:
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_ROOT, "data", "financial_data.db")

_lock = threading.Lock()

# ---- data-version counter: bumped on every write, used for cache invalidation ----
_data_version = 0


def data_version() -> int:
    return _data_version


def _bump():
    global _data_version
    _data_version += 1


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    c = conn.cursor()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS companies (
                        ticker TEXT PRIMARY KEY, name TEXT,
                        region TEXT DEFAULT 'US', unit TEXT DEFAULT 'Billion',
                        last_market_cap REAL, last_eps_ttm REAL, last_update TEXT,
                        sector TEXT DEFAULT 'Unknown', industry TEXT DEFAULT 'Unknown')''')
        c.execute("PRAGMA table_info(companies)")
        cols = [r[1] for r in c.fetchall()]
        for col, ddl in [("region", "TEXT DEFAULT 'US'"), ("sector", "TEXT DEFAULT 'Unknown'"),
                         ("industry", "TEXT DEFAULT 'Unknown'")]:
            if col not in cols:
                c.execute(f"ALTER TABLE companies ADD COLUMN {col} {ddl}")

        metric_cols = ", ".join(f"{m['id']} REAL" for m in FINANCIAL_METRICS)
        c.execute(f'''CREATE TABLE IF NOT EXISTS financial_records (
                        ticker TEXT, year INTEGER, period TEXT, report_date TEXT,
                        {metric_cols}, PRIMARY KEY (ticker, year, period))''')
        c.execute("PRAGMA table_info(financial_records)")
        existing = [r[1] for r in c.fetchall()]
        for m in FINANCIAL_METRICS:
            if m['id'] not in existing:
                try:
                    c.execute(f"ALTER TABLE financial_records ADD COLUMN {m['id']} REAL")
                except Exception:
                    pass

        c.execute('''CREATE TABLE IF NOT EXISTS market_daily (
                        ticker TEXT, date TEXT, close REAL, volume REAL,
                        market_cap REAL, pe_ttm REAL, pe_static REAL, eps_ttm REAL,
                        PRIMARY KEY (ticker, date))''')
        c.execute('''CREATE TABLE IF NOT EXISTS analyst_price_targets (
                        ticker TEXT PRIMARY KEY, symbol TEXT, target_high REAL, target_low REAL,
                        target_mean REAL, target_median REAL, last_updated TEXT, raw_data TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS analyst_estimates (
                        ticker TEXT, estimate_type TEXT, freq TEXT, data TEXT, last_updated TEXT,
                        PRIMARY KEY (ticker, estimate_type, freq))''')
        c.execute('''CREATE TABLE IF NOT EXISTS recommendation_trends (
                        ticker TEXT, period TEXT, strong_buy INTEGER, buy INTEGER,
                        hold INTEGER, sell INTEGER, strong_sell INTEGER,
                        PRIMARY KEY (ticker, period))''')
        c.execute('''CREATE TABLE IF NOT EXISTS company_categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                        display_order INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS category_members (
                        category_id INTEGER, ticker TEXT,
                        PRIMARY KEY (category_id, ticker),
                        FOREIGN KEY (category_id) REFERENCES company_categories(id) ON DELETE CASCADE,
                        FOREIGN KEY (ticker) REFERENCES companies(ticker) ON DELETE CASCADE)''')

        # ---- v4: cross-verification provenance, ingest metadata, news ----
        c.execute('''CREATE TABLE IF NOT EXISTS metric_provenance (
                        ticker TEXT, year INTEGER, period TEXT, metric TEXT,
                        chosen_value REAL, chosen_source TEXT,
                        agreement TEXT, spread REAL, sources_json TEXT,
                        PRIMARY KEY (ticker, year, period, metric))''')
        c.execute('''CREATE TABLE IF NOT EXISTS ingest_meta (
                        ticker TEXT PRIMARY KEY, last_ingest TEXT, report_json TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS news (
                        ticker TEXT, uuid TEXT, title TEXT, publisher TEXT,
                        link TEXT, published TEXT, summary TEXT, sentiment TEXT,
                        PRIMARY KEY (ticker, uuid))''')
        c.execute('''CREATE TABLE IF NOT EXISTS social (
                        ticker TEXT, msg_id TEXT, body TEXT, user TEXT,
                        created TEXT, sentiment TEXT, link TEXT,
                        followers INTEGER DEFAULT 0, official INTEGER DEFAULT 0,
                        name TEXT,
                        PRIMARY KEY (ticker, msg_id))''')
        c.execute("PRAGMA table_info(social)")
        _scols = [r[1] for r in c.fetchall()]
        for _col, _ddl in [("followers", "INTEGER DEFAULT 0"),
                           ("official", "INTEGER DEFAULT 0"), ("name", "TEXT"),
                           ("platform", "TEXT DEFAULT 'stocktwits'"),
                           ("engagement", "INTEGER DEFAULT 0"),
                           ("title", "TEXT"), ("comments", "INTEGER DEFAULT 0")]:
            if _col not in _scols:
                try:
                    c.execute(f"ALTER TABLE social ADD COLUMN {_col} {_ddl}")
                except Exception:
                    pass

        c.execute("SELECT COUNT(*) FROM company_categories")
        if c.fetchone()[0] == 0:
            defaults = [("🇺🇸 美股", 1), ("🇨🇳 沪深", 2), ("🇭🇰 港股", 3), ("🇯🇵 日股", 4), ("🇹🇼 台股", 5)]
            c.executemany("INSERT OR IGNORE INTO company_categories (name, display_order) VALUES (?, ?)", defaults)
            region_map = {"US": "🇺🇸 美股", "CN": "🇨🇳 沪深", "HK": "🇭🇰 港股", "JP": "🇯🇵 日股", "TW": "🇹🇼 台股"}
            c.execute("SELECT ticker, region FROM companies")
            for t, r in c.fetchall():
                cat = region_map.get(r)
                if cat:
                    c.execute("""INSERT OR IGNORE INTO category_members (category_id, ticker)
                                 SELECT id, ? FROM company_categories WHERE name = ?""", (t, cat))
        conn.commit()
    finally:
        conn.close()


# ---------------- financial records ----------------

def get_financial_records(ticker):
    conn = _conn()
    try:
        df = pd.read_sql("SELECT * FROM financial_records WHERE ticker = ? ORDER BY report_date ASC",
                         conn, params=(ticker,))
        return df.to_dict('records')
    except Exception:
        return []
    finally:
        conn.close()


def save_financial_record(record: dict):
    conn = _conn()
    try:
        clean = {k: v for k, v in record.items() if v is not None}
        cols = ", ".join(clean.keys())
        ph = ", ".join(["?"] * len(clean))
        conn.execute(f"INSERT OR REPLACE INTO financial_records ({cols}) VALUES ({ph})", tuple(clean.values()))
        conn.commit()
        _bump()
        return True
    except Exception as e:
        print(f"save_financial_record error: {e}")
        return False
    finally:
        conn.close()


def delete_financial_record(ticker, year, period):
    conn = _conn()
    try:
        conn.execute("DELETE FROM financial_records WHERE ticker=? AND year=? AND period=?", (ticker, year, period))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ---------------- market data ----------------

def save_market_history(ticker, df_history: pd.DataFrame):
    if df_history.empty:
        return
    req = ['Close', 'Volume', 'market_cap', 'pe_ttm', 'pe_static', 'eps_ttm']
    for col in req:
        if col not in df_history.columns:
            df_history[col] = None
    data = [(ticker, d.strftime('%Y-%m-%d'), r['Close'], r['Volume'], r['market_cap'],
             r['pe_ttm'], r['pe_static'], r['eps_ttm']) for d, r in df_history.iterrows()]
    conn = _conn()
    try:
        conn.executemany('''INSERT OR REPLACE INTO market_daily
                            (ticker, date, close, volume, market_cap, pe_ttm, pe_static, eps_ttm)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', data)
        conn.commit()
        _bump()
    finally:
        conn.close()


def get_market_history(ticker):
    conn = _conn()
    try:
        return pd.read_sql("SELECT * FROM market_daily WHERE ticker = ? ORDER BY date ASC",
                           conn, params=(ticker,), parse_dates=['date'])
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


# ---------------- company meta ----------------

def update_company_snapshot(ticker, market_cap, eps_ttm, sector=None, industry=None):
    conn = _conn()
    try:
        fields = ["last_market_cap = ?", "last_eps_ttm = ?", "last_update = date('now')"]
        params = [market_cap, eps_ttm]
        if sector:
            fields.append("sector = ?"); params.append(sector)
        if industry:
            fields.append("industry = ?"); params.append(industry)
        params.append(ticker)
        cur = conn.execute(f"UPDATE companies SET {', '.join(fields)} WHERE ticker = ?", tuple(params))
        if cur.rowcount == 0:
            conn.execute("INSERT INTO companies (ticker, last_market_cap, last_eps_ttm, sector, industry) VALUES (?,?,?,?,?)",
                         (ticker, market_cap, eps_ttm, sector or 'Unknown', industry or 'Unknown'))
        conn.commit()
        _bump()
    finally:
        conn.close()


def get_company_meta(ticker):
    conn = _conn()
    try:
        cur = conn.execute("SELECT * FROM companies WHERE ticker = ?", (ticker,))
        row = cur.fetchone()
        if row:
            return dict(zip([d[0] for d in cur.description], row))
        return {}
    finally:
        conn.close()


def save_company_meta(ticker, name, unit=None, region='US'):
    unit = unit or "Billion"
    conn = _conn()
    try:
        conn.execute("""INSERT INTO companies (ticker, name, unit, region) VALUES (?, ?, ?, ?)
                        ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, unit=excluded.unit, region=excluded.region""",
                     (ticker, name, unit, region))
        conn.commit()
        _bump()
    finally:
        conn.close()


def get_all_tickers():
    conn = _conn()
    try:
        return [r[0] for r in conn.execute("SELECT ticker FROM companies").fetchall()]
    finally:
        conn.close()


def delete_company(ticker):
    conn = _conn()
    try:
        for t in ["category_members", "financial_records", "market_daily",
                  "analyst_price_targets", "analyst_estimates", "recommendation_trends", "companies"]:
            conn.execute(f"DELETE FROM {t} WHERE ticker = ?", (ticker,))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def detect_region_from_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.endswith('.SS') or t.endswith('.SZ'):
        return 'CN'
    if t.endswith('.HK'):
        return 'HK'
    if t.endswith('.T'):
        return 'JP'
    if t.endswith('.TW'):
        return 'TW'
    return 'US'


# ---------------- categories ----------------

def get_all_categories():
    conn = _conn()
    try:
        rows = conn.execute("SELECT id, name, display_order FROM company_categories ORDER BY display_order ASC").fetchall()
        return [{"id": r[0], "name": r[1], "display_order": r[2]} for r in rows]
    finally:
        conn.close()


def get_categories_with_companies():
    conn = _conn()
    try:
        cats = conn.execute("SELECT id, name FROM company_categories ORDER BY display_order ASC").fetchall()
        result, seen = [], set()
        for cid, cname in cats:
            members = conn.execute("""SELECT cm.ticker, COALESCE(co.name, cm.ticker)
                                      FROM category_members cm LEFT JOIN companies co ON cm.ticker = co.ticker
                                      WHERE cm.category_id = ? ORDER BY cm.ticker""", (cid,)).fetchall()
            comps = [{"ticker": m[0], "name": m[1]} for m in members]
            seen.update(m[0] for m in members)
            result.append({"id": cid, "name": cname, "companies": comps})
        allc = conn.execute("SELECT ticker, COALESCE(name, ticker) FROM companies ORDER BY ticker").fetchall()
        un = [{"ticker": t, "name": n} for t, n in allc if t not in seen]
        if un:
            result.append({"id": -1, "name": "📋 未分组", "companies": un})
        return result
    finally:
        conn.close()


def create_category(name):
    conn = _conn()
    try:
        nxt = conn.execute("SELECT COALESCE(MAX(display_order), 0) + 1 FROM company_categories").fetchone()[0]
        conn.execute("INSERT INTO company_categories (name, display_order) VALUES (?, ?)", (name, nxt))
        conn.commit()
        _bump()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_category(category_id):
    conn = _conn()
    try:
        conn.execute("DELETE FROM category_members WHERE category_id = ?", (category_id,))
        conn.execute("DELETE FROM company_categories WHERE id = ?", (category_id,))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def rename_category(category_id, new_name):
    conn = _conn()
    try:
        conn.execute("UPDATE company_categories SET name = ? WHERE id = ?", (new_name, category_id))
        conn.commit()
        _bump()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_company_to_category(category_id, ticker):
    conn = _conn()
    try:
        conn.execute("INSERT OR IGNORE INTO category_members (category_id, ticker) VALUES (?, ?)", (category_id, ticker))
        conn.commit()
        _bump()
        return True
    finally:
        conn.close()


def remove_company_from_category(category_id, ticker):
    conn = _conn()
    try:
        conn.execute("DELETE FROM category_members WHERE category_id = ? AND ticker = ?", (category_id, ticker))
        conn.commit()
        _bump()
        return True
    finally:
        conn.close()


def auto_assign_company_to_region_category(ticker, region):
    region_map = {"US": "🇺🇸 美股", "CN": "🇨🇳 沪深", "HK": "🇭🇰 港股", "JP": "🇯🇵 日股", "TW": "🇹🇼 台股"}
    cat = region_map.get(region)
    if not cat:
        return
    conn = _conn()
    try:
        row = conn.execute("SELECT id FROM company_categories WHERE name = ?", (cat,)).fetchone()
        if row:
            conn.execute("INSERT OR IGNORE INTO category_members (category_id, ticker) VALUES (?, ?)", (row[0], ticker))
            conn.commit()
            _bump()
    finally:
        conn.close()


# ---------------- analyst cache ----------------

def save_price_target(ticker, data):
    conn = _conn()
    try:
        conn.execute('''INSERT OR REPLACE INTO analyst_price_targets
                        (ticker, symbol, target_high, target_low, target_mean, target_median, last_updated, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (ticker, data.get('symbol', ticker), data.get('targetHigh'), data.get('targetLow'),
                      data.get('targetMean'), data.get('targetMedian'),
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'), json.dumps(data)))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_price_target(ticker):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM analyst_price_targets WHERE ticker = ?", (ticker,)).fetchone()
        if not row:
            return None
        cols = ['ticker', 'symbol', 'target_high', 'target_low', 'target_mean', 'target_median', 'last_updated', 'raw_data']
        res = dict(zip(cols, row))
        if res.get('raw_data'):
            try:
                res['raw_data'] = json.loads(res['raw_data'])
            except Exception:
                pass
        return res
    finally:
        conn.close()


def save_analyst_estimates(ticker, estimate_type, freq, data):
    conn = _conn()
    try:
        conn.execute('''INSERT OR REPLACE INTO analyst_estimates (ticker, estimate_type, freq, data, last_updated)
                        VALUES (?, ?, ?, ?, ?)''',
                     (ticker, estimate_type, freq, json.dumps(data), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_analyst_estimates(ticker, estimate_type, freq):
    conn = _conn()
    try:
        row = conn.execute("SELECT data, last_updated FROM analyst_estimates WHERE ticker=? AND estimate_type=? AND freq=?",
                           (ticker, estimate_type, freq)).fetchone()
        if row:
            return {'data': json.loads(row[0]), 'last_updated': row[1]}
        return None
    finally:
        conn.close()


def save_recommendation_trends(ticker, trends):
    conn = _conn()
    try:
        for t in trends:
            conn.execute('''INSERT OR REPLACE INTO recommendation_trends
                            (ticker, period, strong_buy, buy, hold, sell, strong_sell) VALUES (?,?,?,?,?,?,?)''',
                         (ticker, t.get('period', ''), t.get('strong_buy', t.get('strongBuy', 0)),
                          t.get('buy', 0), t.get('hold', 0), t.get('sell', 0),
                          t.get('strong_sell', t.get('strongSell', 0))))
        conn.commit()
        _bump()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_recommendation_trends(ticker):
    conn = _conn()
    try:
        df = pd.read_sql("SELECT * FROM recommendation_trends WHERE ticker = ? ORDER BY period ASC", conn, params=(ticker,))
        return df.to_dict('records')
    except Exception:
        return []
    finally:
        conn.close()


# ---------------- v4: ingest / cross-verification ----------------

def clear_financial_records(ticker):
    conn = _conn()
    try:
        conn.execute("DELETE FROM financial_records WHERE ticker = ?", (ticker,))
        conn.commit()
        _bump()
    finally:
        conn.close()


def clear_provenance(ticker):
    conn = _conn()
    try:
        conn.execute("DELETE FROM metric_provenance WHERE ticker = ?", (ticker,))
        conn.commit()
    finally:
        conn.close()


def save_provenance(ticker, year, period, prov_rows):
    """prov_rows: list of (metric, chosen, source, agreement, spread, sources_dict)."""
    conn = _conn()
    try:
        for metric, chosen, source, agreement, spread, sources in prov_rows:
            conn.execute('''INSERT OR REPLACE INTO metric_provenance
                            (ticker, year, period, metric, chosen_value, chosen_source,
                             agreement, spread, sources_json)
                            VALUES (?,?,?,?,?,?,?,?,?)''',
                         (ticker, year, period, metric, chosen, source,
                          agreement, spread, json.dumps(sources)))
        conn.commit()
    finally:
        conn.close()


def get_provenance(ticker, year=None, period=None):
    conn = _conn()
    try:
        q = "SELECT year, period, metric, chosen_value, chosen_source, agreement, spread, sources_json FROM metric_provenance WHERE ticker = ?"
        params = [ticker]
        if year is not None:
            q += " AND year = ?"; params.append(year)
        if period is not None:
            q += " AND period = ?"; params.append(period)
        rows = conn.execute(q, tuple(params)).fetchall()
        out = []
        for r in rows:
            d = {"year": r[0], "period": r[1], "metric": r[2], "chosen_value": r[3],
                 "chosen_source": r[4], "agreement": r[5], "spread": r[6]}
            try:
                d["sources"] = json.loads(r[7]) if r[7] else {}
            except Exception:
                d["sources"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def set_ingest_meta(ticker, report):
    conn = _conn()
    try:
        conn.execute('''INSERT OR REPLACE INTO ingest_meta (ticker, last_ingest, report_json)
                        VALUES (?,?,?)''',
                     (ticker, report.get("ts"), json.dumps(report)))
        conn.commit()
    finally:
        conn.close()


def get_ingest_meta(ticker):
    conn = _conn()
    try:
        row = conn.execute("SELECT last_ingest, report_json FROM ingest_meta WHERE ticker = ?",
                           (ticker,)).fetchone()
        if not row:
            return None
        try:
            return {"last_ingest": row[0], "report": json.loads(row[1])}
        except Exception:
            return {"last_ingest": row[0], "report": {}}
    finally:
        conn.close()


def get_annual_records(ticker):
    """FY rows only — the long-horizon (5y+) annual statement history."""
    conn = _conn()
    try:
        df = pd.read_sql("SELECT * FROM financial_records WHERE ticker = ? AND period = 'FY' ORDER BY year ASC",
                         conn, params=(ticker,))
        return df.to_dict('records')
    finally:
        conn.close()


# ---------------- v4: news ----------------

def save_news(ticker, items):
    conn = _conn()
    try:
        for it in items:
            conn.execute('''INSERT OR REPLACE INTO news
                            (ticker, uuid, title, publisher, link, published, summary, sentiment)
                            VALUES (?,?,?,?,?,?,?,?)''',
                         (ticker, it.get("uuid"), it.get("title"), it.get("publisher"),
                          it.get("link"), it.get("published"), it.get("summary"),
                          it.get("sentiment")))
        conn.commit()
        _bump()
        return True
    except Exception as e:
        print(f"save_news error: {e}")
        return False
    finally:
        conn.close()


def get_news(ticker, limit=50):
    conn = _conn()
    try:
        df = pd.read_sql("SELECT * FROM news WHERE ticker = ? ORDER BY published DESC LIMIT ?",
                         conn, params=(ticker, limit))
        return df.to_dict('records')
    except Exception:
        return []
    finally:
        conn.close()


def save_social(ticker, items):
    conn = _conn()
    try:
        for it in items:
            conn.execute('''INSERT OR REPLACE INTO social
                            (ticker, msg_id, body, user, created, sentiment, link, followers, official, name,
                             platform, engagement, title, comments)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (ticker, str(it.get("msg_id")), it.get("body"), it.get("user"),
                          it.get("created"), it.get("sentiment"), it.get("link"),
                          int(it.get("followers") or 0), int(bool(it.get("official"))),
                          it.get("name"), it.get("platform") or "stocktwits",
                          int(it.get("engagement") or 0), it.get("title"),
                          int(it.get("comments") or 0)))
        conn.commit()
        _bump()
        return True
    except Exception as e:
        print(f"save_social error: {e}")
        return False
    finally:
        conn.close()


def clear_social(ticker):
    conn = _conn()
    try:
        conn.execute("DELETE FROM social WHERE ticker = ?", (ticker,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_social(ticker, limit=80):
    conn = _conn()
    try:
        df = pd.read_sql("SELECT * FROM social WHERE ticker = ? ORDER BY engagement DESC, created DESC LIMIT ?",
                         conn, params=(ticker, limit))
        return df.to_dict('records')
    except Exception:
        return []
    finally:
        conn.close()

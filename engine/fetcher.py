# engine/fetcher.py — yfinance market & analyst sync (Streamlit-free)
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from engine import db
from modules.core.calculator import process_financial_data

_rf_cache = {"rate": None, "ts": None}


def get_risk_free_rate(proxy=None):
    """10Y Treasury yield via ^TNX, cached 24h in-process. Falls back to 4.5%."""
    now = datetime.now()
    if _rf_cache["rate"] is not None and _rf_cache["ts"] and now - _rf_cache["ts"] < timedelta(hours=24):
        return _rf_cache["rate"]
    try:
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        import yfinance as yf
        hist = yf.Ticker("^TNX").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1]) / 100.0
            _rf_cache.update(rate=rate, ts=now)
            return rate
    except Exception as e:
        print(f"risk-free fetch failed: {e}")
    return 0.045


def _yahoo_chart_history(symbol, proxy=None, rng="10y"):
    """Keyless daily price history via Yahoo chart API (yfinance-independent)."""
    import requests
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": rng, "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Stock-Ward/4"},
                     timeout=15, proxies=proxies)
    r.raise_for_status()
    res = (r.json().get("chart") or {}).get("result") or []
    if not res:
        return None, {}
    res = res[0]
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    vols = q.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        rows.append((datetime.utcfromtimestamp(t), float(c), vols[i] if i < len(vols) and vols[i] else 0))
    if not rows:
        return None, res.get("meta", {})
    df = pd.DataFrame(rows, columns=["date", "Close", "Volume"]).set_index("date")
    return df, res.get("meta", {})


def _nasdaq_summary(symbol):
    """Keyless market cap / sector / industry via Nasdaq summary endpoint."""
    import requests
    try:
        r = requests.get(f"https://api.nasdaq.com/api/quote/{symbol}/summary",
                         params={"assetclass": "stocks"},
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=12)
        r.raise_for_status()
        d = (r.json().get("data") or {}).get("summaryData") or {}
        def _num(k):
            v = ((d.get(k) or {}).get("value") or "").replace("$", "").replace(",", "")
            try:
                return float(v)
            except Exception:
                return None
        return {"market_cap": _num("MarketCap"),
                "sector": (d.get("Sector") or {}).get("value"),
                "industry": (d.get("Industry") or {}).get("value")}
    except Exception:
        return {}


def sync_market_data(ticker_symbol, proxy=None):
    """Download full price history, compute daily PE from financials, store.
    Resilient: falls back to keyless Yahoo chart + Nasdaq when yfinance fails."""
    log = []
    try:
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy

        hist, shares, sector, industry = None, 0, None, None
        # --- primary: yfinance ---
        try:
            import yfinance as yf
            t = yf.Ticker(ticker_symbol)
            hist = t.history(period="max")
            if hist is not None and not hist.empty:
                if hasattr(hist.index, "tz_localize"):
                    hist.index = hist.index.tz_localize(None)
                try:
                    shares = t.fast_info.shares or 0
                except Exception:
                    pass
                try:
                    info = t.info or {}
                    if not shares:
                        shares = info.get("sharesOutstanding", 0) or 0
                    sector = info.get("sector"); industry = info.get("industry")
                except Exception:
                    pass
            else:
                hist = None
        except Exception as e:
            log.append(f"yfinance failed: {e}")

        # --- fallback: keyless Yahoo chart API ---
        if hist is None or hist.empty:
            hist, meta = _yahoo_chart_history(ticker_symbol, proxy)
            if hist is None or hist.empty:
                return {"ok": False, "msg": "No price history (yfinance + chart API both failed)", "log": log}
            log.append(f"chart-API history: {len(hist)} rows")

        # --- fallback for shares / sector via Nasdaq (keyless) ---
        last_close = float(hist["Close"].iloc[-1])
        if not shares or not sector:
            nq = _nasdaq_summary(ticker_symbol)
            if nq.get("market_cap") and last_close > 0 and not shares:
                shares = nq["market_cap"] / last_close
            sector = sector or nq.get("sector")
            industry = industry or nq.get("industry")
        sector = sector or "Unknown"; industry = industry or "Unknown"
        log.append(f"history rows={len(hist)}, shares={shares:.0f}, sector={sector}")

        hist["market_cap"] = hist["Close"] * shares if shares else None

        raw = db.get_financial_records(ticker_symbol)
        hist["pe_ttm"] = None
        hist["eps_ttm"] = None
        hist["pe_static"] = None
        if raw:
            df_raw = pd.DataFrame(raw)
            _, ds = process_financial_data(df_raw)
            if not ds.empty and "EPS_TTM" in ds.columns:
                eps = ds[["report_date", "EPS_TTM"]].dropna().copy()
                eps["report_date"] = pd.to_datetime(eps["report_date"])
                eps = eps.sort_values("report_date")
                h = hist.sort_index().copy()
                h["date_temp"] = h.index
                merged = pd.merge_asof(h, eps, left_on="date_temp", right_on="report_date", direction="backward")
                pe = (merged["Close"] / merged["EPS_TTM"]).replace([np.inf, -np.inf], None)
                hist["pe_ttm"] = pe.values
                hist["eps_ttm"] = merged["EPS_TTM"].values
                log.append(f"PE computed for {int(pe.notna().sum())} days")

        db.save_market_history(ticker_symbol, hist)
        latest = hist.iloc[-1]
        db.update_company_snapshot(ticker_symbol, float(latest.get("market_cap") or 0),
                                   float(latest.get("eps_ttm") or 0), sector=sector, industry=industry)
        mcap = float(latest.get("market_cap") or 0)
        return {"ok": True, "msg": f"Synced. price={float(latest['Close']):.2f}, mcap={mcap/1e9:.1f}B, sector={sector}",
                "log": log}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "msg": str(e), "log": log}


def fetch_analyst_data(symbol, proxy=None):
    results = {"price_target": None, "recommendations": None, "eps_estimate": None,
               "revenue_estimate": None, "errors": []}
    try:
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        import yfinance as yf
        from dateutil.relativedelta import relativedelta
        t = yf.Ticker(symbol)

        try:
            pt = t.analyst_price_targets
            if pt and isinstance(pt, dict):
                data = {"symbol": symbol, "targetHigh": pt.get("high"), "targetLow": pt.get("low"),
                        "targetMean": pt.get("mean"), "targetMedian": pt.get("median"),
                        "currentPrice": pt.get("current")}
                db.save_price_target(symbol, data)
                results["price_target"] = data
        except Exception as e:
            results["errors"].append(f"price_target: {e}")

        try:
            recs = t.recommendations
            if recs is not None and not recs.empty:
                out = []
                for _, row in recs.iterrows():
                    period = row.get("period", "")
                    try:
                        months = int(str(period).replace("m", ""))
                        pstr = (datetime.now() + relativedelta(months=months)).strftime("%Y-%m-01")
                    except Exception:
                        pstr = str(period) or datetime.now().strftime("%Y-%m-01")
                    out.append({"period": pstr, "strong_buy": int(row.get("strongBuy", 0)),
                                "buy": int(row.get("buy", 0)), "hold": int(row.get("hold", 0)),
                                "sell": int(row.get("sell", 0)), "strong_sell": int(row.get("strongSell", 0))})
                if out:
                    db.save_recommendation_trends(symbol, out)
                    results["recommendations"] = out
        except Exception as e:
            results["errors"].append(f"recommendations: {e}")

        for attr, key, prefix in [("earnings_estimate", "eps", "eps"), ("revenue_estimate", "revenue", "revenue")]:
            try:
                est = getattr(t, attr)
                if est is not None and not est.empty:
                    out = []
                    for period in est.columns:
                        row = {"period": str(period)}
                        for idx, name in [("avg", "Avg"), ("high", "High"), ("low", "Low")]:
                            row[f"{prefix}{name}"] = float(est.loc[idx, period]) if idx in est.index else None
                        row["numberAnalysts"] = int(est.loc["numberOfAnalysts", period]) if "numberOfAnalysts" in est.index else None
                        out.append(row)
                    if out:
                        db.save_analyst_estimates(symbol, key, "mixed", out)
                        results[f"{key}_estimate"] = out
            except Exception as e:
                results["errors"].append(f"{key}: {e}")
    except Exception as e:
        results["errors"].append(str(e))
    return results

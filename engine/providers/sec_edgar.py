# engine/providers/sec_edgar.py — official SEC XBRL financial facts (US tickers).
#
# Annual (FY, 10-K) figures only. These are the authoritative numbers used to
# cross-verify the per-vendor statements (yfinance / FMP / AlphaVantage).
import json
import time

import requests

from .common import (SEC_CONCEPTS, to_billions, num, NON_SCALED_METRICS, get_key)

_TICKER_MAP = None
_BASE = "https://data.sec.gov"

# Balance-sheet (instant) metrics — point-in-time, no duration.
INSTANT_METRICS = {"TotalAssets", "CurrentAssets", "TotalLiabilities",
                   "CurrentLiabilities", "TotalEquity", "EquityToParent",
                   "CashEndOfPeriod"}


def _q_from_end(end):
    """Quarter label from a period-end date (calendar quarter)."""
    m = int(end[5:7])
    return f"Q{(m - 1) // 3 + 1}"


def _quarterly_values(concept_block, instant):
    """Returns {(year, 'Qn'): (raw, end)} for single-quarter data.
    Flow metrics: ~3-month (80–100 day) durations. Instant: each snapshot."""
    from datetime import date
    out, best_filed = {}, {}
    units = concept_block.get("units", {})
    unit_key = "USD" if "USD" in units else ("USD/shares" if "USD/shares" in units
                                             else (next(iter(units), None)))
    if unit_key is None:
        return out
    for item in units[unit_key]:
        end = item.get("end")
        if not end:
            continue
        start = item.get("start")
        if instant:
            if start:  # instant metrics shouldn't have a start
                continue
        else:
            if not start:
                continue
            try:
                dur = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except Exception:
                continue
            if not (80 <= dur <= 100):  # keep only single quarters
                continue
        year = int(end[:4])
        key = (year, _q_from_end(end))
        filed = item.get("filed", "")
        if key not in best_filed or filed >= best_filed[key]:
            best_filed[key] = filed
            out[key] = (item.get("val"), end)
    return out


def _headers():
    ua = get_key("SEC_USER_AGENT") or "Stock-Ward research stockward@example.com"
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def _load_ticker_map():
    global _TICKER_MAP
    if _TICKER_MAP is not None:
        return _TICKER_MAP
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=_headers(), timeout=20)
        r.raise_for_status()
        data = r.json()
        _TICKER_MAP = {row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                       for row in data.values()}
    except Exception:
        _TICKER_MAP = {}
    return _TICKER_MAP


def ticker_to_cik(ticker):
    return _load_ticker_map().get(ticker.upper())


def _annual_values(concept_block):
    """concept_block = companyfacts['facts']['us-gaap'][Concept].
    Returns {year: value_raw} for annual 10-K FY entries."""
    out = {}
    units = concept_block.get("units", {})
    # prefer USD; fall back to USD/shares (EPS) or first available
    unit_key = "USD" if "USD" in units else ("USD/shares" if "USD/shares" in units
                                             else (next(iter(units), None)))
    if unit_key is None:
        return out
    best_filed = {}
    for item in units[unit_key]:
        form = str(item.get("form", ""))
        fp = item.get("fp")
        if not form.startswith("10-K") or fp != "FY":
            continue
        end = item.get("end")
        if not end:
            continue
        start = item.get("start")
        if start:  # duration metric — keep only ~full-year spans
            try:
                from datetime import date
                d0 = date.fromisoformat(start)
                d1 = date.fromisoformat(end)
                if not (350 <= (d1 - d0).days <= 380):
                    continue
            except Exception:
                pass
        year = int(end[:4])
        filed = item.get("filed", "")
        if year not in best_filed or filed >= best_filed[year]:
            best_filed[year] = filed
            out[year] = (item.get("val"), end)
    return out


class SECEdgarProvider:
    name = "sec_edgar"

    def available(self):
        return True  # keyless

    def fetch_financials(self, ticker, proxy=None):
        cik = ticker_to_cik(ticker)
        if not cik:
            return []  # non-US / unmapped ticker
        try:
            url = f"{_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
            r = requests.get(url, headers=_headers(), timeout=30)
            r.raise_for_status()
            facts = r.json().get("facts", {}).get("us-gaap", {})
        except Exception:
            return []

        bucket = {}   # keyed by (year, period)

        def put(key_year, period, report_date, metric, raw):
            rkey = (key_year, period)
            rec = bucket.setdefault(rkey, {"year": key_year, "period": period,
                                           "report_date": report_date})
            val = num(raw) if metric in NON_SCALED_METRICS else to_billions(raw)
            if val is not None:
                rec[metric] = val

        for metric, concepts in SEC_CONCEPTS.items():
            block = None
            for concept in concepts:
                if facts.get(concept):
                    block = facts[concept]
                    break
            if not block:
                continue
            # annual FY
            for year, (raw, end) in _annual_values(block).items():
                put(year, "FY", end, metric, raw)
            # multi-year single quarters
            for (year, q), (raw, end) in _quarterly_values(block, metric in INSTANT_METRICS).items():
                put(year, q, end, metric, raw)

        out = []
        for rec in bucket.values():
            rec["_source"] = self.name
            out.append(rec)
        return out

# engine/providers/fmp.py — Financial Modeling Prep (API key required).
import requests

from .common import (FMP_INCOME, FMP_BALANCE, FMP_CASHFLOW, to_billions, num,
                     NON_SCALED_METRICS, get_key)

_BASE = "https://financialmodelingprep.com/api/v3"


def _norm_period(p):
    p = str(p).upper()
    return "FY" if p in ("FY", "ANNUAL", "") else p  # Q1..Q4 pass through


class FMPProvider:
    name = "fmp"

    def available(self):
        return bool(get_key("FMP"))

    def _pull(self, endpoint, ticker, period, key, bucket, fmap):
        try:
            url = f"{_BASE}/{endpoint}/{ticker}"
            params = {"apikey": key, "limit": 40,
                      "period": "annual" if period == "annual" else "quarter"}
            r = requests.get(url, params=params, timeout=25)
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                return
            for row in rows:
                yr = row.get("calendarYear") or (row.get("date", "")[:4])
                if not yr:
                    continue
                per = "FY" if period == "annual" else _norm_period(row.get("period"))
                rkey = (int(yr), per)
                rec = bucket.setdefault(rkey, {"year": int(yr), "period": per,
                                               "report_date": row.get("date")})
                for field, metric in fmap.items():
                    if field in row and row[field] is not None:
                        val = num(row[field]) if metric in NON_SCALED_METRICS else to_billions(row[field])
                        if val is not None:
                            rec[metric] = val
        except Exception:
            pass

    def fetch_financials(self, ticker, proxy=None):
        key = get_key("FMP")
        if not key:
            return []
        bucket = {}
        for period in ("annual", "quarter"):
            self._pull("income-statement", ticker, period, key, bucket, FMP_INCOME)
            self._pull("balance-sheet-statement", ticker, period, key, bucket, FMP_BALANCE)
            self._pull("cash-flow-statement", ticker, period, key, bucket, FMP_CASHFLOW)
        out = []
        for rec in bucket.values():
            rec["_source"] = self.name
            out.append(rec)
        return out

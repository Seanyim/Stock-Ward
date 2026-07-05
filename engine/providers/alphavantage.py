# engine/providers/alphavantage.py — Alpha Vantage fundamentals (API key required).
import requests

from .common import (AV_INCOME, AV_BALANCE, AV_CASHFLOW, to_billions, num,
                     NON_SCALED_METRICS, get_key)

_BASE = "https://www.alphavantage.co/query"


def _q_label(date_str):
    try:
        m = int(date_str[5:7])
        return f"Q{(m - 1) // 3 + 1}"
    except Exception:
        return "FY"


class AlphaVantageProvider:
    name = "alphavantage"

    def available(self):
        return bool(get_key("ALPHAVANTAGE"))

    def _pull(self, function, ticker, key, bucket, fmap):
        try:
            r = requests.get(_BASE, params={"function": function, "symbol": ticker,
                                            "apikey": key}, timeout=25)
            r.raise_for_status()
            data = r.json()
            for section, is_annual in (("annualReports", True), ("quarterlyReports", False)):
                for row in data.get(section, []) or []:
                    fde = row.get("fiscalDateEnding", "")
                    if not fde:
                        continue
                    year = int(fde[:4])
                    period = "FY" if is_annual else _q_label(fde)
                    rkey = (year, period)
                    rec = bucket.setdefault(rkey, {"year": year, "period": period,
                                                   "report_date": fde})
                    for field, metric in fmap.items():
                        v = row.get(field)
                        if v in (None, "None", "", "-"):
                            continue
                        val = num(v) if metric in NON_SCALED_METRICS else to_billions(v)
                        if val is not None:
                            rec[metric] = val
        except Exception:
            pass

    def fetch_financials(self, ticker, proxy=None):
        key = get_key("ALPHAVANTAGE")
        if not key:
            return []
        bucket = {}
        self._pull("INCOME_STATEMENT", ticker, key, bucket, AV_INCOME)
        self._pull("BALANCE_SHEET", ticker, key, bucket, AV_BALANCE)
        self._pull("CASH_FLOW", ticker, key, bucket, AV_CASHFLOW)
        out = []
        for rec in bucket.values():
            rec["_source"] = self.name
            out.append(rec)
        return out

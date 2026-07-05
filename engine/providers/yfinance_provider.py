# engine/providers/yfinance_provider.py — financial statements via yfinance.
from .common import (YF_INCOME, YF_BALANCE, YF_CASHFLOW, to_billions, num,
                     NON_SCALED_METRICS)


def _quarter_label(ts):
    return f"Q{(ts.month - 1) // 3 + 1}"


def _ingest_statement(df, label_map, bucket, period_type):
    """df: yfinance statement (rows=line items, cols=period-end timestamps)."""
    if df is None or getattr(df, "empty", True):
        return
    for col in df.columns:
        try:
            ts = col.to_pydatetime() if hasattr(col, "to_pydatetime") else col
            year = ts.year
            period = "FY" if period_type == "annual" else _quarter_label(ts)
            key = (year, period)
            rec = bucket.setdefault(key, {"year": year, "period": period,
                                          "report_date": ts.strftime("%Y-%m-%d")})
            for label, metric in label_map.items():
                if label not in df.index:
                    continue
                raw = df.loc[label, col]
                val = num(raw) if metric in NON_SCALED_METRICS else to_billions(raw)
                if val is not None:
                    rec[metric] = val
        except Exception:
            continue


class YFinanceProvider:
    name = "yfinance"

    def available(self):
        try:
            import yfinance  # noqa
            return True
        except Exception:
            return False

    def fetch_financials(self, ticker, proxy=None):
        import os
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        import yfinance as yf
        t = yf.Ticker(ticker)
        bucket = {}
        # annual
        for attr, m in (("income_stmt", YF_INCOME), ("balance_sheet", YF_BALANCE),
                        ("cashflow", YF_CASHFLOW)):
            try:
                _ingest_statement(getattr(t, attr), m, bucket, "annual")
            except Exception:
                pass
        # quarterly
        for attr, m in (("quarterly_income_stmt", YF_INCOME),
                        ("quarterly_balance_sheet", YF_BALANCE),
                        ("quarterly_cashflow", YF_CASHFLOW)):
            try:
                _ingest_statement(getattr(t, attr), m, bucket, "quarterly")
            except Exception:
                pass
        out = []
        for rec in bucket.values():
            rec["_source"] = self.name
            out.append(rec)
        return out

# engine/providers/nasdaq.py — Nasdaq company financials (NO API KEY required).
#
# Public endpoint api.nasdaq.com returns annual (frequency=1) and quarterly
# (frequency=2) income / balance / cash-flow tables. Values are in THOUSANDS
# of USD. This is a third keyless cross-verification source (US tickers).
import re
import requests

from .common import to_billions, num, NON_SCALED_METRICS

_BASE = "https://api.nasdaq.com/api/company"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Nasdaq row label -> metric id
NQ_INCOME = {
    "Total Revenue": "TotalRevenue", "Gross Profit": "GrossProfit",
    "Operating Expenses": "OperatingExpenses", "Operating Income": "OperatingProfit",
    "Earnings Before Tax": "PreTaxIncome", "Income Tax": "IncomeTaxExpense",
    "Net Income": "NetIncome",
    "Net Income Applicable to Common Shareholders": "NetIncomeToParent",
}
NQ_BALANCE = {
    "Total Current Assets": "CurrentAssets", "Total Assets": "TotalAssets",
    "Total Current Liabilities": "CurrentLiabilities", "Total Liabilities": "TotalLiabilities",
    "Total Equity": "TotalEquity", "Cash and Cash Equivalents": "CashEndOfPeriod",
}
NQ_CASHFLOW = {
    "Cash Flows-Operating Activities": "OperatingCashFlow",
}


def _money(s):
    """Parse '$416,161,000' (thousands) or '($1,234)' -> dollars (float)."""
    if s is None:
        return None
    t = str(s).strip()
    if t in ("", "--", "-", "N/A"):
        return None
    neg = t.startswith("(")
    t = re.sub(r"[^0-9.]", "", t)
    if not t:
        return None
    try:
        v = float(t) * 1000.0  # thousands -> dollars
    except ValueError:
        return None
    return -v if neg else v


def _q_label(date_str):
    # date like '9/27/2025'
    try:
        m = int(date_str.split("/")[0])
        return f"Q{(m - 1) // 3 + 1}"
    except Exception:
        return "FY"


def _year(date_str):
    try:
        return int(date_str.split("/")[-1])
    except Exception:
        return None


class NasdaqProvider:
    name = "nasdaq"

    def available(self):
        return True  # keyless

    def _ingest_table(self, table, lab_map, annual, bucket):
        if not table:
            return
        headers = table.get("headers") or {}
        # header keys value2..valueN map to period-ending dates
        date_cols = {k: v for k, v in headers.items() if k != "value1"}
        for row in table.get("rows") or []:
            metric = lab_map.get(row.get("value1"))
            if not metric:
                continue
            for col, date_str in date_cols.items():
                if not date_str:
                    continue
                yr = _year(date_str)
                if yr is None:
                    continue
                period = "FY" if annual else _q_label(date_str)
                rkey = (yr, period)
                rec = bucket.setdefault(rkey, {"year": yr, "period": period,
                                               "report_date": _fmt_date(date_str)})
                raw = _money(row.get(col))
                if raw is None:
                    continue
                val = num(raw) if metric in NON_SCALED_METRICS else to_billions(raw)
                if val is not None:
                    rec[metric] = val

    def fetch_financials(self, ticker, proxy=None):
        bucket = {}
        for freq, annual in ((1, True), (2, False)):
            try:
                r = requests.get(f"{_BASE}/{ticker}/financials", params={"frequency": freq},
                                 headers=_HEADERS, timeout=20)
                r.raise_for_status()
                data = (r.json() or {}).get("data") or {}
            except Exception:
                continue
            self._ingest_table(data.get("incomeStatementTable"), NQ_INCOME, annual, bucket)
            self._ingest_table(data.get("balanceSheetTable"), NQ_BALANCE, annual, bucket)
            self._ingest_table(data.get("cashFlowTable"), NQ_CASHFLOW, annual, bucket)
        out = []
        for rec in bucket.values():
            rec["_source"] = self.name
            out.append(rec)
        return out


def _fmt_date(s):
    # '9/27/2025' -> '2025-09-27'
    try:
        m, d, y = s.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return None

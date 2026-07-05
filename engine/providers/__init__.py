# engine/providers — multi-source financial data providers.
#
# Each provider exposes:
#     name: str
#     available() -> bool           # True if usable (e.g. API key present)
#     fetch_financials(ticker) -> list[StatementRecord]
#
# A StatementRecord is a plain dict:
#     {"year": int, "period": "FY"|"Q1".."Q4", "report_date": "YYYY-MM-DD",
#      "<MetricId>": float (in Billions), ...,  "_source": name}
#
# Values are normalized to BILLIONS to match the financial_records schema
# (UNIT_SCALE = 1e9 in engine/valuation.py).
from .yfinance_provider import YFinanceProvider
from .sec_edgar import SECEdgarProvider
from .nasdaq import NasdaqProvider

# All providers are KEYLESS (no API key required). yfinance, SEC EDGAR and
# Nasdaq each independently supply statements, enabling cross-verification
# without any user-supplied keys.
ALL_PROVIDERS = [
    YFinanceProvider(),
    SECEdgarProvider(),
    NasdaqProvider(),
]


def active_providers():
    return [p for p in ALL_PROVIDERS if p.available()]

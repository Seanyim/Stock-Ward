# engine/providers/common.py — shared helpers, API-key loading, metric maps.
import os
import sys
import json
import math

if getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_KEYS_PATH = os.path.join(_ROOT, "data", "api_keys.json")

BILLION = 1e9


# --------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------
def load_keys() -> dict:
    """Load API keys from data/api_keys.json, falling back to environment vars.

    File format (all optional):
        {"FMP": "...", "ALPHAVANTAGE": "...", "FINNHUB": "...",
         "SEC_USER_AGENT": "Your Name your@email.com"}
    """
    keys = {}
    try:
        if os.path.exists(_KEYS_PATH):
            with open(_KEYS_PATH, "r", encoding="utf-8") as f:
                keys = json.load(f) or {}
    except Exception:
        keys = {}
    for k in ("FMP", "ALPHAVANTAGE", "FINNHUB", "SEC_USER_AGENT"):
        env = os.environ.get(f"STOCKWARD_{k}") or os.environ.get(k)
        if env and not keys.get(k):
            keys[k] = env
    return keys


def get_key(name: str):
    return load_keys().get(name)


# --------------------------------------------------------------------------
# value helpers
# --------------------------------------------------------------------------
def to_billions(v):
    """Convert a raw currency figure to Billions; return None on bad input."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f / BILLION


def num(v):
    """Pass-through numeric (per-share figures like EPS are NOT scaled)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


# Metrics that are per-share / ratio and must NOT be divided by 1e9.
NON_SCALED_METRICS = {
    "EPS", "GrossMargin", "OperatingMargin", "EBITMargin", "NetProfitMargin",
    "EBITDAMargin", "EffectiveTaxRate", "ROE", "ROA", "ROIC",
    "FCFToRevenue", "FCFToNetIncome",
}


# --------------------------------------------------------------------------
# Canonical metric maps per source row label -> our FINANCIAL_METRICS id
# --------------------------------------------------------------------------

# yfinance statement row labels (income / balance / cashflow)
YF_INCOME = {
    "Total Revenue": "TotalRevenue",
    "Operating Revenue": "OperatingRevenue",
    "Gross Profit": "GrossProfit",
    "Operating Expense": "OperatingExpenses",
    "Operating Income": "OperatingProfit",
    "Pretax Income": "PreTaxIncome",
    "Net Income": "NetIncome",
    "Net Income Common Stockholders": "NetIncomeToParent",
    "Diluted EPS": "EPS",
    "EBITDA": "EBITDA",            # used for margin calc only
    "Tax Provision": "IncomeTaxExpense",
}
YF_BALANCE = {
    "Total Assets": "TotalAssets",
    "Current Assets": "CurrentAssets",
    "Total Non Current Assets": "NonCurrentAssets",
    "Total Liabilities Net Minority Interest": "TotalLiabilities",
    "Current Liabilities": "CurrentLiabilities",
    "Total Non Current Liabilities Net Minority Interest": "NonCurrentLiabilities",
    "Stockholders Equity": "TotalEquity",
    "Common Stock Equity": "EquityToParent",
}
YF_CASHFLOW = {
    "Operating Cash Flow": "OperatingCashFlow",
    "Investing Cash Flow": "InvestingCashFlow",
    "Financing Cash Flow": "FinancingCashFlow",
    "Free Cash Flow": "FreeCashFlow",
    "End Cash Position": "CashEndOfPeriod",
}

# SEC EDGAR us-gaap concept -> metric id (annual + quarterly).
# First concept that yields a value wins (list = priority order).
SEC_CONCEPTS = {
    "TotalRevenue": ["RevenueFromContractWithCustomerExcludingAssessedTax",
                     "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax",
                     "SalesRevenueNet"],
    "GrossProfit": ["GrossProfit"],
    "OperatingProfit": ["OperatingIncomeLoss"],
    "PreTaxIncome": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "IncomeTaxExpense": ["IncomeTaxExpenseBenefit"],
    "NetIncome": ["NetIncomeLoss", "ProfitLoss"],
    "NetIncomeToParent": ["NetIncomeLoss"],
    "EPS": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "TotalAssets": ["Assets"],
    "CurrentAssets": ["AssetsCurrent"],
    "TotalLiabilities": ["Liabilities"],
    "CurrentLiabilities": ["LiabilitiesCurrent"],
    "TotalEquity": ["StockholdersEquity",
                    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "EquityToParent": ["StockholdersEquity"],
    "OperatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
    "InvestingCashFlow": ["NetCashProvidedByUsedInInvestingActivities"],
    "FinancingCashFlow": ["NetCashProvidedByUsedInFinancingActivities"],
    "CashEndOfPeriod": ["CashAndCashEquivalentsAtCarryingValue"],
}

# FMP statement JSON field -> metric id
FMP_INCOME = {
    "revenue": "TotalRevenue", "grossProfit": "GrossProfit",
    "operatingExpenses": "OperatingExpenses", "operatingIncome": "OperatingProfit",
    "incomeBeforeTax": "PreTaxIncome", "incomeTaxExpense": "IncomeTaxExpense",
    "netIncome": "NetIncome", "epsdiluted": "EPS", "ebitda": "EBITDA",
}
FMP_BALANCE = {
    "totalAssets": "TotalAssets", "totalCurrentAssets": "CurrentAssets",
    "totalNonCurrentAssets": "NonCurrentAssets", "totalLiabilities": "TotalLiabilities",
    "totalCurrentLiabilities": "CurrentLiabilities",
    "totalNonCurrentLiabilities": "NonCurrentLiabilities",
    "totalStockholdersEquity": "TotalEquity",
}
FMP_CASHFLOW = {
    "operatingCashFlow": "OperatingCashFlow",
    "netCashUsedForInvestingActivites": "InvestingCashFlow",
    "netCashUsedProvidedByFinancingActivities": "FinancingCashFlow",
    "freeCashFlow": "FreeCashFlow", "cashAtEndOfPeriod": "CashEndOfPeriod",
}

# AlphaVantage statement field -> metric id
AV_INCOME = {
    "totalRevenue": "TotalRevenue", "grossProfit": "GrossProfit",
    "operatingExpenses": "OperatingExpenses", "operatingIncome": "OperatingProfit",
    "incomeBeforeTax": "PreTaxIncome", "incomeTaxExpense": "IncomeTaxExpense",
    "netIncome": "NetIncome", "ebitda": "EBITDA",
}
AV_BALANCE = {
    "totalAssets": "TotalAssets", "totalCurrentAssets": "CurrentAssets",
    "totalNonCurrentAssets": "NonCurrentAssets",
    "totalLiabilities": "TotalLiabilities",
    "totalCurrentLiabilities": "CurrentLiabilities",
    "totalNonCurrentLiabilities": "NonCurrentLiabilities",
    "totalShareholderEquity": "TotalEquity",
}
AV_CASHFLOW = {
    "operatingCashflow": "OperatingCashFlow",
    "cashflowFromInvestment": "InvestingCashFlow",
    "cashflowFromFinancing": "FinancingCashFlow",
    "cashAndCashEquivalentsAtCarryingValue": "CashEndOfPeriod",
}

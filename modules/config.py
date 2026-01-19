# modules/config.py

# 财务指标定义 (用于数据库建表和UI生成)
# Added "category" field for UI grouping
FINANCIAL_METRICS = [
    # --- Income Statement ---
    {"id": "Revenue", "label": "营收 (Revenue)", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "Profit", "label": "净利润 (Net Income)", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "EPS", "label": "每股收益 (EPS)", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "EBITDA", "label": "EBITDA", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "Interest_Expense", "label": "利息支出", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "Pre_Tax_Income", "label": "税前利润", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    {"id": "Income_Tax", "label": "所得税费用", "format": "%.3f", "default": 0.0, "category": "Income Statement"},
    
    # --- Cash Flow ---
    {"id": "FCF", "label": "自由现金流 (FCF)", "format": "%.3f", "default": 0.0, "category": "Cash Flow"},
    {"id": "Dividends", "label": "股息支付 (Dividends)", "format": "%.3f", "default": 0.0, "category": "Cash Flow"},

    # --- Balance Sheet ---
    {"id": "Cash", "label": "现金及等价物", "format": "%.3f", "default": 0.0, "category": "Balance Sheet"},
    {"id": "Total_Debt", "label": "总债务 (Total Debt)", "format": "%.3f", "default": 0.0, "category": "Balance Sheet"},
    {"id": "Total_Assets", "label": "总资产 (Total Assets)", "format": "%.3f", "default": 0.0, "category": "Balance Sheet"},
    {"id": "Total_Liabilities", "label": "总负债 (Total Liabilities)", "format": "%.3f", "default": 0.0, "category": "Balance Sheet"},
    {"id": "Book_Value", "label": "账面价值 (Book Value)", "format": "%.3f", "default": 0.0, "category": "Balance Sheet"},
    
    # --- Manual Market / Others ---
    {"id": "Shares", "label": "总股本 (Shares)", "format": "%.3f", "default": 0.0, "category": "Manual Market Data"},
    {"id": "Manual_Market_Cap", "label": "市值 (录入时快照)", "format": "%.3f", "default": 0.0, "category": "Manual Market Data"},
]

# 用于计算的指标列表
GROWTH_METRIC_KEYS = ["Revenue", "Profit", "EPS", "FCF", "EBITDA"]
ALL_METRIC_KEYS = [m["id"] for m in FINANCIAL_METRICS]
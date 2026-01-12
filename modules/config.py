# modules/config.py

# 定义系统支持的所有财务指标映射
# Key: 内部字段名 (DB Column)
# Labels: YFinance 中可能的 Index 名称 (列表)
METRIC_MAPPING = [
    # --- 利润表 (Income Statement) ---
    {"id": "Revenue", "label": "总营收", "yf_keys": ["Total Revenue", "Operating Revenue", "Revenue"]},
    {"id": "Profit", "label": "净利润", "yf_keys": ["Net Income", "Net Income Common Stockholders"]},
    {"id": "EPS", "label": "EPS", "yf_keys": ["Basic EPS"]},
    {"id": "Gross_Profit", "label": "毛利润", "yf_keys": ["Gross Profit"]},
    {"id": "Operating_Income", "label": "营业利润", "yf_keys": ["Operating Income"]},
    {"id": "EBITDA", "label": "EBITDA", "yf_keys": ["EBITDA", "Normalized EBITDA"]},
    {"id": "R_n_D", "label": "研发费用", "yf_keys": ["Research And Development"]},
    {"id": "SG_n_A", "label": "销售管理费", "yf_keys": ["Selling General And Administration"]},
    {"id": "Interest_Expense", "label": "利息支出", "yf_keys": ["Interest Expense"]},
    {"id": "Income_Tax", "label": "所得税", "yf_keys": ["Tax Provision"]},
    
    # --- 资产负债表 (Balance Sheet) ---
    {"id": "Total_Assets", "label": "总资产", "yf_keys": ["Total Assets"]},
    {"id": "Total_Liabilities", "label": "总负债", "yf_keys": ["Total Liabilities Net Minority Interest", "Total Liabilities"]},
    {"id": "Total_Equity", "label": "股东权益", "yf_keys": ["Total Equity Gross Minority Interest", "Stockholders Equity"]},
    {"id": "Cash", "label": "现金及等价物", "yf_keys": ["Cash And Cash Equivalents"]},
    {"id": "Total_Debt", "label": "总债务", "yf_keys": ["Total Debt"]},
    {"id": "Inventory", "label": "存货", "yf_keys": ["Inventory"]},
    {"id": "Accounts_Receivable", "label": "应收账款", "yf_keys": ["Accounts Receivable"]},
    
    # --- 现金流量表 (Cash Flow) ---
    {"id": "Operating_Cash_Flow", "label": "经营现金流", "yf_keys": ["Operating Cash Flow"]},
    {"id": "Investing_Cash_Flow", "label": "投资现金流", "yf_keys": ["Investing Cash Flow"]},
    {"id": "Financing_Cash_Flow", "label": "筹资现金流", "yf_keys": ["Financing Cash Flow"]},
    {"id": "Capex", "label": "资本开支", "yf_keys": ["Capital Expenditure", "Capital Expenditures"]},
    {"id": "Free_Cash_Flow", "label": "自由现金流", "yf_keys": ["Free Cash Flow"]}, # YF 有时直接提供
]

# 提取所有 ID 供其他模块使用
ALL_METRIC_KEYS = [m["id"] for m in METRIC_MAPPING]

# 定义哪些指标不需要计算增长率 (存量/比率/负数常态)
NON_GROWTH_METRICS = ["Interest_Expense", "Income_Tax", "R_n_D", "SG_n_A"]
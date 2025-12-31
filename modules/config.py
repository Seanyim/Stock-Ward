# modules/config.py

# 定义所有需要录入的财务指标
# id: JSON中的键名 (英文)
# label: 显示在界面的名称 (中文)
# help: 提示信息
# default: 默认值
# modules/config.py
FINANCIAL_METRICS = [
    # --- 核心增长指标 (需要绘图/计算增长率) ---
    {
        "id": "Revenue",
        "label": "累计营收",
        "help": "公司的主营业务收入",
        "default": 0.0,
        "calc_growth": True,  # 是否计算 YoY/QoQ/TTM 并绘图
        "format": "%.3f"
    },
    {
        "id": "Profit",
        "label": "累计净利润",
        "help": "归属于母公司股东的净利润",
        "default": 0.0,
        "calc_growth": True,
        "format": "%.3f"
    },
    {
        "id": "EPS",
        "label": "累计 EPS",
        "help": "每股收益",
        "default": 0.0,
        "calc_growth": True,
        "format": "%.3f" # EPS 多保留一位小数
    },
    {
        "id": "FCF",
        "label": "累计自由现金流",
        "help": "用于 DCF 估值 (经营现金流 - 资本开支)",
        "default": 0.0,
        "calc_growth": True,
        "format": "%.3f"
    },
    
    # --- WACC 辅助指标 (不需要计算增长率/不需要绘图) ---
    {
        "id": "Pre_Tax_Income",
        "label": "累计税前利润",
        "help": "用于计算有效税率 (EBT)",
        "default": 0.0,
        "calc_growth": False, # 不计算增长率
        "format": "%.3f"
    },
    {
        "id": "Income_Tax",
        "label": "累计所得税",
        "help": "用于计算有效税率",
        "default": 0.0,
        "calc_growth": False,
        "format": "%.3f"
    },
    {
        "id": "Interest_Expense",
        "label": "累计利息费用",
        "help": "用于计算债务成本",
        "default": 0.0,
        "calc_growth": False,
        "format": "%.3f"
    },
    {
        "id": "Total_Debt",
        "label": "总债务 (期末值)",
        "help": "短期债务 + 长期债务",
        "default": 0.0,
        "calc_growth": False,
        "format": "%.3f"
    },
    {
        "id": "Market_Cap",
        "label": "市值 (期末值)",
        "help": "股价 * 总股本",
        "default": 0.0,
        "calc_growth": False,
        "format": "%.3f"
    },
]

# 提取需要计算增长率的指标 (用于 calculator 和 charts)
GROWTH_METRIC_KEYS = [m["id"] for m in FINANCIAL_METRICS if m.get("calc_growth", True)]

# 提取所有指标 ID (用于 data_entry 存储)
ALL_METRIC_KEYS = [m["id"] for m in FINANCIAL_METRICS]
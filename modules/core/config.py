# modules/config.py
# 财务指标定义 (用于数据库建表和UI生成)
# v2.0 - 重构为四类：关键指标、利润表、资产负债表、现金流量表

FINANCIAL_METRICS = [
    # ============================================================
    # 关键指标 (Key Ratios) - 11项
    # ============================================================
    {"id": "GrossMargin", "label": "毛利率 (%)", "format": "%.2f", "default": None, 
     "category": "关键指标", "help": "毛利 / 总收入 × 100，反映产品定价能力和成本控制"},
    {"id": "OperatingMargin", "label": "营业利润率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "营业利润 / 总收入 × 100，反映核心业务盈利能力"},
    {"id": "EBITMargin", "label": "EBIT利润率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "息税前利润 / 总收入 × 100，剔除融资和税收影响"},
    {"id": "NetProfitMargin", "label": "归母净利润率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "归属母公司净利润 / 总收入 × 100"},
    {"id": "EBITDAMargin", "label": "EBITDA利润率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "EBITDA / 总收入 × 100，剔除折旧摊销的盈利能力"},
    {"id": "EffectiveTaxRate", "label": "有效税率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "所得税费用 / 税前利润 × 100"},
    {"id": "ROE", "label": "ROE 净资产收益率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "净利润 / 股东权益 × 100，衡量股东资本回报"},
    {"id": "ROA", "label": "ROA 总资产收益率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "净利润 / 总资产 × 100，衡量资产利用效率"},
    {"id": "ROIC", "label": "ROIC 投入资本回报率 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "NOPAT / (总资产 - 流动负债) × 100，衡量资本配置效率"},
    {"id": "FCFToRevenue", "label": "自由现金流/收入比 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "自由现金流 / 总收入 × 100，反映收入转化为现金能力"},
    {"id": "FCFToNetIncome", "label": "自由现金流/净利润比 (%)", "format": "%.2f", "default": None,
     "category": "关键指标", "help": "自由现金流 / 归母净利润 × 100，反映利润质量"},

    # ============================================================
    # 利润表 (Income Statement) - 9项
    # ============================================================
    {"id": "TotalRevenue", "label": "总收入", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "公司主营业务和其他业务的全部收入"},
    {"id": "OperatingRevenue", "label": "营业总收入", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "主营业务产生的收入"},
    {"id": "GrossProfit", "label": "毛利", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "总收入 - 营业成本"},
    {"id": "OperatingExpenses", "label": "营业费用", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "销售、管理、研发等运营支出"},
    {"id": "OperatingProfit", "label": "营业利润", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "毛利 - 营业费用"},
    {"id": "PreTaxIncome", "label": "税前利润", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "扣除所得税前的利润"},
    {"id": "NetIncome", "label": "净利润", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "扣除所有费用和税收后的利润"},
    {"id": "NetIncomeToParent", "label": "归属母公司净利润", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "归属于母公司股东的净利润"},
    {"id": "EPS", "label": "每股收益 (EPS)", "format": "%.3f", "default": 0.0,
     "category": "利润表", "help": "归属普通股股东净利润 / 加权平均股数"},

    # ============================================================
    # 资产负债表 (Balance Sheet) - 8项
    # ============================================================
    {"id": "TotalAssets", "label": "总资产", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "公司拥有的全部资产"},
    {"id": "CurrentAssets", "label": "流动资产", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "一年内可变现的资产（现金、应收账款等）"},
    {"id": "NonCurrentAssets", "label": "非流动资产", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "长期资产（固定资产、无形资产等）"},
    {"id": "TotalLiabilities", "label": "负债合计", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "公司承担的全部债务"},
    {"id": "CurrentLiabilities", "label": "流动负债", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "一年内需偿还的债务"},
    {"id": "NonCurrentLiabilities", "label": "非流动负债", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "一年以上的长期债务"},
    {"id": "TotalEquity", "label": "股东权益合计", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "总资产 - 总负债"},
    {"id": "EquityToParent", "label": "归属母公司股东权益合计", "format": "%.3f", "default": 0.0,
     "category": "资产负债表", "help": "归属于母公司股东的净资产"},

    # ============================================================
    # 现金流量表 (Cash Flow Statement) - 8项
    # ============================================================
    {"id": "OperatingCashFlow", "label": "经营活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "日常经营活动产生的现金净流入"},
    {"id": "ContinuingOpCashFlow", "label": "持续经营活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "持续经营业务产生的现金流"},
    {"id": "InvestingCashFlow", "label": "投资活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "投资活动产生的现金净流出（通常为负）"},
    {"id": "ContinuingInvCashFlow", "label": "持续投资活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "持续性投资活动的现金流"},
    {"id": "FinancingCashFlow", "label": "融资活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "融资活动产生的现金净流入/流出"},
    {"id": "ContinuingFinCashFlow", "label": "持续融资活动现金流量净额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "持续性融资活动的现金流"},
    {"id": "CashEndOfPeriod", "label": "现金及等价物期末余额", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "期末持有的现金及现金等价物"},
    {"id": "FreeCashFlow", "label": "自由现金流 (FCF)", "format": "%.3f", "default": 0.0,
     "category": "现金流量表", "help": "经营现金流 - 资本支出，可自由支配的现金"},
]

# 类别显示顺序
CATEGORY_ORDER = ["关键指标", "利润表", "资产负债表", "现金流量表"]

# 用于增长率计算的指标 (流量指标，需要做TTM和YoY计算)
GROWTH_METRIC_KEYS = [
    # 利润表
    "TotalRevenue", "OperatingRevenue", "GrossProfit", "OperatingExpenses", 
    "OperatingProfit", "PreTaxIncome", "NetIncome", "NetIncomeToParent", "EPS",
    # 现金流量表
    "OperatingCashFlow", "ContinuingOpCashFlow", "InvestingCashFlow", 
    "ContinuingInvCashFlow", "FinancingCashFlow", "ContinuingFinCashFlow", 
    "FreeCashFlow"
]

# 所有指标ID列表
ALL_METRIC_KEYS = [m["id"] for m in FINANCIAL_METRICS]
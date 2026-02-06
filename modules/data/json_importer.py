# modules/json_importer.py
# JSON 财务数据批量导入模块
# v1.1 - 只保存 config 中定义的科目，自动检测数据单位

import json
import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

# 导入有效字段列表
from modules.core.config import ALL_METRIC_KEYS


# ============================================================
# 指标名映射表 (中文 → 数据库字段)
# 支持利润表、资产负债表、现金流量表、关键指标
# ============================================================

METRIC_MAPPING = {
    # ===== 利润表 =====
    "总收入": "TotalRevenue",
    "营业总收入": "OperatingRevenue",
    "营业收入": "OperatingRevenue",
    "营业总成本": "TotalOperatingCost",
    "毛利": "GrossProfit",
    "营业费用": "OperatingExpenses",
    "经营费用": "OperatingExpenses",
    "销售和管理费用": "SGA",
    "— 销售费用": "SellingExpenses",
    "— 管理费用": "AdminExpenses",
    "研发费用": "RDExpenses",
    "营业利润": "OperatingProfit",
    "税前利润": "PreTaxIncome",
    "税前收入": "PreTaxIncome",
    "所得税": "IncomeTax",
    "净利润": "NetIncome",
    "持续经营利润": "NetIncome",
    "归属于母公司股东净利润": "NetIncomeToParent",
    "归属于普通股股东净利润": "NetIncomeToParent",
    "归母净利润": "NetIncomeToParent",
    "基本每股收益": "EPS",
    "稀释每股收益": "EPS",
    "每股收益": "EPS",
    "营业外利息收入(费用)": "NetInterestIncome",
    "营业外利息收入": "InterestIncome",
    "营业外利息费用": "InterestExpense",
    "其他净收入(费用)": "OtherNetIncome",
    
    # ===== 资产负债表 =====
    "资产合计": "TotalAssets",
    "总资产": "TotalAssets",
    "资产总额": "TotalAssets",
    "流动资产合计": "CurrentAssets",
    "流动资产": "CurrentAssets",
    "非流动资产合计": "NonCurrentAssets",
    "非流动资产": "NonCurrentAssets",
    "现金及现金等价物和短期投资": "CashAndShortTermInvestments",
    "— 现金和现金等价物": "CashAndEquivalents",
    "现金及等价物": "CashAndEquivalents",
    "现金及现金等价物": "CashAndEquivalents",
    "— 短期投资": "ShortTermInvestments",
    "应收款项": "Receivables",
    "— 应收账款净额": "AccountsReceivable",
    "应收账款": "AccountsReceivable",
    "存货": "Inventory",
    "其他流动资产": "OtherCurrentAssets",
    "固定资产净额": "NetFixedAssets",
    "— 固定资产": "GrossFixedAssets",
    "— 累计折旧": "AccumulatedDepreciation",
    "总投资": "TotalInvestments",
    "— 长期股权投资": "LongTermEquityInvestment",
    "商誉及其他无形资产": "GoodwillAndIntangibles",
    "— 商誉": "Goodwill",
    "— 其他无形资产": "OtherIntangibles",
    "其他非流动资产": "OtherNonCurrentAssets",
    
    "负债合计": "TotalLiabilities",
    "总负债": "TotalLiabilities",
    "负债总额": "TotalLiabilities",
    "流动负债合计": "CurrentLiabilities",
    "流动负债": "CurrentLiabilities",
    "非流动负债合计": "NonCurrentLiabilities",
    "非流动负债": "NonCurrentLiabilities",
    "应付账款": "AccountsPayable",
    "— 应付票据": "NotesPayable",
    "— 应交税费": "TaxPayable",
    "短期债务及融资租赁负债": "ShortTermDebt",
    "— 短期借款": "ShortTermBorrowings",
    "递延负债": "DeferredLiabilities",
    "其他流动负债": "OtherCurrentLiabilities",
    "长期应付款及融资租赁负债": "LongTermPayables",
    "长期借款及融资租赁": "LongTermDebtAndLease",
    "— 长期借款": "LongTermDebt",
    "长期债务": "LongTermDebt",
    "长期负债": "LongTermDebt",
    "— 长期租赁负债": "LongTermLeaseLiabilities",
    "其他非流动负债": "OtherNonCurrentLiabilities",
    
    "股东权益合计": "TotalEquity",
    "归属于母公司股东权益合计": "EquityToParent",  # 映射到独立字段
    "归属母公司股东权益合计": "EquityToParent",    # 用户修改后的完整名称
    "股东权益": "TotalEquity",
    "归属母公司股东权益": "EquityToParent",
    "— 股本": "ShareCapital",
    "— 普通股股本": "CommonStock",
    "留存收益": "RetainedEarnings",
    "不影响留存收益的损益": "OtherComprehensiveIncome",
    "总债务": "TotalDebt",
    
    # ===== 现金流量表 =====
    "经营活动现金流量净额": "OperatingCashFlow",
    "经营现金流": "OperatingCashFlow",
    "经营活动产生的现金流量": "OperatingCashFlow",
    
    # 持续经营活动现金流量净额 - 独立字段
    "• 持续经营活动现金流量净额": "ContinuingOpCashFlow",
    "持续经营活动现金流量净额": "ContinuingOpCashFlow",
    
    "持续经营净收入": "ContinuingOperationsNetIncome",
    "折旧损耗及摊销": "DepreciationAndAmortization",
    "递延所得税": "DeferredIncomeTax",
    "营运资金变化": "WorkingCapitalChange",
    "— 应收账款 (增) 减": "ReceivablesChange",
    "— 存货 (增) 减": "InventoryChange",
    "— 应付账款及应计费用 (增) 减": "PayablesChange",
    
    "投资活动现金流量净额": "InvestingCashFlow",
    "投资现金流": "InvestingCashFlow",
    
    # 持续投资活动现金流量净额 - 独立字段
    "• 持续投资活动现金流量净额": "ContinuingInvCashFlow",
    "持续投资活动现金流量净额": "ContinuingInvCashFlow",
    
    "固定资产交易净额": "CapExNet",
    "业务交易净额": "BusinessAcquisitions",
    "投资产品交易净额": "InvestmentTransactions",
    
    "融资活动现金流量净额": "FinancingCashFlow",
    "筹资活动现金流量净额": "FinancingCashFlow",
    "融资现金流": "FinancingCashFlow",
    
    # 持续融资活动现金流量净额 - 独立字段
    "• 持续筹资活动现金流量净额": "ContinuingFinCashFlow",
    "持续筹资活动现金流量净额": "ContinuingFinCashFlow",
    
    "债务发行/偿还的净额": "DebtIssuanceRepayment",
    "普通股发行/回购的净额": "StockIssuanceRepurchase",
    "现金股利支付": "DividendsPaid",
    
    "自由现金流": "FreeCashFlow",
    "自由现金流 (FCF)": "FreeCashFlow",
    "资本支出": "CapEx",
    "资本性支出": "CapEx",
    "现金及等价物期末余额": "CashEndOfPeriod",
    "现金及现金等价物期末余额": "CashEndOfPeriod",
    "现金及现金等价物净增加额": "NetCashChange",
    "现金及现金等价物期初余额": "CashBeginOfPeriod",
    "汇率变动影响": "FXEffect",
    
    # ===== 股息 =====
    "每股派息": "DividendPerShare",
    "每股股息": "DividendPerShare",
    
    # ===== 关键指标 (百分比格式) =====
    "毛利率": "GrossMargin",
    "营业利润率": "OperatingMargin",
    "EBIT利润率": "EBITMargin",
    "归母净利率": "NetProfitMargin",
    "净利率": "NetProfitMargin",
    "EBITDA利润率": "EBITDAMargin",
    "税率": "EffectiveTaxRate",
    "有效税率": "EffectiveTaxRate",
    "净资产收益率 (ROE)": "ROE",
    "ROE": "ROE",
    "总资产净利率 (ROA)": "ROA",
    "ROA": "ROA",
    "投入资本回报率 (ROIC)": "ROIC",
    "ROIC": "ROIC",
    "自由现金流与收入比率": "FCFToRevenue",
    "自由现金流与母公司净利润比率": "FCFToNetIncome",
    "利息保障倍数 (倍)": "InterestCoverage",
    "研发费用率": "RDExpenseRatio",
    "销售费用率": "SellingExpenseRatio",
    "管理费用率": "AdminExpenseRatio",
    "长期负债股东权益比率": "LongTermDebtToEquity",
    "财务杠杆": "FinancialLeverage",
    "股东权益比率": "EquityRatio",
    "有息负债率": "InterestBearingDebtRatio",
    "流动比率": "CurrentRatio",
    "速动比率": "QuickRatio",
    "资金周转周期 (天)": "CashConversionCycle",
    "应收账款周转率 (次)": "ReceivablesTurnover",
    "存货周转率 (次)": "InventoryTurnover",
    "应付账款周转率 (次)": "PayablesTurnover",
    "固定资产周转率 (次)": "FixedAssetTurnover",
    "总资产周转率 (次)": "AssetTurnover",
    
    # ===== 元数据 =====
    "截止日期": "_report_date",
    "会计准则": "_accounting_standard",
}


def detect_data_unit(json_data: dict) -> str:
    """自动检测 JSON 数据中的单位
    
    通过检查数据中是否包含"亿"或"万"来判断单位
    
    Returns:
        "Billion" (默认) - 需要转换的中文格式
        "Raw" - 无需转换的原始数据
    """
    data = json_data.get("data", [])
    
    for item in data:
        values = item.get("values", [])
        for val in values[:5]:  # 只检查前5个值
            if val and isinstance(val, str):
                if "亿" in val or "万" in val:
                    return "ChineseUnit"
    
    return "Raw"


def parse_value(value_str: str, data_unit: str = "ChineseUnit") -> Optional[float]:
    """解析数值字符串为浮点数
    
    支持格式:
    - "461.52亿" → 46.152 (Billion)
    - "-5600.00万" → -0.056 (Billion) 
    - "68.93%" → 68.93 (百分比直接保留数值)
    - "-" → None (空值)
    - "0.000" → 0
    - "2.17" → 2.17 (纯数字，如 EPS)
    
    Args:
        value_str: 原始值字符串
        data_unit: 数据单位类型 ("ChineseUnit" 或 "Raw")
    
    Returns:
        解析后的浮点数 (金额以 Billion 为单位，比率保留原值)，或 None 表示空值
    """
    if value_str is None:
        return None
    
    value_str = str(value_str).strip()
    
    # 空值处理
    if value_str in ["-", "", "—", "N/A", "NA", "null", "None"]:
        return None
    
    # 百分比格式处理 (如 "68.93%")
    if value_str.endswith("%"):
        try:
            return float(value_str[:-1].replace(",", ""))
        except ValueError:
            return None
    
    # 提取符号
    is_negative = value_str.startswith("-")
    if is_negative:
        value_str = value_str[1:]
    
    # 尝试提取数字和单位
    match = re.match(r'^([\d,\.]+)\s*(亿|万)?$', value_str)
    
    if match:
        number_str = match.group(1).replace(",", "")
        unit = match.group(2)
        
        try:
            number = float(number_str)
        except ValueError:
            return None
        
        # 单位转换 (统一到 Billion)
        if unit == "亿":
            # 中文亿 = 1亿 = 0.1 Billion (1B = 10亿)
            number = number / 10
        elif unit == "万":
            # 中文万 = 1万 = 0.00001 Billion
            number = number / 100000
        # 无单位时为纯数字 (如 EPS)
        
        return -number if is_negative else number
    
    # 尝试直接解析为数字 (纯数字格式，如 EPS, 日期等)
    try:
        number = float(value_str.replace(",", ""))
        return -number if is_negative else number
    except ValueError:
        return None


def parse_header(header: str) -> Tuple[int, str]:
    """解析 header 获取年份和季度
    
    Args:
        header: 格式如 "2024/Q1" 或 "2024/Q2"
    
    Returns:
        (year, period) 元组
    """
    match = re.match(r'^(\d{4})[/\-]?Q?(\d)$', header)
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        return year, f"Q{quarter}"
    
    # 尝试其他格式
    match = re.match(r'^(\d{4})[/\-]Q(\d)$', header, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        return year, f"Q{quarter}"
    
    return None, None


def parse_report_date(date_str: str) -> Optional[str]:
    """解析报告截止日期
    
    Args:
        date_str: 格式如 "2024/09/30" 或 "2024-09-30"
    
    Returns:
        标准格式 "YYYY-MM-DD"
    """
    if not date_str or date_str in ["-", "", "N/A"]:
        return None
    
    for fmt in ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return None


def get_valid_db_fields() -> set:
    """获取数据库中有效的字段列表
    
    只返回 config.py 中定义的字段
    """
    # 基础字段 + 财务指标
    base_fields = {"ticker", "year", "period", "report_date"}
    return base_fields | set(ALL_METRIC_KEYS)


def parse_financial_json(json_data: dict, ticker: str) -> List[Dict]:
    """解析财务 JSON 数据
    
    自动检测数据单位，只保存 config 中定义的字段
    
    Args:
        json_data: JSON 数据
        ticker: 股票代码
    
    Returns:
        解析后的记录列表，每条记录对应一个季度
    """
    headers = json_data.get("headers", [])
    data = json_data.get("data", [])
    
    if not headers or not data:
        return []
    
    # 自动检测数据单位
    data_unit = detect_data_unit(json_data)
    
    # 获取有效字段
    valid_fields = get_valid_db_fields()
    
    # 先找到截止日期行
    report_dates = {}
    for item in data:
        metric = item.get("metric", "")
        if metric == "截止日期":
            for i, val in enumerate(item.get("values", [])):
                if i < len(headers):
                    report_dates[i] = parse_report_date(val)
            break
    
    # 为每个 header (季度) 创建记录
    records = []
    
    for col_idx, header in enumerate(headers):
        year, period = parse_header(header)
        if year is None:
            continue
        
        record = {
            "ticker": ticker,
            "year": year,
            "period": period,
            "report_date": report_dates.get(col_idx),
        }
        
        # 遍历所有指标
        for item in data:
            metric = item.get("metric", "")
            values = item.get("values", [])
            
            if col_idx >= len(values):
                continue
            
            db_field = METRIC_MAPPING.get(metric)
            if not db_field or db_field.startswith("_"):
                continue
            
            # 验证字段是否在 config 中定义
            if db_field not in valid_fields:
                continue
            
            value = parse_value(values[col_idx], data_unit)
            
            # 只有非 None 值才写入
            if value is not None:
                record[db_field] = value
        
        records.append(record)
    
    return records


def import_json_to_database(json_data: dict, ticker: str) -> Tuple[int, List[str]]:
    """将 JSON 数据导入数据库
    
    自动检测数据单位，过滤无效字段
    
    Args:
        json_data: JSON 数据
        ticker: 股票代码
    
    Returns:
        (成功数量, 错误列表)
    """
    from modules.core.db import save_financial_record
    
    records = parse_financial_json(json_data, ticker)
    
    success_count = 0
    errors = []
    
    for record in records:
        try:
            if save_financial_record(record):
                success_count += 1
            else:
                errors.append(f"{record['year']}/{record['period']}: 保存失败")
        except Exception as e:
            errors.append(f"{record['year']}/{record['period']}: {str(e)}")
    
    return success_count, errors


def validate_json_structure(json_data: dict) -> Tuple[bool, str]:
    """验证 JSON 结构是否符合要求
    
    Returns:
        (是否有效, 错误信息)
    """
    if not isinstance(json_data, dict):
        return False, "JSON 必须是对象格式"
    
    if "headers" not in json_data:
        return False, "缺少 'headers' 字段"
    
    if "data" not in json_data:
        return False, "缺少 'data' 字段"
    
    headers = json_data.get("headers", [])
    if not isinstance(headers, list) or len(headers) == 0:
        return False, "'headers' 必须是非空数组"
    
    data = json_data.get("data", [])
    if not isinstance(data, list) or len(data) == 0:
        return False, "'data' 必须是非空数组"
    
    # 检查至少有一个有效的指标映射
    valid_metrics = 0
    for item in data:
        metric = item.get("metric", "")
        if metric in METRIC_MAPPING:
            valid_metrics += 1
    
    if valid_metrics == 0:
        return False, "未找到可识别的财务指标"
    
    return True, f"验证通过，识别到 {valid_metrics} 个指标"


# ============================================================
# 测试函数
# ============================================================

def test_parse_value():
    """测试数值解析"""
    test_cases = [
        ("461.52亿", 46.152),
        ("-5600.00万", -0.056),
        ("-", None),
        ("0.000", 0.0),
        ("2.17", 2.17),
        ("1.41亿", 0.141),
        ("-1.75亿", -0.175),
    ]
    
    print("测试 parse_value():")
    for value_str, expected in test_cases:
        result = parse_value(value_str)
        status = "✅" if (result == expected or (result is None and expected is None)) else "❌"
        print(f"  {status} '{value_str}' → {result} (期望: {expected})")


def test_import_msft():
    """测试 MSFT 利润表导入"""
    import os
    
    json_path = os.path.join("upload", "MSFT_profit.json")
    if not os.path.exists(json_path):
        print(f"❌ 测试文件不存在: {json_path}")
        return
    
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    # 验证结构
    is_valid, msg = validate_json_structure(json_data)
    print(f"验证结构: {msg}")
    
    if not is_valid:
        return
    
    # 解析数据
    records = parse_financial_json(json_data, "MSFT", "Billion")
    print(f"\n解析到 {len(records)} 条记录")
    
    # 显示前 3 条
    for i, record in enumerate(records[:3]):
        print(f"\n记录 {i+1}: {record['year']}/{record['period']}")
        for key, val in record.items():
            if key not in ['ticker', 'year', 'period']:
                print(f"  {key}: {val}")


if __name__ == "__main__":
    test_parse_value()
    print("\n" + "="*50 + "\n")
    test_import_msft()

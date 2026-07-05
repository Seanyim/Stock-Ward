# engine/masters.py — 9-master scoring + QG-Pro (Streamlit-free, fixed debt/units)
import numpy as np
import pandas as pd

from modules.data.industry_data import get_industry_benchmarks
from engine.valuation import safe, _f, resolve_debt_cash, resolve_ebitda, resolve_tax_rate, UNIT_SCALE

MASTER_DEFINITIONS = {
    "Buffett":    {"name_cn": "沃伦·巴菲特", "name_en": "Warren Buffett", "philosophy_cn": "护城河与现金回报", "philosophy_en": "Moats & cash returns", "icon": "🏰", "color": "#2E86AB"},
    "Munger":     {"name_cn": "查理·芒格", "name_en": "Charlie Munger", "philosophy_cn": "质量风控与反转", "philosophy_en": "Quality & risk control", "icon": "🛡️", "color": "#A23B72"},
    "Lynch":      {"name_cn": "彼得·林奇", "name_en": "Peter Lynch", "philosophy_cn": "动态 GARP", "philosophy_en": "Dynamic GARP", "icon": "📈", "color": "#F18F01"},
    "Graham":     {"name_cn": "本杰明·格雷厄姆", "name_en": "Benjamin Graham", "philosophy_cn": "深度价值与安全边际", "philosophy_en": "Deep value & margin of safety", "icon": "🔒", "color": "#C73E1D"},
    "Greenblatt": {"name_cn": "乔尔·格林布拉特", "name_en": "Joel Greenblatt", "philosophy_cn": "神奇公式", "philosophy_en": "Magic formula", "icon": "✨", "color": "#2D936C"},
    "Fisher":     {"name_cn": "菲利普·费雪", "name_en": "Philip Fisher", "philosophy_cn": "极速成长与创新", "philosophy_en": "Hyper-growth & innovation", "icon": "🚀", "color": "#6B4226"},
    "Templeton":  {"name_cn": "约翰·邓普顿", "name_en": "John Templeton", "philosophy_cn": "逆向估值与均值回归", "philosophy_en": "Contrarian & mean reversion", "icon": "🔄", "color": "#5C4D7D"},
    "Dalio":      {"name_cn": "瑞·达里奥", "name_en": "Ray Dalio", "philosophy_cn": "宏观稳健与债务杠杆", "philosophy_en": "Macro resilience & leverage", "icon": "🌊", "color": "#1B4965"},
    "Soros":      {"name_cn": "乔治·索罗斯", "name_en": "George Soros", "philosophy_cn": "动量与反身性", "philosophy_en": "Momentum & reflexivity", "icon": "⚡", "color": "#E63946"},
}


def linear_scale(value, bad, target, excellent, reverse=False):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if reverse:
        value, bad, target, excellent = -value, -bad, -target, -excellent
    if value <= bad:
        return 0.0
    if value < target:
        d = target - bad
        return 5.0 * (value - bad) / d if d != 0 else 2.5
    if value < excellent:
        d = excellent - target
        return 5.0 + 5.0 * (value - target) / d if d != 0 else 7.5
    return 10.0


def _weighted_score(items):
    """items: [(score_or_None, weight, name)] → (0-100 score, status)"""
    avail = [(s, w, n) for s, w, n in items if s is not None]
    if not avail:
        return 50.0, {"degraded": "all factors missing → neutral 50"}
    tw = sum(w for _, w, _ in avail)
    if tw == 0:
        return 50.0, {"degraded": "zero weights"}
    final = float(np.clip(sum(s * (w / tw) for s, w, _ in avail) * 10, 0, 100))
    status = {}
    missing = [n for s, _, n in items if s is None]
    if missing:
        status["degraded"] = "missing: " + ", ".join(missing)
    return final, status


def _safe_div(a, b, default=0.0):
    if b == 0 or b is None or a is None or (isinstance(b, float) and np.isnan(b)) or (isinstance(a, float) and np.isnan(a)):
        return default
    return a / b


def _ma_deviation(prices, current_price):
    if current_price <= 0 or len(prices) == 0:
        return None, None
    if len(prices) >= 200:
        ma = prices.iloc[-200:].mean(); label = "MA200"
    elif len(prices) >= 50:
        ma = prices.iloc[-50:].mean(); label = "MA50 (fallback)"
    else:
        return None, None
    if pd.isna(ma) or ma == 0:
        return None, None
    return (current_price / ma) - 1.0, label


def compute_master_scores(ctx):
    ds, latest, meta, dp = ctx["df_single"], ctx["latest"], ctx["meta"], ctx["df_price"]
    results = {}
    if latest is None:
        return results
    market_cap = ctx["market_cap"]
    bench = get_industry_benchmarks(ctx["sector"])
    price = ctx["current_price"]
    eps = ctx["eps_ttm"]
    pe_ttm = ctx["pe_ttm"]

    def col(name):
        return pd.to_numeric(ds[name], errors="coerce").dropna() if name in ds.columns else pd.Series(dtype=float)

    roe_s, gm_s, fcf_s = col("ROE"), col("GrossMargin"), col("FreeCashFlow_TTM")
    rev_s, eps_s, opex_s = col("TotalRevenue_TTM"), col("EPS_TTM"), col("OperatingExpenses_TTM")

    fcf = safe(latest, "FreeCashFlow_TTM", 0)
    ocf = safe(latest, "OperatingCashFlow_TTM", 0)
    if fcf == 0 and ocf != 0:
        icf = safe(latest, "InvestingCashFlow_TTM", 0)
        fcf = ocf + icf if icf != 0 else ocf
    ni = safe(latest, "NetIncome_TTM", 0)
    debt_b, cash_b = resolve_debt_cash(ctx)            # fixed debt proxy
    te = safe(latest, "TotalEquity", 0)
    ta = safe(latest, "TotalAssets", 0)
    ebitda_b, _ = resolve_ebitda(ctx)
    ca = safe(latest, "CurrentAssets", 0)
    tl = safe(latest, "TotalLiabilities", 0)
    tax = resolve_tax_rate(ctx)
    op = safe(latest, "OperatingProfit_TTM", 0)
    invested = te + debt_b
    roic_val = (op * (1 - tax) / invested * 100) if (op != 0 and invested > 0) else (safe(latest, "ROIC", 0) or 0)

    # ---- Buffett ----
    f = {}
    s1 = s2 = s3 = None
    if len(roe_s) >= 4:
        stab = _safe_div(roe_s.mean(), roe_s.std() + 0.01)
        s1 = linear_scale(stab, 0.5, 2.0, 5.0)
        f["ROE mean %"] = _f(roe_s.mean(), 1); f["ROE stability μ/σ"] = _f(stab, 2)
    if len(fcf_s) >= 4 and ta > 0:
        pct = fcf_s.mean() / ta * 100
        s2 = linear_scale(pct, -2, 5, 15)
        f["FCF/TotalAssets %"] = _f(pct, 1)
    elif fcf != 0 and ta > 0:
        pct = fcf / ta * 100
        s2 = linear_scale(pct, -2, 5, 15)
        f["FCF/TotalAssets %"] = _f(pct, 1)
    if len(gm_s) >= 4:
        s3 = linear_scale(gm_s.std(), 15, 5, 1, reverse=True)
        f["GrossMargin σ %"] = _f(gm_s.std(), 2)
    sc, st = _weighted_score([(s1, .45, "ROE stability"), (s2, .35, "FCF mean"), (s3, .20, "GM volatility")])
    f.update(st)
    results["Buffett"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2, s3))}

    # ---- Munger ----
    f = {}
    de = _safe_div(debt_b, te) if te > 0 else None
    conv = _safe_div(fcf, ni) if ni > 0 else None
    s1 = linear_scale(roic_val, 5, 15, 25) if roic_val != 0 else None
    s2 = linear_scale(de, 2.0, 1.0, 0.3, reverse=True) if de is not None else None
    s3 = linear_scale(conv, 0.3, 0.8, 1.2) if conv is not None else None
    if roic_val:
        f["ROIC %"] = _f(roic_val, 1)
    if de is not None:
        f["Debt/Equity"] = _f(de, 2)
    if conv is not None:
        f["FCF conversion"] = _f(conv, 2)
    sc, st = _weighted_score([(s1, .40, "ROIC"), (s2, .30, "D/E"), (s3, .30, "FCF conv")])
    f.update(st)
    results["Munger"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2, s3))}

    # ---- Lynch ----
    f = {}
    eps_yoy = safe(latest, "EPS_TTM_YoY", None)
    s1 = s2 = None
    if pe_ttm > 0 and eps_yoy is not None and eps_yoy > 0:
        peg = pe_ttm / (eps_yoy * 100 + 0.01)
        s1 = linear_scale(peg, 3.0, 1.0, 0.5, reverse=True)
        f["PE TTM"] = _f(pe_ttm, 1); f["EPS YoY %"] = _f(eps_yoy * 100, 1); f["Adjusted PEG"] = _f(peg, 2)
    if len(eps_s) >= 4:
        r = eps_s.iloc[-4:]
        tr = (r.iloc[-1] - r.iloc[0]) / (abs(r.iloc[0]) + 0.01)
        s2 = linear_scale(tr, -0.2, 0.1, 0.5)
        f["EPS trend %"] = _f(tr * 100, 1)
    sc, st = _weighted_score([(s1, .60, "PEG"), (s2, .40, "EPS trend")])
    f.update(st)
    results["Lynch"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Graham ----
    f = {}
    s1 = s2 = None
    if market_cap > 0:
        ncav_b = ca - tl
        ncav_ratio = ncav_b * UNIT_SCALE / market_cap
        s1 = linear_scale(ncav_ratio, 0, 0.5, 1.0)
        f["NCAV (B)"] = _f(ncav_b, 1); f["NCAV/MCap"] = _f(ncav_ratio, 2)
        if te > 0:
            pb = market_cap / (te * UNIT_SCALE)
            s2 = linear_scale(pb, 5.0, 1.5, 0.8, reverse=True)
            f["P/B"] = _f(pb, 2)
    sc, st = _weighted_score([(s1, .55, "NCAV/MCap"), (s2, .45, "P/B")])
    f.update(st)
    results["Graham"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Greenblatt ----
    f = {}
    roc = roic_val if roic_val != 0 else safe(latest, "ROA", 0)
    ey = _safe_div(eps, price) * 100 if price > 0 else 0
    s1 = linear_scale(roc, 5, 15, 30) if roc != 0 else None
    s2 = linear_scale(ey, 2, 7, 15) if ey > 0 else None
    if roc:
        f["ROC %"] = _f(roc, 1)
    if ey > 0:
        f["Earnings Yield %"] = _f(ey, 1)
    sc, st = _weighted_score([(s1, .50, "ROC"), (s2, .50, "EY")])
    f.update(st)
    results["Greenblatt"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Fisher ----
    f = {}
    s1 = s2 = None
    cagr = 0
    if len(rev_s) >= 8 and rev_s.iloc[0] > 0 and rev_s.iloc[-1] > 0:
        yrs = len(rev_s) / 4
        cagr = (rev_s.iloc[-1] / rev_s.iloc[0]) ** (1 / yrs) - 1
    else:
        rv = safe(latest, "TotalRevenue_TTM_YoY", None)
        if rv is not None:
            cagr = rv
    if cagr != 0:
        s1 = linear_scale(cagr, 0.02, 0.15, 0.30)
        f["Revenue CAGR %"] = _f(cagr * 100, 1)
    if len(rev_s) >= 4 and len(opex_s) >= 4:
        eff = _safe_div(rev_s.iloc[-1] - rev_s.iloc[0], abs(opex_s.sum()) + 0.01) * 100
        if eff != 0:
            s2 = linear_scale(eff, 0, 2.0, 5.0)
            f["Growth efficiency"] = _f(eff, 2)
    sc, st = _weighted_score([(s1, .55, "Sales CAGR"), (s2, .45, "R&D eff")])
    f.update(st)
    results["Fisher"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Templeton ----
    f = {}
    s1 = s2 = None
    ind_pe = bench.get("pe_ttm", 20)
    if pe_ttm > 0:
        rel = pe_ttm / ind_pe
        s1 = linear_scale(rel, 2.0, 1.0, 0.5, reverse=True)
        f["PE TTM"] = _f(pe_ttm, 1); f["Industry PE"] = _f(ind_pe, 1); f["PE relative"] = _f(rel, 2)
    if dp is not None and not dp.empty and len(dp) > 20 and price > 0:
        prices = pd.to_numeric(dp["close"], errors="coerce").dropna()
        pctile = float((prices < price).mean())
        s2 = linear_scale(pctile, 0.9, 0.5, 0.1, reverse=True)
        f["Price percentile %"] = _f(pctile * 100, 0)
    sc, st = _weighted_score([(s1, .50, "PE rel"), (s2, .50, "Price pctile")])
    f.update(st)
    results["Templeton"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Dalio ----
    f = {}
    s1 = s2 = None
    if debt_b <= 0:
        s1 = 10.0
        f["FCF/Debt"] = "debt-free"
    elif fcf != 0:
        ratio = fcf / debt_b
        s1 = linear_scale(ratio, 0.05, 0.3, 0.6)
        f["FCF/Debt"] = _f(ratio, 2)
    nd = debt_b - cash_b
    if ebitda_b > 0:
        nde = nd / ebitda_b
        s2 = linear_scale(nde, 5.0, 2.0, 0.5, reverse=True)
        f["NetDebt (B)"] = _f(nd, 1); f["NetDebt/EBITDA"] = _f(nde, 2)
    sc, st = _weighted_score([(s1, .55, "FCF/Debt"), (s2, .45, "ND/EBITDA")])
    f.update(st)
    results["Dalio"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    # ---- Soros ----
    f = {}
    s1 = s2 = None
    if dp is not None and not dp.empty and price > 0:
        prices = pd.to_numeric(dp["close"], errors="coerce").dropna()
        m12 = m1 = 0
        if len(prices) >= 252:
            m12 = price / prices.iloc[-252] - 1 if prices.iloc[-252] > 0 else 0
        elif len(prices) >= 60:
            m12 = price / prices.iloc[0] - 1 if prices.iloc[0] > 0 else 0
        if len(prices) >= 21:
            m1 = price / prices.iloc[-21] - 1 if prices.iloc[-21] > 0 else 0
        net = m12 - m1
        if net != 0 or m12 != 0:
            s1 = linear_scale(net, -0.10, 0.10, 0.40)
            f["12M momentum %"] = _f(m12 * 100, 1); f["1M momentum %"] = _f(m1 * 100, 1); f["Net momentum %"] = _f(net * 100, 1)
        dev, label = _ma_deviation(prices, price)
        if dev is not None:
            s2 = linear_scale(dev, -0.20, 0.05, 0.30)
            f[f"{label} deviation %"] = _f(dev * 100, 1)
    sc, st = _weighted_score([(s1, .55, "Momentum"), (s2, .45, "MA deviation")])
    f.update(st)
    results["Soros"] = {"score": _f(sc, 1), "factors": f, "available": any(x is not None for x in (s1, s2))}

    return results


def compute_qg_pro(ctx):
    ds, latest = ctx["df_single"], ctx["latest"]
    factors = {}
    if latest is None:
        return {"score": 50, "factors": {}, "available": False, "dim_scores": {}}

    if "NetIncome_YoY" in ds.columns and not pd.to_numeric(ds["NetIncome_YoY"], errors="coerce").isna().all():
        g_series = pd.to_numeric(ds["NetIncome_YoY"], errors="coerce").dropna()
        g_name = "NetIncome"
    elif "TotalRevenue_YoY" in ds.columns:
        g_series = pd.to_numeric(ds["TotalRevenue_YoY"], errors="coerce").dropna()
        g_name = "Revenue"
    else:
        g_series, g_name = pd.Series(dtype=float), "fundamental"

    g_t = float(g_series.iloc[-1]) if len(g_series) >= 1 else 0.0
    g_t1 = float(g_series.iloc[-2]) if len(g_series) >= 2 else 0.0

    g_adj_score = s_down_score = d_risk_score = cf_score = None
    if len(g_series) >= 1:
        g_adj = np.sign(g_t) * np.log1p(abs(g_t)) + 0.5 * (g_t - g_t1)
        g_adj_score = linear_scale(g_adj, 0.0, 0.15, 0.30)
        factors[f"{g_name} YoY (t)"] = _f(g_t * 100, 1)
        factors[f"{g_name} YoY (t-1)"] = _f(g_t1 * 100, 1)
        factors["G_adj"] = _f(g_adj, 3)
    if len(g_series) >= 4:
        downside = np.minimum(g_series.iloc[-8:], 0)
        s_down = float(np.var(downside))
        s_down_score = linear_scale(s_down, 0.04, 0.01, 0.0, reverse=True)
        factors["S_down"] = _f(s_down, 4)
    if len(g_series) >= 2:
        d_risk = 1.0 if (g_t < 0 and g_t1 < 0) else 0.0
        d_risk_score = 0.0 if d_risk == 1.0 else 10.0
        factors["D_risk"] = "high ⚠️" if d_risk == 1.0 else "normal ✅"
    ocf = safe(latest, "OperatingCashFlow_TTM", 0)
    npft = safe(latest, "NetIncome_TTM", 0)
    if ocf != 0 or npft != 0:  # require real data, not missing-as-zero
        cfq = ocf / (abs(npft) + 1e-4)
        if abs(npft) < 1e-2:
            cf_score = 10.0 if ocf > 0 else 0.0
        else:
            cf_score = linear_scale(cfq, 0.0, 0.8, 1.2)
        factors["OCF TTM"] = _f(ocf, 1)
        factors["NetIncome TTM"] = _f(npft, 1)
        factors["CF_quality"] = _f(cfq, 2)

    score, status = _weighted_score([
        (g_adj_score, 0.40, "growth"), (s_down_score, 0.25, "downside"),
        (d_risk_score, 0.20, "drawdown"), (cf_score, 0.15, "cf quality"),
    ])
    factors.update(status)
    return {
        "score": _f(score, 1), "factors": factors,
        "available": any(s is not None for s in (g_adj_score, s_down_score, d_risk_score, cf_score)),
        "dim_scores": {
            "G_adj": _f(g_adj_score * 10, 1) if g_adj_score is not None else 50,
            "S_down": _f(s_down_score * 10, 1) if s_down_score is not None else 50,
            "D_risk": _f(d_risk_score * 10, 1) if d_risk_score is not None else 50,
            "CF_quality": _f(cf_score * 10, 1) if cf_score is not None else 50,
        },
    }

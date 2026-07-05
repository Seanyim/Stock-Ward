# engine/valuation.py — Pure valuation models (Streamlit-free, corrected math)
#
# Fixes vs v2.5 Streamlit code:
#   * Consistent unit handling: all financials stored in Billions (meta.unit == 'Billion');
#     UNIT_SCALE converts to dollars explicitly. No "< 10000" heuristics.
#   * Debt proxy: schema has no TotalDebt column → use NonCurrentLiabilities (long-term debt proxy).
#   * FCF resolution: FreeCashFlow → (OCF + InvestingCashFlow approx, flagged) → never silently OCF.
#   * DCF: EV → equity bridge (EV − net debt) before per-share / market-cap comparison.
#   * ROIC: NOPAT / invested capital (equity + non-current liabilities), not NI/equity.
#   * Fisher PEG standardized: fair PE = G + 2×Rf  (single formula everywhere).
#   * Monte Carlo vectorized with numpy.

import numpy as np
import pandas as pd

from modules.core.calculator import process_financial_data
from modules.data.industry_data import get_industry_benchmarks

UNIT_SCALE = 1e9  # all financial_records values are stored in Billions

DEFAULT_TAX = 0.21


def safe(row, key, default=0.0):
    try:
        v = row.get(key, default)
    except AttributeError:
        return default
    if v is None:
        return default
    if isinstance(v, float) and np.isnan(v):
        return default
    return v


def _f(x, nd=6):
    """JSON-safe float"""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if np.isnan(x) or np.isinf(x):
        return None
    return round(x, nd)


# ============================================================
# Shared context
# ============================================================

def build_context(ticker, df_raw, meta, df_price):
    """Process raw records once; resolve all commonly-used quantities."""
    ctx = {
        "ticker": ticker, "meta": meta,
        "market_cap": meta.get("last_market_cap") or 0,
        "sector": meta.get("sector") or "Unknown",
        "df_raw": df_raw, "df_price": df_price,
        "df_single": pd.DataFrame(), "latest": None,
        "current_price": 0.0, "shares": 0.0,
        "eps_ttm": 0.0, "pe_ttm": 0.0,
    }
    if not df_raw.empty:
        _, df_single = process_financial_data(df_raw)
        ctx["df_single"] = df_single
        if not df_single.empty:
            ctx["latest"] = df_single.iloc[-1]
    if df_price is not None and not df_price.empty:
        ctx["current_price"] = float(df_price.iloc[-1].get("close") or 0)
    if ctx["market_cap"] > 0 and ctx["current_price"] > 0:
        ctx["shares"] = ctx["market_cap"] / ctx["current_price"]
    if ctx["latest"] is not None:
        ctx["eps_ttm"] = safe(ctx["latest"], "EPS_TTM", 0)
        if ctx["eps_ttm"] > 0 and ctx["current_price"] > 0:
            ctx["pe_ttm"] = ctx["current_price"] / ctx["eps_ttm"]
    return ctx


def resolve_fcf(ctx):
    """Resolve base FCF (in Billions) with explicit, honest fallbacks.

    Priority:
      1. FreeCashFlow_TTM (if quarterly data newer than last FY) or FY FreeCashFlow
      2. OCF_TTM + InvestingCashFlow_TTM (approximation, flagged)
    """
    latest, df_raw = ctx["latest"], ctx["df_raw"]
    if latest is None:
        return 0.0, "none"
    df_fy = df_raw[df_raw["period"] == "FY"].sort_values("year") if not df_raw.empty else pd.DataFrame()
    latest_fy_year = int(df_fy.iloc[-1]["year"]) if not df_fy.empty else 0
    last_year = int(latest.get("year", 0) or 0)

    val_ttm = safe(latest, "FreeCashFlow_TTM", 0)
    val_fy = safe(df_fy.iloc[-1], "FreeCashFlow", 0) if not df_fy.empty else 0

    if val_ttm != 0 and (last_year > latest_fy_year or val_fy == 0):
        return float(val_ttm), f"FCF TTM ({last_year} {latest.get('period','')})"
    if val_fy != 0:
        return float(val_fy), f"FCF FY{latest_fy_year}"
    # Approximation: FCF ≈ OCF + InvestingCF (capex dominates investing outflows)
    ocf = safe(latest, "OperatingCashFlow_TTM", 0)
    icf = safe(latest, "InvestingCashFlow_TTM", 0)
    if ocf != 0 and icf != 0:
        return float(ocf + icf), "OCF+InvestingCF TTM (approx)"
    if ocf != 0:
        return float(ocf), "OCF TTM (no CapEx data — overstated)"
    # Annual fallback: latest FY OperatingCashFlow (+ InvestingCashFlow) — works
    # when quarterly cash-flow data is sparse (e.g. SEC-only). Returns the real
    # value, which may be NEGATIVE for cash-burning companies (handled upstream).
    if not df_fy.empty:
        fy = df_fy.iloc[-1]
        ocf_fy = safe(fy, "OperatingCashFlow", 0)
        icf_fy = safe(fy, "InvestingCashFlow", 0)
        if ocf_fy != 0 and icf_fy != 0:
            return float(ocf_fy + icf_fy), f"OCF+InvestingCF FY{latest_fy_year} (approx)"
        if ocf_fy != 0:
            return float(ocf_fy), f"OCF FY{latest_fy_year} (no CapEx — overstated)"
    return 0.0, "none"


def resolve_debt_cash(ctx):
    """Debt proxy = NonCurrentLiabilities, cash = CashEndOfPeriod (both Billions)."""
    latest = ctx["latest"]
    if latest is None:
        return 0.0, 0.0
    debt = safe(latest, "NonCurrentLiabilities", 0)
    if debt == 0:
        tl = safe(latest, "TotalLiabilities", 0)
        cl = safe(latest, "CurrentLiabilities", 0)
        debt = max(tl - cl, 0)
    cash = safe(latest, "CashEndOfPeriod", 0)
    return float(debt), float(cash)


def resolve_ebitda(ctx):
    latest = ctx["latest"]
    if latest is None:
        return 0.0, "none"
    for key, lbl in [("EBITDA_TTM", "EBITDA TTM"), ("OperatingProfit_TTM", "OperatingProfit TTM (proxy)"),
                     ("OperatingProfit", "OperatingProfit (proxy)")]:
        v = safe(latest, key, 0)
        if v != 0:
            return float(v), lbl
    return 0.0, "none"


def resolve_tax_rate(ctx):
    latest = ctx["latest"]
    if latest is None:
        return DEFAULT_TAX
    etr = safe(latest, "EffectiveTaxRate", 0)
    if 0 < etr < 60:
        return etr / 100.0
    return DEFAULT_TAX


def resolve_growth_options(ctx):
    """Historical growth candidates for DCF stage-1 (log-linear trend, CAGR, revenue CAGR)."""
    df_raw, df_single = ctx["df_raw"], ctx["df_single"]
    options = []  # [{label, value_pct, detail}]
    df_fy = df_raw[df_raw["period"] == "FY"].sort_values("year") if not df_raw.empty else pd.DataFrame()

    # synthesize annual FCF from quarters when FY rows are missing
    target = df_fy
    if len(target) < 3 and not df_single.empty and "FreeCashFlow" in df_single.columns:
        rows = []
        for year, grp in df_single.groupby("year"):
            if len(grp) == 4:
                s = pd.to_numeric(grp["FreeCashFlow"], errors="coerce").sum()
                if s != 0 and not np.isnan(s):
                    rows.append({"year": year, "FreeCashFlow": s})
        if len(rows) >= 3:
            target = pd.DataFrame(rows).sort_values("year")

    if len(target) >= 3:
        trend = target.tail(5)
        vals, years = [], []
        for _, r in trend.iterrows():
            v = r.get("FreeCashFlow")
            v = 0.0 if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)
            vals.append(v)
            years.append(int(r["year"]))
        arr, yrs = np.array(vals, dtype=float), np.array(years, dtype=float)
        pos = arr > 0
        detail = None
        if pos.sum() >= 3:
            x = yrs[pos] - yrs[0]
            y = np.log(arr[pos])
            slope, intercept = np.polyfit(x, y, 1)
            pred = slope * x + intercept
            ss_res, ss_tot = np.sum((y - pred) ** 2), np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0
            g = (np.exp(slope) - 1) * 100
            if -100 < g < 300:
                fit = np.exp(slope * (yrs - yrs[0]) + intercept)
                detail = {"type": "log_linear", "slope": _f(slope), "intercept": _f(intercept),
                          "r2": _f(r2), "years": years, "values": [_f(v) for v in vals],
                          "fit": [_f(v) for v in fit]}
                options.append({"label": f"Trend (log-linear) {g:.1f}%", "value": _f(g, 2), "detail": detail})
        if detail is None:
            x = yrs - yrs[0]
            slope, intercept = np.polyfit(x, arr, 1)
            avg = np.mean(np.abs(arr))
            if avg != 0:
                g = slope / avg * 100
                pred = slope * x + intercept
                ss_res, ss_tot = np.sum((arr - pred) ** 2), np.sum((arr - arr.mean()) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0
                options.append({"label": f"Trend (linear) {g:.1f}%", "value": _f(g, 2),
                                "detail": {"type": "linear", "slope": _f(slope), "intercept": _f(intercept),
                                           "r2": _f(r2), "years": years, "values": [_f(v) for v in vals],
                                           "fit": [_f(v) for v in pred]}})
    # simple 5Y CAGR
    if len(df_fy) >= 5:
        sub = df_fy.tail(5)
        v0 = safe(sub.iloc[0], "FreeCashFlow", 0)
        v1 = safe(sub.iloc[-1], "FreeCashFlow", 0)
        if v0 > 0 and v1 > 0:
            cagr = ((v1 / v0) ** 0.25 - 1) * 100
            options.append({"label": f"FCF 5Y CAGR {cagr:.1f}%", "value": _f(cagr, 2),
                            "detail": {"type": "cagr", "start_year": int(sub.iloc[0]["year"]),
                                       "end_year": int(sub.iloc[-1]["year"]),
                                       "start_val": _f(v0), "end_val": _f(v1)}})
        rev = pd.to_numeric(sub["TotalRevenue"], errors="coerce").dropna().values if "TotalRevenue" in sub.columns else []
        if len(rev) >= 2 and rev[0] > 0 and rev[-1] > 0:
            g = ((rev[-1] / rev[0]) ** (1 / (len(rev) - 1)) - 1) * 100
            options.append({"label": f"Revenue 5Y CAGR {g:.1f}%", "value": _f(g, 2), "detail": {"type": "rev_cagr"}})
    if not options:
        options.append({"label": "Default 10%", "value": 10.0, "detail": {"type": "default"}})
    return options


def default_growth(ctx):
    latest = ctx["latest"]
    if latest is None:
        return 0.10
    for k in ("EPS_TTM_YoY", "NetIncomeToParent_TTM_YoY", "TotalRevenue_TTM_YoY"):
        v = safe(latest, k, None)
        if v is not None and v > 0:
            return min(float(v), 0.50)
    return 0.10


# ============================================================
# WACC  (fixed: real debt proxy + consistent units)
# ============================================================

def compute_wacc(ctx, rf, beta=1.2, erp=0.055, rd=None, tax=None):
    debt_b, _ = resolve_debt_cash(ctx)
    debt = debt_b * UNIT_SCALE
    mc = ctx["market_cap"]
    if mc <= 0:
        mc = 100 * UNIT_SCALE  # neutral fallback
    total = debt + mc
    we, wd = mc / total, debt / total
    cost_debt = rd if rd is not None else 0.05
    tax_rate = tax if tax is not None else resolve_tax_rate(ctx)
    cost_equity = rf + beta * erp
    wacc = we * cost_equity + wd * cost_debt * (1 - tax_rate)
    return {
        "wacc": _f(wacc), "rf": _f(rf), "beta": _f(beta), "erp": _f(erp),
        "cost_equity": _f(cost_equity), "cost_debt": _f(cost_debt), "tax_rate": _f(tax_rate),
        "market_cap": _f(mc), "debt": _f(debt), "we": _f(we), "wd": _f(wd),
        "debt_source": "NonCurrentLiabilities (long-term debt proxy)",
    }


# ============================================================
# DCF (forward + reverse + sensitivity) — with equity bridge
# ============================================================

def _dcf_ev(fcf0, g, wacc, perp, years=5):
    """Enterprise value for constant stage-1 growth. Units follow fcf0."""
    c, pv = fcf0, 0.0
    flows, pvs = [], []
    for i in range(1, years + 1):
        c *= (1 + g)
        d = c / ((1 + wacc) ** i)
        pv += d
        flows.append(c)
        pvs.append(d)
    tv = c * (1 + perp) / (wacc - perp)
    tpv = tv / ((1 + wacc) ** years)
    return pv + tpv, flows, pvs, tv, tpv


def _implied_growth(target_value, fcf0, wacc, perp, years=5, lo=-0.5, hi=1.5):
    """Bisection: growth s.t. EV == target_value."""
    if fcf0 <= 0 or target_value <= 0 or wacc <= perp:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        ev, *_ = _dcf_ev(fcf0, mid, wacc, perp)
        if abs(ev - target_value) < target_value * 1e-5:
            return mid
        if ev < target_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def dcf_forward(ctx, wacc, rf, growth_pct=None, perp_pct=None, base_fcf=None):
    fcf_auto, fcf_source = resolve_fcf(ctx)
    fcf = base_fcf if base_fcf is not None else fcf_auto
    if fcf == 0:
        return {"error": "no_fcf", "message": "No free-cash-flow data available for this company."}
    if fcf < 0:
        return {"error": "negative_fcf", "base_fcf": _f(fcf, 3), "fcf_source": fcf_source,
                "message": "Free cash flow is negative (the company is burning cash), "
                           "so a discounted-cash-flow value is not meaningful."}

    growth_opts = resolve_growth_options(ctx)
    g = (growth_pct if growth_pct is not None else growth_opts[0]["value"]) / 100.0
    rf_pct = rf * 100 if rf < 0.5 else rf
    perp = (perp_pct if perp_pct is not None else min(3.0, rf_pct * 0.8)) / 100.0
    if wacc <= perp:
        return {"error": "wacc_le_perp", "wacc": _f(wacc), "perp": _f(perp),
                "message": "WACC must exceed terminal growth"}

    ev_b, flows, pvs, tv, tpv = _dcf_ev(fcf, g, wacc, perp)
    stage1_pv = sum(pvs)

    debt_b, cash_b = resolve_debt_cash(ctx)
    net_debt_b = debt_b - cash_b
    equity_b = ev_b - net_debt_b  # equity bridge (fix)

    mc = ctx["market_cap"]
    shares = ctx["shares"]
    per_share = (equity_b * UNIT_SCALE / shares) if shares > 0 else None
    vs_mc = (equity_b * UNIT_SCALE / mc - 1) * 100 if mc > 0 else None

    # market-implied growth (reverse, vs current EQUITY value + net debt = EV target)
    implied = None
    if mc > 0 and fcf > 0:
        target_ev_b = mc / UNIT_SCALE + net_debt_b
        ig = _implied_growth(target_ev_b, fcf, wacc, perp)
        implied = _f(ig * 100, 2) if ig is not None else None

    # sensitivity: WACC × perp → EV (Billions)
    wacc_range = [wacc - 0.02, wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01, wacc + 0.02]
    g_range = [perp - 0.01, perp - 0.005, perp, perp + 0.005, perp + 0.01]
    g_range = [x for x in g_range if 0 <= x < min(wacc_range)] or [perp]
    matrix = []
    for gp in g_range:
        row = []
        for w in wacc_range:
            if w <= gp:
                row.append(None)
            else:
                ev_s, *_ = _dcf_ev(fcf, g, w, gp)
                row.append(_f(ev_s, 2))
        matrix.append(row)

    return {
        "base_fcf": _f(fcf, 4), "fcf_source": fcf_source,
        "growth_options": growth_opts, "growth_pct": _f(g * 100, 2), "perp_pct": _f(perp * 100, 2),
        "wacc": _f(wacc, 4), "rf_pct": _f(rf_pct, 2),
        "flows": [_f(x, 3) for x in flows], "pvs": [_f(x, 3) for x in pvs],
        "yoy": [_f(g * 100, 1)] * 5,
        "discount_factors": [_f(1 / ((1 + wacc) ** i), 4) for i in range(1, 6)],
        "terminal_fcf": _f(flows[-1] * (1 + perp), 3), "terminal_value": _f(tv, 2), "terminal_pv": _f(tpv, 2),
        "stage1_pv": _f(stage1_pv, 2), "enterprise_value": _f(ev_b, 2),
        "net_debt": _f(net_debt_b, 2), "equity_value": _f(equity_b, 2),
        "terminal_mix": _f(tpv / ev_b if ev_b else 0, 4),
        "per_share": _f(per_share, 2), "current_price": _f(ctx["current_price"], 2),
        "market_cap_b": _f(mc / UNIT_SCALE, 2), "vs_market_cap_pct": _f(vs_mc, 1),
        "implied_growth_pct": implied,
        "sensitivity": {"wacc": [_f(w * 100, 1) for w in wacc_range],
                        "perp": [_f(x * 100, 2) for x in g_range], "matrix": matrix},
    }


def dcf_reverse(ctx, wacc, perp_pct=2.5):
    fcf, fcf_source = resolve_fcf(ctx)
    mc = ctx["market_cap"]
    if fcf == 0:
        return {"error": "no_fcf", "message": "No free-cash-flow data available."}
    if fcf < 0:
        return {"error": "negative_fcf", "base_fcf": _f(fcf, 3),
                "message": "Free cash flow is negative — reverse DCF is not applicable."}
    if mc <= 0:
        return {"error": "no_market_cap"}
    perp = perp_pct / 100.0
    if wacc <= perp:
        return {"error": "wacc_le_perp"}
    debt_b, cash_b = resolve_debt_cash(ctx)
    target_ev_b = mc / UNIT_SCALE + (debt_b - cash_b)
    ig = _implied_growth(target_ev_b, fcf, wacc, perp)
    if ig is None:
        return {"error": "no_solution"}
    path = []
    c = fcf
    for i in range(1, 6):
        c *= (1 + ig)
        path.append({"year": f"Y{i}", "fcf": _f(c, 3), "df": _f(1 / ((1 + wacc) ** i), 4)})
    # sensitivity matrix: implied g over wacc×perp grid
    wacc_opts = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
    perp_opts = [perp - 0.01, perp - 0.005, perp, perp + 0.005, perp + 0.01]
    mtx = []
    for p in perp_opts:
        row = []
        for w in wacc_opts:
            if w <= p or p < 0:
                row.append(None)
            else:
                gg = _implied_growth(target_ev_b, fcf, w, p)
                row.append(_f(gg * 100, 2) if gg is not None else None)
        mtx.append(row)
    return {
        "implied_growth_pct": _f(ig * 100, 2), "base_fcf": _f(fcf, 4), "fcf_source": fcf_source,
        "market_cap_b": _f(mc / UNIT_SCALE, 2), "target_ev_b": _f(target_ev_b, 2),
        "net_debt_b": _f(debt_b - cash_b, 2), "wacc": _f(wacc, 4), "perp_pct": _f(perp_pct, 2),
        "path": path,
        "sensitivity": {"wacc": [_f(w * 100, 1) for w in wacc_opts],
                        "perp": [_f(p * 100, 2) for p in perp_opts], "matrix": mtx},
    }


# ============================================================
# PE / PEG
# ============================================================

def pe_analysis(ctx, rf):
    df_single, df_price = ctx["df_single"], ctx["df_price"]
    if df_single.empty:
        return {"error": "no_eps"}
    if df_price is None or df_price.empty:
        return {"error": "no_price", "message": "Sync market data first"}

    ds = df_single.copy()
    ds["report_date"] = pd.to_datetime(ds["report_date"])
    # EPS_TTM with a robust fallback: derive from NetIncome(-to-parent) TTM ÷ shares
    if "EPS_TTM" not in ds.columns or pd.to_numeric(ds["EPS_TTM"], errors="coerce").dropna().empty:
        shares = ctx.get("shares") or 0
        ni_col = "NetIncomeToParent_TTM" if "NetIncomeToParent_TTM" in ds.columns else (
                 "NetIncome_TTM" if "NetIncome_TTM" in ds.columns else None)
        if shares > 0 and ni_col:
            ds["EPS_TTM"] = pd.to_numeric(ds[ni_col], errors="coerce") * UNIT_SCALE / shares
        else:
            return {"error": "no_eps"}
    ds["EPS_TTM"] = pd.to_numeric(ds["EPS_TTM"], errors="coerce")
    ds = ds.dropna(subset=["EPS_TTM"])
    ds = ds[ds["EPS_TTM"] != 0]
    if ds.empty:
        return {"error": "no_eps"}

    dp = df_price.copy()
    dp["date"] = pd.to_datetime(dp["date"])
    ds, dp = ds.sort_values("report_date"), dp.sort_values("date")

    # DAILY PE history: carry each period's EPS_TTM forward onto every trading
    # day, so percentile bands reflect the full historical PE distribution
    # (not just ~20-40 quarterly snapshots).
    daily = pd.merge_asof(dp[["date", "close"]], ds[["report_date", "EPS_TTM"]],
                          left_on="date", right_on="report_date", direction="backward").dropna(subset=["EPS_TTM"])
    daily["PE_TTM"] = daily["close"] / daily["EPS_TTM"]
    valid = daily[(daily["PE_TTM"] > 0) & (daily["PE_TTM"] < 300)]
    if valid.empty:
        return {"error": "no_valid_pe"}

    q = lambda p: float(valid["PE_TTM"].quantile(p))
    percentiles = {"p10": q(.1), "p20": q(.2), "p25": q(.25), "p50": q(.5), "p75": q(.75), "p80": q(.8), "p90": q(.9)}
    eps_ttm = float(ds.iloc[-1]["EPS_TTM"])
    price = ctx["current_price"]
    pe_now = price / eps_ttm if eps_ttm > 0 else 0
    pct_rank = float((valid["PE_TTM"].values <= pe_now).mean() * 100)

    # static PE from last FY EPS
    eps_static, static_src = None, None
    fy = ctx["df_raw"][ctx["df_raw"]["period"] == "FY"]
    if not fy.empty:
        r = fy.sort_values("year").iloc[-1]
        v = r.get("EPS")
        if v and not (isinstance(v, float) and np.isnan(v)):
            eps_static, static_src = float(v), f"FY{int(r['year'])}"
    if eps_static is None:
        for year in sorted(ctx["df_raw"]["year"].unique(), reverse=True):
            yd = ctx["df_raw"][(ctx["df_raw"]["year"] == year) & (ctx["df_raw"]["period"].isin(["Q1", "Q2", "Q3", "Q4"]))]
            if len(yd) == 4 and "EPS" in yd.columns:
                s = pd.to_numeric(yd["EPS"], errors="coerce").sum()
                if s > 0:
                    eps_static, static_src = float(s), f"FY{int(year)} (ΣQ1-Q4)"
                    break
    pe_static = price / eps_static if eps_static and eps_static > 0 else None

    # growth for PEG
    growth_pct, growth_src = None, None
    latest = ctx["latest"]
    for k, lbl in [("NetIncomeToParent_TTM_YoY", "NetIncome-to-parent TTM YoY"), ("EPS_TTM_YoY", "EPS TTM YoY")]:
        v = safe(latest, k, None)
        if v is not None and v > 0:
            growth_pct, growth_src = float(v) * 100, lbl
            break
    g = growth_pct if growth_pct else 15.0
    rf_pct = rf * 100 if rf < 0.5 else rf
    peg = pe_now / g if g > 0 else None
    fisher_fair_pe = g + 2 * rf_pct                       # standardized Fisher
    fisher_peg = pe_now / fisher_fair_pe if fisher_fair_pe > 0 else None
    implied_growth = pe_now - 2 * rf_pct                  # reverse Fisher

    fair_low, fair_mid, fair_high = percentiles["p20"] * eps_ttm, percentiles["p50"] * eps_ttm, percentiles["p80"] * eps_ttm
    peg1_fair = g * eps_ttm if g > 0 else None
    fisher_fair = fisher_fair_pe * eps_ttm

    # PE band chart series. Two equivalent views from the SAME daily PE history:
    #   • "pe" view  : the actual daily P/E line + horizontal P20/P50/P80 PE lines
    #   • "price" view: price line + bands = EPS_TTM × those percentiles
    band = valid.copy()
    band["b80"] = band["EPS_TTM"] * percentiles["p80"]
    band["b50"] = band["EPS_TTM"] * percentiles["p50"]
    band["b20"] = band["EPS_TTM"] * percentiles["p20"]
    step = max(1, len(band) // 700)
    bs = band.iloc[::step]
    series = {
        "dates": bs["date"].dt.strftime("%Y-%m-%d").tolist(),
        "close": [_f(x, 2) for x in bs["close"]],
        "b80": [_f(x, 2) for x in bs["b80"]],
        "b50": [_f(x, 2) for x in bs["b50"]],
        "b20": [_f(x, 2) for x in bs["b20"]],
        # P/E view: the daily P/E itself plus flat percentile reference lines
        "pe": [_f(x, 2) for x in bs["PE_TTM"]],
        "pe_p80": _f(percentiles["p80"], 2),
        "pe_p50": _f(percentiles["p50"], 2),
        "pe_p20": _f(percentiles["p20"], 2),
        "pe_now": _f(pe_now, 2),
    }
    report_dates = ds["report_date"].dt.strftime("%Y-%m-%d").tolist()

    # sensitivity: growth × target PEG → fair price
    g_sens = [max(5, g - 10), max(5, g - 5), g, g + 5, g + 10]
    peg_sens = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    price_matrix = [[_f(p * gg * eps_ttm, 2) for p in peg_sens] for gg in g_sens]

    return {
        "current_price": _f(price, 2), "eps_ttm": _f(eps_ttm, 3), "pe_ttm": _f(pe_now, 2),
        "pe_static": _f(pe_static, 2), "pe_static_source": static_src,
        "pe_forward": _f(price / (eps_ttm * (1 + g / 100)), 2) if eps_ttm > 0 else None,
        "percentiles": {k: _f(v, 2) for k, v in percentiles.items()},
        "percentile_rank": _f(pct_rank, 1),
        "growth_pct": _f(g, 2), "growth_source": growth_src or "default 15%",
        "rf_pct": _f(rf_pct, 2),
        "peg": _f(peg, 2), "fisher_fair_pe": _f(fisher_fair_pe, 1), "fisher_peg": _f(fisher_peg, 2),
        "implied_growth_pct": _f(implied_growth, 1),
        "fair_prices": {"pe20": _f(fair_low, 2), "pe50": _f(fair_mid, 2), "pe80": _f(fair_high, 2),
                        "peg1": _f(peg1_fair, 2), "fisher": _f(fisher_fair, 2)},
        "band": series, "report_dates": report_dates,
        "sensitivity": {"growth": [_f(x, 1) for x in g_sens], "peg": peg_sens, "price_matrix": price_matrix},
    }


# ============================================================
# EV / EBITDA
# ============================================================

def ev_ebitda(ctx):
    mc = ctx["market_cap"]
    ebitda_b, src = resolve_ebitda(ctx)
    if mc <= 0 or ebitda_b <= 0:
        return {"error": "missing_data"}
    debt_b, cash_b = resolve_debt_cash(ctx)
    ev = mc + (debt_b - cash_b) * UNIT_SCALE
    multiple = ev / (ebitda_b * UNIT_SCALE)
    bench = get_industry_benchmarks(ctx["sector"])
    ind = bench.get("ev_ebitda", 15.0)
    implied_mc = ind * ebitda_b * UNIT_SCALE - debt_b * UNIT_SCALE + cash_b * UNIT_SCALE

    # historical multiple trend (approx: current MC, historical EBITDA)
    hist = []
    for _, row in ctx["df_single"].iterrows():
        e = safe(row, "EBITDA_TTM", 0) or safe(row, "OperatingProfit_TTM", 0)
        if e > 0:
            d = safe(row, "NonCurrentLiabilities", 0)
            cch = safe(row, "CashEndOfPeriod", 0)
            hist.append({"period": f"{row.get('year','')}{row.get('period','')}",
                         "multiple": _f((mc + (d - cch) * UNIT_SCALE) / (e * UNIT_SCALE), 2)})

    mult_range = sorted({round(multiple * f, 1) for f in (0.7, 0.85, 1.0, 1.15, 1.3)} | {round(ind, 1)})
    chg = [-20, -10, 0, 10, 20]
    matrix = [[_f((m * ebitda_b * (1 + c / 100) - debt_b + cash_b), 1) for m in mult_range] for c in chg]

    return {
        "ev_b": _f(ev / UNIT_SCALE, 2), "ebitda_b": _f(ebitda_b, 3), "ebitda_source": src,
        "multiple": _f(multiple, 2), "industry_multiple": _f(ind, 1), "sector": ctx["sector"],
        "premium_pct": _f((multiple / ind - 1) * 100, 1),
        "implied_mc_b": _f(implied_mc / UNIT_SCALE, 2),
        "implied_vs_current_pct": _f((implied_mc / mc - 1) * 100, 1),
        "debt_b": _f(debt_b, 2), "cash_b": _f(cash_b, 2), "history": hist,
        "sensitivity": {"multiples": [_f(m, 1) for m in mult_range], "ebitda_chg": chg, "matrix": matrix},
    }


# ============================================================
# Growth perspective
# ============================================================

def growth_analysis(ctx):
    ds = ctx["df_single"]
    if len(ds) < 4:
        return {"error": "insufficient_data"}
    metric_map = [
        ("scale", "TotalRevenue_TTM", "Revenue"), ("scale", "GrossProfit_TTM", "GrossProfit"),
        ("profit", "NetIncome_TTM", "NetIncome"), ("profit", "EPS_TTM", "EPS"),
        ("cash", "OperatingCashFlow_TTM", "OCF"), ("cash", "FreeCashFlow_TTM", "FCF"),
        ("balance", "TotalAssets", "TotalAssets"), ("balance", "TotalEquity", "TotalEquity"),
        ("balance", "NonCurrentLiabilities", "LT-Liabilities"),
    ]
    rows = []
    for cat, col, name in metric_map:
        if col not in ds.columns:
            continue
        s = pd.to_numeric(ds[col], errors="coerce").dropna()
        if len(s) < 4:
            continue
        vnew = float(s.iloc[-1])
        cagr = None
        if len(s) >= 5:
            vold = float(s.iloc[-5])
            if vold != 0 and vnew != 0:
                mag = (abs(vnew) / abs(vold)) ** 0.25 - 1
                if vnew > 0 and vold > 0:
                    cagr = mag
                elif vnew < 0 < vold:
                    cagr = -abs(mag)
                elif vold < 0 < vnew:
                    cagr = abs(mag)
                else:
                    cagr = abs(mag) if vnew > vold else -abs(mag)
        qoq = (vnew / float(s.iloc[-2]) - 1) if len(s) >= 2 and s.iloc[-2] != 0 else None
        rows.append({"category": cat, "metric": name, "latest": _f(vnew, 3),
                     "qoq_pct": _f(qoq * 100 if qoq is not None else None, 1),
                     "cagr_pct": _f(cagr * 100 if cagr is not None else None, 1)})
    # time series for charting
    ts = {"dates": ds["report_date"].astype(str).tolist()}
    for col, key in [("TotalRevenue_TTM", "revenue"), ("NetIncome_TTM", "netincome"), ("FreeCashFlow_TTM", "fcf")]:
        if col in ds.columns:
            ts[key] = [_f(x, 3) for x in pd.to_numeric(ds[col], errors="coerce")]
    return {"rows": rows, "series": ts}


# ============================================================
# Monte Carlo  (vectorized)
# ============================================================

def monte_carlo(ctx, wacc, metric="FreeCashFlow_TTM_YoY", growth_mean=None, growth_std=None,
                n_sims=2000, perp=0.025, seed=42):
    fcf, fcf_source = resolve_fcf(ctx)
    if fcf == 0:
        return {"error": "no_fcf", "message": "No free-cash-flow data available."}
    if fcf < 0:
        return {"error": "negative_fcf", "base_fcf": _f(fcf, 3),
                "message": "Free cash flow is negative — a cash-flow simulation is not meaningful."}
    ds = ctx["df_single"]
    hist_mean, hist_std, src = 0.10, 0.05, "default"
    if metric in ds.columns:
        s = pd.to_numeric(ds[metric], errors="coerce").dropna()
        s = s[(s > -0.5) & (s < 1.0)]
        if len(s) >= 4:
            hist_mean, hist_std, src = float(s.mean()), float(s.std()), f"{len(s)} quarters of {metric}"
    gm = growth_mean if growth_mean is not None else hist_mean
    gs = growth_std if growth_std is not None else hist_std
    if wacc <= perp:
        return {"error": "wacc_le_perp"}

    rng = np.random.default_rng(seed)
    g = np.clip(rng.normal(gm, gs, int(n_sims)), -0.3, 0.6)            # (n,)
    years = np.arange(1, 6)
    fcf_paths = fcf * (1 + g[:, None]) ** years[None, :]               # (n,5)
    disc = (1 + wacc) ** years
    pv = (fcf_paths / disc[None, :]).sum(axis=1)
    last = fcf_paths[:, -1]
    tv = last * (1 + perp) / (wacc - perp) / ((1 + wacc) ** 5)
    ev_b = pv + tv                                                     # Billions

    debt_b, cash_b = resolve_debt_cash(ctx)
    eq_b = ev_b - (debt_b - cash_b)
    mc = ctx["market_cap"]
    shares = ctx.get("shares") or 0
    price = ctx.get("current_price") or 0
    pcts = {p: _f(float(np.percentile(eq_b, p)), 2) for p in (10, 25, 50, 75, 90)}
    hist_counts, hist_edges = np.histogram(eq_b, bins=50)
    upside_p50 = (np.percentile(eq_b, 50) * UNIT_SCALE / mc - 1) * 100 if mc > 0 else None

    # --- per-share fair PRICE distribution + probability analysis ---
    price_block = None
    if shares > 0:
        fair_px = eq_b * UNIT_SCALE / shares                      # simulated fair price/share
        ppcts = {p: _f(float(np.percentile(fair_px, p)), 2) for p in (5, 10, 25, 50, 75, 90, 95)}
        ph_counts, ph_edges = np.histogram(fair_px, bins=50)
        prob_above = float((fair_px > price).mean() * 100) if price > 0 else None
        prob_up20 = float((fair_px > price * 1.2).mean() * 100) if price > 0 else None
        prob_dn20 = float((fair_px < price * 0.8).mean() * 100) if price > 0 else None
        price_block = {
            "current_price": _f(price, 2),
            "percentiles": ppcts,                                 # fair-price targets
            "median": ppcts[50], "p10": ppcts[10], "p90": ppcts[90],
            "prob_above_price_pct": _f(prob_above, 1),            # P(fair value > today's price)
            "prob_upside_20_pct": _f(prob_up20, 1),
            "prob_downside_20_pct": _f(prob_dn20, 1),
            "expected_return_pct": _f((float(np.median(fair_px)) / price - 1) * 100, 1) if price > 0 else None,
            "histogram": {"counts": ph_counts.tolist(), "edges": [_f(e, 2) for e in ph_edges]},
        }
    return {
        "fcf": _f(fcf, 3), "fcf_source": fcf_source,
        "growth_mean_pct": _f(gm * 100, 2), "growth_std_pct": _f(gs * 100, 2), "param_source": src,
        "n_sims": int(n_sims), "percentiles": pcts, "mean": _f(float(eq_b.mean()), 2),
        "market_cap_b": _f(mc / UNIT_SCALE, 2) if mc > 0 else None,
        "upside_p50_pct": _f(upside_p50, 1),
        "histogram": {"counts": hist_counts.tolist(), "edges": [_f(e, 2) for e in hist_edges]},
        "price": price_block,
        "note": "equity value ($B); price block = simulated fair price per share",
    }


# ============================================================
# Profitability (ROE / ROA / ROIC fixed)
# ============================================================

def profitability(ctx, wacc):
    ds = ctx["df_single"]
    latest = ctx["latest"]
    if latest is None or len(ds) < 2:
        return {"error": "insufficient_data"}
    ni = safe(latest, "NetIncome_TTM", 0)
    ta = safe(latest, "TotalAssets", 0)
    te = safe(latest, "TotalEquity", 0)
    debt_b, _ = resolve_debt_cash(ctx)
    rev = safe(latest, "TotalRevenue_TTM", 0)
    op = safe(latest, "OperatingProfit_TTM", 0)
    tax = resolve_tax_rate(ctx)

    roa = ni / ta * 100 if ta > 0 else None
    roe = ni / te * 100 if te > 0 else None
    invested = te + debt_b
    nopat = op * (1 - tax) if op != 0 else ni     # NOPAT preferred (fix)
    roic = nopat / invested * 100 if invested > 0 else None

    npm = ni / rev * 100 if rev > 0 else None
    at = rev / ta if ta > 0 else None
    em = ta / te if te > 0 else None
    de = debt_b / te if te > 0 else None

    bench = get_industry_benchmarks(ctx["sector"])

    # history
    hist = {"dates": ds["report_date"].astype(str).tolist(), "roe": [], "roic": []}
    for _, row in ds.iterrows():
        n = safe(row, "NetIncome_TTM", None)
        e = safe(row, "TotalEquity", None)
        d = safe(row, "NonCurrentLiabilities", 0)
        o = safe(row, "OperatingProfit_TTM", None)
        hist["roe"].append(_f(n / e * 100, 2) if n and e and e > 0 else None)
        cap = (e or 0) + d
        nop = o * (1 - tax) if o else n
        hist["roic"].append(_f(nop / cap * 100, 2) if nop and cap > 0 else None)

    spread = (roic - wacc * 100) if roic is not None else None
    return {
        "roe": _f(roe, 2), "roa": _f(roa, 2), "roic": _f(roic, 2),
        "roic_method": "NOPAT / (Equity + NonCurrentLiabilities)",
        "industry": {"roe": bench.get("roe"), "roa": bench.get("roa"), "roic": bench.get("roic")},
        "dupont": {"net_margin": _f(npm, 2), "asset_turnover": _f(at, 3), "equity_multiplier": _f(em, 2)},
        "de_ratio": _f(de, 2), "wacc_pct": _f(wacc * 100, 2), "spread_pct": _f(spread, 2),
        "tax_rate": _f(tax, 4), "history": hist, "sector": ctx["sector"],
    }

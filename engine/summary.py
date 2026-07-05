# engine/summary.py — forward valuations, dashboard integration, summary signals
import numpy as np
import pandas as pd

from modules.data.industry_data import get_industry_benchmarks
from engine.valuation import (
    safe, _f, UNIT_SCALE, resolve_fcf, resolve_debt_cash, resolve_ebitda,
    _dcf_ev, _implied_growth, default_growth,
)


def forward_valuations(ctx, wacc, rf, growth_pct=None, perp_pct=2.5):
    """All models → fair price per share. Returns dict name → {fair_price, method, model}."""
    res = {}
    latest = ctx["latest"]
    if latest is None:
        return res
    eps = ctx["eps_ttm"]
    price = ctx["current_price"]
    mc = ctx["market_cap"]
    shares = ctx["shares"]
    g = (growth_pct / 100.0) if growth_pct is not None else default_growth(ctx)
    g_pct = g * 100
    rf_pct = rf * 100 if rf < 0.5 else rf

    # PE band
    ds, dp = ctx["df_single"], ctx["df_price"]
    if eps > 0 and price > 0 and dp is not None and not dp.empty and "report_date" in ds.columns:
        d1 = ds.copy(); d1["report_date"] = pd.to_datetime(d1["report_date"])
        d2 = dp.copy(); d2["date"] = pd.to_datetime(d2["date"])
        m = pd.merge_asof(d1.sort_values("report_date"), d2.sort_values("date"),
                          left_on="report_date", right_on="date", direction="backward")
        m["PE_TTM"] = m["close"] / m["EPS_TTM"]
        v = m[(m["PE_TTM"] > 0) & (m["PE_TTM"] < 200)]
        if not v.empty:
            for q, name in [(.2, "PE Band 20%"), (.5, "PE Band 50%"), (.8, "PE Band 80%")]:
                pe_q = float(v["PE_TTM"].quantile(q))
                res[name] = {"fair_price": _f(pe_q * eps, 2), "method": f"PE {pe_q:.1f}x × EPS {eps:.2f}", "model": "PE"}

    # PEG=1 and Fisher
    if eps > 0 and g_pct > 0:
        res["PEG=1"] = {"fair_price": _f(g_pct * eps, 2), "method": f"PE={g_pct:.0f}x × EPS {eps:.2f}", "model": "PEG"}
        fpe = g_pct + 2 * rf_pct
        res["Fisher"] = {"fair_price": _f(fpe * eps, 2), "method": f"PE=(G+2Rf)={fpe:.1f}x × EPS {eps:.2f}", "model": "PEG"}

    # DCF (equity bridge)
    fcf, src = resolve_fcf(ctx)
    perp = perp_pct / 100.0
    if fcf != 0 and wacc > perp and shares > 0:
        ev_b, *_ = _dcf_ev(fcf, min(g, 0.5), wacc, perp)
        debt_b, cash_b = resolve_debt_cash(ctx)
        eq_b = ev_b - (debt_b - cash_b)
        res["DCF"] = {"fair_price": _f(eq_b * UNIT_SCALE / shares, 2),
                      "method": f"FCF={fcf:.1f}B ({src}), g={g_pct:.1f}%, WACC={wacc:.1%}", "model": "DCF"}

    # EV/EBITDA industry
    ebitda_b, esrc = resolve_ebitda(ctx)
    if ebitda_b > 0 and shares > 0:
        bench = get_industry_benchmarks(ctx["sector"])
        ind = bench.get("ev_ebitda", 15.0)
        debt_b, cash_b = resolve_debt_cash(ctx)
        implied_mc_b = ind * ebitda_b - debt_b + cash_b
        res["EV/EBITDA"] = {"fair_price": _f(implied_mc_b * UNIT_SCALE / shares, 2),
                            "method": f"industry {ind:.1f}x × EBITDA {ebitda_b:.1f}B ({esrc})", "model": "EV/EBITDA"}
    return res


def reverse_valuations(ctx, wacc, rf, perp_pct=2.5):
    res = {}
    pe_ttm = ctx["pe_ttm"]
    rf_pct = rf * 100 if rf < 0.5 else rf
    if pe_ttm > 0:
        res["Fisher implied growth"] = {"value": _f(pe_ttm - 2 * rf_pct, 1), "unit": "%",
                                        "method": f"G = PE({pe_ttm:.1f}) − 2×Rf({rf_pct:.1f}%)", "model": "PE"}
        res["PEG=1 implied growth"] = {"value": _f(pe_ttm, 1), "unit": "%",
                                       "method": f"G = PE({pe_ttm:.1f})", "model": "PE"}
    fcf, _src = resolve_fcf(ctx)
    mc = ctx["market_cap"]
    perp = perp_pct / 100.0
    if fcf > 0 and mc > 0 and wacc > perp:
        debt_b, cash_b = resolve_debt_cash(ctx)
        target_ev_b = mc / UNIT_SCALE + (debt_b - cash_b)
        ig = _implied_growth(target_ev_b, fcf, wacc, perp)
        if ig is not None:
            res["DCF implied growth"] = {"value": _f(ig * 100, 1), "unit": "%",
                                         "method": f"FCF={fcf:.1f}B supports EV {target_ev_b:.0f}B", "model": "DCF"}
    ebitda_b, _ = resolve_ebitda(ctx)
    if ebitda_b > 0 and mc > 0:
        debt_b, cash_b = resolve_debt_cash(ctx)
        actual = (mc / UNIT_SCALE + debt_b - cash_b) / ebitda_b
        res["EV/EBITDA actual"] = {"value": _f(actual, 1), "unit": "x",
                                   "method": f"EV / EBITDA({ebitda_b:.1f}B)", "model": "EV/EBITDA"}
    return res


def dashboard(ctx, wacc, rf, growth_pct=None, perp_pct=2.5, weights=None):
    fwd = forward_valuations(ctx, wacc, rf, growth_pct, perp_pct)
    rev = reverse_valuations(ctx, wacc, rf, perp_pct)
    price = ctx["current_price"]
    latest = ctx["latest"]
    unified_g = growth_pct if growth_pct is not None else default_growth(ctx) * 100

    w = weights or {"PE": 0.25, "PEG": 0.20, "DCF": 0.35, "EV/EBITDA": 0.20}
    tw = sum(w.values()) or 1
    w = {k: v / tw for k, v in w.items()}

    contrib = {}
    for name, info in fwd.items():
        contrib.setdefault(info["model"], []).append(info["fair_price"])
    wsum = used = 0.0
    for model, prices in contrib.items():
        mw = w.get(model, 0)
        if mw > 0:
            wsum += float(np.median(prices)) * mw
            used += mw
    intrinsic = wsum / used if used > 0 else 0
    margin = (intrinsic / price - 1) * 100 if price > 0 and intrinsic > 0 else None

    all_fairs = [i["fair_price"] for i in fwd.values()]
    disp = (np.std(all_fairs) / np.mean(all_fairs) * 100) if all_fairs and np.mean(all_fairs) != 0 else None
    confidence = "high" if disp is not None and disp < 15 else "medium" if disp is not None and disp < 30 else "low"

    g_points = {k: v["value"] for k, v in rev.items() if v["unit"] == "%"}
    g_points["unified"] = _f(unified_g, 1)
    gv = [v for v in g_points.values() if v is not None]
    cv = float(np.std(gv) / abs(np.mean(gv)) * 100) if gv and np.mean(gv) != 0 else None

    ni = safe(latest, "NetIncome_TTM", 0) if latest is not None else 0
    ocf = safe(latest, "OperatingCashFlow_TTM", 0) if latest is not None else 0
    quality = min(min(ocf / ni, 2.0) * 50, 100) if ni > 0 and ocf > 0 else 50

    bullish = sum(1 for i in fwd.values() if i["fair_price"] and price > 0 and i["fair_price"] > price * 1.1)
    bearish = sum(1 for i in fwd.values() if i["fair_price"] and price > 0 and i["fair_price"] < price * 0.9)

    return {
        "forward": fwd, "reverse": rev,
        "unified_growth_pct": _f(unified_g, 1), "perp_pct": _f(perp_pct, 2),
        "wacc": _f(wacc, 4), "current_price": _f(price, 2),
        "weights": {k: _f(v, 3) for k, v in w.items()},
        "intrinsic_value": _f(intrinsic, 2), "margin_pct": _f(margin, 1),
        "dispersion_pct": _f(disp, 1), "confidence": confidence,
        "growth_cv_pct": _f(cv, 1), "growth_points": g_points,
        "quality_score": _f(quality, 0),
        "bullish": bullish, "bearish": bearish, "total_models": len(fwd),
    }


def summary(ctx, wacc, rf, master_scores, qg):
    fwd = forward_valuations(ctx, wacc, rf)
    price = ctx["current_price"]
    fairs = [i["fair_price"] for i in fwd.values() if i["fair_price"]]
    intrinsic = float(np.median(fairs)) if fairs else 0
    margin = (intrinsic / price - 1) * 100 if price > 0 and intrinsic > 0 else None

    master_avg = None
    if master_scores:
        avail = [master_scores[k]["score"] for k in master_scores if master_scores[k]["available"]]
        if avail:
            master_avg = float(np.mean(avail))

    latest = ctx["latest"]
    ni = safe(latest, "NetIncome_TTM", 0) if latest is not None else 0
    ocf = safe(latest, "OperatingCashFlow_TTM", 0) if latest is not None else 0
    quality = min(min(ocf / ni, 2.0) * 50, 100) if ni > 0 and ocf > 0 else 50

    qg_score = qg.get("score") if qg and qg.get("available") else None
    comp = float(np.mean([
        50 + (margin or 0), quality,
        master_avg if master_avg is not None else 50,
        qg_score if qg_score is not None else 50,
    ]))

    # DCF sensitivity per-share matrix
    fcf, _src = resolve_fcf(ctx)
    shares = ctx["shares"]
    sens = None
    if fcf > 0 and shares > 0:
        debt_b, cash_b = resolve_debt_cash(ctx)
        nd = debt_b - cash_b
        wr = [max(0.04, wacc - 0.02), max(0.05, wacc - 0.01), wacc, wacc + 0.01, wacc + 0.02]
        gr = [0.03, 0.06, 0.10, 0.15, 0.20, 0.25]
        matrix = []
        for g in gr:
            row = []
            for w_ in wr:
                if w_ <= 0.025:
                    row.append(None); continue
                ev_b, *_ = _dcf_ev(fcf, g, w_, 0.025)
                row.append(_f((ev_b - nd) * UNIT_SCALE / shares, 2))
            matrix.append(row)
        sens = {"wacc": [_f(w_ * 100, 1) for w_ in wr], "growth": [_f(g * 100, 0) for g in gr], "matrix": matrix}

    # PE sensitivity
    eps, pe_ttm = ctx["eps_ttm"], ctx["pe_ttm"]
    pe_sens = None
    if eps > 0 and pe_ttm > 0:
        pr = [max(5, pe_ttm * 0.5), pe_ttm * 0.75, pe_ttm, pe_ttm * 1.25, pe_ttm * 1.5]
        ec = [-20, -10, 0, 10, 20, 30]
        pe_sens = {"pe": [_f(p, 1) for p in pr], "eps_chg": ec,
                   "matrix": [[_f(p * eps * (1 + c / 100), 2) for p in pr] for c in ec]}

    bullish = sum(1 for i in fwd.values() if i["fair_price"] and price > 0 and i["fair_price"] > price * 1.1)
    return {
        "forward": fwd, "intrinsic_value": _f(intrinsic, 2), "margin_pct": _f(margin, 1),
        "current_price": _f(price, 2), "pe_ttm": _f(pe_ttm, 2),
        "master_avg": _f(master_avg, 1), "quality_score": _f(quality, 0),
        "qg_score": _f(qg_score, 1) if qg_score is not None else None,
        "composite": _f(comp, 1),
        "bullish": bullish, "total_models": len(fwd),
        "dcf_sensitivity": sens, "pe_sensitivity": pe_sens,
    }

# server.py — Stock-Ward v3 FastAPI backend
# Local deploy: python run.py  → opens http://127.0.0.1:8377 in the browser
import os
import math
import time
import asyncio
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from engine import db
from engine import fetcher
from engine import ingest as ingest_engine
from engine import news as news_engine
from engine import grade as grade_engine
from engine import health as health_engine
from engine import technical as technical_engine
from engine.providers import ALL_PROVIDERS
from engine.valuation import (
    build_context, compute_wacc, dcf_forward, dcf_reverse, pe_analysis,
    ev_ebitda, growth_analysis, monte_carlo, profitability, resolve_growth_options, _f,
)
from engine.masters import compute_master_scores, compute_qg_pro, MASTER_DEFINITIONS
from engine.summary import dashboard as dash_calc, summary as summary_calc
from modules.core.calculator import process_financial_data, get_view_data
from modules.core.config import FINANCIAL_METRICS, CATEGORY_ORDER

ROOT = os.path.dirname(os.path.abspath(__file__))
# When frozen by PyInstaller, bundled read-only assets live under _MEIPASS.
_ASSET_ROOT = getattr(__import__("sys"), "_MEIPASS", ROOT)
WEB_DIR = os.path.join(_ASSET_ROOT, "web")

app = FastAPI(title="Stock-Ward v3", docs_url="/api/docs")

db.init_db()

# ----------------------------------------------------------------------------
# Lightweight per-ticker context cache, invalidated by db.data_version()
# ----------------------------------------------------------------------------
_ctx_cache: Dict[str, Any] = {}
_quote_cache: Dict[str, Any] = {}


def get_live_quote_cached(ticker: str, max_age: int = 120):
    """Newest quote with a tiny TTL so valuation cards do not run on stale DB prices."""
    key = ticker.upper()
    now = time.time()
    hit = _quote_cache.get(key)
    if hit and now - hit["ts"] < max_age:
        return hit["quote"]
    q = technical_engine.live_quote(key)
    _quote_cache[key] = {"ts": now, "quote": q}
    return q


def overlay_live_price(ctx, quote):
    if not isinstance(quote, dict) or quote.get("price") is None:
        return ctx
    live_price = float(quote["price"])
    stored_price = float(ctx.get("current_price") or 0)
    market_cap = float(ctx.get("market_cap") or 0)
    if market_cap > 0 and stored_price > 0:
        ctx["shares"] = market_cap / stored_price
        ctx["market_cap"] = ctx["shares"] * live_price
    ctx["current_price"] = live_price
    eps = float(ctx.get("eps_ttm") or 0)
    ctx["pe_ttm"] = live_price / eps if eps > 0 else 0.0
    ctx["live_quote"] = quote
    return ctx


_price_cache: Dict[str, Any] = {}
_mktcap_cache: Dict[str, Any] = {}


def get_live_pricedf_cached(ticker: str, max_age: int = 900):
    """Live ~5y daily price series (keyless Yahoo chart) so price-dependent
    models (PE bands) work even when the local market cache is empty."""
    key = ticker.upper()
    now = time.time()
    hit = _price_cache.get(key)
    if hit and now - hit["ts"] < max_age:
        return hit["df"]
    df = None
    try:
        ch = technical_engine._fetch_chart(key, rng="5y", interval="1d")
        if ch and ch.get("dates"):
            df = pd.DataFrame({"date": pd.to_datetime(ch["dates"]), "close": ch["closes"]})
    except Exception:
        df = None
    _price_cache[key] = {"ts": now, "df": df}
    return df


def get_nasdaq_mktcap_cached(ticker: str, max_age: int = 1800):
    key = ticker.upper()
    now = time.time()
    hit = _mktcap_cache.get(key)
    if hit and now - hit["ts"] < max_age:
        return hit["mc"]
    mc = None
    try:
        mc = fetcher._nasdaq_summary(key).get("market_cap")
    except Exception:
        mc = None
    _mktcap_cache[key] = {"ts": now, "mc": mc}
    return mc


def get_ctx(ticker: str):
    key = ticker.upper()
    ver = db.data_version()
    hit = _ctx_cache.get(key)
    if hit and hit["ver"] == ver:
        return overlay_live_price(hit["ctx"], get_live_quote_cached(key))
    raw = db.get_financial_records(key)
    df_raw = pd.DataFrame(raw)
    meta = db.get_company_meta(key)
    df_price = db.get_market_history(key)
    ctx = build_context(key, df_raw, meta, df_price)

    # --- robustness: backfill price history + market cap from live keyless
    # sources when the local DB is empty, so DCF/EV/PE never silently blank. ---
    dp = ctx.get("df_price")
    if dp is None or getattr(dp, "empty", True):
        live_df = get_live_pricedf_cached(key)
        if live_df is not None and not live_df.empty:
            ctx["df_price"] = live_df
            ctx["current_price"] = float(live_df["close"].iloc[-1])
    if float(ctx.get("market_cap") or 0) <= 0:
        mc = get_nasdaq_mktcap_cached(key)
        cp = float(ctx.get("current_price") or 0)
        if mc and cp > 0:
            ctx["market_cap"] = mc
            ctx["shares"] = mc / cp
            if ctx.get("eps_ttm", 0) and ctx["eps_ttm"] > 0:
                ctx["pe_ttm"] = cp / ctx["eps_ttm"]

    ctx = overlay_live_price(ctx, get_live_quote_cached(key))
    _ctx_cache[key] = {"ver": ver, "ctx": ctx}
    return ctx


def clean_json(obj):
    """Recursively replace NaN/Inf so JSON serialization never fails."""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime("%Y-%m-%d")
    return obj


def ok(data):
    return JSONResponse(clean_json(data))


def wacc_for(ctx, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5):
    rf_val = (rf / 100.0) if rf is not None else fetcher.get_risk_free_rate()
    return compute_wacc(ctx, rf_val, beta=beta, erp=erp / 100.0), rf_val


# ============================ companies & groups ============================

@app.get("/api/bootstrap")
def bootstrap():
    return ok({
        "categories": db.get_categories_with_companies(),
        "all_categories": db.get_all_categories(),
        "tickers": db.get_all_tickers(),
        "metrics": FINANCIAL_METRICS,
        "metric_categories": CATEGORY_ORDER,
        "rf": fetcher.get_risk_free_rate(),
        "masters": {k: {kk: vv for kk, vv in v.items()} for k, v in MASTER_DEFINITIONS.items()},
        "providers": [{"name": p.name, "available": p.available()} for p in ALL_PROVIDERS],
    })


@app.post("/api/companies")
def add_company(payload: dict = Body(...)):
    ticker = (payload.get("ticker") or "").strip().upper()
    if not ticker:
        raise HTTPException(400, "ticker required")
    name = payload.get("name") or ""
    region = payload.get("region") or db.detect_region_from_ticker(ticker)
    db.save_company_meta(ticker, name, region=region)
    db.auto_assign_company_to_region_category(ticker, region)
    return ok({"ok": True, "ticker": ticker, "region": region})


@app.delete("/api/companies/{ticker}")
def remove_company(ticker: str):
    return ok({"ok": db.delete_company(ticker.upper())})


@app.post("/api/categories")
def create_cat(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    return ok({"ok": db.create_category(name)})


@app.delete("/api/categories/{cat_id}")
def del_cat(cat_id: int):
    return ok({"ok": db.delete_category(cat_id)})


@app.put("/api/categories/{cat_id}")
def rename_cat(cat_id: int, payload: dict = Body(...)):
    return ok({"ok": db.rename_category(cat_id, (payload.get("name") or "").strip())})


@app.post("/api/categories/{cat_id}/members")
def add_member(cat_id: int, payload: dict = Body(...)):
    return ok({"ok": db.add_company_to_category(cat_id, payload.get("ticker", "").upper())})


@app.delete("/api/categories/{cat_id}/members/{ticker}")
def del_member(cat_id: int, ticker: str):
    return ok({"ok": db.remove_company_from_category(cat_id, ticker.upper())})


# ============================ records & company data ============================

@app.get("/api/company/{ticker}")
def company_overview(ticker: str):
    ctx = get_ctx(ticker)
    meta = ctx["meta"]
    records = db.get_financial_records(ticker.upper())
    dp = ctx["df_price"]
    price_series = None
    if dp is not None and not dp.empty:
        step = max(1, len(dp) // 800)
        sub = dp.iloc[::step]
        price_series = {"dates": sub["date"].dt.strftime("%Y-%m-%d").tolist(),
                        "close": [_f(x, 2) for x in sub["close"]]}
    return ok({
        "meta": meta, "records": records,
        "record_count": len(records),
        "current_price": _f(ctx["current_price"], 2),
        "market_cap": _f(ctx["market_cap"], 0),
        "eps_ttm": _f(ctx["eps_ttm"], 3), "pe_ttm": _f(ctx["pe_ttm"], 2),
        "price_series": price_series,
    })


@app.post("/api/company/{ticker}/records")
def save_record(ticker: str, payload: dict = Body(...)):
    payload["ticker"] = ticker.upper()
    if not payload.get("year") or not payload.get("period"):
        raise HTTPException(400, "year and period required")
    return ok({"ok": db.save_financial_record(payload)})


@app.delete("/api/company/{ticker}/records/{year}/{period}")
def del_record(ticker: str, year: int, period: str):
    return ok({"ok": db.delete_financial_record(ticker.upper(), year, period)})


@app.post("/api/company/{ticker}/import")
def import_json(ticker: str, payload: dict = Body(...)):
    from modules.data.json_importer import validate_json_structure, import_json_to_database
    data = payload.get("data")
    if not data:
        raise HTTPException(400, "data required")
    valid, msg = validate_json_structure(data)
    if not valid:
        raise HTTPException(400, msg)
    count, errors = import_json_to_database(data, ticker.upper())
    return ok({"ok": True, "imported": count, "errors": errors})


@app.get("/api/company/{ticker}/trends")
def trends(ticker: str, view: str = "single"):
    ctx = get_ctx(ticker)
    ds = ctx["df_single"]
    if ds.empty:
        return ok({"error": "no_data"})
    dv = get_view_data(ds, view)
    if dv.empty:
        return ok({"error": "no_data"})
    dv = dv.replace([np.inf, -np.inf], np.nan)
    labels = (dv["year"].astype(int).astype(str) + " " + dv["period"].astype(str)).tolist()
    out = {"labels": labels, "series": {}}
    skip = {"year", "period", "report_date", "Sort_Key", "ticker", "s"}
    for c in dv.columns:
        if c in skip or not pd.api.types.is_numeric_dtype(dv[c]):
            continue
        vals = [(_f(v, 4) if pd.notna(v) else None) for v in dv[c]]
        if any(v is not None for v in vals):
            out["series"][c] = vals
    return ok(out)


# ============================ market sync (async, threaded) ============================

@app.post("/api/company/{ticker}/sync")
async def sync(ticker: str, payload: dict = Body(default={})):
    proxy = payload.get("proxy") or None
    res = await asyncio.to_thread(fetcher.sync_market_data, ticker.upper(), proxy)
    return ok(res)


@app.post("/api/company/{ticker}/analyst/fetch")
async def analyst_fetch(ticker: str, payload: dict = Body(default={})):
    proxy = payload.get("proxy") or None
    res = await asyncio.to_thread(fetcher.fetch_analyst_data, ticker.upper(), proxy)
    return ok(res)


@app.get("/api/company/{ticker}/analyst")
def analyst_cached(ticker: str):
    t = ticker.upper()
    return ok({
        "price_target": db.get_price_target(t),
        "recommendations": db.get_recommendation_trends(t),
        "eps_estimates": db.get_analyst_estimates(t, "eps", "mixed"),
        "revenue_estimates": db.get_analyst_estimates(t, "revenue", "mixed"),
        "current_price": _f(get_ctx(t)["current_price"], 2),
    })


# ============================ v4: multi-source ingest ============================

@app.get("/api/providers")
async def providers_status():
    return ok(await asyncio.to_thread(health_engine.connection_status))


@app.post("/api/company/{ticker}/ingest")
async def ingest_endpoint(ticker: str, payload: dict = Body(default={})):
    """Auto-fetch + cross-verify 5y+ financial statements from all sources."""
    t = ticker.upper()
    proxy = payload.get("proxy") or None
    # ensure the company exists so a brand-new ticker can be onboarded in one call
    if not db.get_company_meta(t):
        region = db.detect_region_from_ticker(t)
        db.save_company_meta(t, payload.get("name") or "", region=region)
        db.auto_assign_company_to_region_category(t, region)
    res = await asyncio.to_thread(ingest_engine.ingest_ticker, t, proxy)
    return ok(res)


@app.post("/api/company/{ticker}/refresh")
async def refresh_endpoint(ticker: str, payload: dict = Body(default={})):
    """One-click: financials (cross-verified) + prices + analyst + news."""
    t = ticker.upper()
    proxy = payload.get("proxy") or None
    if not db.get_company_meta(t):
        region = db.detect_region_from_ticker(t)
        db.save_company_meta(t, payload.get("name") or "", region=region)
        db.auto_assign_company_to_region_category(t, region)

    def _run_all():
        out = {"ingest": ingest_engine.ingest_ticker(t, proxy, replace=payload.get("replace", False))}
        out["market"] = fetcher.sync_market_data(t, proxy)
        out["analyst"] = fetcher.fetch_analyst_data(t, proxy)
        out["news"] = news_engine.fetch_news(t, proxy)
        out["social"] = news_engine.fetch_social(t, proxy)
        _quote_cache.pop(t, None)
        _ctx_cache.pop(t, None)
        return out

    return ok(await asyncio.to_thread(_run_all))


@app.get("/api/company/{ticker}/ingest/meta")
def ingest_meta_endpoint(ticker: str):
    return ok(db.get_ingest_meta(ticker.upper()) or {})


@app.get("/api/company/{ticker}/provenance")
def provenance_endpoint(ticker: str, year: Optional[int] = None, period: Optional[str] = None):
    return ok(db.get_provenance(ticker.upper(), year=year, period=period))


@app.get("/api/company/{ticker}/annual")
def annual_endpoint(ticker: str):
    return ok({"records": db.get_annual_records(ticker.upper())})


# ============================ v4: news ============================

@app.post("/api/company/{ticker}/news/fetch")
async def news_fetch_endpoint(ticker: str, payload: dict = Body(default={})):
    proxy = payload.get("proxy") or None
    t = ticker.upper()
    def _both():
        return {"news": news_engine.fetch_news(t, proxy),
                "social": news_engine.fetch_social(t, proxy)}
    return ok(await asyncio.to_thread(_both))


@app.get("/api/company/{ticker}/news")
def news_endpoint(ticker: str, limit: int = 40):
    return ok(news_engine.analyze(ticker.upper(), limit=limit))


# ============================ valuations ============================

@app.get("/api/company/{ticker}/wacc")
def wacc_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5):
    ctx = get_ctx(ticker)
    w, _rf = wacc_for(ctx, rf, beta, erp)
    return ok(w)


@app.get("/api/company/{ticker}/valuation/dcf")
def dcf_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5,
                 growth: Optional[float] = None, perp: Optional[float] = None,
                 fcf: Optional[float] = None, wacc_override: Optional[float] = None):
    ctx = get_ctx(ticker)
    w, rf_val = wacc_for(ctx, rf, beta, erp)
    wacc_val = (wacc_override / 100.0) if wacc_override is not None else w["wacc"]
    fwd = dcf_forward(ctx, wacc_val, rf_val, growth_pct=growth, perp_pct=perp, base_fcf=fcf)
    rev = dcf_reverse(ctx, wacc_val, perp_pct=perp if perp is not None else 2.5)
    return ok({"wacc": w, "forward": fwd, "reverse": rev})


@app.get("/api/company/{ticker}/valuation/pe")
def pe_endpoint(ticker: str, rf: Optional[float] = None):
    ctx = get_ctx(ticker)
    rf_val = (rf / 100.0) if rf is not None else fetcher.get_risk_free_rate()
    return ok(pe_analysis(ctx, rf_val))


@app.get("/api/company/{ticker}/valuation/ev_ebitda")
def ev_endpoint(ticker: str):
    return ok(ev_ebitda(get_ctx(ticker)))


@app.get("/api/company/{ticker}/valuation/growth")
def growth_endpoint(ticker: str):
    return ok(growth_analysis(get_ctx(ticker)))


@app.get("/api/company/{ticker}/valuation/montecarlo")
def mc_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5,
                metric: str = "FreeCashFlow_TTM_YoY", mean: Optional[float] = None,
                std: Optional[float] = None, sims: int = 2000):
    ctx = get_ctx(ticker)
    w, _ = wacc_for(ctx, rf, beta, erp)
    return ok(monte_carlo(ctx, w["wacc"], metric=metric,
                          growth_mean=mean / 100.0 if mean is not None else None,
                          growth_std=std / 100.0 if std is not None else None, n_sims=sims))


@app.get("/api/company/{ticker}/valuation/profitability")
def prof_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5):
    ctx = get_ctx(ticker)
    w, _ = wacc_for(ctx, rf, beta, erp)
    return ok(profitability(ctx, w["wacc"]))


@app.get("/api/company/{ticker}/masters")
def masters_endpoint(ticker: str):
    ctx = get_ctx(ticker)
    scores = compute_master_scores(ctx)
    qg = compute_qg_pro(ctx)
    groups = {"value": ["Buffett", "Munger", "Graham", "Greenblatt", "Templeton"],
              "growth": ["Lynch", "Fisher"], "trend": ["Soros"], "defense": ["Dalio"]}
    dims = {}
    for gname, keys in groups.items():
        vals = [scores[k]["score"] for k in keys if k in scores and scores[k]["available"]]
        dims[gname] = _f(float(np.mean(vals)), 1) if vals else 50.0
    avail = [scores[k]["score"] for k in scores if scores[k]["available"]]
    return ok({"scores": scores, "qg": qg, "dimensions": dims,
               "average": _f(float(np.mean(avail)), 1) if avail else None,
               "available_count": len(avail), "definitions": MASTER_DEFINITIONS})


@app.get("/api/company/{ticker}/dashboard")
def dashboard_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5,
                       growth: Optional[float] = None, perp: float = 2.5,
                       w_pe: float = 0.25, w_peg: float = 0.20, w_dcf: float = 0.35, w_ev: float = 0.20):
    ctx = get_ctx(ticker)
    w, rf_val = wacc_for(ctx, rf, beta, erp)
    weights = {"PE": w_pe, "PEG": w_peg, "DCF": w_dcf, "EV/EBITDA": w_ev}
    return ok(dash_calc(ctx, w["wacc"], rf_val, growth_pct=growth, perp_pct=perp, weights=weights))


@app.get("/api/company/{ticker}/summary")
def summary_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5):
    ctx = get_ctx(ticker)
    w, rf_val = wacc_for(ctx, rf, beta, erp)
    scores = compute_master_scores(ctx)
    qg = compute_qg_pro(ctx)
    s = summary_calc(ctx, w["wacc"], rf_val, scores, qg)
    groups = {"value": ["Buffett", "Munger", "Graham", "Greenblatt", "Templeton"],
              "growth": ["Lynch", "Fisher"], "trend": ["Soros"], "defense": ["Dalio"]}
    dims = {}
    for gname, keys in groups.items():
        vals = [scores[k]["score"] for k in keys if k in scores and scores[k]["available"]]
        dims[gname] = _f(float(np.mean(vals)), 1) if vals else 50.0
    s["master_scores"] = scores
    s["master_dimensions"] = dims
    s["qg"] = qg
    return ok(s)


@app.get("/api/company/{ticker}/statements")
def statements_endpoint(ticker: str, freq: str = "annual", years: int = 5):
    """Statement rows: freq=annual (FY) or quarterly (Q1-Q4), last `years` years."""
    t = ticker.upper()
    rows = db.get_financial_records(t)
    if freq == "quarterly":
        rows = [r for r in rows if r.get("period") in ("Q1", "Q2", "Q3", "Q4")]
    else:
        rows = [r for r in rows if r.get("period") == "FY"]
    yrs = sorted({r["year"] for r in rows if r.get("year")}, reverse=True)[:max(1, years)]
    rows = [r for r in rows if r.get("year") in yrs]
    rows.sort(key=lambda r: (r.get("year", 0), {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}.get(r.get("period"), 0)))
    return ok({"freq": freq, "years": yrs, "rows": rows})


@app.get("/api/company/{ticker}/financial_summary")
def financial_summary_endpoint(ticker: str, lang: str = "en"):
    ctx = get_ctx(ticker)
    return ok({"summary": grade_engine.financial_summary(ctx, lang=lang)})


@app.get("/api/company/{ticker}/quote")
async def quote_endpoint(ticker: str):
    return ok(await asyncio.to_thread(get_live_quote_cached, ticker.upper()))


@app.get("/api/company/{ticker}/technical")
async def technical_endpoint(ticker: str):
    return ok(await asyncio.to_thread(technical_engine.analyze, ticker.upper()))


@app.get("/api/company/{ticker}/grade")
async def grade_endpoint(ticker: str, rf: Optional[float] = None, beta: float = 1.2, erp: float = 5.5):
    """Composite letter grade + bilingual advice synthesizing all dimensions."""
    t = ticker.upper()
    ctx = get_ctx(t)
    w, rf_val = wacc_for(ctx, rf, beta, erp)
    dash = dash_calc(ctx, w["wacc"], rf_val)
    scores = compute_master_scores(ctx)
    qg = compute_qg_pro(ctx)
    avail = [scores[k]["score"] for k in scores if scores[k]["available"]]
    masters_avg = float(np.mean(avail)) if avail else None
    qg_score = qg.get("score") if qg and qg.get("available") else None
    fin_health, fin_factors = grade_engine.financial_health(ctx)
    growth = growth_analysis(ctx)
    growth_score = grade_engine.growth_score(growth.get("rows") if isinstance(growth, dict) else None)

    tech = await asyncio.to_thread(technical_engine.analyze, t)
    tech_score = tech.get("score") if isinstance(tech, dict) else None

    news_score, news_tone = None, None
    n = news_engine.analyze(t)
    if n and n.get("count"):
        news_score = 50 + (n.get("sentiment_score") or 0) * 50
        news_tone = n.get("tone")

    margin = dash.get("margin_pct")
    gi = grade_engine.compute_grade(margin, dash.get("confidence"), masters_avg,
                                    qg_score, news_score, fin_health,
                                    growth_score=growth_score, technical_score=tech_score)
    return ok({
        "grade": gi["grade"], "score": gi["score"], "components": gi["components"],
        "margin_pct": margin, "confidence": dash.get("confidence"),
        "financial_health": fin_health, "financial_factors": fin_factors,
        "technical": {"score": tech_score, "trend_en": tech.get("trend_en") if isinstance(tech, dict) else None,
                      "trend_zh": tech.get("trend_zh") if isinstance(tech, dict) else None},
        "news_tone": news_tone,
        "advice_en": grade_engine.advice(gi, margin, news_tone, "en"),
        "advice_zh": grade_engine.advice(gi, margin, news_tone, "zh"),
    })


@app.get("/api/rf")
def rf_endpoint():
    return ok({"rf": fetcher.get_risk_free_rate()})


# ============================ static frontend ============================

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

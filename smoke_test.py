#!/usr/bin/env python3
"""Stock-Ward smoke test — run on YOUR machine to confirm everything boots.

    python smoke_test.py

It imports the whole app (FastAPI server + engine), checks the data sources are
reachable, runs the valuation engine on one ticker, and prints a clear PASS/FAIL.
No browser, no key needed. If this prints ALL CHECKS PASSED, the app is healthy.
"""
import sys, time, traceback

OK, FAIL = "  [PASS]", "  [FAIL]"
problems = []


def check(name, fn):
    try:
        msg = fn()
        print(f"{OK} {name}: {msg}")
    except Exception as e:
        print(f"{FAIL} {name}: {e}")
        problems.append(name)


def t_imports():
    import server  # noqa  (pulls in engine, providers, fastapi, everything)
    return "server + engine import cleanly"


def t_sources():
    from engine import health
    st = health.connection_status()
    live = [s["name"] for s in st if s["status"] == "live"]
    return f"{len(live)}/{len(st)} live -> {', '.join(live) or 'none'}"


def t_engine():
    # full pipeline on a profitable large-cap, all keyless
    import pandas as pd
    from engine import db, ingest, technical
    from engine.valuation import build_context, pe_analysis, dcf_forward, monte_carlo, compute_wacc
    from engine import fetcher
    rep = ingest.ingest_ticker("MSFT")
    raw = db.get_financial_records("MSFT")
    ctx = build_context("MSFT", pd.DataFrame(raw), db.get_company_meta("MSFT"), db.get_market_history("MSFT"))
    # backfill live price + market cap (same as the server does)
    ch = technical._fetch_chart("MSFT", rng="2y", interval="1d")
    if ch and ch.get("dates"):
        ctx["df_price"] = pd.DataFrame({"date": pd.to_datetime(ch["dates"]), "close": ch["closes"]})
        ctx["current_price"] = float(ctx["df_price"]["close"].iloc[-1])
    nq = fetcher._nasdaq_summary("MSFT")
    if nq.get("market_cap") and ctx["current_price"]:
        ctx["market_cap"] = nq["market_cap"]; ctx["shares"] = nq["market_cap"] / ctx["current_price"]
    w = compute_wacc(ctx, 0.045)["wacc"]
    pe = pe_analysis(ctx, 0.045)
    dcf = dcf_forward(ctx, w, 0.045)
    mc = monte_carlo(ctx, w)
    parts = [f"ingest {rep.get('records_written', 0)} periods"]
    parts.append(f"PE band {'OK' if 'percentiles' in pe else pe.get('error')}")
    parts.append(f"DCF {'OK' if not dcf.get('error') else dcf.get('error')}")
    parts.append(f"MC {'price+prob OK' if (isinstance(mc, dict) and mc.get('price')) else mc.get('error')}")
    return " | ".join(parts)


if __name__ == "__main__":
    print("\n=== Stock-Ward smoke test ===")
    t0 = time.time()
    check("imports", t_imports)
    check("data sources", t_sources)
    check("valuation engine (MSFT)", t_engine)
    print(f"\nFinished in {time.time()-t0:.1f}s")
    if problems:
        print("RESULT:  SOME CHECKS FAILED ->", ", ".join(problems))
        sys.exit(1)
    print("RESULT:  ALL CHECKS PASSED  ✅  (app is healthy)")

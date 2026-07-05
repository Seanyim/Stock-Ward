# engine/ingest.py — multi-source fetch + cross-verification orchestrator.
#
# Pulls financial statements from every available provider, reconciles each
# (year, period, metric) cell across sources, writes the consensus value into
# financial_records, and records full provenance (every source value, the
# agreement status, and the chosen source) for the data-quality panel.
import statistics
from datetime import datetime

from engine import db
from engine.providers import active_providers
from modules.core.config import ALL_METRIC_KEYS

# Source authority for tie-breaking on conflict (most authoritative first).
SOURCE_PRIORITY = ["sec_edgar", "nasdaq", "fmp", "alphavantage", "yfinance"]

# Relative-spread tolerance for declaring sources "in agreement".
DEFAULT_TOL = 0.02            # 2 %
PER_METRIC_TOL = {"EPS": 0.03, "FreeCashFlow": 0.05, "CashEndOfPeriod": 0.05}

# Keep a rolling window of recent years. Quarterly investors need more than the
# usual 5 quarters returned by some vendor SDKs, so preserve a wider local cache.
YEARS_BACK = 12


def _priority_rank(source):
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)


def _reconcile(metric, source_values):
    """source_values: {source: value}. Returns (chosen, chosen_source, agreement, spread)."""
    items = [(s, v) for s, v in source_values.items() if v is not None]
    if not items:
        return None, None, "missing", None
    if len(items) == 1:
        return items[0][1], items[0][0], "single", 0.0

    vals = [v for _, v in items]
    median = statistics.median(vals)
    ref = abs(median) if median else (abs(max(vals, key=abs)) or 1.0)
    spread = (max(vals) - min(vals)) / ref if ref else 0.0
    tol = PER_METRIC_TOL.get(metric, DEFAULT_TOL)

    if spread <= tol:
        # Agreement: take the value from the most authoritative source.
        best = sorted(items, key=lambda it: _priority_rank(it[0]))[0]
        return best[1], best[0], "verified", round(spread, 4)
    # Conflict: still prefer authoritative source, but flag it.
    best = sorted(items, key=lambda it: _priority_rank(it[0]))[0]
    return best[1], best[0], "conflict", round(spread, 4)


def ingest_ticker(ticker, proxy=None, replace=True):
    """Fetch + cross-verify + persist. Returns a structured report dict."""
    ticker = ticker.upper()
    providers = active_providers()
    report = {"ticker": ticker, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "sources_used": [], "sources_failed": [],
              "records_written": 0, "cells": 0, "verified": 0, "conflicts": 0,
              "single_source": 0, "conflict_detail": []}

    cur_year = datetime.now().year
    min_year = cur_year - YEARS_BACK

    # 1. collect per-source records ---------------------------------------
    # cells[(year, period)][metric] = {source: value}
    cells = {}
    report_dates = {}
    for p in providers:
        try:
            recs = p.fetch_financials(ticker, proxy=proxy)
        except Exception as e:
            report["sources_failed"].append({"source": p.name, "error": str(e)})
            continue
        if not recs:
            report["sources_failed"].append({"source": p.name, "error": "no data"})
            continue
        report["sources_used"].append(p.name)
        for rec in recs:
            year = rec.get("year")
            period = rec.get("period")
            if year is None or period is None or year < min_year:
                continue
            ckey = (int(year), str(period))
            cell = cells.setdefault(ckey, {})
            rd = rec.get("report_date")
            if rd:
                report_dates.setdefault(ckey, rd)
            for metric, value in rec.items():
                if metric in ("year", "period", "report_date", "_source"):
                    continue
                if metric not in ALL_METRIC_KEYS and metric not in ("EBITDA", "IncomeTaxExpense"):
                    continue
                cell.setdefault(metric, {})[rec["_source"]] = value

    if not report["sources_used"]:
        report["error"] = "No data returned from any source."
        return report

    if replace:
        db.clear_financial_records(ticker)
        db.clear_provenance(ticker)

    # 2. reconcile each cell ---------------------------------------------
    for (year, period), metrics in sorted(cells.items()):
        out_rec = {"ticker": ticker, "year": year, "period": period,
                   "report_date": report_dates.get((year, period))}
        prov_rows = []
        for metric, source_values in metrics.items():
            chosen, src, agreement, spread = _reconcile(metric, source_values)
            report["cells"] += 1
            if agreement == "verified":
                report["verified"] += 1
            elif agreement == "conflict":
                report["conflicts"] += 1
                report["conflict_detail"].append(
                    {"year": year, "period": period, "metric": metric,
                     "spread": spread, "values": source_values})
            elif agreement == "single":
                report["single_source"] += 1

            if metric in ALL_METRIC_KEYS and chosen is not None:
                out_rec[metric] = chosen
            prov_rows.append((metric, chosen, src, agreement, spread, source_values))

        db.save_financial_record(out_rec)
        report["records_written"] += 1
        db.save_provenance(ticker, year, period, prov_rows)

    # 3. annual integrity check (sum of quarters vs FY) -------------------
    report["integrity"] = _annual_integrity(cells)
    db.set_ingest_meta(ticker, report)
    return report


def _annual_integrity(cells):
    """Compare sum of quarterly TotalRevenue/NetIncome to the FY figure."""
    checks = []
    by_year = {}
    for (year, period), metrics in cells.items():
        by_year.setdefault(year, {})[period] = metrics
    for year, periods in sorted(by_year.items()):
        fy = periods.get("FY")
        if not fy:
            continue
        for metric in ("TotalRevenue", "NetIncome", "OperatingCashFlow"):
            q_vals = []
            for q in ("Q1", "Q2", "Q3", "Q4"):
                qm = periods.get(q, {}).get(metric)
                if qm:
                    q_vals.append(statistics.median([v for v in qm.values() if v is not None] or [0]))
            fy_cell = fy.get(metric)
            if fy_cell and len(q_vals) == 4:
                fy_val = statistics.median([v for v in fy_cell.values() if v is not None] or [0])
                qsum = sum(q_vals)
                if fy_val:
                    diff = abs(qsum - fy_val) / abs(fy_val)
                    checks.append({"year": year, "metric": metric,
                                   "fy": round(fy_val, 4), "q_sum": round(qsum, 4),
                                   "diff_pct": round(diff * 100, 2),
                                   "ok": diff <= 0.03})
    return checks

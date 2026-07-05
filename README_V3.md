# Stock-Ward v3 — Apple-style local valuation workstation

Streamlit has been replaced by a **FastAPI backend + single-page Apple-style web UI** (bilingual EN/中文).

## Run

```bash
python run.py
```

That's it — the server starts on `http://127.0.0.1:8377` and your default browser opens automatically.
(Windows: double-click `run.bat`. First run auto-installs dependencies from `requirements.txt`.)

## What changed in v3

### Architecture
| | v2.5 (Streamlit) | v3 |
|---|---|---|
| UI | Streamlit reruns whole script per click | SPA, lazy tab loading, per-tab caching |
| Charts | Plotly | ECharts (bundled locally, offline-capable) |
| Backend | none (monolith) | FastAPI REST (`/api/docs` for OpenAPI) |
| Language | 中文 only | EN / 中文 toggle |
| Launch | `streamlit run main.py` | `python run.py` → browser opens |

### Calculation fixes (engine/)
1. **WACC** — debt previously read from nonexistent `Total_Debt` column → always 0. Now uses
   `NonCurrentLiabilities` as long-term-debt proxy with consistent $ units.
2. **FCF fallback** — `OCF − CapEx` silently became raw OCF (no CapEx column). Now:
   `FreeCashFlow` → `OCF + InvestingCashFlow` (flagged approximation), never silent.
3. **Unit handling** — removed all `value < 10000 → ×1e9` heuristics; explicit Billion→$ scale.
4. **DCF equity bridge** — EV is now reduced by net debt before per-share value and
   market-cap comparison (previously EV was compared directly to equity market cap).
5. **ROIC** — now `NOPAT / (Equity + NonCurrentLiabilities)` instead of degenerating to ROE.
6. **EV/EBITDA** — debt/cash now read from real schema columns.
7. **Fisher PEG** — standardized to `fair PE = G + 2×Rf` everywhere.
8. **QG-Pro** — missing OCF/NI no longer scores 0 (treated as unavailable → neutral).
9. **Monte Carlo** — vectorized with numpy (5,000 paths ≈ 4 ms) and returns equity value.

### Performance
- Per-ticker context cache on the server, invalidated automatically on any DB write.
- Frontend response cache per (ticker, tab, WACC params); tabs load lazily.
- Price/PE-band series downsampled server-side (≤ 800 points) for instant chart rendering.
- SQLite WAL mode; market sync & analyst fetch run in a thread pool (UI never blocks).

## Layout

```
run.py / run.bat        launcher (auto-opens browser)
server.py               FastAPI app + REST API
engine/                 pure calculation layer (no UI deps)
  db.py  valuation.py  masters.py  summary.py  fetcher.py
web/index.html          Apple-style SPA (EN/中文)
web/echarts.min.js      bundled chart library
modules/                legacy v2.5 code (calculator/config/json_importer still reused)
```

The old Streamlit app (`main.py`) is kept for reference but is no longer the entry point,
and `streamlit` was removed from `requirements.txt`.

# Stock-Ward v4 — Bloomberg-style multi-source valuation terminal

## Run
Windows: double-click **`run.bat`**. It now auto-creates a local virtual
environment (`.venv`), installs/updates dependencies into it, and launches the
server under that venv. Subsequent launches are fast (deps only reinstall when
`requirements.txt` changes). `python run.py` does the same on any OS — it
re-execs itself inside `.venv` automatically.

The browser opens to `http://127.0.0.1:8377`.

## What changed in v4

### 1. Automatic financial data (no more manual entry)
The app now fetches and stores **5+ years** of financial statements itself.
Press **⟳ REFRESH** in the terminal (or call `POST /api/company/{ticker}/refresh`)
and it pulls statements, prices, analyst data, and news, then runs the
valuation engine on the result. Data is stored in `data/financial_data.db`.

### 2. Multi-source cross-verification
Four providers, reconciled cell-by-cell (every year × period × metric):

| Source | Key needed | Coverage |
|---|---|---|
| **yfinance** | none | annual + quarterly statements, prices, analyst, news |
| **SEC EDGAR** | none | authoritative annual (10-K) figures, US tickers |
| **Financial Modeling Prep** | yes | annual + quarterly |
| **Alpha Vantage** | yes | annual + quarterly |

For each metric the engine compares all sources: within 2% → **VERIFIED**
(keeps the most authoritative value, SEC first); beyond tolerance → **CONFLICT**
(flagged, all source values kept); one source → **SINGLE**. It also runs an
annual integrity check (Σ quarters vs. reported FY). See it all in the
**DATA QUALITY** tab.

### 3. Adding API keys (optional but recommended)
Copy `data/api_keys.example.json` to `data/api_keys.json` and fill in any keys
you have. With no keys the app runs fully on yfinance + SEC EDGAR. Keys unlock
extra sources for stronger cross-verification.

```json
{
  "SEC_USER_AGENT": "Your Name your-email@example.com",
  "FMP": "your_fmp_key",
  "ALPHAVANTAGE": "your_av_key"
}
```
(`api_keys.json` is git-ignored.) Keys are also accepted via environment
variables, e.g. `STOCKWARD_FMP` / `FMP`.

### 4. News + pros / cons / forward effects
The **NEWS** tab fetches recent headlines (yfinance), sentiment-tags each, and
buckets them into Pros/Tailwinds, Cons/Risks, and Forward Effects (guidance,
outlook, targets), with a synthesized sentiment summary.

### 5. Bloomberg-style terminal UI + interaction model
The Apple-style SPA was replaced with a dark, dense, monospace terminal:
- **Command bar** — type a ticker, press **Enter**/**GO**. **⟳ REFRESH** fetches
  + cross-verifies. Live 10Y risk-free rate and source-status lights up top.
- **Function-key tabs** — `F1` Overview · `F2` Fundamentals · `F3` Valuation ·
  `F4` Masters · `F5` News · `F6` Data Quality. Press `/` to jump to the command bar.
- **Watchlist rail** — categories → tickers, click to load.
- Dense panels, color-coded (green up / red down / amber headers), ECharts
  visuals (price, revenue/margins, style radar, Monte-Carlo distribution).

## Data model note
`financial_records` stores single-quarter rows (Q1–Q4, drive TTM/YoY in the
valuation engine) **plus** annual `FY` rows (5y+ history, shown in the
Fundamentals statement table). The calculator was adjusted so FY rows coexist
with quarterly rows without breaking format detection.

## v4.1 additions

- **Three keyless sources.** Added **Nasdaq** (official exchange financials + analyst
  consensus, no key) alongside yfinance and SEC EDGAR — so 3 of the source lights
  are green with no API keys at all. FMP / Alpha Vantage remain optional bonus
  sources that light up when you add keys.
- **Bigger, readable type** across the terminal (kept dense, Bloomberg-style).
- **EN / 中文 toggle** (中文/EN button, top right). Advice, news summaries and the
  financial narrative are generated bilingually.
- **Day / Night theme** toggle (☀/☾ button) — full light + dark palettes.
- **Editable watchlist.** Add/remove tickers, create/rename/delete groups, and move
  a ticker between groups (hover a row for ⇄ move / ✕ remove; hover a group header
  for ✎ rename / ✕ delete; ＋⊞ adds a group).
- **Overview grade & advice.** Each ticker gets a composite **A–F grade** synthesizing
  valuation margin, investor-lens scores, financial health, QG-Pro and news sentiment,
  with a written recommendation (bilingual).
- **Richer valuation.** Surfaced the full engine: DCF 5-year projection table, WACC×g
  **sensitivity heatmap**, reverse-DCF implied path, **P/E percentile bands** chart,
  **profitability** (ROE/ROA/ROIC, ROIC−WACC spread), **growth** table, and **analyst
  consensus** — in addition to the composite/DCF/PE/EV/Monte-Carlo cards.
- **Fundamentals upgrades.** Annual ⇄ quarterly toggle, a 3/5/8/10-year window
  selector, and a written financial-report summary.
- **Fuller news summary** — a multi-sentence synthesized read (pros, cons, forward
  signals, net call), bilingual.

## Packaging into a standalone Windows app

Run **`build.bat`** (needs Python + internet once). It installs PyInstaller into the
`.venv` and produces `dist\Stock-Ward\Stock-Ward.exe`. Ship/copy the whole
`dist\Stock-Ward\` folder; double-clicking the `.exe` launches the server and opens
the browser — no Python install required on the target machine. The database and
`data\api_keys.json` live next to the `.exe` so your data persists between runs.
(Build on Windows to get a Windows executable.)

## v4.2 additions

- **Runs as a desktop app, not a browser.** The launcher now opens Stock-Ward in a
  native window (via `pywebview`, using the built-in Windows WebView2 — no extra
  runtime). If a webview backend isn't available it falls back to the browser.
  Packaged with `build.bat`, `dist\Stock-Ward\Stock-Ward.exe` launches straight
  into the app window.
- **Claude × Bloomberg styling.** Warm Anthropic palette — cream paper + terracotta
  accent in light mode, warm charcoal + terracotta in dark — with sans-serif prose
  and monospace data tables, softly rounded panels, kept dense.
- **Live source connectivity.** Every source is pinged for real on load (and shown in
  Data Quality): green = connected, amber = needs API key, red = unreachable. Added
  two more keyless connections — **Stooq** (prices) and **StockTwits** (social) — so
  five sources are green with no keys; only FMP/Alpha Vantage show amber until you
  add their keys. No more gray bulbs.
- **Richer hover tooltips** on all charts — metric name, value, and proper units
  ($, B, %, ×), with the period.
- **多维图 quality view.** The Overview grade panel now shows a score **gauge** and a
  **multi-dimensional radar** across the five quality dimensions (valuation, masters,
  financial health, QG-Pro, news) alongside the written advice.
- **Tweets / retail discussion.** News now pulls recent **StockTwits** posts
  (no key), sentiment-tags them, shows a discussion panel, and folds the retail
  bull/bear tone into the bilingual news summary.

## v4.3 additions

- **All data sources are now keyless.** Removed FMP and Alpha Vantage (which
  required API keys). Cross-verification runs on yfinance + SEC EDGAR + Nasdaq
  (financials), plus Stooq (prices) and StockTwits (social) — five live green
  lights, no keys, no gray bulbs. Click **SOURCES** (top right) for a live
  status popup.
- **Newest price + live history.** The Overview now shows the live price with an
  as-of timestamp, and the price-history chart falls back to a live Yahoo series
  when the local market cache is empty — so it always renders.
- **Clickable grade.** Click **Overall grade & advice** to open a full-screen
  breakdown: every one of the 7 quality dimensions with its score and a plain
  explanation of *how it is computed*, plus valuation, financial and technical
  detail and the written recommendation.
- **Valuation "how it's calculated" indicators.** Each valuation card (Composite,
  DCF forward/reverse, P/E, EV/EBITDA) has an ⓘ that explains its formula. Empty
  panels now tell you to press ⟳ REFRESH (and why) instead of silently blank.
- **Technicals on the newest price.** RSI, MACD, SMA20/50/200, 52-week position,
  returns and volatility are computed from a live 2-year daily series and feed a
  technical dimension in the quality radar.
- **Influential tweets.** StockTwits posts are ranked by follower count and
  official-account status; the News tab surfaces an "Influential voices" block,
  and the summary reports both the crowd tone and the audience-weighted tone of
  the most-followed accounts.
- **Slack + terminal theme.** Replaced the warm cream theme with a Slack-style
  structured workspace (dark sidebar, blue accent, clean panels) over a
  terminal-dense, monospace-data core. Light mode is a clean cool grey.

## Backups
Your previous database was backed up to
`data/financial_data_backup_<timestamp>.db` before the v4 changes.

# Stock-Ward

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)

[English](README.md) | [简体中文](README/README_ZH.md)

A local, bilingual equity-research terminal that combines multi-source financial data, valuation models, technical indicators, company quality scores, news, and retail discussion in one desktop-style interface.

Stock-Ward runs on your machine. Its FastAPI backend stores research data in SQLite, while a dense browser UI or native `pywebview` window provides the terminal experience.

![Stock-Ward dashboard](assets/images/dashboard_placeholder.png)

> Stock-Ward is a research tool, not financial advice. Validate source data and assumptions before making investment decisions.

## Highlights

- **Keyless financial data:** fetch annual and quarterly statements from yfinance, SEC EDGAR, and Nasdaq without paid API keys.
- **Cross-source verification:** reconcile each period and metric, retain provenance, flag conflicts, and compare quarterly totals with reported fiscal-year figures.
- **Valuation suite:** composite fair value, forward and reverse DCF, WACC sensitivity, P/E bands, PEG, EV/EBITDA, Monte Carlo analysis, profitability, and growth diagnostics.
- **Market context:** live quotes, price history, RSI, MACD, moving averages, returns, volatility, analyst estimates, and the US 10-year risk-free rate.
- **Research synthesis:** company grades, financial-health checks, investor-style scorecards, QG-Pro factors, news sentiment, and engagement-weighted retail discussion.
- **Terminal workflow:** editable watchlists, keyboard navigation, dark/light themes, and an English/Chinese interface.
- **Local persistence:** financial records, source provenance, watchlists, and analysis data are stored in SQLite under `data/`.

## Data sources

| Source | Role | API key |
|---|---|---:|
| yfinance / Yahoo Finance | Statements, quotes, price history, news | No |
| SEC EDGAR | Official US-company filings and XBRL facts | No |
| Nasdaq | Statements, company data, analyst context | No |
| Stooq | Price-history fallback | No |
| Reddit | Retail-investor discussion and engagement | No |
| StockTwits | Connectivity indicator retained by the source monitor | No |

Coverage varies by ticker, market, source availability, and network conditions. SEC data is primarily relevant to US-listed issuers.

## Quick start

### Requirements

- Python 3.10 or newer recommended
- Git
- Internet access for live market and financial data

### Windows

```powershell
git clone https://github.com/Seanyim/Stock-Ward.git
cd Stock-Ward
.\run.bat
```

`run.bat` creates `.venv`, installs dependencies when needed, and launches Stock-Ward. The app normally opens in a native desktop window; if a compatible webview is unavailable, it opens in your default browser.

### macOS or Linux

```bash
git clone https://github.com/Seanyim/Stock-Ward.git
cd Stock-Ward
python3 run.py
```

`run.py` creates a local virtual environment on first launch and installs the packages in `requirements.txt`.

### Manual launch

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

The local server listens at `http://127.0.0.1:8377`. Set a different port before launch with the `STOCKWARD_PORT` environment variable. Set `STOCKWARD_BROWSER=1` to force browser mode.

## Using the terminal

1. Enter a ticker in the command bar and press **Enter** or **GO**.
2. Select **REFRESH** to fetch statements, prices, analyst data, news, and social discussion, then run cross-source reconciliation.
3. Move through the six workspaces:
   - **F1 Overview** — quote, summary, grade, quality dimensions, and key trends.
   - **F2 Fundamentals** — annual or quarterly statements and financial narrative.
   - **F3 Valuation** — composite valuation, DCF, P/E, EV/EBITDA, growth, profitability, and scenario analysis.
   - **F4 Masters** — investor-style scoring frameworks and QG-Pro analysis.
   - **F5 News** — headlines, sentiment, forward signals, and retail discussion.
   - **F6 Data Quality** — provider status, provenance, agreement, conflicts, and integrity checks.
4. Use the watchlist rail to create groups, add or remove tickers, rename groups, and move companies between them.

Press `/` to focus the command bar. Use the controls in the upper-right corner to switch language, theme, and inspect live source connectivity.

## How verification works

For every `(year, period, metric)` cell, Stock-Ward compares all available provider values:

- Values within the metric tolerance are marked **verified**.
- Larger differences are marked **conflict** and remain visible in Data Quality.
- A value reported by only one provider is marked **single source**.
- When a consensus value must be selected, source priority favors SEC EDGAR, then Nasdaq, then yfinance.

Financial values are normalized to billions internally. The database keeps up to 12 years of fetched records, including fiscal-year and single-quarter rows when available.

## Project structure

```text
Stock-Ward/
├── run.py                 # Cross-platform launcher
├── run.bat                # Windows launcher
├── server.py              # FastAPI application and API routes
├── web/                   # Terminal-style single-page interface
├── engine/                # Ingestion, providers, valuation, news, grading
├── modules/               # Financial calculations and legacy analysis modules
├── data/                  # SQLite databases and local configuration
├── tests/                 # Automated checks
├── smoke_test.py          # Live end-to-end health check
└── build.bat              # Windows packaging script
```

## Testing

Run the local automated tests:

```bash
python -m pip install pytest
python -m pytest tests
```

Run the live smoke test, which imports the application, checks source connectivity, fetches MSFT data, and exercises core valuation models:

```bash
python smoke_test.py
```

The smoke test writes fetched data to the local database and requires internet access.

## Build a Windows application

```powershell
.\build.bat
```

The build script installs PyInstaller and creates `dist\Stock-Ward\Stock-Ward.exe`. Distribute the entire `dist\Stock-Ward\` folder, not only the executable. Runtime databases are kept beside the packaged application.

## Privacy and data notes

- Research data remains in local SQLite files unless you explicitly copy or publish them.
- Live refreshes send ticker requests to the external sources listed above.
- `data/api_keys.json` is ignored by Git. Current core providers do not require paid API keys; an optional `SEC_USER_AGENT` can identify your SEC requests.
- Back up the databases in `data/` before migrations or large refreshes if the research history matters to you.

## License

Released under the [MIT License](LICENSE).

# PriceEstimated 📈 

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/license/apache-2-0)
[![Update Log](https://img.shields.io/badge/Updates-View%20Log-orange)](./README/updates.md)

[English] | [简体中文](./README/README_ZH.md) |

**A High-Performance Quantitative Valuation Station**

PriceEstimated is a professional-grade financial analysis tool built with Python. It automates the process of fetching market data, normalizing financial statements, and applying rigorous valuation models (PE Bands & DCF) to identify investment opportunities.

---

## 🎯 Key Features

* **🧩 Cumulative to Single Quarter (SQ)**: Sophisticated logic to transform YTD/Cumulative financial data into discrete single-quarter metrics for accurate trend analysis.
* **📊 Dual Valuation Models**:
    * **PE Band Analysis**: Statistical valuation using historical PE percentiles and Forward PE projections.
    * **DCF Model**: Intrinsic value estimation powered by automated WACC (Weighted Average Cost of Capital) calculations.
* **⚡ Smart Data Entry**: Automated backfilling of market caps and closing prices for historical report dates via `yfinance`.
* **📈 Interactive Visuals**: Dynamic PE Bands and financial trend charts built with Plotly.
* **🗄️ Local Data Vault**: High-performance SQLite backend for storing normalized financial records.

## 🛠️ Tech Stack

* **UI Framework**: [Streamlit](https://streamlit.io/)
* **Data Engine**: [Pandas](https://pandas.pydata.org/), [SQLite](https://www.sqlite.org/)
* **Finance API**: [yfinance](https://github.com/ranarousset/yfinance)
* **Visualization**: [Plotly](https://plotly.com/python/)

## 📊 Quantitative Logic

The core valuation leverages the Intrinsic Value ($V$) formula:

$$V = \sum_{t=1}^{n} \frac{CF_t}{(1 + r)^t} + \frac{TV}{(1 + r)^n}$$

Where $CF_t$ is Free Cash Flow, $r$ is the calculated WACC, and $TV$ is the Terminal Value.

## 🚀 Quick Start

1. **Clone & Install**:
   ```bash
   git clone [https://github.com/Seanyim/PriceEstimated.git](https://github.com/Seanyim/PriceEstimated.git)
   cd PriceEstimated
   pip install -r requirements.txt
   ```

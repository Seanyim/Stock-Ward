# PriceEstimated 📈

[English] | [简体中文](./README/README_ZH.md) | [日本語](./README/README_JA.md)

Integration of Strong Stock Analysis Models for quantitative price estimation and financial data processing.

---

## Introduction
PriceEstimated is a Python-based quantitative analysis framework designed to integrate multiple stock valuation models. It streamlines the pipeline from raw financial data acquisition to final price estimation, ensuring high precision through modular design and rigorous calculation.

## Features
* **Multi-Model Integration**: Combines various valuation methods (DCF, Relative Valuation, etc.) into a unified interface.
* **Data Management**: Automated handling of `financial_data.json` and local CSV datasets via `data_manager.py`.
* **Highly Configurable**: Hyperparameters and model weights are easily managed through `config.md`.
* **Automated Workflows**: Built-in GitHub Actions for continuous integration and unit testing.

## Installation
1.  **Clone the repository**:
    ```bash
    git clone [https://github.com/Seanyim/PriceEstimated.git](https://github.com/Seanyim/PriceEstimated.git)
    cd PriceEstimated
    ```
2.  **Set up the environment**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage
To execute the primary analysis and generate price estimates:
```bash
python main.py
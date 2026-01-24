# PriceEstimated 📈

[English](./README.md) | [简体中文] | [日本語](./README/README_JA.md)

集成强力股票分析模型，实现精准的价格估算与财务数据处理。

---

## 项目简介
PriceEstimated 是一个基于 Python 的量化分析框架，旨在集成多种股票估值模型。它简化了从原始财务数据获取到最终价格预测的流程，通过模块化设计和严谨的计算确保高精度。

## 核心功能
* **多模型集成**: 将多种估值方法（如 DCF、相对估值法等）整合到统一界面中。
* **数据管理**: 通过 `data_manager.py` 自动处理 `financial_data.json` 和本地 CSV 数据集。
* **高可配置性**: 通过 `config.md` 轻松管理超参数和模型权重。
* **自动化工作流**: 内置 GitHub Actions 用于持续集成和单元测试。

## 安装指南
1.  **克隆仓库**:
    ```bash
    git clone [https://github.com/Seanyim/PriceEstimated.git](https://github.com/Seanyim/PriceEstimated.git)
    cd PriceEstimated
    ```
2.  **配置环境**:
    ```bash
    pip install -r requirements.txt
    ```

## 使用说明
运行主分析引擎并生成价格预测：
```bash
python main.py
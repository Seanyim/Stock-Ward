# Stock-Ward

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](../LICENSE)

[English](../README.md) | [简体中文](README_ZH.md)

Stock-Ward 是一款本地运行的双语股票研究终端，将多源财务数据、估值模型、技术指标、企业质量评分、新闻与散户讨论整合到统一的桌面式界面中。

程序在本机运行：FastAPI 后端负责计算与数据服务，SQLite 保存研究数据，前端则通过浏览器或原生 `pywebview` 窗口呈现紧凑的终端体验。

![Stock-Ward 仪表盘](../assets/images/dashboard_placeholder.png)

> Stock-Ward 仅用于研究，不构成投资建议。做出投资决策前，请独立核验数据来源与模型假设。

## 核心能力

- **无需密钥的财务数据：** 从 yfinance、SEC EDGAR 与 Nasdaq 获取年度及季度财务报表，无需付费 API Key。
- **多源交叉验证：** 按报告期和指标逐项比对数据，保留来源记录、标记冲突，并检查四个季度合计与财年数据的一致性。
- **完整估值工具箱：** 综合公允价值、正向/反向 DCF、WACC 敏感性分析、PE Band、PEG、EV/EBITDA、蒙特卡洛、盈利能力与成长性分析。
- **市场信息：** 实时报价、历史价格、RSI、MACD、均线、收益率、波动率、分析师预期与美国十年期无风险利率。
- **研究结论整合：** 企业综合评级、财务健康检查、投资大师风格评分、QG-Pro 因子、新闻情绪与按互动热度加权的散户讨论。
- **终端式工作流：** 可编辑自选股、键盘导航、深浅主题，以及中英文界面切换。
- **本地数据持久化：** 财务数据、来源追踪、自选股和分析结果均保存在 `data/` 目录下的 SQLite 数据库中。

## 数据来源

| 数据源 | 用途 | 需要 API Key |
|---|---|---:|
| yfinance / Yahoo Finance | 财报、报价、历史价格、新闻 | 否 |
| SEC EDGAR | 美国上市公司的官方申报与 XBRL 数据 | 否 |
| Nasdaq | 财报、公司信息、分析师数据 | 否 |
| Stooq | 历史价格备用来源 | 否 |
| Reddit | 散户讨论及互动热度 | 否 |
| StockTwits | 数据源监控中保留的连通性指标 | 否 |

实际覆盖范围取决于股票代码、所属市场、数据源可用性与网络状况。SEC 数据主要适用于美国上市公司。

## 快速开始

### 环境要求

- 建议使用 Python 3.10 或更高版本
- Git
- 用于获取市场与财务数据的网络连接

### Windows

```powershell
git clone https://github.com/Seanyim/Stock-Ward.git
cd Stock-Ward
.\run.bat
```

`run.bat` 会自动创建 `.venv`、按需安装依赖并启动 Stock-Ward。程序通常以原生桌面窗口打开；如果系统没有兼容的 WebView，则会自动使用默认浏览器。

### macOS 或 Linux

```bash
git clone https://github.com/Seanyim/Stock-Ward.git
cd Stock-Ward
python3 run.py
```

首次运行时，`run.py` 会创建本地虚拟环境并安装 `requirements.txt` 中的依赖。

### 手动启动

```bash
python -m venv .venv
# Windows：.venv\Scripts\activate
# macOS/Linux：source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

本地服务默认监听 `http://127.0.0.1:8377`。启动前可通过 `STOCKWARD_PORT` 环境变量修改端口；设置 `STOCKWARD_BROWSER=1` 可强制使用浏览器模式。

## 使用终端

1. 在顶部命令栏输入股票代码，按 **Enter** 或点击 **GO/查询**。
2. 点击 **REFRESH/刷新**，获取财报、价格、分析师数据、新闻与社交讨论，并执行多源校验。
3. 在六个工作区之间切换：
   - **F1 概览** — 报价、摘要、评级、质量维度与核心趋势。
   - **F2 基本面** — 年度/季度财务报表与财务叙述。
   - **F3 估值** — 综合估值、DCF、PE、EV/EBITDA、成长、盈利能力与情景分析。
   - **F4 大师评分** — 投资大师风格框架与 QG-Pro 分析。
   - **F5 新闻** — 新闻标题、情绪、前瞻信号与散户讨论。
   - **F6 数据质量** — 数据源状态、来源追踪、一致性、冲突与完整性检查。
4. 使用左侧自选股栏创建分组、添加或删除股票、重命名分组，以及在分组间移动公司。

按 `/` 可快速聚焦命令栏。右上角按钮可切换语言、主题，并查看各数据源的实时连接状态。

## 交叉验证机制

Stock-Ward 会对每个 `(年份, 报告期, 财务指标)` 单元格比较所有可用来源：

- 差异处于对应指标容差内时标记为 **verified（已验证）**。
- 差异较大时标记为 **conflict（冲突）**，并在“数据质量”中保留明细。
- 只有一个来源提供数据时标记为 **single source（单一来源）**。
- 需要选取最终值时，来源优先级依次为 SEC EDGAR、Nasdaq、yfinance。

财务数值在内部统一换算为十亿单位。数据库最多保留约 12 年的抓取记录，并在数据源支持时同时保存财年与单季度数据。

## 项目结构

```text
Stock-Ward/
├── run.py                 # 跨平台启动器
├── run.bat                # Windows 启动器
├── server.py              # FastAPI 应用与 API 路由
├── web/                   # 终端式单页前端
├── engine/                # 数据抓取、数据源、估值、新闻与评分引擎
├── modules/               # 财务计算与旧版分析模块
├── data/                  # SQLite 数据库及本地配置
├── tests/                 # 自动化测试
├── smoke_test.py          # 在线端到端健康检查
└── build.bat              # Windows 打包脚本
```

## 测试

运行本地自动化测试：

```bash
python -m pip install pytest
python -m pytest tests
```

运行在线冒烟测试。该测试会导入应用、检查数据源连接、抓取 MSFT 数据并执行核心估值模型：

```bash
python smoke_test.py
```

冒烟测试需要网络连接，并会把抓取的数据写入本地数据库。

## 打包 Windows 应用

```powershell
.\build.bat
```

脚本会安装 PyInstaller，并生成 `dist\Stock-Ward\Stock-Ward.exe`。分发时请复制整个 `dist\Stock-Ward\` 文件夹，而不是只复制可执行文件。运行时数据库会保存在打包程序旁边。

## 隐私与数据说明

- 研究数据保存在本地 SQLite 文件中，除非您主动复制或发布。
- 在线刷新会向上文列出的外部数据源发送股票代码请求。
- `data/api_keys.json` 已被 Git 忽略。当前核心数据源无需付费密钥；您可以通过可选的 `SEC_USER_AGENT` 标识自己的 SEC 请求。
- 如果研究历史很重要，数据库迁移或大规模刷新前请先备份 `data/` 目录中的数据库。

## 开源许可证

本项目采用 [MIT License](../LICENSE) 开源。

# AKShare 文档 MCP 服务

## 概述

AKShare 文档 MCP 服务为 AI Agent 提供对 AKShare 开源金融数据接口库文档的检索和查询能力。通过该服务，Agent 可以：

- 搜索 AKShare 提供的 1000+ 个金融数据接口
- 获取接口的完整参数说明和调用示例
- 按类目浏览数据字典（股票、期货、债券、基金等 28 个类目）
- 在线搜索 AKShare 官方文档

## 架构

```
QSExt/DocPortal/doc_portal/akshare/   ← 核心模块
├── __init__.py
├── models.py                  ← 数据模型（InterfaceDetail, ParamInfo 等）
├── fetcher.py                 ← Sphinx 文档抓取器
└── scraper.py                 ← 索引构建（优先 akshare API，回退 Sphinx）


mcp/akshare_doc.py                            ← MCP 服务入口（5 个工具）

QSExt/DocPortal/scripts/scrape_akshare_doc.py  ← 预抓取脚本
QSExt/DocPortal/config.py                       ← 缓存目录配置
```

## 数据来源

按优先级自动选择：

1. **akshare 内置离线检索 API**（推荐）：1.18.96 版本的 `ak.search()`、`ak.interface_info()`、`ak.list_categories()` 提供完全离线的结构化接口元数据（注意：早期 1.18.x 版本尚无这三个 API）
2. **Sphinx 文档页面解析**：未安装 akshare 时的回退方案，解析在线 HTML 文档

## MCP 工具

| 工具名 | 功能 | 典型用法 |
|--------|------|----------|
| `search_interfaces` | 关键词搜索接口 | "搜索可转债相关接口" |
| `get_interface_info` | 获取接口详情 | "查看 stock_zh_a_hist 的参数" |
| `browse_categories` | 浏览类目目录 | "AKShare 有哪些数据类别" |
| `get_category_page` | 获取类目文档 | "查看股票数据有哪些接口" |
| `search_online` | Sphinx 在线搜索 | 本地搜索无结果时的兜底 |

## 快速开始

### 1. 安装/升级 akshare（推荐）

```bash
pip install --upgrade akshare
```

### 2. 构建本地索引

```bash
python -m QSExt.DocPortal.scripts.scrape_akshare_doc
# 或指定缓存目录
python -m QSExt.DocPortal.scripts.scrape_akshare_doc --cache-dir D:/Data/AKShareDoc
```

### 3. 启动 MCP 服务

```bash
# stdio 模式
python mcp/akshare_doc.py

# 指定缓存目录
python mcp/akshare_doc.py --cache-dir D:/Data/AKShareDoc

# 启动前重建全部缓存（清除旧索引与接口/页面缓存并重新抓取）
python mcp/akshare_doc.py --rebuild-cache

# 环境变量方式
set QS_AKSHARE_DOC_CACHE=D:/Data/AKShareDoc
python mcp/akshare_doc.py
```

## 缓存说明

本服务不会自动更新缓存：`tree_index.json` 在启动时加载一次，`interfaces/<接口名>.json`
与 `pages/<页路径>.json` 一旦写入便永久复用。AKShare 文档有更新时，需重启服务并加上
`--rebuild-cache` 才会刷新。

`--rebuild-cache` 会清除 `interfaces/`、`pages/` 与 `tree_index.json` 后重新抓取。
重建优先走 akshare 内置离线 API（完全离线，耗时约数秒）；未安装 akshare 时回退到抓取
Sphinx 在线文档（需要网络，耗时较长）。重建失败不会阻止服务启动，会自动回退到现有缓存。

### 4. 在 Claude Code 中配置

在 `.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "akshare_doc": {
      "command": "D:/PythonEnv/QS312/Scripts/python.exe",
      "args": ["mcp/akshare_doc.py", "--cache-dir", "D:/Data/AKShareDoc"]
    }
  }
}
```

## 数据类目

AKShare 数据字典覆盖以下 28 个类目：

| 类目 | 接口数 | 说明 |
|------|--------|------|
| stock | 388 | 股票数据（行情、财务、资金等） |
| macro | 215 | 宏观数据（GDP、CPI、PMI 等） |
| fund | 90 | 公募/私募基金数据 |
| index | 94 | 指数数据 |
| futures | 83 | 期货数据 |
| option | 46 | 期权数据 |
| bond | 44 | 债券数据（含可转债） |
| others | 34 | 另类数据 |
| spot | 15 | 现货数据 |
| interest_rate | 14 | 利率数据 |
| fx | 11 | 外汇数据 |
| energy | 8 | 能源数据 |
| qhkc | 8 | 奇货可查期货数据 |
| article | 7 | 论文数据 |
| stock_feature | 6 | 股票特色数据 |
| currency | 5 | 货币数据 |
| stock_fundamental | 4 | 股票基本面数据 |
| cal | 3 | 日历数据 |
| dc | 3 | 加密货币数据 |
| qdii | 3 | QDII 数据 |
| event | 2 | 迁徙数据 |
| nlp | 2 | 自然语言处理 |
| futures_derivative | 1 | 期货衍生品 |
| hf | 1 | 高频数据 |
| reits | 1 | REITs 数据 |
| tool | 1 | 工具箱 |
| bank | 1 | 银行数据 |

## 与 tinysoft_doc MCP 的对比

| 维度 | tinysoft_doc | akshare_doc |
|------|-------------|-------------|
| 文档站 | 天软 TSDN（自建系统） | Sphinx（ReadTheDocs） |
| 数据来源 | HTML 解析 | akshare API + Sphinx 回退 |
| 接口数量 | 数千个函数 | 1090 个接口 |
| 搜索方式 | 本地索引 + 在线搜索 | 本地索引 + ak.search() + Sphinx |
| 缓存策略 | 按文档 ID 缓存 | 按页面 + 按接口名缓存 |
| 缓存重建 | `--rebuild-cache` | `--rebuild-cache` |

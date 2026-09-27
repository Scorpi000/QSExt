# 天软(Tinysoft)文档 MCP 服务

## 概述

`tinysoft_doc` MCP 服务为 AI Agent 提供天软 TSDN 文档站的检索和查询能力。Agent 可通过该服务搜索 TSL 语言函数、查阅函数定义和用法、浏览文档分类目录。

## 项目结构

```
QSExt/DocPortal/
├── doc_portal/tinysoft/          # 核心模块
│   ├── __init__.py
│   ├── models.py                 # 数据模型（DocNode, DocContent, SearchResultItem）
│   ├── fetcher.py                # 文档抓取器（HTTP + GB2312解码 + HTML解析 + 缓存）
│   └── scraper.py                # 目录树预抓取模块

mcp/tinysoft_doc.py                            # MCP 服务入口（FastMCP, stdio/http）

QSExt/DocPortal/scripts/scrape_tinysoft_doc.py  # 独立爬虫脚本入口
QSExt/DocPortal/config.py                       # 缓存目录配置
docs/DocPortal/tinysoft_doc.md                  # 本文档

D:\Data\TinySoftDoc\              # 可配置的外部缓存目录
├── tree_index.json               # 目录树索引（预抓取生成）
└── docs/                         # 文档内容缓存（按需自动缓存）
```

## 支持的文档板块

| 板块 | 说明 |
|------|------|
| **TSL 语言基础** | TSL 语言语法、关键字、数据类型、控制流等基础文档 |
| **.NET 函数大全** | 完整的 TSL 函数参考，涵盖数千个函数（含定义/参数/示例） |
| **知识库** | 矩阵专题、代码优化技巧、天软数据字典等实用知识 |

## MCP 工具列表

| 工具名 | 功能 | 典型使用场景 |
|--------|------|--------------|
| `search_docs` | 本地索引搜索 | 快速查找函数名、主题或概念 |
| `get_doc_content` | 获取文档详情 | 查看函数定义、参数说明和代码示例 |
| `browse_categories` | 浏览目录结构 | 了解文档整体组织结构 |
| `get_function_list` | 列出函数 | 浏览特定分类下的函数列表 |
| `search_online` | 在线全文搜索 | 本地搜索无结果时使用 |

## 安装与配置

### 1. 确保依赖已安装

```bash
pip install beautifulsoup4 requests fastmcp pydantic
```

### 2. 运行预抓取脚本

首次使用前，需要先抓取文档目录树索引：

```bash
# 使用默认缓存目录 (D:\Data\TinySoftDoc)
python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc

# 指定自定义缓存目录
python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc --cache-dir E:/Cache/TinySoftDoc

# 只抓取特定板块
python -m QSExt.DocPortal.scripts.scrape_tinysoft_doc --categories tsl dotnet
```

### 3. 配置 MCP 客户端

#### Claude Code / Claude Desktop

在 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "tinysoft_doc": {
      "command": "D:\\PythonEnv\\QS312\\Scripts\\python.exe",
      "args": ["mcp/tinysoft_doc.py", "--cache-dir", "D:\\Data\\TinySoftDoc"],
      "env": {"PYTHONPATH": "D:\\Project\\QuantStudio;D:\\Project\\QSExt"}
    }
  }
}
```

#### 通过环境变量配置缓存目录

```bash
set QS_TINYSOFT_DOC_CACHE=D:\Data\TinySoftDoc
```

## 缓存说明

本服务不会自动更新缓存：`tree_index.json` 在启动时加载一次，`docs/<doc_id>.json`
一旦写入便永久复用。天软文档有更新时，需重启服务并加上 `--rebuild-cache` 才会刷新：

```bash
# 启动前重建全部缓存（清除旧索引与文档内容缓存并重新抓取）
python mcp/tinysoft_doc.py --rebuild-cache
```

重建需要网络访问天软文档站，耗时较长，期间服务不会响应。重建失败不会阻止服务启动，
会自动回退到现有缓存。

## Agent 使用示例

### 查找 DataType 函数的用法

```
Agent 调用: search_docs(keyword="DataType", category="dotnet")
→ 找到匹配文档 ID: 19939

Agent 调用: get_doc_content(doc_id=19939, format="markdown")
→ 返回 DataType 函数的完整说明（定义、参数、示例代码）
```

### 浏览 TSL 语言基础知识结构

```
Agent 调用: browse_categories(category="tsl", depth=2)
→ 返回 TSL 语言基础的目录树
```

### 搜索矩阵相关函数

```
Agent 调用: get_function_list(keyword="Matrix")
→ 返回所有包含 "Matrix" 的函数列表
```

## 架构说明

```
MCP Client (Agent)
    │  stdio
    ▼
mcp/tinysoft_doc.py (FastMCP)
    │
    └── DocPortal/doc_portal/tinysoft/
        ├── models.py          数据模型
        ├── fetcher.py         文档抓取 + 本地缓存
        │   ├── 本地索引 (tree_index.json)  ← 快速标题/路径搜索
        │   ├── 本地缓存 (docs/*.json)      ← 已抓取的文档内容
        │   └── 天软 TSDN 网站              ← 实时抓取（GB2312 解码）
        └── scraper.py         预抓取脚本
```

**混合模式策略：**
1. 目录树索引预抓取，启动时加载到内存 → 快速搜索
2. 文档内容按需抓取，抓取后自动缓存到本地 → 逐步积累
3. 支持在线搜索作为补充 → 覆盖全文搜索需求

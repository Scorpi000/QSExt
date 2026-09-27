# TinySoft Doc MCP 优化方案

## 原则

- **不搞大规模预抓取**：不批量爬取 14,000+ 文档页面
- **运行时按需获取**：用户查询时才请求文档内容，获取后缓存复用
- **充分挖掘已有数据**：`tree_index.json` 中的 name、path 已包含丰富语义，优先利用
- **小成本静态配置**：用同义词表等轻量配置弥补索引不足

## 问题与方案

### 问题 1：search_docs 召回率低

**现状**：纯子串匹配 `name` 字段，搜索"基金基本信息"返回空，搜索"DataType"不会命中"数据类型"。

**原因**：`flat_index` 只有 `{id, name, category, path, is_folder}` 五个字段，无摘要无关键词；搜索逻辑是 `keyword.lower() in name.lower()`。

**方案：三层召回 + 评分排序（零网络请求）**

```
search_docs("基金类型")
    │
    ├─ 第 1 层：同义词扩展
    │   "基金类型" → ["基金", "Fund", "类型", "Type", "Style"]
    │
    ├─ 第 2 层：多字段匹配（name + path 组件）
    │   name: "FundStyleName1"      ← 命中 "Style"
    │   path: "金融函数/基金/..."    ← 命中 "基金"
    │
    └─ 第 3 层：评分排序
        name 精确匹配  > name 包含  > path 包含  > 摘要包含
```

具体改动：

**a) 新增同义词配置文件** `knowledge/tinysoft/synonyms.json`

```json
{
  "基金": ["Fund", "基金", "MutualFund"],
  "净值": ["NAV", "NetAsset", "净值", "NAW"],
  "基金管理人": ["管理人", "FundCompany", "基金管理公司", "Org"],
  "基金经理": ["FundManager", "基金经理", "Manager"],
  "数据类型": ["DataType", "数据类型", "Type"],
  "收益率": ["Return", "收益率", "Yield"],
  "分红": ["Dividend", "分红", "送配"],
  "投资组合": ["Portfolio", "投资组合", "持仓"],
  "指数": ["Index", "指数"],
  "股票": ["Stock", "股票", "A股"],
  "行情": ["Quote", "行情", "HQ", "Market"],
  "财务": ["Financial", "财务", "Finance"],
  "板块": ["Sector", "板块", "BK", "行业"]
}
```

维护方式：手动补充，从实际使用中逐步积累。初始版本覆盖金融领域常见概念即可。

**b) 改造 `search_docs` 逻辑**

```python
def search_docs(keyword, category="all", max_results=10):
    # 1) 同义词扩展
    expanded = expand_keyword(keyword, synonyms)  # ["基金类型", "Fund", "Style", ...]

    # 2) 多字段匹配 + 评分
    scored = []
    for entry in flat_index:
        if category != "all" and entry["category"] != category:
            continue
        score = score_entry(entry, expanded)
        if score > 0:
            scored.append((score, entry))

    # 3) 排序后截取
    scored.sort(key=lambda x: -x[0])
    return scored[:max_results]
```

评分规则：

| 匹配位置 | 得分 | 说明 |
|----------|------|------|
| name 精确匹配（忽略大小写） | 10 | "FundName" 搜 "FundName" |
| name 包含关键词 | 5 | "FundStyleName1" 搜 "Style" |
| path 末级（函数名）包含 | 4 | path 末段即函数名 |
| path 中间层级包含 | 3 | "金融函数/基金/..." 搜 "基金" |
| 同义词匹配 name | 2 | "基金" ↔ "Fund" |

---

### 问题 2：get_function_list 缺少描述信息

**现状**：返回 `{id, name, path}`，AI 无法判断函数用途，必须逐个调 `get_doc_content`。

**方案：路径摘要（免费）+ 按需加载签名（懒加载）**

**a) 路径摘要（零成本，改 `_collect_functions`）**

从 `path` 中提取有意义的中间层级作为分类上下文：

```python
def _path_summary(path: str) -> str:
    """'金融函数/基金/基本信息/FundStyleName1' → '基金/基本信息'"""
    parts = path.split("/")
    # 去掉顶层板块名和末级函数名，保留中间分类
    if len(parts) >= 3:
        return "/".join(parts[1:-1])
    return ""
```

返回结构变为：

```json
{
  "id": 33401,
  "name": "FundStyleName1",
  "path": "金融函数/基金/基本信息/FundStyleName1",
  "summary": "基金/基本信息"
}
```

AI 看到 `summary: "基金/基本信息"` 就能判断该函数与当前需求是否相关。

**b) 按需签名加载（懒加载 + 缓存）**

新增可选参数 `load_signatures=False`，设为 True 时对当前页的函数懒加载签名行：

```python
def get_function_list(sub_category, keyword="", offset=0, limit=30,
                      load_signatures=False):
    functions = _collect_filtered(sub_category, keyword)
    page = functions[offset:offset + limit]

    results = []
    for f in page:
        item = {
            "id": f["id"],
            "name": f["name"],
            "path": f["path"],
            "summary": _path_summary(f["path"])
        }
        if load_signatures:
            # 从缓存读取，未缓存则按需抓取并缓存
            doc = fetch_doc_if_needed(f["id"])  # 复用 fetcher 缓存机制
            item["signature"] = extract_definition_line(doc)
        results.append(item)

    return results
```

`load_signatures=True` 时，最多抓取当前页 30 个函数的文档（首次），后续命中缓存。相比全量预抓取 14,000 个，这是可控的按需开销。

---

### 问题 3：search_docs + search_online 需要分两次调用

**现状**：AI 先调 `search_docs`，没结果再调 `search_online`，多一轮交互。

**方案：改造 `search_docs` 增加自动 fallback**

```python
def search_docs(keyword, category="all", max_results=10,
                enable_online=True):
    """本地搜索，本地结果不足时自动 fallback 到在线搜索。

    Args:
        enable_online: 本地结果不足 3 条时自动补充在线结果（默认开启）
    """
    # 1) 本地搜索（含同义词扩展 + 评分）
    local_results = _local_search(keyword, category, max_results)

    # 2) 自动 fallback
    if enable_online and len(local_results) < 3:
        online_results = _online_search(keyword, max_results - len(local_results))
        # 标记来源，去重合并
        for r in online_results:
            r["source"] = "online"
        local_results.extend(online_results)

    return local_results
```

---

### 问题 4：browse_categories 信息密度低

**现状**：只显示目录树结构，每个节点只有 name + id + 📁/📄 标记。

**方案：为叶节点附加签名行（仅 dotnet 板块，从缓存中读取）**

不新增网络请求。对已缓存的文档（`cache_dir/docs/*.json`），在渲染时附带 definition 行：

```
├── 📁 基本信息 (ID: 33393)
│   ├── 📄 FundMasterCode  — FundMasterCode():String
│   ├── 📄 FundName        — FundName():String
│   ├── 📄 FundStyleName1  — FundStyleName1():String
│   └── ...
```

未缓存的节点保持原样。随着使用积累，缓存会逐步丰富。

---

## 改动汇总

| 改动 | 涉及文件 | 是否需要网络请求 | 工作量 |
|------|----------|-----------------|--------|
| 同义词配置 | 新增 `synonyms.json` | 否 | 小（~200 条配置） |
| search_docs 评分排序 | `tinysoft_doc.py` | 否 | 小（~80 行） |
| search_docs 同义词扩展 | `tinysoft_doc.py` | 否 | 小（~30 行） |
| search_docs 自动 fallback | `tinysoft_doc.py` | 默认开启，本地不足时自动请求 | 小（~20 行） |
| get_function_list 路径摘要 | `tinysoft_doc.py` | 否 | 小（~10 行） |
| get_function_list 签名懒加载 | `tinysoft_doc.py` + `fetcher.py` | 按需，缓存后不再请求 | 中（~40 行） |
| browse_categories 签名展示 | `tinysoft_doc.py` | 否（读缓存） | 小（~15 行） |
| get_function_list 分页 | `tinysoft_doc.py` | 否 | 小（~5 行） |

**总网络请求增量：search_docs 本地不足时自动请求在线搜索（已有机制，无额外开销）+ 签名懒加载最多 30 次（首次查询时，缓存后不再请求）**

## 实施顺序

1. **同义词表 + search_docs 评分排序 + 自动 fallback**：统一改造 search_docs，立竿见影
2. **get_function_list 路径摘要 + 分页**：减少不必要的 get_doc_content 调用
3. **get_function_list 签名懒加载**：进一步减少交互轮次
4. **browse_categories 签名展示**：锦上添花

---
name: generate-factor-def-code
description: |
  生成符合 QSExt DefModule 框架规范的因子定义 Python 脚本。根据用户需求或假设文档，
  查阅因子 API 参考，验证数据可用性，产出可执行的因子定义脚本。
  当用户提到以下场景时使用此 skill：开发因子、写一个因子、因子定义、因子代码生成、
  创建因子脚本、新增因子、因子实现、factor definition、defFactor、defNode。
---

# 生成因子定义脚本

你是 QSExt DefModule 框架的因子开发助手。你的任务是根据需求生成符合 DefModule 框架规范的可执行因子定义脚本。

## 核心约束

- 产出符合 DefModule 框架规范的因子定义脚本
- 所有代码必须符合 `__FACTOR_META__` + `defNode(fdi) -> List[Factor]` 规范（兼容 `defFactor`）
- 数据表和字段必须来自真实的数据源（通过 jy_base_doc 工具验证），**禁止捏造**
- 遵循 CLAUDE.md 中的行为准则：简洁优先、精准改动、编码前先思考

## 脚本命名规范

脚本文件名必须与 `__FACTOR_META__` 中的 `TargetTable` 保持一致：

- 格式：`{TargetTable}.py`
- 示例：`TargetTable = "stock_cn_factor_pe_ttm"` → 文件名 `stock_cn_factor_pe_ttm.py`

`TargetTable` 命名约定：`{标的类型}_{交易市场}_factor_{因子信息}`
- 标的类型：`stock`（股票）、`mf`（公募基金）、`mf_etf`（ETF）等
- 交易市场：`cn`（中国）、`hk`（香港）、`us`（美国）等

## 可用工具

| 工具集 | 工具 | 用途 |
|--------|------|------|
| **jy_base_doc** | `query_table` | 查询聚源数据表的字段结构和说明 |
| | `search_table_list` | 按关键词搜索相关数据表 |
| | `query_qs_read_data_help` | 获取在 QuantStudio 中读取数据的使用说明 |
| | `query_qs_get_factor_help` | 获取在 QuantStudio 中获取因子对象的说明 |
| **qs-registry** | `search_factors` | 搜索已注册的因子，寻找参考实现 |
| | `get_factor_info` | 获取因子详细信息 |
| | `get_factor_code` | 获取已注册因子的源代码作为参考 |
| **Read / Write / Edit** | — | 读写代码文件 |
| **Bash** | — | 执行 Python 进行语法验证 |

## API 参考

> 完整 API 参考见 `references/factor_def_api.md`，包含以下全部内容：

- **`__FACTOR_META__` 字段详解** — 所有字段的类型、默认值、说明
- **`DefInput` 接口** — `fdi.FDB`、`fdi.Factors`、`fdi.ModelArgs` 等属性
- **`defNode`/`defFactor` 模式** — 标准模式、使用依赖因子、使用 ModelArgs
- **数据源访问** — JYDB 连接、行情/财务数据读取
- **依赖机制** — 解析流程、FactorDeps 两种 entry 格式、参数透传 `$`
- **常用算子** — 数学、条件、时序、截面、重命名
- **自定义算子** — Point/Section/Time/Panel 四种类型及 args 参数规范
- **主板/科创板合并模式** — 双板单位换算 + `where(notnull)` 合并
- **导入速查** — 标准 import 清单

## 常用数据表速查

以下为 A 股常用数据表的参考关键词（需通过 `jy_base_doc` 工具验证后使用）：

| 数据内容 | 参考查询关键词 | 说明 |
|----------|--------------|------|
| 日行情（主板） | `日行情` | 含开盘价、收盘价、成交量等 |
| 日行情（科创板） | `科创板` `日行情` | 科创板独立行情表 |
| 财务数据 | `财务` `资产负债表` `利润表` | 需设置 `CalcType` 参数 |
| 股票状态 | `上市状态` `停牌` `ST` | 上市状态、特别处理等 |
| 行业分类 | `申万` `行业` | 申万行业分类 |
| 估值数据 | `估值` `PE` `PB` | 市盈率、市净率等 |

**注意**：上表仅作提示，**实际使用时必须通过 `jy_base_doc` 工具验证具体表名和字段名**。

## 最佳实践速查

**NaN 处理：**
```python
# ❌ 错误：scipy.stats.rankdata 会对 NaN 排名
return scipy.stats.rankdata(data) / n

# ✅ 正确：只对非 NaN 值排名
mask = ~np.isnan(data)
result = np.full_like(data, np.nan)
result[mask] = scipy.stats.rankdata(data[mask]) / mask.sum()
return result
```

**双板合并：**
```python
FT = JYDB.getTable("主板行情表", args={"LookBack": 0})
main_val = FT.getFactor("字段名")

FT_STAR = JYDB.getTable("科创板行情表", args={"LookBack": 0})
star_val = FT_STAR.getFactor("字段名")

where = fo.Where(dtype="double")
notnull = fo.NotNull()
result = where(main_val, notnull(main_val), star_val)
```

## 测试验证

脚本生成后，按以下步骤验证：

### 1. 语法验证

```bash
PYTHONPATH="<QuantStudio路径>;<QSExt路径>" <Python解释器> -c "import py_compile; py_compile.compile('path/to/script.py', doraise=True); print('Syntax OK')"
```

### 2. dry-run 验证

```bash
python -m QSExt.DefModule.scripts.run_def --settings <settings_path> --dry-run
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `KeyError: '因子名'` | 字段名不匹配 | 用 `FT.FactorNames` 查看实际可用因子名 |
| `ValueError: truth value of array ambiguous` | Point 算子中对数组用了标量判断 | 使用 `np.where` 替代 `if` |
| 数据全为 NaN | 表名或 args 参数错误 | 检查 `CalcType`、`LookBack` 等参数 |

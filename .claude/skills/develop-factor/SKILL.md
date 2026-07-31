---
name: develop-factor
description: |
  因子定义脚本开发。根据用户需求基于 QuantStudio 生成符合 QSExt FactorDef 框架规范的因子定义 Python 脚本。
  当用户提到以下场景时使用此 skill：开发因子、写一个因子、因子定义、因子代码生成、
  创建因子脚本、新增因子、因子实现、factor definition、defFactor。
---

# 因子定义脚本开发

你是 QuantStudio FactorDef 框架的因子开发助手。你的任务是将用户的因子需求转化为符合 FactorDef 框架规范的可执行因子定义脚本。

## 核心约束

- **只产出因子定义脚本**（`.py` 文件），不包含参数搜索、验证流水线等功能
- 所有代码必须符合 FactorDef 框架规范：`__FACTOR_META__` + `defFactor(fdi) -> List[Factor]`
- 数据表和字段必须来自真实的数据源（通过工具验证），**禁止捏造表名或字段名**
- 遵循 CLAUDE.md 中的行为准则：简洁优先、精准改动、编码前先思考

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

## 执行流程

### Step 1: 理解需求

从用户描述中提取以下信息：

- **因子名称**：因子的英文/拼音名称
- **因子含义**：因子衡量什么（用简洁的中文描述）
- **计算逻辑**：具体的计算公式和步骤
- **所用数据**：需要哪些原始数据（表名 + 字段名）
- **所属分类**：因子类别（如动量、反转、波动率、财务质量、流动性等）
- **证券类型**：`A股`、`ETF`、`公募基金`、`期货`、`期权`、`指数` 等
- **输出位置**：用户期望的脚本保存路径（未指定时询问用户）

如果用户需求不明确，主动询问缺失的关键信息（尤其是计算逻辑和所用数据）。

### Step 2: 调研数据与参考

**2a. 验证数据可用性（必须）**

用 `jy_base_doc/query_table` 或 `search_table_list` 验证用户提到的（或你计划使用的）数据表和字段在 JYDB 中真实存在。

- 如果表名不确定，用 `search_table_list` 按关键词搜索
- 确认字段名、字段类型、单位等关键信息
- **绝对不要凭空假设表名或字段名**，哪怕看起来"显然正确"

**2b. 查阅已有因子（推荐）**

用 `qs-registry/search_factors` 搜索功能相近的已有因子，用 `get_factor_code` 获取源代码作为参考：
- 学习相似因子的计算逻辑和数据处理方式
- 了解常用表名和字段名的确切拼写
- 避免重复造轮子——如果已有因子完全覆盖需求，告知用户

### Step 3: 生成因子定义脚本

基于需求和数据调研结果，生成完整的因子定义 Python 脚本。

> 详细的 API 参考（`__FACTOR_META__` 字段、`defFactor` 签名、算子说明、双板合并模式等）见 `references/factor_def_api.md`。

**脚本结构：**

```python
# -*- coding: utf-8 -*-
"""因子名称: {factor_name}
描述: {description}
"""
from typing import List

import numpy as np
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.Factor.FactorOperation import FactorOperatorized
from QSExt.FactorDef.FactorDefContent import FactorDefInput


__FACTOR_META__ = {
    "TargetTable": "stock_cn_factor_{factor_name}",
    "IDType": "A股",
    "Author": "{author}",
    "Description": "{description}",
    "FactorDeps": {},          # 依赖因子声明
    "DBDeps": {"JYDB": "聚源数据库，提供行情和财务数据"},
    "DefScriptPath": __file__,
}


def defFactor(fdi: FactorDefInput) -> List[Factor]:
    JYDB = fdi.FDB["JYDB"]
    Factors = []

    # ... 因子构建逻辑 ...

    return Factors
```

**必须遵循的规则：**

1. `defFactor` 签名为 `defFactor(fdi: FactorDefInput) -> List[Factor]`
2. `__FACTOR_META__` 必须包含 `TargetTable`、`IDType`、`Description`、`DefScriptPath`
3. A 股因子必须同时覆盖主板和科创板，使用 `fo.Where + fo.NotNull` 合并
4. 有依赖因子时通过 `FactorDeps` 声明，由框架自动注入 `fdi.Factors`
5. 直接访问的因子库通过 `DBDeps` 声明，框架校验存在性
6. **自定义算子中 NaN 必须正确处理**：`scipy.stats.rankdata` 等函数不会自动跳过 NaN
7. 因子通过 `rename()` 重命名并设置 `Meta.Description`
8. 输出因子表命名规范：`stock_cn_factor_{name}`（A 股）

### Step 4: 保存脚本

将生成的代码保存到用户指定的位置。如果用户未指定，按以下优先级选择：

1. 询问用户期望的保存路径
2. 默认保存到当前工作目录下，文件名为 `{factor_name}.py`

## 代码编写规范

### 常用数据表速查

以下为 A 股常用数据表的真实表名和字段（需通过 `jy_base_doc/query_table` 确认后使用）：

| 数据内容 | 参考查询关键词 | 说明 |
|----------|--------------|------|
| 日行情（主板） | `日行情` | 含开盘价、收盘价、成交量等 |
| 日行情（科创板） | `科创板` `日行情` | 科创板独立行情表 |
| 财务数据 | `财务` `资产负债表` `利润表` | 财务数据通常需要根据需求设置 `CalcType` 参数为 TTM, 最新或者单季度|
| 股票状态 | `上市状态` `停牌` `ST` | 上市状态、特别处理等 |
| 行业分类 | `申万` `行业` | 申万行业分类 |
| 指数成分 | `指数成分` `沪深300` `中证500` | 指数成分股 |
| 估值数据 | `估值` `PE` `PB` | 市盈率、市净率等 |

**重要**：上表仅作提示，**实际使用时必须通过 `jy_base_doc` 工具验证具体表名和字段名**。

### 最佳实践速查

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

### 输出产物

仅产出 **一个文件**：因子定义 Python 脚本（`{factor_name}.py`）。

包含：
- 模块文档字符串（因子名称、描述）
- `__FACTOR_META__` 完整声明
- 自定义算子定义（如有）
- `defFactor(fdi) -> List[Factor]` 函数实现

## 参考文档

- `references/factor_def_api.md` — FactorDef 框架 API 完整参考（`__FACTOR_META__` 字段详解、`defFactor` 模式、`FactorDefInput` 接口、自定义算子、常用算子、依赖声明等）

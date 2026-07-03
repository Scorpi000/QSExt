# QSRegistry — QSID 跨 Session 一致性问题

> 返回 [总览](QSGraphDB设计.md)

## 问题概述

通过 `storeFactors` 将因子注册到图数据库后，在其他 session 中调用 `reconstructFactor` 重建因子对象，发现部分因子的 QSID 与存储值不一致。经分析，根因分三层。

## 根因分析

### 第 1 层：`_sanitizeForJSON` 中 numpy 类型检查顺序错误（已修复）

**文件**：`_serialization.py` 第 19 行

```python
# 修复前（有问题）
if value is None or isinstance(value, (int, float, str, bool)):
    return value          # np.int64(0) 在此被直接返回，未经显式转换
if isinstance(value, np.integer):
    return int(value)     # 永远不会执行（np.int64 是 int 的子类）
```

`np.int64` 是 Python `int` 的子类，因此 `isinstance(np.int64(0), (int, float, str, bool))` 返回 `True`，导致 numpy 整数类型跳过显式转换。经过 JSON 序列化/反序列化后，`0`（int）可能变为 `0.0`（float），导致 `RawLookBack` 等字段类型变化，QSID 改变。

**修复**（已实施）：将 `np.integer`、`np.floating`、`np.bool_` 的检查移到通用 `isinstance` 之前：

```python
# 修复后
if value is None:
    return value
if isinstance(value, np.integer):
    return int(value)
if isinstance(value, np.floating):
    v = float(value)
    if np.isnan(v): return {"__nan__": True}
    if np.isinf(v): return {"__inf__": True, "sign": 1 if v > 0 else -1}
    return v
if isinstance(value, np.bool_):
    return bool(value)
if isinstance(value, (int, float, str, bool)):
    return value
```

### 第 2 层：`JYDB.getTable` 合并 FTArgs/DefaultArgs 导致 FactorTable QSID 变化（已部分修复）

**文件**：`JYDB.py` 第 980-984 行

```python
Args = self._QSArgs.FTArgs.copy()   # 当前 session 的 FTArgs（如 PreFilterID）
Args.update(DefaultArgs)             # 数据库 DefaultArgs
Args.update(args)                    # 用户传入的 args
Args["Name"] = table_name
```

问题：
- 即使传入完整的存储 args，当前 `FTArgs` 和 `DefaultArgs` 仍被合并，可能引入额外字段
- 不同 FactorDef 模块对同一物理表传入不同的视图参数（如 `FilterCondition`、`LookBack`），导致同一张表（如 `日行情表`）产生多个不同 QSID 的 FactorTable 节点

**现象**：Neo4j 中 53 个 FactorTable 节点仅覆盖 26 个唯一表名，14 张表存在 2~6 个重复节点。例如 `日行情表` 的两个节点差异为：

| 字段 | 节点 1 | 节点 2 |
|------|--------|--------|
| `FilterCondition` | `'{Table}.ClosePrice>0'` | `''` |
| `LookBack` | `inf` | `0` |

**已做修复**：
- `storeFactorTable` 持久化 `QSArgsJSON`（`ft._QSArgs.model_dump()` 的完整快照）
- `_reconstructFactorTableFactor` 改为直接构造表类，绕过 `getTable` 的合并逻辑

### 第 3 层：`SQL_Table.__QS_ArgClass__.__init__` 非幂等（未修复，核心问题）

**文件**：`FactorUtils.py` 第 411-439 行

```python
def __init__(self, /, **data: Any) -> None:
    ...
    # AdditionalCondition 被强制重算，无论 data 中是否已有
    ConditionFields = Owner._FactorInfo[Owner._FactorInfo["FieldType"]=="Condition"].index.tolist()
    AdditionalCondition = {}
    for iCondition in ConditionFields:
        AdditionalCondition[iCondition] = ...
    data["AdditionalCondition"] = AdditionalCondition | data.get("AdditionalCondition", {})
    # ↑ 始终用当前 _FactorInfo 计算值覆盖，不幂等
```

问题：
- `IDField`、`DTField` 仅在 data 中不存在时才计算——**幂等**，传入已有值可直接通过
- `AdditionalCondition` **无论是否已在 data 中都强制重算并合并**。`AdditionalCondition` 由当前 session 的 `_FactorInfo`（来自 `JYDBInfo.hdf5`）计算，如果 hdf5 元数据在不同 session 间有差异，重建后的 `AdditionalCondition` 就不同

**连锁影响链路**：
```
_FactorInfo 变化
  → FactorTable.__QS_ArgClass__.__init__ 重算 AdditionalCondition
    → FactorTable._QSArgs.model_dump() 不同
      → FactorTable.QSID 不同
        → Factor.model_dump().deps 中包含 FactorTable.model_dump()
          → Factor.QSID 不同（约 49% 的因子受影响）
```

## 修改方案

### 方案 A：修复 `__QS_ArgClass__.__init__` 使其幂等（推荐，优先实施）

**文件**：`FactorUtils.py`，`SQL_Table.__QS_ArgClass__.__init__`

```python
# 修改前
data["AdditionalCondition"] = AdditionalCondition | data.get("AdditionalCondition", {})

# 修改后
if "AdditionalCondition" not in data:
    data["AdditionalCondition"] = AdditionalCondition
else:
    # 保留传入值，仅补充 data 中缺失的 ConditionField
    data["AdditionalCondition"] = AdditionalCondition | data["AdditionalCondition"]
```

同时在 `SQL_Table.__init__` 或相关 table 子类的 `__init__` 中确保 `_FactorInfo` 在 `super().__init__()` 之前赋值（目前已满足），保证 `__QS_ArgClass__.__init__` 中能访问 `Owner._FactorInfo`。

**效果**：确保传入完整 args 时，重建的 FactorTable QSID 与存储时一致。

### 方案 B：修复 `_reconstructFactorTableFactor` 中的表类解析

**文件**：`QSGraphDB.py`，`_reconstructFactorTableFactor`

当前修改使用 `eval(f"_{TableClass}(...)")` 绕过 `getTable`，但 `_WideTable` 等类定义在 `JYDB.py` 模块中，`QSGraphDB.py` 的命名空间无法直接访问。需通过模块引用正确获取类：

```python
import sys
jy_module = sys.modules[fdb.__class__.__module__]
TableCls = getattr(jy_module, f"_{TableClass}")
ft = TableCls(fdb=fdb, args=ft_stored_args, 
              table_info=fdb._TableInfo.loc[ft_name],
              factor_info=fdb._FactorInfo.loc[ft_name],
              security_info=fdb._SecurityInfo,
              exchange_info=fdb._ExchangeInfo,
              logger=fdb._QS_Logger)
```

### 方案 C：消除 FactorTable 重复节点

**文件**：`QSGraphDB.py`，`_collectDAGFromTableBatch` / `storeFactorTable`

在存储 FactorTable 时，使用表的**规范形式**（`fdb.getTable(name)` 不带额外视图参数）生成 QSID 和存储节点，确保同一物理表只有一个节点。

需配合方案 A 一起实施（因为改变 FactorTable QSID 会连锁改变所有引用该表的 Factor QSID）。

## 实施顺序

1. **先实施方案 A**（修复 `AdditionalCondition` 幂等性）——核心问题
2. **再实施方案 B**（修复表类名解析）——让绕过 `getTable` 的逻辑正常工作
3. **清除图数据库，重新运行注册脚本**
4. **验证所有因子 QSID 匹配率达到 100%**
5. **视需要实施方案 C**（消除重复节点）

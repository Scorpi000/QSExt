## Context

`QSGraphDB._reconstructFactorTableFactor` 重建因子时，通过 `_FactorDBRegistry` 获取 `FactorDB` 实例。该注册表由调用方通过 `registerFactorDB` 显式注入。如果图引用的 FactorDB 不在注册表中，重建直接报错。

当前 `_extractFDBConnection` 仅序列化 `{"type": "JYDB"}` 级别的骨架信息，不足以自举重建 FactorDB。

目标：图节点中存储足够多的非敏感元信息，使得 `_reconstructFactorTableFactor` 在 `_FactorDBRegistry` 未命中时，能自行构建并连接 FactorDB。

## Goals / Non-Goals

**Goals:**
- `_extractFDBConnection` 序列化完整的 `ClassName`、`ModulePath`、`ConfigFile` 以及非敏感的 `_QSArgs` 参数，使得从图节点能重建 FactorDB
- 敏感字段通过 `QSArgs` 中 Pydantic `Field` 原生的 `exclude=True` 属性排除，不写入 Neo4j
- `_reconstructFactorTableFactor` 在 `_FactorDBRegistry` 未命中时，自动构建 FactorDB、connect、缓存，再继续因子重建
- `registerFactorDB` 保留作为显式注入/预热接口，调用方仍可主动注册
- 密码和连接凭据不写入 Neo4j，始终从 `~/QuantStudioConfig/` 配置文件读取

**Non-Goals:**
- 不修改各 FactorDB 子类的初始化行为
- 不修改配置文件格式
- 不改变 `storeFactors` 时的存储流程（因子库节点已由 `registerFactorDB` 写入）
- 不支持没有对应配置文件的 FactorDB（如果类依赖 config_file 但文件不存在，重建会失败）

## Decisions

### D1: 序列化策略 — 存 `_QSArgs.model_dump()`，利用 Pydantic 原生 `exclude`

当前：
```python
conn_info = {"type": fdb.__class__.__name__}
if hasattr(fdb._QSArgs, "MainDir"):
    conn_info["MainDir"] = str(fdb._QSArgs.MainDir)
```

改为：
```python
conn_info = {
    "ClassName": fdb.__class__.__name__,
    "ModulePath": fdb.__class__.__module__,
    "ConfigFile": fdb.ConfigFile,
    "QSArgs": _sanitizeForJSON(fdb._QSArgs.model_dump()),
}
```

**`exclude` 机制**：直接调用 `fdb._QSArgs.model_dump()`，Pydantic 原生跳过 `Field(exclude=True)` 的字段。这是 Pydantic 的标准语义——"排除在序列化之外"——与"不存入图数据库"完全吻合。密码、API Key 等敏感字段在各 FactorDB 的 `__QS_ArgClass__` 中定义时已设 `exclude=True`，无需额外过滤逻辑。

**`ConfigFile` 属性**：`FactorDB` 基类新增 `ConfigFile` 属性，返回该实例关联的配置文件绝对路径。存储此路径可在重建时精确还原初始化参数。

**备选方案**：手写每个 FactorDB 类型的白名单字段 → 维护成本高，拒绝。

### D2: 重建策略 — 惰性构建 + 缓存，传入 ConfigFile

`_reconstructFactorTableFactor` 中，`_FactorDBRegistry` 未命中时的流程：

```
图节点 ConnectionJSON → 解析 ModulePath/ClassName/ConfigFile/QSArgs
                       → importlib.import_module + getattr
                       → FactorDBClass(args=qs_args, config_file=ConfigFile)
                       → fdb.connect()
                       → _FactorDBRegistry[fdb.Name] = fdb
                       → 继续因子重建
```

关键点：以存储的 `ConfigFile` 作为 `config_file` 参数传入 `__init__`，确保 FactorDB 使用正确的配置文件路径而非依赖默认约定。

### D3: 保留 `registerFactorDB` 的覆盖语义

调用方显式调用的 `registerFactorDB` 优先生效：它写入的实例已经在 `_FactorDBRegistry` 中，惰性构建在命中注册表时直接跳过。这允许 QSWeb 等场景预热自己的连接，避免重复建连。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `ConfigFile` 返回的路径在另一台机器上不存在 | 重建失败 | 错误信息明确提示缺失的配置文件路径 |
| `exclude=True` 未标记导致敏感信息泄露 | 密码写入 Neo4j | 敏感字段在 `__QS_ArgClass__` 定义时必须设置 `Field(exclude=True)`；代码审查时重点关注 |
| 某些 FactorDB 子类的 `_QSArgs` 不含足够的重建信息 | 特定 DB 类型重建失败 | 按需补充 `_QSArgs` 中的必要字段；对少数无法自动重建的类，仍要求显式 `registerFactorDB` |
| `model_dump()` 在旧版 Pydantic 上行为差异 | 序列化不完整 | QuantStudio 已全面使用 Pydantic v2，`model_dump` 行为稳定 |
| 自动 `connect()` 可能耗时 | 首次重建慢 | 缓存到 `_FactorDBRegistry` 后后续调用 O(1)；可选的 `registerFactorDB` 预热仍可用 |
| `ConfigFile` 属性返回 `None`（某些 DB 无配置文件） | 重建时 `config_file=None` | 与默认行为一致，FactorDB 子类自行处理 `None` 情况 |

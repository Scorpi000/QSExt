## Why

当前 `QSGraphDB.reconstructFactor` 重建 `FactorTableFactor` 时，依赖调用方提前通过 `registerFactorDB` 注入活的 `FactorDB` 实例。如果图里引用了 QSWeb 中未连接的因子库，重建直接失败。这让"从图元数据自举重建计算图"成为半成品——元数据完整，但缺少最后一步的自动化。

## What Changes

- **`_extractFDBConnection` 序列化完整 `QSArgs`**：将 `ClassName`、`ModulePath`、`ConfigFile`（因子库配置文件路径）以及 `QSArgs` 的 `model_dump()` 结果写入因子库节点。`QSArgs` 中标记 `exclude=True` 的字段（如密码、API Key 等敏感信息）不序列化——这是 Pydantic `Field` 的原生属性，语义即"排除在序列化之外"。
- **`_reconstructFactorTableFactor` 惰性重建 FactorDB**：`_FactorDBRegistry` 未命中时，从图节点元数据动态构建 FactorDB 实例——以 `ConfigFile` 作为 `config_file` 参数传入 `__init__`，调用 `connect()`，缓存到注册表，再继续因子重建。
- **移除对调用方显式 `registerFactorDB` 的硬依赖**：重建链路不再要求前置注入。`registerFactorDB` 保留作为显式覆盖/预热接口。

## Capabilities

### New Capabilities

- `factor-db-auto-reconstruct`: FactorDB 自动重建——`reconstructFactor` 遇到 `FactorTableFactor` 且对应 FactorDB 未注册时，从图节点中存储的完整连接元信息自动构建 FactorDB 实例并缓存

### Modified Capabilities

<!-- 不涉及对现有 spec 的需求级变更 -->

## Impact

- **核心库**：`QSExt/QSRegistry/QSGraphDB.py` — `_extractFDBConnection`、`_reconstructFactorTableFactor` 方法
- **QSWeb**：`QSWeb/backend/app/services/qs_bridge.py` — 可移除或简化 `register_factor_dbs` 的显式调用（不再必需，可保留为预热优化）
- **配置文件**：依赖各 FactorDB 自身从 `~/QuantStudioConfig/` 读取连接凭据的行为，无新增配置要求

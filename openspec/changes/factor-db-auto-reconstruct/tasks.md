## 1. 序列化完整重建信息

- [ ] 1.1 修改 `_extractFDBConnection`：序列化 `ClassName`、`ModulePath`、`ConfigFile`（`fdb.ConfigFile` 属性），以及 `_QSArgs.model_dump()`（Pydantic 原生跳过 `exclude=True` 字段，经 `_sanitizeForJSON` 处理），替换当前仅存 `type` 和 `MainDir` 的骨架逻辑

## 2. 惰性自动重建 FactorDB

- [ ] 2.1 在 `_reconstructFactorTableFactor` 中添加 `_FactorDBRegistry` 未命中时的自动构建分支：解析 `ConnectionJSON` → 动态导入类 → 以 `QSArgs` 为 `args`、`ConfigFile` 为 `config_file` 构造实例 → `connect()` → 缓存到 `_FactorDBRegistry`
- [ ] 2.2 保持 `registerFactorDB` 不变，确保显式注册的实例优先于自动构建（`_FactorDBRegistry` 命中时跳过自动构建分支）

## 3. 测试

- [ ] 3.1 编写 `_extractFDBConnection` 序列化往返测试：验证不同 FactorDB 类型（JYDB、HDF5DB、ClickHouseDB）的 `ConnectionJSON` 包含 `ClassName`、`ModulePath`、`ConfigFile`、`QSArgs` 必要字段，且 `exclude=True` 的敏感字段不在输出中
- [ ] 3.2 编写 `_reconstructFactorTableFactor` 自动重建集成测试：模拟未注册 → 从图节点自动构建 → 传入 `config_file=ConfigFile` → 缓存命中的完整流程

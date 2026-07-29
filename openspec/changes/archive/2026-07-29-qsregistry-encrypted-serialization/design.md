## Context

QuantStudio 核心在 `Core/_encryption.py` 新增了 Fernet 对称加密模块，并在 `__QS_Args__` / `__QS_Object__` 上提供了 `serialize()` / `deserialize()` 方法。调用链：

```
__QS_Object__.serialize()
  → self.model_dump()                    # 子类可扩展字段
  → result["__qsargs__"] = self._QSArgs.serialize()  # 加密 secret 字段
       → encrypt_value(str(value))       # "ENC:<base64>" 格式
```

QSRegistry 当前有自己独立的序列化体系：
- `_sanitizeForJSON()` — 将 numpy/pandas/datetime/callable 转为 JSON 兼容 dict
- `_desanitizeFromJSON()` — 逆操作
- `serializeFactorArgs()` — 对 factor._QSArgs.model_dump() 做 sanitize
- `serializeOperatorArgs()` — 对 operator._QSArgs.ModelArgs 做 sanitize

这两套体系完全独立运行，QSRegistry 不走 QuantStudio 的 `serialize()`，因此：
1. 敏感字段（`secret=True`）不会加密
2. QSRegistry 需要知道哪些字段可序列化（手动挑字段）
3. RiskDB 的 ConnectionJSON 非常简陋，无法用于自动重建

### 约束

- **向后兼容**：`decrypt_value()` 对非 `"ENC:"` 前缀的值透传，旧数据不受影响
- **Neo4j 属性限制**：Neo4j 节点属性只支持基本类型（str, int, float, bool, list），复杂类型仍需 `_sanitizeForJSON`
- **Factor 重建特殊性**：Factor 的重建必须按拓扑顺序（先重建描述子和算子），不能直接用 `cls.deserialize()`，因为 `Factor.__init__` 需要 `descriptors` 参数

## Goals / Non-Goals

**Goals:**
- 所有 `_QSArgs` 的存储使用 `serialize()` 进行加密
- FactorDB 使用 `__QS_Object__.serialize()` 完整输出，替代手动 `_extractFDBConnection`
- RiskDB ConnectionJSON 补齐为与 FactorDB 一致的完整信息
- 所有重建路径使用 `__QS_ArgClass__.deserialize()` 进行解密
- 旧数据（无 `ENC:` 前缀）完全兼容

**Non-Goals:**
- 不修改 QuantStudio 核心代码
- 不改变 Neo4j 图结构（节点类型、关系类型不变）
- 不修改 Factor 和 FactorOperator 的拆分存储模式（它们因图遍历需要，必须保持关系型存储）
- 不涉及配置文件（`~/QuantStudioConfig/`）的加密存储

## Decisions

### Decision 1: 两层序列化架构（serialize → sanitize）

**选择**：`_QSArgs.serialize()`（加密层）→ `_sanitizeForJSON()`（JSON 兼容层）

**备选**：将 `_sanitizeForJSON` 逻辑合并进 `__QS_Args__.serialize()`。

**理由**：`_sanitizeForJSON` 是 QSRegistry 特定的需求（numpy/pandas/callable → JSON），不应上提到 QuantStudio 核心。保持两层独立，各司其职。

处理顺序：
```
存储: _QSArgs.serialize() → _sanitizeForJSON() → json.dumps() → Neo4j
重建: Neo4j → json.loads() → _desanitizeFromJSON() → ArgClass.deserialize() → args dict
```

### Decision 2: FactorDB 存储格式切换为 `fdb.serialize()`

**选择**：`_extractFDBConnection` 改为存 `fdb.serialize()` 完整输出，仅额外补充 `__module__` 和 `_ConfigFile`。

**备选**：继续存手动挑的字段，仅在 QSArgs 层面加密。

**理由**：FactorDB 是 `__QS_Object__` 子类，`serialize()` 已经产出了标准结构（`__type__`、`__class__`、加密的 `__qsargs__`）。自维护的 `ConnectionJSON` 是冗余的，且随时可能与 QS_Object 演进不同步。仅额外存 `__module__`（因为 `serialize()` 不包含模块路径）和 `_ConfigFile`（因为 `deserialize()` 不传 config_file）。

### Decision 3: 保留 Factor/Operator 的拆分存储，仅加密 args 层

**选择**：因子和算子继续保持关系型存储（`USES_OPERATOR`、`DESCRIBES` 关系等），仅在 `QSArgsJSON` 和 `ModelArgsJSON` 上使用 `serialize()` 加密。

**备选**：整个因子存为一个 blob。

**理由**：图数据库的价值在于关系遍历（`getDependents`、`getDescriptors`、影响分析）。将因子存为一个 blob 会失去这些能力。当前拆分存储模式是正确的，只需在 args 层面统一到 QuantStudio 的加密协议。

### Decision 4: RiskDB 对齐 FactorDB 的 ConnectionJSON

**选择**：`registerRiskDB` 存储与 FactorDB 相同的完整连接信息（`ClassName`、`ModulePath`、`ConfigFile`、加密的 `QSArgs`），Reconstruct 路径复用 FactorDB 的 `_autoBuildFactorDB` 同款逻辑。

**备选**：只给 RiskDB 补上 QSArgs 加密，保持其他字段不变。

**理由**：RiskDB 和 FactorDB 都是 `__QS_Object__` 的子类，拥有相同的能力（`connect()`、`ConfigFile`、`QSArgs`）。当前 RiskDB 的 ConnectionJSON 只有 `{"type": "..."}` 是严重不足的。对齐后两者的重建逻辑可以统一。

### Decision 5: `_sanitizeForJSON` 中新增 `ENC:` 字符串处理

**选择**：`_sanitizeForJSON` 对普通字符串透传（不会在外层包 `{"__str_repr__": ...}`），`"ENC:<base64>"` 就是普通字符串，自然透传。

**理由**：`encrypt_value()` 返回的是普通 `"ENC:..."` 字符串。在 `_sanitizeForJSON` 中，字符串类型直接 `return value`（line 50），所以加密后的值直接作为字符串存入 JSON，无需额外处理。`_desanitizeFromJSON` 也正确：字符串不会被解析为 dict，原样返回 `"ENC:..."`，然后 `__QS_ArgClass__.deserialize()` 中的 `decrypt_value()` 识别前缀并解密。

## Risks / Trade-offs

- **[Risk] 加密密钥丢失 → 所有加密字段无法解密**  
  → Mitigation: Fernet 密钥持久化在 `~/QuantStudioConfig/secret.key`，与数据备份一起保护。首次使用时自动生成，日志提示密钥路径。

- **[Risk] `serialize()` 可能产出 `_sanitizeForJSON` 不认识的类型**  
  → Mitigation: `serialize()` 遍历字段值，每个值要么是 `"ENC:..."` 字符串，要么是原始 Python 值。这些原始值都在 `_sanitizeForJSON` 已知覆盖范围内。如果未来 QuantStudio 在 `serialize()` 中引入新类型，`_sanitizeForJSON` 的兜底逻辑 `{"__str_repr__": True}` 会捕获。

- **[Trade-off] 序列化/反序列化多了一层函数调用**  
  → 影响可忽略。`_get_fernet()` 是进程内单例，加密开销极小。`decrypt_value()` 对非加密值直接透传。

## Open Questions

（无）

---
name: tinysoft-add-table
description: >
  向 QSExt 的 TinySoft 因子库配置文件中添加新表。当用户要求"添加一张表到 TinySoftDB"、
  "把天软某个 INFOTABLE 接入 QuantStudio"、"在 TinySoftDBInfo 里配置新表"、"TinySoftDB 读取不到某张表"、
  或需要修改 QSExt/Resource/TinySoftDBInfo.xlsx 的 TableInfo / FactorInfo 工作表时触发。
  也适用于排查已配置表的字段类型、参数或表类型问题。
---

# 向 TinySoftDB 配置添加新表

QSExt 的 `TinySoftDB` 因子库由 `QSExt/Resource/TinySoftDBInfo.xlsx` 驱动。该文件决定
"天软的哪些 INFOTABLE、哪些字段可以被 QuantStudio 当作因子读取"，以及每张表的读取语义。

本 Skill 指导把一个天软新 INFOTABLE 接入该配置文件的完整流程。

## 配置文件结构

`TinySoftDBInfo.xlsx` 含 3 个工作表：

| 工作表 | 作用 | 索引 |
|--------|------|------|
| `TableInfo` | 一张表一行，声明表级配置 | `TableName` |
| `FactorInfo` | 一个字段一行，声明字段级配置 | `(TableName, FieldName)` |
| `ExchangeInfo` | 交易所信息（后缀映射） | `Suffix` |

三张工作表都按上述索引列去重。**重复不会报错**，但取数时会命中错误行——
追加行前先确认表名/字段名不存在。

## 工作流程

### 步骤 1 — 从 MCP 查询天软数据字典信息

用 `tinysoft_doc` MCP 工具获取目标 INFOTABLE 的表号、字段和说明：

```
mcp__tinysoft_doc__browse_categories()                          # 先看有哪些分类
mcp__tinysoft_doc__search_docs(keyword="财务指标")               # 按关键词搜索文档
mcp__tinysoft_doc__get_doc_content(doc_id=1234)                 # 获取文档详情
mcp__tinysoft_doc__get_function_list(keyword="Stock")           # 浏览函数列表
mcp__tinysoft_doc__search_online(keyword="INFOTABLE 财务")       # 在线搜索补充
```

| 工具 | 返回 | 用途 |
|------|------|------|
| `browse_categories` | 有哪些分类、各分类文档数量 | 不知道目标表在哪个分类时先看全景 |
| `search_docs` | 文档标题、路径、描述 | 按中文业务词定位 INFOTABLE |
| `get_doc_content` | 文档描述、**字段列表**、**参数说明**、代码示例 | 步骤 2-5 填写配置的依据 |
| `get_function_list` | .NET 函数列表 | 查看可用的 TSL 函数 |
| `search_online` | 同 `search_docs`，更实时 | 本地结果不足时补充 |

`get_doc_content` 是最关键的：**它给出 INFOTABLE 的字段信息和使用方法**。
`format` 取 `markdown`（表格更易读）或 `text`（默认）。

**若 MCP 不可用**：可以改用天软的在线文档或直接在天软客户端中查看 INFOTABLE 的字段定义。

### 步骤 2 — 判断表的读取语义（选 TableClass）

这是最关键的一步。`TableClass` 决定 QuantStudio 如何调用天软 TSL 代码并把返回数据
翻译成"时点 × ID × 因子"三维数据。**表类型选错会导致数据静默错误**，
务必先实际执行一次 TSL 语句观察返回结构，再按下表选择。

TinySoftDB 支持 5 种 TableClass：

| TableClass | 数据形态 | 判据 | 代码类 |
|------------|----------|------|--------|
| `TradeTable` | 按 ID 逐个查询，传入起止日期，返回该 ID 的时间序列 | 使用 `tradetable` 语法，返回含日期列的数据 | `_TradeTable` |
| `QuoteTable` | 按周期查询行情数据，支持秒级/日级周期 | 使用 `markettable` 语法，需设置周期参数 | `_QuoteTable` |
| `WideTable` | 宽表格式，通过 INFOTABLE 查询，支持发布日期追溯 | 使用 `INFOTABLE` + SQL 语法，一行一个 ID 的时间序列 | `_WideTable` |
| `FeatureTable` | 无时点的截面快照，一次调用返回所有 ID 的当前状态 | 使用 `INFOTABLE` + SQL 语法，无日期条件 | `_FeatureTable` |
| `MappingTable` | 映射表，有起始日和结束日的有效期区间 | 使用 `INFOTABLE` + SQL 语法，含有效期字段 | `_MappingTable` |

**选择方法**：先在天软客户端执行 TSL 语句观察返回结构：

```tsl
// 示例：查看 INFOTABLE 302 的字段
return exportjsonstring(
  select ['StockID'],['基金名称'],['投资类型'],['设立日']
  from infotable 302
  of array('OF000001','OF000002')
end);
```

- 返回含日期列 + 多个数值列，按单个 ID 查询 → `TradeTable`
- 返回行情数据，需要设置周期 → `QuoteTable`
- 使用 INFOTABLE 查询，含日期条件（截止日/公告日）→ `WideTable`
- 使用 INFOTABLE 查询，无日期条件 → `FeatureTable`
- 使用 INFOTABLE 查询，含有效期字段（起始日/结束日）→ `MappingTable`

**注意**：
- `TradeTable` 使用天软的 `tradetable` 语法，适合行情数据
- `QuoteTable` 使用天软的 `markettable` 语法，适合分时数据
- `WideTable`、`FeatureTable`、`MappingTable` 都使用 `INFOTABLE` 语法，区别在于日期处理方式
- `WideTable` 是最常用的 INFOTABLE 类型，支持发布日期追溯（PublDTField）

### 步骤 3 — 填写 TableInfo 行

在 `TableInfo` 工作表追加一行，按下表逐列填写。**列名必须完全一致**。

| 列名 | 必填 | 含义与填法 |
|------|------|------------|
| `TableName` | 是 | **QuantStudio 内部表名，可自由命名**。`getTable(name)` / `TableNames` 用的是这一列 |
| `DBTableName` | 是 | 天软 **INFOTABLE 表号**（如 `302`）或特殊表名（`tradetable`/`markettable`）。必须是天软数据字典中真实存在的表 |
| `TableClass` | 是 | 步骤 2 选定的类型（`TradeTable`/`QuoteTable`/`WideTable`/`FeatureTable`/`MappingTable`）；留空则该表不出现在 `TableNames` 中 |
| `DefaultArgs` | 否 | Python dict 字面量（用 `eval` 解析），作为该表默认参数。如 `{"DTField":"截止日"}` |
| `SecurityType` | 否 | 证券类型说明，如 `A股`、`基金`、`期货`、`债券`。用于 ID 转换逻辑 |
| `提取方式` | 否 | 提取方式说明（仅作标注） |
| `Description` | 否 | 表说明 |

**`TableName` 可任意命名，且允许同一 `DBTableName` 出现多行**。
同一 INFOTABLE 以不同 `TableName` + 不同 `DefaultArgs` 注册两次，就得到两套读取语义。
**表名唯一性约束在 `TableName` 上**，与 `DBTableName` 无关。

**`DefaultArgs` 常用取值**：

对于 `WideTable`/`MappingTable`：
- `{"DTField":"截止日"}` — 指定日期字段名（必填）
- `{"IDField":"代码"}` — 指定 ID 字段名（默认使用 FactorInfo 中 FieldType=ID 的字段）
- `{"PublDTField":"公告日"}` — 指定发布日期字段（WideTable 可选，用于追溯）
- `{"EndDTField":"结束日"}` — 指定结束日期字段（MappingTable 必填）
- `{"LookBack":365}` — 回溯天数（WideTable 可选）
- `{"EndDateASC":true}` — 截止日期是否递增（WideTable 可选）

对于 `TradeTable`：
- 通常不需要额外参数

对于 `QuoteTable`：
- `{"Cycle":60, "CycleUnit":"s"}` — 周期设置（默认 60 秒）

### 步骤 4 — 填写 FactorInfo 行

为该表的**每个需要暴露的字段**追加一行。不需要全部字段都配置——
只配置用户实际要用的字段即可，未配置的字段在 QuantStudio 中不可见。

| 列名 | 必填 | 含义与填法 |
|------|------|------------|
| `TableName` | 是 | 与 TableInfo 一致 |
| `FieldName` | 是 | **QuantStudio 因子名**（如 `基金名称`、`投资类型`）。用户在 QuantStudio 中看到的名称 |
| `DBFieldName` | 是 | **天软字段名**（如 `基金名称`、`投资类型`）。TSL 语句中使用的字段名 |
| `DataType` | 是 | 数据类型：`float64`、`int64`、`object` 等。数值型用 `float64`，字符串型用 `object` |
| `FieldType` | 是 | 字段角色标注，决定它是否成为因子（见下表） |
| `Supplementary` | 否 | 补充说明，一般留空 |
| `DBFieldCode` | 否 | 天软字段代码（如 `302000`），仅作参考 |
| `IsPK` | 否 | 是否主键字段（`Y`/`N`），一般留空 |
| `Description` | 否 | 字段说明（如"注意单位: %"、"注意单位: 手"） |

`FieldType` 取值：

| FieldType | 含义 | 说明 |
|-----------|------|------|
| `因子` | 普通因子字段（最常用） | 会被 QuantStudio 当作因子读取 |
| `ID` | ID 字段（每表至多一个） | 证券代码字段，如 `代码`、`StockID` |
| `Date` | 时点字段 | 日期列，如 `截止日`、`date` |
| `EndDate` | 结束日期字段 | 仅 `MappingTable` 使用 |
| `PublDT` | 发布日期字段 | 仅 `WideTable` 使用（公告日追溯） |

`FieldType` 留空（NaN）的字段**不会成为因子**，仅作内部辅助。

**如何确定 FieldType**：
1. 先执行 TSL 语句观察返回的数据结构
2. 日期列 → `Date`（如 `截止日`、`date`）
3. 证券代码列 → `ID`（如 `StockID`、`代码`）
4. 结束日期列 → `EndDate`（仅 MappingTable）
5. 公告日期列 → `PublDT`（仅 WideTable，可选）
6. 其余数值/字符串列 → `因子`

**DataType 确定方法**：

根据天软数据字典中的字段类型确定：
- `Float`/`Integer` → `float64`
- `Char`/`String` → `object`
- `Date` → `float64`（天软日期格式为 YYYYMMDD 整数）

### 步骤 5 — 填写 ExchangeInfo（仅当需要新的交易所映射时）

`ExchangeInfo` 定义天软交易所代码与 QuantStudio 后缀的映射关系。
通常不需要修改，除非接入新的交易所类型。

| 列名 | 含义 |
|------|------|
| `Suffix` | QuantStudio 后缀（如 `.SH`、`.SZ`） |
| `Exchange` | 交易所代码（如 `SSE`、`SZSE`） |
| `ExchangeName` | 交易所名称（如 `上海证券交易所`、`深圳证券交易所`） |

### 步骤 6 — 验证

配置改完后**必须实际跑一遍**，仅看 Excel 无法发现类型/ID 错误。

**先做离线检查**（不需要连接天软，几秒完成）——能立刻发现表名重复、索引错乱、
列缺失这类配置级错误：

```python
import os, logging, sys; sys.stdout.reconfigure(encoding='utf-8')
from QSExt import __QS_MainPath__
from QSExt.Factor.TinySoftDB import importInfo
XLSX = os.path.join(__QS_MainPath__, 'Resource', 'TinySoftDBInfo.xlsx')
TI, FI, EI = importInfo(None, XLSX, out_info=True)
print('TableInfo:', TI.shape, TI.index.name)
print('FactorInfo:', FI.shape, FI.index.names)
print('ExchangeInfo:', EI.shape)
print('新表已入库:', '你的表名' in TI.index)
print('新表字段数:', FI.loc['你的表名'].shape[0])
print('TableName 重复:', int(TI.index.duplicated().sum()))          # 应为 0
```

用 `__QS_MainPath__`（即 `QSExt` 包目录）拼路径，**不要写相对路径**——
后者要求恰好从仓库根目录运行，换工作目录就会 `FileNotFoundError`。

`importInfo` 会按 `TableName` 对 TableInfo 建索引、按 `(TableName, FieldName)` 对
FactorInfo 建索引。**若出现表名或字段名重复，pandas 不会报错**，但后续按表名取数据时
会取到错误行。离线检查中确认 shape 与索引名正常、重复数为 0，即说明配置结构无误。

**再跑在线验证**（需连接天软服务器）：

```python
from QSExt.Factor.TinySoftDB import TinySoftDB
FDB = TinySoftDB().connect()
print('表已注册:', '你的表名' in FDB.TableNames)
FT = FDB.getTable('你的表名')
print('因子数:', len(FT.FactorNames))
print('因子列表:', FT.FactorNames)
```

验证要点（按重要性排序）：

1. **表已注册**：`'你的表名' in FDB.TableNames` 应为 `True`
2. **因子名正确**：`FactorNames` 应列出配置的中文因子名
3. **数据可读取**：传入合理的 `ids` 和 `dts` 调用 `readData`
4. **数据非空且有值**：`readData` 返回的 Panel 应有真实数值，不是全 NaN
5. **ID 形态正确**：A 股 ID 应为 `000001.SZ` 格式（带后缀）

```python
import datetime as dt
# WideTable 示例验证
FT = FDB.getTable('你的表名')
IDs = ["000001.SZ", "000002.SZ"]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(5)]
Data = FT.readData(factor_names=FT.FactorNames[:3], ids=IDs, dts=DTs)
print(Data)
```

## 注意事项

### 信息文件缓存

`updateInfo` 会比较 `TinySoftDBInfo.xlsx` 与 `TinySoftDBInfo.hdf5` 的修改时间。
**只要 xlsx 比 hdf5 新就会重新解析并覆盖缓存**，所以正常编辑保存后
**无需手动删除 hdf5**；仅当 xlsx 修改时间反而更早（少见，但某些编辑器/复制文件
会保留原时间戳）时才需要手动删除 `QSExt/Resource/TinySoftDBInfo.hdf5` 强制重建。

### 不要臆造字段信息

`FieldName`（QuantStudio 因子名）、`DBFieldName`（天软字段名）和 `DataType`（数据类型）
必须来自天软数据字典或实际执行 TSL 语句的返回结果。凭空编造的字段名会让 `readData` 取不到数据，
而错误的 `DataType` 会导致数值被当成字符串（或反之）。

### ID 转换机制

TinySoftDB 通过 `SecurityType` 参数控制 ID 的转换方式：

| SecurityType | QuantStudio ID | 天软代码 | 转换方法 |
|--------------|----------------|----------|----------|
| `A股` | `000001.SZ` | `SZ000001` | `AStockID2TSCode` / `AStockTSCode2ID` |
| `基金` | `000001.OF` | `OF000001` | `MutualFundID2TSCode` / `MutualFundTSCode2ID` |
| `期货` | `IF2401.CFFEX` | `IF2401` | `FutureID2TSCode` / `FutureTSCode2ID` |
| `债券` | `010001.SH` | `SH010001` | `BondID2TSCode` / `BondTSCode2ID` |

在 `TableInfo` 的 `SecurityType` 列设置正确的证券类型，框架会自动调用对应的转换方法。

### WideTable 的发布日期追溯

`WideTable` 支持通过 `PublDTField` 参数实现发布日期追溯。这在财务数据场景下很有用：
- `DTField`：截止日期（如财报报告期）
- `PublDTField`：公告日期（如财报实际发布日）

启用追溯后，框架会确保在查询某日数据时，只返回该日之前已公告的数据，避免未来信息泄露。

设置方法：
```python
DefaultArgs = {"DTField": "截止日", "PublDTField": "公告日"}
```

### 环境无关性

本 Skill 不写死表号、字段名或 TSL 代码——这些都通过 `tinysoft_doc` MCP
或用户输入动态获取。天软数据字典可能随版本更新改变字段定义，
配置时以实际执行结果为准。

## 相关参考

- `QSExt/Factor/TinySoftDB.py` — TinySoftDB 因子库实现
  - `_TSTable:54` — 基础因子表类
  - `_TradeTable:121` — tradetable 类型（行情数据）
  - `_QuoteTable:163` — markettable 类型（分时数据）
  - `_TS_SQL_Table:239` — INFOTABLE 基类
  - `_WideTable:281` — 宽因子表类（最常用）
  - `_FeatureTable:425` — 特征因子表类（截面快照）
  - `_MappingTable:445` — 映射因子表类（有效期区间）
  - `TinySoftDB:489` — 因子库主类
  - `importInfo:23` / `updateInfo:38` — 信息文件导入与缓存
- `QSExt/Resource/TinySoftDBInfo.xlsx` — 配置信息文件
- 天软数据字典：通过 `tinysoft_doc` MCP 访问

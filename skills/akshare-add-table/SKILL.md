---
name: akshare-add-table
description: >
  向 QSExt 的 AKShare 因子库配置文件中添加新表。当用户要求"添加一张表到 AKShareDB"、
  "把 akshare 某个接口接入 QuantStudio"、"在 AKShareDBInfo 里配置新表"、"AKShareDB 读取不到某张表"、
  或需要修改 QSExt/Resource/AKShareDBInfo.xlsx 的 TableInfo / FactorInfo / ArgInfo 工作表时触发。
  也适用于排查已配置表的字段类型、参数或表类型问题。
---

# 向 AKShareDB 配置添加新表

QSExt 的 `AKShareDB` 因子库由 `QSExt/Resource/AKShareDBInfo.xlsx` 驱动。该文件决定
"akshare 的哪些 API 函数、哪些返回字段可以被 QuantStudio 当作因子读取"，以及每张表的读取语义。

本 Skill 指导把一个 akshare 新接口接入该配置文件的完整流程。

## 配置文件结构

`AKShareDBInfo.xlsx` 含 3 个工作表：

| 工作表 | 作用 | 索引 |
|--------|------|------|
| `TableInfo` | 一张表一行，声明表级配置 | `TableName` |
| `FactorInfo` | 一个字段一行，声明字段级配置 | `(TableName, FieldName)` |
| `ArgInfo` | 一个 API 参数一行，声明参数级配置 | `(TableName, ArgName)` |

三张工作表都按上述索引列去重。**重复不会报错**，但取数时会命中错误行——
追加行前先确认表名/字段名/参数名不存在。

## 工作流程

### 步骤 1 — 从 MCP 查询 akshare 接口信息

用 `akshare_doc` MCP 工具获取目标接口的函数名、参数和返回字段：

```
mcp__akshare_doc__browse_categories()                          # 先看有哪些分类
mcp__akshare_doc__search_interfaces(keyword="历史行情")         # 按关键词搜索接口
mcp__akshare_doc__get_interface_info(name="stock_zh_a_hist")   # 获取接口详情
mcp__akshare_doc__get_category_page(category="stock")          # 浏览某分类下所有接口
```

| 工具 | 返回 | 用途 |
|------|------|------|
| `browse_categories` | 有哪些分类、各分类接口数量 | 不知道目标接口在哪个分类时先看全景 |
| `search_interfaces` | 接口名、描述、分类 | 按中文业务词定位接口 |
| `get_interface_info` | 接口描述、**输入参数**、**输出参数**、调用示例 | 步骤 2-5 填写配置的依据 |
| `get_category_page` | 某分类下所有接口的名称与描述 | 浏览整分类 |
| `search_online` | 同 `search_interfaces`，更实时 | 本地结果不足时补充 |

`get_interface_info` 是最关键的：**它给出输入参数和输出字段的完整信息**。
`format` 取 `markdown`（表格更易读）或 `text`（默认）。

**若 MCP 不可用**：可以改用 akshare 的在线文档或直接在 Python 中调用
`help(ak.函数名)` 查看接口信息，但 MCP 能提供更结构化的参数和返回字段信息。

### 步骤 2 — 判断表的读取语义（选 TableClass）

这是最关键的一步。`TableClass` 决定 QuantStudio 如何调用 akshare API 并把返回数据
翻译成"时点 × ID × 因子"三维数据。**表类型选错会导致数据静默错误**，
务必先实际调用一次 API 观察返回结构，再按下表选择。

AKShareDB 支持 5 种 TableClass：

| TableClass | 数据形态 | 判据 | 代码类 |
|------------|----------|------|--------|
| `DTRangeTable` | 按 ID 逐个查询，传入起止日期，返回该 ID 的时间序列 | API 需要 `symbol`/`代码` + `start_date` + `end_date`，返回含日期列的 DataFrame | `_DTRangeTable` |
| `DTTable` | 按日期查询，传入单个日期，返回该日所有 ID 的截面数据 | API 需要 `date`/`日期` 参数，返回含 ID 列的 DataFrame | `_DTTable` |
| `AutoDTTable` | 无时间入参，从返回数据的指定列自动提取时点 | API 按单个 ID 调用，无时间参数，返回数据含日期列（如除净日、公告日期） | `_AutoDTTable` |
| `FeatureTable` | 无时点的截面快照，一次调用返回所有 ID 的当前状态 | API 无日期参数，返回含 ID 列的 DataFrame | `_AKSTable`（基类） |
| `NarrowTable` | 长表格式，一行一个 (ID, 因子名, 因子值) | API 返回含 `item`/`value` 等列的窄表 | `_AKSTable`（基类） |

**选择方法**：先用 Python 实际调用 API 观察返回结构：

```python
import akshare as ak
# 示例：查看 stock_zh_a_hist 的参数和返回
df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250101", end_date="20250110")
print(df.columns.tolist())
print(df.head())
```

- 返回含日期列（如 `日期`）+ 多个数值列 → `DTRangeTable`
- API 按单个 ID 调用，返回该 ID 的多条事件记录（如分红派息、停复牌），每行有一个日期列 → `AutoDTTable`
- 返回含 ID 列（如 `代码`）+ 多个数值列，无日期 → `FeatureTable`
- API 需要传入单个日期参数返回截面数据 → `DTTable`
- 返回 `item`/`value` 窄表格式 → `NarrowTable`

**注意**：`DTRangeTable` 是最常用的类型。它会**遍历每个 ID 逐一调用 API**，
所以 API 必须支持按单个 ID 查询。如果 API 一次返回所有 ID（如 `stock_zh_a_spot_em`），
应选 `FeatureTable`。`AutoDTTable` 也按 ID 逐个调用，但每个 ID 返回多行事件数据
（如一只股票有多次分红记录），用 `DTField` 指定的日期列作为时点维度。

### 步骤 3 — 填写 TableInfo 行

在 `TableInfo` 工作表追加一行，按下表逐列填写。**列名必须完全一致**。

| 列名 | 必填 | 含义与填法 |
|------|------|------------|
| `TableName` | 是 | **QuantStudio 内部表名，可自由命名**。`getTable(name)` / `TableNames` 用的是这一列 |
| `DBTableName` | 是 | akshare **API 函数名**，如 `stock_zh_a_hist`。必须是 `akshare` 模块中真实存在的函数 |
| `TableClass` | 是 | 步骤 2 选定的类型（`DTRangeTable`/`DTTable`/`AutoDTTable`/`FeatureTable`/`NarrowTable`）；留空则该表不出现在 `TableNames` 中 |
| `DefaultArgs` | 否 | Python dict 字面量（用 `eval` 解析），作为该表默认参数。如 `{"IDAdj":"前缀"}` |
| `SecurityType` | 否 | 证券类型说明，如 `A股`、`指数`、`公募基金`。仅作标注，不影响取数逻辑 |
| `Description` | 否 | 表说明 |
| `URL` | 否 | 数据来源 URL（如东方财富、新浪财经的页面地址） |

**`TableName` 可任意命名，且允许同一 `DBTableName` 出现多行**。
同一 API 以不同 `TableName` + 不同 `DefaultArgs` 注册两次，就得到两套读取语义。
**表名唯一性约束在 `TableName` 上**，与 `DBTableName` 无关。

**`DefaultArgs` 常用取值**：
- `{"IDAdj":"前缀"}` — ID 前缀调整（如新浪接口需要 `sh600000` 格式）
- `{"IDAdj":"无"}` — 不调整 ID
- `{"IDAdj":"去后缀去零"}` — 去后缀并去除前导零，保留至少4位（如港股 `00700.HK` → `0700`）
- `{"DTField":"除净日"}` — **AutoDTTable 必填**，指定用作时点维度的列名
- 留空或 `NaN` — 使用默认的"去后缀"调整

**AutoDTTable 的 `DefaultArgs` 必须包含 `DTField`**，指定 API 返回数据中用作时点的日期列名。
例如分红派息表：`{"DTField": "除净日"}`。AutoDTTable 自动启用 `MultiMapping` 模式，
因为同一 ID 在同一时点可能有多条事件记录。

### 步骤 4 — 填写 FactorInfo 行

为该表的**每个需要暴露的字段**追加一行。不需要全部字段都配置——
只配置用户实际要用的字段即可，未配置的字段在 QuantStudio 中不可见。

| 列名 | 必填 | 含义与填法 |
|------|------|------------|
| `TableName` | 是 | 与 TableInfo 一致 |
| `FieldName` | 是 | **akshare API 返回的列名**（如 `开盘`、`收盘`、`代码`）。同时作为 QuantStudio 的因子名 |
| `DataType` | 是 | pandas 数据类型字符串：`float64`、`int64`、`int32`、`object` 等。从 API 返回的 `df.dtypes` 获取 |
| `FieldType` | 是 | 字段角色标注，决定它是否成为因子（见下表） |
| `Supplementary` | 否 | 补充说明，一般留空 |
| `Description` | 否 | 字段说明（如"注意单位: %"、"注意单位: 手"） |

`FieldType` 取值：

| FieldType | 含义 | 说明 |
|-----------|------|------|
| `因子` | 普通因子字段（最常用） | 会被 QuantStudio 当作因子读取 |
| `ID` | ID 字段（每表至多一个） | 证券代码字段，如 `代码`、`symbol` |
| `Date` | 时点字段 | 日期列，如 `日期`、`trade_date` |
| `Time` | 时间字段 | 时间列（分时数据使用） |
| `FactorName` | 窄表的因子名字段 | 仅 `NarrowTable` 使用 |
| `FactorValue` | 窄表的因子值字段 | 仅 `NarrowTable` 使用 |

`FieldType` 留空（NaN）的字段**不会成为因子**，仅作内部辅助。

**如何确定 FieldType**：
1. 先调用 API 观察返回的 DataFrame 结构
2. 日期列 → `Date`
3. 证券代码列 → `ID`
4. `item`/`factor_name` 类列 → `FactorName`（仅窄表）
5. `value`/`factor_value` 类列 → `FactorValue`（仅窄表）
6. 其余数值/字符串列 → `因子`

**DataType 获取方法**：

```python
import akshare as ak
df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250101", end_date="20250110")
print(df.dtypes)  # 查看每列的数据类型
```

### 步骤 5 — 填写 ArgInfo 行（仅当表有 API 参数时）

`ArgInfo` 定义 akshare API 函数的输入参数。并非所有表都需要——
`FeatureTable` 类型的表通常不需要参数，而 `DTRangeTable` 和 `DTTable` 必须配置。

| 列名 | 必填 | 含义与填法 |
|------|------|------------|
| `TableName` | 是 | 与 TableInfo 一致 |
| `ArgName` | 是 | akshare API 的参数名（如 `symbol`、`start_date`、`end_date`、`period`） |
| `DataType` | 是 | 参数数据类型：`str`、`int`、`float` |
| `FieldType` | 是 | 参数角色标注（见下表） |
| `DefaultValue` | 否 | 参数默认值（示例值，用于文档说明） |
| `ArgInfo` | 否 | 参数约束信息（JSON 格式），仅 `QSArg` 类型需要 |
| `Description` | 否 | 参数说明 |

`FieldType` 取值：

| FieldType | 含义 | 说明 |
|-----------|------|------|
| `ID` | ID 参数 | 传入证券代码的参数（如 `symbol`）。每表至多一个 |
| `Date` | 日期参数 | 传入单个日期的参数（如 `date`）。`DTTable` 使用 |
| `StartDate` | 起始日期参数 | `DTRangeTable` 使用 |
| `EndDate` | 结束日期参数 | `DTRangeTable` 使用 |
| `QSArg` | 可配置参数 | 用户可通过 `APIArgs` 传入的参数（如 `period`、`adjust`） |

**`QSArg` 类型的 `ArgInfo` 格式**（JSON）：

对于单选参数：
```json
{"arg_type": "SingleOption", "option_range": ["daily", "weekly", "monthly"]}
```

**典型配置示例**：

`DTRangeTable`（如 `stock_zh_a_hist`）需要配置：

| ArgName | DataType | FieldType | DefaultValue | ArgInfo |
|---------|----------|-----------|--------------|---------|
| symbol | str | ID | 603777 | NaN |
| period | str | QSArg | daily | {"arg_type":"SingleOption","option_range":["daily","weekly","monthly"]} |
| start_date | str | StartDate | 20210301 | NaN |
| end_date | str | EndDate | 20210616 | NaN |
| adjust | str | QSArg | NaN | {"arg_type":"SingleOption","option_range":["","qfq","hfq"]} |

`DTTable`（如 `stock_tfp_em`）需要配置：

| ArgName | DataType | FieldType | DefaultValue |
|---------|----------|-----------|--------------|
| date | str | Date | NaN |

`FeatureTable` 和 `NarrowTable` 通常不需要 ArgInfo（API 无参数或参数固定）。

### 步骤 6 — 验证

配置改完后**必须实际跑一遍**，仅看 Excel 无法发现类型/ID 错误。

**先做离线检查**（不需要网络，几秒完成）——能立刻发现表名重复、索引错乱、
列缺失这类配置级错误：

```python
import os, logging, sys; sys.stdout.reconfigure(encoding='utf-8')
from QSExt import __QS_MainPath__
from QSExt.Factor.AKShareDB import _importInfo
XLSX = os.path.join(__QS_MainPath__, 'Resource', 'AKShareDBInfo.xlsx')
TI, FI, AI = _importInfo(None, XLSX, logging.getLogger('t'), out_info=True)
print('TableInfo:', TI.shape, TI.index.name)
print('FactorInfo:', FI.shape, FI.index.names)
print('ArgInfo:', AI.shape, AI.index.names)
print('新表已入库:', '你的表名' in TI.index)
print('新表字段数:', FI.loc['你的表名'].shape[0])
print('TableName 重复:', int(TI.index.duplicated().sum()))          # 应为 0
```

用 `__QS_MainPath__`（即 `QSExt` 包目录）拼路径，**不要写相对路径**——
后者要求恰好从仓库根目录运行，换工作目录就会 `FileNotFoundError`。

`_importInfo` 会按 `TableName` 对 TableInfo 建索引、按 `(TableName, FieldName)` 对
FactorInfo 建索引。**若出现表名或字段名重复，pandas 不会报错**，但后续按表名取数据时
会取到错误行。离线检查中确认 shape 与索引名正常、重复数为 0，即说明配置结构无误。

**再跑在线验证**（需网络访问 akshare API）：

```python
from QSExt.Factor.AKShareDB import AKShareDB
FDB = AKShareDB().connect()
print('表已注册:', '你的表名' in FDB.TableNames)
FT = FDB.getTable('你的表名')
print('因子数:', len(FT.FactorNames))
print('因子列表:', FT.FactorNames)
```

验证要点（按重要性排序）：

1. **表已注册**：`'你的表名' in FDB.TableNames` 应为 `True`
2. **因子名正确**：`FactorNames` 应列出配置的中文因子名
3. **数据可读取**：对 `DTRangeTable`/`DTTable`，传入合理的 `ids` 和 `dts` 调用 `readData`
4. **数据非空且有值**：`readData` 返回的 Panel 应有真实数值，不是全 NaN
5. **ID 形态正确**：A 股 ID 应为 `000001.SZ` 格式（带后缀）

```python
import datetime as dt
# DTRangeTable 示例验证
FT = FDB.getTable('你的表名')
IDs = ["000001.SZ", "000002.SZ"]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(5)]
Data = FT.readData(factor_names=FT.FactorNames[:3], ids=IDs, dts=DTs)
print(Data)
```

## 注意事项

### 信息文件缓存

`_updateInfo` 会比较 `AKShareDBInfo.xlsx` 与 `AKShareDBInfo.hdf5` 的修改时间。
**只要 xlsx 比 hdf5 新就会重新解析并覆盖缓存**，所以正常编辑保存后
**无需手动删除 hdf5**；仅当 xlsx 修改时间反而更早（少见，但某些编辑器/复制文件
会保留原时间戳）时才需要手动删除 `QSExt/Resource/AKShareDBInfo.hdf5` 强制重建。

### 不要臆造字段信息

`FieldName`（列名）和 `DataType`（数据类型）必须来自实际调用 akshare API 的返回结果
或 `akshare_doc` MCP 的查询结果。凭空编造的列名会让 `readData` 取不到数据，
而错误的 `DataType` 会导致数值被当成字符串（或反之）。

### ID 调整机制

AKShareDB 通过 `IDAdj` 参数控制 ID 的后缀处理方式（见 `_AKSTable.__QS_getIDMapping__`）：

| IDAdj 值 | 行为 | 适用场景 |
|----------|------|----------|
| `去后缀`（默认） | `000001.SZ` → `000001` | API 需要纯数字代码（如东财接口） |
| `去后缀去零` | `00700.HK` → `0700` | API 需要去掉前导零的代码（如同花顺港股接口），保留至少4位 |
| `前缀` | `000001.SZ` → `sz000001` | API 需要带交易所前缀的代码（如新浪接口） |
| `无` | 不调整 | API 直接接受带后缀的代码 |

在 `DefaultArgs` 中设置 `{"IDAdj":"前缀"}` 或 `{"IDAdj":"无"}` 来覆盖默认行为。

### 时点格式调整

如果 API 返回的日期列不是标准 datetime 格式，可以通过 `DTFmt` 参数指定解析格式：

```python
DefaultArgs = {"DTFmt": "%Y%m%d"}  # 日期格式为 "20250101"
```

### 环境无关性

本 Skill 不写死表名、字段名或 API 参数——这些都通过 `akshare_doc` MCP
或用户输入动态获取。akshare 库可能随版本更新改变 API 的参数和返回结构，
配置时以实际调用结果为准。

## 相关参考

- `QSExt/Factor/AKShareDB.py` — AKShareDB 因子库实现
  - `_AKSTable:59` — 基础因子表类（`FeatureTable` / `NarrowTable` 使用）
  - `_DTTable:154` — 单时点因子表类
  - `_DTRangeTable:197` — 时间区间因子表类
  - `_AutoDTTable:251` — 事件型因子表类（分红派息、停复牌等多行事件数据）
  - `_FeatureTable` — 截面快照因子表类
  - `AKShareDB` — 因子库主类
  - `_importInfo:22` / `_updateInfo:43` — 信息文件导入与缓存
- `QSExt/Resource/AKShareDBInfo.xlsx` — 配置信息文件
- akshare 文档：https://akshare.akfamily.xyz/index.html

# SQLite3DB — 基于 SQLite3 的因子库

## 1. 概述

SQLite3DB 是基于 SQLite3 数据库的因子库实现，继承自 `WritableFactorDB`，支持因子数据的读写、追加更新和管理功能。

- **类名**：`SQLite3DB`
- **模块**：`QSExt.Factor.SQLite3DB`
- **基类**：`QuantStudio.Factor.FactorDB.WritableFactorDB`
- **因子表类**：`SQL_WideTable` / `SQL_FeatureTable` / `SQL_NarrowTable` / `SQL_TimeSeriesTable` / `SQL_MappingTable` / `SQL_ConstituentTable` / `SQL_FinancialTable`（继承自 `QuantStudio.Factor.FactorUtils.SQL_Table`）

---

## 2. 存储结构

SQLite3DB 使用单个 `.sqlite3` 文件存储所有因子数据。数据库中的表使用 `InnerPrefix` 作为内部前缀以区分 QS 因子表和其他表。

### 表结构

每张 QS 因子表对应数据库中的一张物理表，结构如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `DTField`（默认 `datetime`） | `text NOT NULL` | 时点字段，主键之一 |
| `IDField`（默认 `code`） | `text NOT NULL` | ID 字段，主键之一 |
| 自定义因子字段 | `real` 或 `text` | 因子数据列 |

### 元数据管理

元数据分为两层，均存储于内存中的 `pd.DataFrame`：

| 元数据 | 变量 | 索引 | 说明 |
|--------|------|------|------|
| `_TableInfo` | `DataFrame` | `TableName` | 表名 → `DBTableName`、`TableClass`、`Description` |
| `_FactorInfo` | `DataFrame` | `(TableName, FieldName)` | 因子名 → `DBFieldName`、`DataType`、`FieldType`、`Supplementary`、`Description` |

`connect()` 时通过 `PRAGMA table_info` 自动扫描所有符合 `InnerPrefix` 前缀的表及其字段信息。

### 字段类型映射

| SQLite3 类型 | FieldType | 说明 |
|-------------|-----------|------|
| 包含 `text` / `char` 且字段名 = `IDField` | `ID` | ID 字段 |
| 包含 `text` / `char` 且字段名 = `DTField` | `Date`（Supplementary=`Default`） | 默认时点字段 |
| 包含 `text` / `char` | `Date` | 其他时点字段 |
| 其他 | `因子` | 普通因子 |

---

## 3. 参数说明

### SQLite3DB 参数

继承自 `WritableFactorDB.__QS_ArgClass__`，增加以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"SQLite3DB"` | 因子库名称（不可变） |
| `DBFile` | `str` | `""` | SQLite3 数据库文件路径，支持 `:memory:` 内存数据库（不可变） |
| `InnerPrefix` | `str` | `"qs_"` | 内部表名前缀，用于筛选 QS 管理的表（不可变） |
| `DTField` | `str` | `"datetime"` | 默认时点字段名（不可变） |
| `IDField` | `str` | `"code"` | 默认 ID 字段名（不可变） |
| `DTFmt` | `str` | `"%Y-%m-%d %H:%M:%S"` | 时点解析格式（不可变） |
| `IgnoreFields` | `List[str]` | `[]` | 扫描时忽略的字段名（不可变） |
| `FTArgs` | `dict` | `{}` | 创建因子表时使用的默认参数（不可变） |
| `TablePrefix` | `str` | `""` | 物理表名前缀（不可变） |
| `CheckWriteData` | `bool` | `False` | 写入时是否检查并校正数据（可变） |
| `CheckNullable` | `bool` | `False` | 写入时是否检查并移除 NULL 值（可变） |

### 配置文件

参数可从配置文件 `~/QuantStudioConfig/SQLite3DBConfig.json` 加载。示例：

```json
{
    "DBFile": "C:/Data/factors.sqlite3",
    "InnerPrefix": "qs_",
    "DTField": "datetime",
    "IDField": "code",
    "DTFmt": "%Y-%m-%d %H:%M:%S",
    "TablePrefix": ""
}
```

### SQL_Table 参数（通过 `getTable` 的 `args` 传入）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TableType` | `str` | 自动判断 | 因子表类型，可选 `WideTable`、`FeatureTable`、`NarrowTable`、`TimeSeriesTable`、`MappingTable`、`ConstituentTable`、`FinancialTable` |
| `DTField` | `str` / `None` | 自动判断 | 时点字段名 |
| `IDField` | `str` / `None` | 自动判断 | ID 字段名 |
| `DTFmt` | `str` | DB 级默认值 | 时点解析格式 |
| `MultiMapping` | `bool` | 自动判断 | 是否允许多重映射（主键多于 DT+ID 时自动启用） |
| `IgnoreTime` | `bool` | `False` | 是否忽略时间部分 |
| `LookBack` | `int` | `0` | 缺失填充回溯天数 |
| `FilterCondition` | `str` | `""` | 附加 SQL WHERE 条件 |
| `PreFilterID` | `bool` | `True` | 是否在 SQL 中预筛选 ID |

---

## 4. API 方法

### 4.1 连接管理

#### `connect() -> SQLite3DB`

连接数据库，扫描表信息。返回 `self` 以支持链式调用。

```python
# 文件数据库
SDB = SQLite3DB(args={"DBFile": "/path/to/data.sqlite3"}).connect()

# 内存数据库（用于测试）
SDB = SQLite3DB(args={"DBFile": ":memory:", "InnerPrefix": ""}).connect()
```

#### `disconnect() -> int`

断开数据库连接。

```python
SDB.disconnect()
```

#### `Connection -> sqlite3.Connection`

获取底层 `sqlite3.Connection` 对象，可用于执行原生 SQL。

```python
pd.read_sql_query("SELECT * FROM my_table", SDB.Connection)
```

### 4.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有表名（按字母排序）。

#### `getTable(table_name: str, args: dict = {}) -> SQL_Table`

获取指定名称的因子表对象。`args` 中的 `TableType` 参数可指定因子表类型：

```python
# 自动判断类型
FT = SDB.getTable("stock_cn_day_bar")

# 显式指定为财务因子表
FT = SDB.getTable("test_financial", args={
    "TableType": "FinancialTable",
    "DTField": "report_date",
    "报告期": "年报",
    "计算方法": "最新",
    "回溯年数": 1,
})
```

#### `renameTable(old_table_name: str, new_table_name: str)`

重命名因子表。底层执行 `ALTER TABLE ... RENAME TO`。

#### `deleteTable(table_name: str)`

删除因子表。底层执行 `DROP TABLE IF EXISTS`。

#### `createTable(table_name: str, field_types: Dict[str, str])`

手动创建因子表。`field_types` 格式为 `{因子名: SQLite3数据类型}`，会自动添加 `DTField` 和 `IDField` 作为主键。

```python
SDB.createTable("my_table", {
    "Factor0": "real",
    "Factor1": "text",
})
```

### 4.3 因子操作

#### `addFactor(table_name: str, field_types: Dict[str, str])`

向已有表添加新因子列。底层逐列执行 `ALTER TABLE ... ADD COLUMN`。

#### `renameFactor(table_name, old_factor_name, new_factor_name)`

重命名因子。底层执行 `ALTER TABLE ... RENAME COLUMN`（需要 SQLite3 ≥ 3.25.0）。

#### `deleteFactor(table_name, factor_names: List[str])`

删除因子。底层逐列执行 `ALTER TABLE ... DROP COLUMN`（需要 SQLite3 ≥ 3.35.0）。如果删除后表内只剩下 `datetime` 和 `code` 字段，表不会被自动删除。

### 4.4 数据写入

#### `writeData(data: Panel, table_name: str, if_exists="update", data_type={}) -> int`

批量写入因子表数据。如果表不存在则自动创建，如果写入的因子列不存在则自动添加。

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | `Panel` | 因子数据，items=因子名，major_axis=时点，minor_axis=ID |
| `table_name` | `str` | 表名 |
| `if_exists` | `"update"` / `"append"` / `"update_notnull"` | 写入方式 |
| `data_type` | `dict` | `{因子名: "double"/"string"/"object"}`，未指定时根据 dtype 自动识别 |

写入方式说明：

| 方式 | 行为 |
|------|------|
| `update` | 覆盖写入指定的时点×ID 范围内的数据，未指定的因子列保留旧值 |
| `append` | 仅填充原有 NaN 位置，不覆盖已有非空值 |
| `update_notnull` | 新数据非空时覆盖旧值，新数据为空时保留旧值 |

底层使用 `INSERT OR REPLACE` 实现 upsert 语义，以 `(DTField, IDField)` 作为唯一键。

```python
from QuantStudio.Core.QSObject import Panel

Data = Panel({
    "close": pd.DataFrame(...),
    "volume": pd.DataFrame(...),
})
SDB.writeData(data=Data, table_name="stock_cn_day_bar", if_exists="update")
```

#### `deleteData(table_name, ids=None, dts=None, dt_ids=None)`

删除指定条件的数据。

- `ids=None` 且 `dts=None`：清空整张表
- 指定 `ids`：删除指定 ID 的所有数据
- 指定 `dts`：删除指定时点的所有数据
- 指定 `dt_ids`：精确删除 (时点, ID) 对

### 4.5 数据读取（SQL_Table）

因子表对象提供标准的 QuantStudio 数据读取接口：

#### `FactorNames -> List[str]`

返回表中的所有字段名（包含 `DTField` 和 `IDField`）。

#### `getID(ifactor_name=None, idt=None) -> List[str]`

获取 ID 序列。指定 `idt` 时仅返回该时点有数据的 ID。

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None) -> List[datetime]`

获取时点序列，支持时间范围过滤。

#### `readData(factor_names, ids, dts) -> Panel`

读取因子数据。返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`。

```python
FT = SDB.getTable("stock_cn_day_bar")
Data = FT.readData(
    factor_names=["close", "volume"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 2)]
)
```

---

## 5. 使用示例

### 5.1 基本流程

```python
import datetime as dt
import numpy as np
import pandas as pd

from QSExt.Factor.SQLite3DB import SQLite3DB
from QuantStudio.Core.QSObject import Panel

# 连接因子库（内存数据库）
SDB = SQLite3DB(args={
    "DBFile": ":memory:",
    "InnerPrefix": "",
    "TablePrefix": "",
}).connect()

# 准备数据
nDT, nID = 100, 20
IDs = [f"{i:06d}.SZ" for i in range(1, nID + 1)]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]

Data = {
    "close": pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTs, columns=IDs),
    "volume": pd.DataFrame(np.random.rand(nDT, nID) * 100, index=DTs, columns=IDs),
}
SDB.writeData(data=Panel(Data), table_name="stock_cn_day_bar", if_exists="update")

# 读取数据
FT = SDB.getTable("stock_cn_day_bar")
print("因子列表:", FT.FactorNames)
print("ID 列表:", FT.getID()[:5])
print("时点范围:", FT.getDateTime()[0], "~", FT.getDateTime()[-1])

# 读取指定因子、ID、时点
Data = FT.readData(
    factor_names=["close"],
    ids=IDs[:5],
    dts=DTs[:10]
)
print(Data)
```

### 5.2 带参数的因子表读取

```python
# 忽略时间部分，按日期匹配
FT = SDB.getTable("stock_cn_day_bar", args={"IgnoreTime": True})

# 指定 LookBack 回溯填充
FT = SDB.getTable("stock_cn_day_bar", args={"LookBack": 5})

# 附带筛选条件
FT = SDB.getTable("stock_cn_day_bar", args={
    "FilterCondition": "{Table}.volume > 0"
})
```

### 5.3 增量更新数据

```python
# 首次写入
SDB.writeData(data=Panel({"factor1": initial_data}), table_name="my_table")

# 增量追加（不覆盖已有非空值）
SDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="append"
)

# 增量覆盖（仅更新非空值到已有数据）
SDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="update_notnull"
)
```

### 5.4 管理操作

```python
# 查看所有表
print(SDB.TableNames)

# 重命名表
SDB.renameTable("old_name", "new_name")

# 删除表
SDB.deleteTable("table_to_delete")

# 重命名因子
SDB.renameFactor("my_table", "old_factor", "new_factor")

# 删除因子
SDB.deleteFactor("my_table", ["factor_to_remove"])

# 为已有表添加新因子
SDB.addFactor("my_table", {"new_factor": "real"})

# 删除指定 ID 的数据
SDB.deleteData("my_table", ids=["000001.SZ"])
```

### 5.5 使用配置文件

```python
# 从配置文件加载连接参数
SDB = SQLite3DB(
    config_file="SQLite3DBConfig.json"
).connect()

# 运行时覆盖部分参数
SDB = SQLite3DB(
    args={"DBFile": "/custom/path/data.sqlite3"},
    config_file="SQLite3DBConfig.json"
).connect()
```

### 5.6 文件持久化

```python
# 文件数据库
SDB = SQLite3DB(args={
    "DBFile": "C:/Data/my_factors.sqlite3",
    "InnerPrefix": "qs_",
}).connect()

# 写入数据后，数据持久化到磁盘
SDB.writeData(data=Panel({...}), table_name="persistent_table")
SDB.disconnect()

# 下次使用时重新连接，数据自动可用
SDB2 = SQLite3DB(args={"DBFile": "C:/Data/my_factors.sqlite3"}).connect()
print(SDB2.TableNames)  # 包含 'persistent_table'
```

---

## 6. 因子表类型说明

SQLite3DB 支持 7 种因子表类型，对应不同的数据组织形式：

| TableType | 类 | 典型用途 |
|-----------|-----|---------|
| `WideTable` | `SQL_WideTable` | 标准宽表，每个因子一列 |
| `FeatureTable` | `SQL_FeatureTable` | 特征因子表，无时点维度 |
| `NarrowTable` | `SQL_NarrowTable` | 窄表，因子名存于一列中 |
| `TimeSeriesTable` | `SQL_TimeSeriesTable` | 时序因子表，无 ID 维度 |
| `MappingTable` | `SQL_MappingTable` | 映射因子表，除 DT/ID 外还有额外主键 |
| `ConstituentTable` | `SQL_ConstituentTable` | 成份因子表，涉及证券成份变更 |
| `FinancialTable` | `SQL_FinancialTable` | 财务因子表，支持报告期、调整类型等财务数据特性 |

类型默认由 `DTField` 和 `IDField` 的有无自动判断：

| DTField | IDField | 默认 TableType |
|---------|---------|---------------|
| 有 | 有 | `WideTable`（或 `_TableInfo` 中记录的类型） |
| 无 | 有 | `FeatureTable` |
| 有 | 无 | `TimeSeriesTable` |

可通过 `getTable` 的 `args` 中的 `TableType` 显式指定。

---

## 7. 数据写入实现细节

### upsert 机制

使用 SQLite3 的 `INSERT OR REPLACE` 语法，以 `(datetime, code)` 作为主键实现 upsert。当写入的 `(datetime, code)` 组合已存在时，整行数据被替换。

### 自动建表

`writeData` 在表不存在时自动创建表，数据类型根据 `pd.DataFrame` 的 dtype 推断：
- `np.dtype("O")` → `text`
- 其他 → `real`

如果写入的因子表中没有某个因子列，会自动执行 `ALTER TABLE ... ADD COLUMN`。

### 时点存储

`Panel` 的 `major_axis`（`datetime` 类型）在写入前通过 `.astype(str)` 转为字符串，默认格式为 `YYYY-MM-DD HH:MM:SS`。读取时通过 `DTFmt` 参数控制解析格式。

---

## 8. 与 SQLDB 的对比

| 特性 | SQLite3DB | SQLDB |
|------|-----------|-------|
| 数据库 | SQLite3 | MySQL / PostgreSQL |
| 存储方式 | 单文件 | 远程数据库服务器 |
| 连接器 | Python 内置 `sqlite3` | 多种连接器（pymysql、psycopg2 等） |
| 并发支持 | 单写入者（SQLite3 限制） | 多用户并发 |
| 元数据扫描 | `PRAGMA table_info` | `information_schema` 查询 |
| upsert | `INSERT OR REPLACE` | `INSERT ... ON DUPLICATE KEY UPDATE` |
| 配置参数 | 简化的文件路径参数 | 完整的 DB 连接参数（IP、端口、用户、密码等） |
| 适用场景 | 本地开发、测试、单用户场景 | 生产环境、团队协作 |
| 部署复杂度 | 零依赖，开箱即用 | 需要数据库服务 |

---

## 9. 依赖

| 包 | 用途 |
|---|------|
| `sqlite3` | Python 标准库，数据库驱动 |
| `numpy` | 数值计算 |
| `pandas` | 数据框操作 |
| `pydantic` | 参数校验 |
| `QuantStudio.Core` | `__QS_Error__`、`Panel` 等基础类 |
| `QuantStudio.Factor.FactorDB` | `WritableFactorDB` 基类 |
| `QuantStudio.Factor.FactorUtils` | `SQL_*` 因子表类 |
| `QuantStudio.Tools.SQLDBFun` | `genSQLInCondition` SQL 工具函数 |

---

## 10. 注意事项

1. **版本要求**：因子重命名需要 SQLite3 ≥ 3.25.0，因子删除需要 SQLite3 ≥ 3.35.0
2. **数据类型限制**：仅支持 `real`（双精度浮点）和 `text`（字符串）两种数据类型，不支持 Python 对象的原生存储
3. **并发写入**：SQLite3 不支持多进程并发写入，多进程场景建议使用 SQLDB（PostgreSQL）或 ZarrDB
4. **内存数据库**：`:memory:` 仅在单连接内有效，断开连接后数据丢失
5. **字段名冲突**：`DTField` 和 `IDField` 为保留字段名，不应与因子名重复

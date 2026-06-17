# DuckDB — 基于 DuckDB 的因子库

## 1. 概述

DuckDB 是基于 [DuckDB](https://duckdb.org/) 数据库的因子库实现，继承自 `WritableFactorDB`，支持因子数据的读写、追加更新和管理功能。DuckDB 是一个高性能的内嵌式列存分析数据库，与 SQLite3 一样无需独立服务器，但具有更好的分析查询性能。

除原生 DuckDB 表外，还支持将 Parquet 文件目录作为外部只读数据源注册为 DuckDB 视图，通过 `read_parquet` + Hive 分区实现零运维的列存离线分析。

- **类名**：`DuckDB`
- **模块**：`QSExt.Factor.DuckDB`
- **基类**：`QuantStudio.Factor.FactorDB.WritableFactorDB`
- **因子表类**：`SQL_WideTable` / `SQL_FeatureTable` / `SQL_NarrowTable` / `SQL_TimeSeriesTable` / `SQL_MappingTable` / `SQL_ConstituentTable` / `SQL_FinancialTable`（复用自 `QuantStudio.Factor.FactorUtils.SQL_Table`）

---

## 2. 存储结构

DuckDB 支持两种存储模式：

| 模式 | DBFile 参数 | 说明 |
|------|------------|------|
| 内存模式 | `:memory:`（默认） | 数据仅在连接期间存在，断开后丢失 |
| 文件模式 | 文件路径，如 `C:/Data/factors.duckdb` | 数据持久化到磁盘 |

数据库中的表使用 `InnerPrefix` 作为内部前缀以区分 QS 因子表和其他表。

### 表结构

每张 QS 因子表对应数据库中的一张物理表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `DTField`（默认 `datetime`） | `VARCHAR NOT NULL` | 时点字段 |
| `IDField`（默认 `code`） | `VARCHAR NOT NULL` | ID 字段 |
| 自定义因子字段 | `DOUBLE` 或 `VARCHAR` | 因子数据列 |

> 与 SQLite3DB 不同，DuckDB 不使用 PRIMARY KEY 约束，因为其内部索引会阻止 `ALTER TABLE ... DROP COLUMN` 操作。写入时采用 "先删除冲突数据、再插入新数据" 的策略保证数据一致性。

### 元数据管理

元数据分为两层，均存储于内存中的 `pd.DataFrame`：

| 元数据 | 变量 | 索引 | 说明 |
|--------|------|------|------|
| `_TableInfo` | `DataFrame` | `TableName` | 表名 → `DBTableName`、`TableClass`、`Description` |
| `_FactorInfo` | `DataFrame` | `(TableName, FieldName)` | 因子名 → `DBFieldName`、`DataType`、`FieldType`、`Supplementary`、`Description` |

`connect()` 时通过 `information_schema.tables` 查找所有符合前缀的表，再通过 `PRAGMA table_info` 逐表扫描字段信息。

### 字段类型映射

| DuckDB 类型 | FieldType | 说明 |
|-------------|-----------|------|
| 包含 `varchar` / `text` / `char` / `string` 且字段名 = `IDField` | `ID` | ID 字段 |
| 包含 `varchar` / `text` / `char` / `string` 且字段名 = `DTField` | `Date`（Supplementary=`Default`） | 默认时点字段 |
| 包含 `varchar` / `text` / `char` / `string` | `Date` | 其他时点字段 |
| 包含 `timestamp` / `datetime` / `date` | `Date` | 时点字段（时间戳类型，Parquet 数据常用） |
| 其他 | `因子` | 普通因子 |

### Parquet 外部数据源

通过 `ParquetDir` 参数可指定 Parquet 文件根目录。`connect()` 时自动扫描目录树，为每个 `data_class` 子目录创建 DuckDB 视图。该功能依赖 DuckDB 原生的 [`read_parquet`](https://duckdb.org/docs/data/parquet) 函数，利用 Hive 分区自动推断 `dt` 分区列。

**目录结构要求**（兼容 DataScrapy 的 `ParquetPipeline` 输出）：

```
parquet_data/
├── stock_cn_minute_bar/
│   ├── dt=2026-06-01/
│   │   ├── part-0.parquet
│   │   └── part-1.parquet
│   └── dt=2026-06-02/
│       └── part-0.parquet
├── stock_cn_transaction/
│   └── ...
└── exceptions/    ← 自动跳过
    └── ...
```

**注册规则**：

| 行为 | 说明 |
|------|------|
| 视图命名 | `InnerPrefix + data_class 名`，如 `qs_stock_cn_minute_bar` |
| 同名冲突 | 原生表优先，已存在的表不会被覆盖 |
| 分区列 | Hive 分区 `dt=YYYY-MM-DD` 自动转为 `dt` 列（VARCHAR），可用于 SQL 过滤 |
| 异常目录 | `exceptions/` 目录自动跳过 |
| 失败处理 | 单个目录注册失败仅输出 warning，不影响数据库连接 |

**限制**：

- Parquet 视图为**只读**，所有写操作（`writeData`、`deleteData`、`addFactor`、`renameFactor` 等）均被拒绝并抛出 `__QS_Error__`
- `deleteTable` 对 Parquet 视图执行 `DROP VIEW`（而非 `DROP TABLE`）
- 数据管理（分区、过期）需由数据生产方（如 DataScrapy 的 `ParquetPipeline`）负责

---

## 3. SQL 方言

DuckDB 的 SQL 方言兼容 PostgreSQL。框架通过 `_SQLFun` 字典适配 SQL 函数：

```python
_SQLFun = {
    "toDate": "CAST(%s AS DATE)",
    "toString": "CAST(%s AS VARCHAR)",
}
```

> DuckDB 使用双引号 `"` 引用标识符，而非 SQLite3 的方括号 `[]`。

---

## 4. 参数说明

### DuckDB 参数

继承自 `WritableFactorDB.__QS_ArgClass__`，增加以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"DuckDB"` | 因子库名称（不可变） |
| `DBFile` | `str` | `":memory:"` | DuckDB 数据库文件路径（不可变） |
| `InnerPrefix` | `str` | `"qs_"` | 内部表名前缀，用于筛选 QS 管理的表（不可变） |
| `DTField` | `str` | `"datetime"` | 默认时点字段名（不可变） |
| `IDField` | `str` | `"code"` | 默认 ID 字段名（不可变） |
| `DTFmt` | `str` | `"%Y-%m-%d %H:%M:%S"` | 时点存储与解析格式（不可变） |
| `IgnoreFields` | `List[str]` | `[]` | 扫描时忽略的字段名（不可变） |
| `FTArgs` | `dict` | `{}` | 创建因子表时使用的默认参数（不可变） |
| `TablePrefix` | `str` | `""` | 物理表名前缀（不可变） |
| `CheckWriteData` | `bool` | `False` | 写入时是否检查并校正数据（可变） |
| `CheckNullable` | `bool` | `False` | 写入时是否检查并移除 NULL 值（可变） |
| `ParquetDir` | `str` | `""` | Parquet 文件根目录，设置后将自动注册各 data_class 子目录为只读视图（不可变） |

### 配置文件

参数可从配置文件 `~/QuantStudioConfig/DuckDBConfig.json` 加载。示例：

```json
{
    "DBFile": "C:/Data/factors.duckdb",
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

## 5. API 方法

### 5.1 连接管理

#### `connect() -> DuckDB`

连接数据库，扫描原生表并注册 Parquet 外部视图（若配置了 `ParquetDir`）。返回 `self` 以支持链式调用。

```python
from QSExt.Factor.DuckDB import DuckDB

# 内存数据库（默认）
DDB = DuckDB().connect()

# 文件数据库
DDB = DuckDB(args={"DBFile": "C:/Data/factors.duckdb"}).connect()

# Parquet 外部数据源（只读）
DDB = DuckDB(args={"ParquetDir": "D:/Data/QSData/DataScrapy/Parquet"}).connect()

# 混合使用：文件数据库 + Parquet 视图
DDB = DuckDB(args={
    "DBFile": "C:/Data/factors.duckdb",
    "ParquetDir": "D:/Data/QSData/DataScrapy/Parquet",
}).connect()
```

#### `disconnect() -> int`

断开数据库连接。

```python
DDB.disconnect()
```

#### `Connection -> DuckDBPyConnection`

获取底层 `duckdb.DuckDBPyConnection` 对象，可用于执行原生 SQL。

```python
print(DDB.Connection.execute("SELECT version()").fetchone())
```

### 5.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有表名（按字母排序）。

#### `getTable(table_name: str, args: dict = {}) -> SQL_Table`

获取指定名称的因子表对象。

```python
# 自动判断类型
FT = DDB.getTable("stock_cn_day_bar")

# 显式指定为财务因子表
FT = DDB.getTable("test_financial", args={
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

删除因子表。原生表执行 `DROP TABLE IF EXISTS`；Parquet 视图执行 `DROP VIEW IF EXISTS`。

#### `createTable(table_name: str, field_types: Dict[str, str])`

手动创建因子表。`field_types` 格式为 `{因子名: DuckDB数据类型}`，会自动添加 `DTField` 和 `IDField` 字段。

```python
DDB.createTable("my_table", {
    "Factor0": "DOUBLE",
    "Factor1": "VARCHAR",
})
```

### 5.3 因子操作

#### `addFactor(table_name: str, field_types: Dict[str, str])`

向已有表添加新因子列。底层逐列执行 `ALTER TABLE ... ADD COLUMN`。

#### `renameFactor(table_name, old_factor_name, new_factor_name)`

重命名因子。底层执行 `ALTER TABLE ... RENAME COLUMN`。

#### `deleteFactor(table_name, factor_names: List[str])`

删除因子。底层逐列执行 `ALTER TABLE ... DROP COLUMN`。如果表上存在外部索引，会自动删除索引后重试。如果删除后表内只剩下 `datetime` 和 `code` 字段，表不会被自动删除。

### 5.4 数据写入

#### `writeData(data: Panel, table_name: str, if_exists="update", data_type={})`

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

> DuckDB 中不使用 `INSERT OR REPLACE`（需要 UNIQUE/PRIMARY KEY 约束），而是先 `DELETE` 冲突的 `(dt, code)` 数据，再 `INSERT` 新数据。

```python
from QuantStudio.Core.QSObject import Panel

Data = Panel({
    "close": pd.DataFrame(...),
    "volume": pd.DataFrame(...),
})
DDB.writeData(data=Data, table_name="stock_cn_day_bar", if_exists="update")
```

#### `deleteData(table_name, ids=None, dts=None, dt_ids=None)`

删除指定条件的数据。

- `ids=None` 且 `dts=None`：清空整张表
- 指定 `ids`：删除指定 ID 的所有数据
- 指定 `dts`：删除指定时点的所有数据
- 指定 `dt_ids`：精确删除 (时点, ID) 对

### 5.5 数据读取（SQL_Table）

因子表对象提供标准的 QuantStudio 数据读取接口：

#### `FactorNames -> List[str]`

返回表中的所有字段名（包含 `DTField` 和 `IDField`）。

#### `getID(ifactor_name=None, idt=None) -> List[str]`

获取 ID 序列。

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None) -> List[datetime]`

获取时点序列。

#### `readData(factor_names, ids, dts) -> Panel`

读取因子数据。返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`。

```python
FT = DDB.getTable("stock_cn_day_bar")
Data = FT.readData(
    factor_names=["close", "volume"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 2)]
)
```

---

## 6. 使用示例

### 6.1 基本流程

```python
import datetime as dt
import numpy as np
import pandas as pd

from QSExt.Factor.DuckDB import DuckDB
from QuantStudio.Core.QSObject import Panel

# 连接因子库（内存模式）
DDB = DuckDB().connect()

# 准备数据
nDT, nID = 100, 20
IDs = [f"{i:06d}.SZ" for i in range(1, nID + 1)]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]

Data = {
    "close": pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTs, columns=IDs),
    "volume": pd.DataFrame(np.random.rand(nDT, nID) * 100, index=DTs, columns=IDs),
}
DDB.writeData(data=Panel(Data), table_name="stock_cn_day_bar", if_exists="update")

# 读取数据
FT = DDB.getTable("stock_cn_day_bar")
print("因子列表:", FT.FactorNames)
print("ID 列表:", FT.getID()[:5])
print("时点范围:", FT.getDateTime()[0], "~", FT.getDateTime()[-1])

# 读取指定因子、ID、时点
Data = FT.readData(factor_names=["close"], ids=IDs[:5], dts=DTs[:10])
print(Data)
```

### 6.2 带参数的因子表读取

```python
# 忽略时间部分，按日期匹配
FT = DDB.getTable("stock_cn_day_bar", args={"IgnoreTime": True})

# 指定 LookBack 回溯填充
FT = DDB.getTable("stock_cn_day_bar", args={"LookBack": 5})

# 附带筛选条件
FT = DDB.getTable("stock_cn_day_bar", args={
    "FilterCondition": "{Table}.volume > 0"
})
```

### 6.3 增量更新数据

```python
# 首次写入
DDB.writeData(data=Panel({"factor1": initial_data}), table_name="my_table")

# 增量追加（不覆盖已有非空值）
DDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="append"
)

# 增量覆盖（仅更新非空值到已有数据）
DDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="update_notnull"
)
```

### 6.4 管理操作

```python
# 查看所有表
print(DDB.TableNames)

# 重命名表
DDB.renameTable("old_name", "new_name")

# 删除表
DDB.deleteTable("table_to_delete")

# 重命名因子
DDB.renameFactor("my_table", "old_factor", "new_factor")

# 删除因子
DDB.deleteFactor("my_table", ["factor_to_remove"])

# 为已有表添加新因子
DDB.addFactor("my_table", {"new_factor": "DOUBLE"})

# 删除指定 ID 的数据
DDB.deleteData("my_table", ids=["000001.SZ"])

# 删除指定时点的数据
DDB.deleteData("my_table", dts=[dt.datetime(2025, 1, 15)])
```

### 6.5 文件持久化

```python
# 文件数据库
DDB = DuckDB(args={
    "DBFile": "C:/Data/my_factors.duckdb",
    "InnerPrefix": "qs_",
}).connect()

# 写入数据后，数据持久化到磁盘
DDB.writeData(data=Panel({...}), table_name="persistent_table")
DDB.disconnect()

# 下次使用时重新连接，数据自动可用
DDB2 = DuckDB(args={"DBFile": "C:/Data/my_factors.duckdb"}).connect()
print(DDB2.TableNames)  # 包含 'persistent_table'
```

### 6.6 Parquet 外部数据源

```python
from QSExt.Factor.DuckDB import DuckDB

# 连接 Parquet 数据目录（兼容 DataScrapy 的 ParquetPipeline 输出）
DDB = DuckDB(args={
    "ParquetDir": r"D:\Data\QSData\DataScrapy\Parquet",
}).connect()

# Parquet 视图和原生表统一管理
print(DDB.TableNames)
# ['stock_cn_minute_bar', 'stock_cn_transaction', ...]

# 读取 Parquet 数据，用法与原生表完全一致
FT = DDB.getTable("stock_cn_minute_bar")
print("因子列表:", [f for f in FT.FactorNames if f not in ("code", "datetime")])
print("ID 列表:", FT.getID()[:5])

# 按日期范围读取（dt 分区列自动可用）
DTs = FT.getDateTime(start_dt=dt.datetime(2026, 6, 1), end_dt=dt.datetime(2026, 6, 5))
Data = FT.readData(
    factor_names=["open", "high", "low", "close", "volume"],
    ids=["000001.SZ"],
    dts=DTs,
)
print(Data)

# 写入操作会被拒绝
try:
    DDB.writeData(data=Panel({...}), table_name="stock_cn_minute_bar")
except __QS_Error__ as e:
    print(f"预期错误: {e}")  # Parquet 视图为只读

# 同时使用原生表和 Parquet 视图
DDB2 = DuckDB(args={
    "DBFile": "C:/Data/research.duckdb",
    "ParquetDir": r"D:\Data\QSData\DataScrapy\Parquet",
}).connect()
# TableNames 包含原生持久化表 + Parquet 视图
```

### 6.7 混合使用：计算结果写入原生表，原始数据来自 Parquet

```python
# 场景：从 Parquet 读取分钟行情计算日频因子，结果写入原生表
DDB = DuckDB(args={
    "DBFile": "C:/Data/my_factors.duckdb",
    "ParquetDir": r"D:\Data\QSData\DataScrapy\Parquet",
}).connect()

# 1. 从 Parquet 视图读取原始数据
RawFT = DDB.getTable("stock_cn_minute_bar")
RawData = RawFT.readData(
    factor_names=["close", "volume"],
    ids=["000001.SZ", "000002.SZ"],
    dts=some_dts,
)

# 2. 计算因子（自定义逻辑）
# ... 计算得到 DailyFactor (Panel)

# 3. 写入原生 DuckDB 表（持久化）
DDB.writeData(data=DailyFactor, table_name="my_daily_factors", if_exists="update")

# 4. 后续使用时，两个表都可用
print(DDB.TableNames)
# ['my_daily_factors', 'stock_cn_minute_bar', 'stock_cn_transaction']
DDB.disconnect()
```

---

## 7. 因子表类型说明

DuckDB 支持 7 种因子表类型，与 SQLite3DB 完全一致：

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

---

## 8. 与 SQLite3DB 的对比

| 特性 | DuckDB | SQLite3DB |
|------|--------|-----------|
| 数据库 | DuckDB | SQLite3 |
| 存储引擎 | 列式存储（OLAP） | 行式存储（OLTP） |
| 分析查询性能 | 显著更快（向量化执行） | 一般 |
| SQL 方言 | PostgreSQL 兼容 | SQLite3 特有 |
| 标识符引用 | 双引号 `"` | 方括号 `[]` |
| PRIMARY KEY | 不使用（会阻止 DROP COLUMN） | 使用 |
| 索引 | 不需要（列式引擎） | 使用 B-Tree 索引 |
| upsert 方式 | DELETE + INSERT | INSERT OR REPLACE |
| 外部数据读取 | 直接查询 Parquet、CSV、JSON 文件；通过视图注册实现零拷贝读取 | 不支持 |
| Parquet 视图 | 支持，自动扫描 Hive 分区，与原生表统一查询 | 不支持 |
| 并发写入 | 多进程可同时读，写入串行 | 单写入者 |
| 部署复杂度 | `pip install duckdb` + `pyarrow`（Parquet 场景） | Python 标准库内置 |
| 适用场景 | 本地分析、中大规模因子计算、离线 Parquet 查询 | 本地开发、轻量级测试 |

---

## 9. 依赖

| 包 | 用途 |
|---|------|
| `duckdb` | 数据库驱动（需 `pip install duckdb`） |
| `pyarrow` | Parquet 文件读写（Parquet 场景必需，`conda install -c conda-forge pyarrow`） |
| `numpy` | 数值计算 |
| `pandas` | 数据框操作 |
| `pydantic` | 参数校验 |
| `QuantStudio.Core` | `__QS_Error__`、`Panel` 等基础类 |
| `QuantStudio.Factor.FactorDB` | `WritableFactorDB` 基类 |
| `QuantStudio.Factor.FactorUtils` | `SQL_*` 因子表类 |
| `QuantStudio.Tools.SQLDBFun` | `genSQLInCondition` SQL 工具函数 |

---

## 10. 注意事项

1. **数据类型**：DOUBLE 用于数值型因子，VARCHAR 用于字符串型因子，不支持 Python 对象的原生存储
2. **DROP COLUMN 限制**：DuckDB 在表上有索引时不允许 DROP COLUMN。本实现不在表上创建索引，但如果外部创建了索引，`deleteField` 会先尝试删除索引再删列
3. **写入策略**：不使用 `INSERT OR REPLACE`（因无 UNIQUE 约束），改为先 `DELETE` 冲突行再 `INSERT`。这保证了数据一致性
4. **时点格式一致性**：`DTFmt` 参数同时控制写入时的格式化和读取/删除时的日期匹配，务必保持一致。默认格式 `"%Y-%m-%d %H:%M:%S"` 适用于日频及以上数据
5. **内存数据库**：`:memory:` 仅在单连接内有效，断开连接后数据丢失。如果需要跨连接共享内存数据库，DuckDB 不支持（这是 DuckDB 的设计限制）
6. **文件数据库**：DuckDB 数据库文件与版本相关（当前为 1.5.x），升级 DuckDB 版本后可能需要手动迁移数据库文件
7. **字段名冲突**：`DTField` 和 `IDField` 为保留字段名，不应与因子名重复
8. **Parquet 视图只读**：`ParquetDir` 注册的视图不支持写入操作（`writeData`、`deleteData`、`addFactor` 等），如需写入请使用 `DBFile` 文件模式的原生表。`deleteTable` 对 Parquet 视图执行 `DROP VIEW`
9. **Parquet 依赖**：读取 Parquet 文件需要安装 `pyarrow` 和 `duckdb`，可使用 `conda install -c conda-forge pyarrow duckdb` 安装
10. **分区裁剪**：查询 Parquet 视图时，在 SQL 的 WHERE 子句中使用 `dt` 列可触发 DuckDB 的 Hive 分区裁剪，显著减少扫描文件数。通过 `readData` 的 `dts` 参数间接实现时间范围过滤
11. **混合使用**：`DBFile` 和 `ParquetDir` 可同时指定，一个 `DuckDB` 实例同时管理计算结果表（原生写入）和爬虫产出的 Parquet 文件（只读查询），`TableNames` 统一返回两者

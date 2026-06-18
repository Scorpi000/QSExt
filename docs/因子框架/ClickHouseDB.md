# ClickHouseDB — 基于 ClickHouse 的因子库

## 1. 概述

ClickHouseDB 是基于 [ClickHouse](https://clickhouse.com/) 列式数据库的因子库实现，继承自 `SQLDB`，支持因子数据的读写、追加更新和管理功能。ClickHouse 是一个面向在线分析处理（OLAP）的高性能列式数据库，适合大规模时序数据的存储和聚合查询。

- **类名**：`ClickHouseDB`
- **模块**：`QSExt.Factor.ClickHouseDB`
- **基类**：`QSExt.Tools.ClickHouseFun.QSClickHouseObject` + `QuantStudio.Factor.SQLDB.SQLDB`
- **因子表类**：`SQL_WideTable` / `SQL_FeatureTable` / `SQL_NarrowTable` / `SQL_TimeSeriesTable` / `SQL_MappingTable`（继承自 `QuantStudio.Factor.FactorUtils.SQL_Table`）

---

## 2. 存储结构

### 表结构

每张 QS 因子表对应 ClickHouse 数据库中的一张 MergeTree 引擎表，表名 = `InnerPrefix` + 表名（默认前缀 `qs_`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `DTField`（默认 `datetime`） | `DateTime` | 时点字段 |
| `IDField`（默认 `code`） | `String` | ID 字段，MergeTree 排序键 |
| 自定义因子字段 | `Float64` 或 `Nullable(String)` | 因子数据列 |

MergeTree 引擎以 `IDField` 作为 `ORDER BY` 键，适合按 ID 高效查询。

### 元数据管理

元数据在 `connect()` 时通过查询 `system.columns` 系统表自动扫描，存储于内存中的 `pd.DataFrame`：

| 元数据 | 变量 | 索引 | 说明 |
|--------|------|------|------|
| `_TableInfo` | `DataFrame` | `TableName` | 表名 → `DBTableName`、`TableClass` |
| `_FactorInfo` | `DataFrame` | `(TableName, FieldName)` | 因子名 → `DBFieldName`、`DataType`、`FieldType`、`Supplementary`、`Description`、`FieldKey` |

扫描 SQL：

```sql
SELECT RIGHT(table, CHAR_LENGTH(table)-{nPrefix}) AS TableName,
       table AS DBTableName, name AS DBFieldName, LOWER(type) AS DataType
FROM system.columns
WHERE database='{DBName}' AND table LIKE '{InnerPrefix}%%'
  AND name NOT IN ({IgnoreFields})
ORDER BY TableName, DBFieldName
```

### 字段类型映射

| ClickHouse 类型 | FieldType | 说明 |
|----------------|-----------|------|
| 包含 `date`（不区分大小写） | `Date` | 时点字段 |
| 包含 `str` / `uuid` / `ip` 且字段名 = `IDField` | `ID` | ID 字段 |
| 其他 | `因子` | 普通因子 |

写入时的数据类型识别：

| 数据情况 | ClickHouse 类型 |
|---------|----------------|
| 可转换为 `float` | `Float64` |
| 其他 | `Nullable(String)` |

---

## 3. 参数说明

### ClickHouseDB 参数

继承自 `QSClickHouseObject.__QS_ArgClass__` 和 `SQLDB.__QS_ArgClass__`，合并后的参数列表：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"ClickHouseDB"` | 因子库名称（不可变） |
| `DBType` | `Literal["ClickHouse"]` | `"ClickHouse"` | 数据库类型（不可变） |
| `DBName` | `str` | `"qsdata"` | 数据库名称（不可变） |
| `IPAddr` | `str` | `"localhost"` | 服务地址（不可变） |
| `Port` | `int` | `9000` | TCP 端口，使用原生协议（不可变） |
| `User` | `str` | `""` | 用户名（不可变） |
| `Pwd` | `str` | `""` | 密码（不可变） |
| `DSN` | `str` | `""` | DSN 连接字符串，优先级高于 IP/Port（不可变） |
| `TablePrefix` | `str` | `""` | 物理表名前缀（不可变） |
| `Connector` | `Literal["default", "clickhouse-driver"]` | `"default"` | 连接器（不可变） |
| `InnerPrefix` | `str` | `"qs_"` | 内部表名前缀（不可变） |
| `DTField` | `str` | `"datetime"` | 默认时点字段名（不可变） |
| `IDField` | `str` | `"code"` | 默认 ID 字段名（不可变） |
| `IgnoreFields` | `List[str]` | `[]` | 扫描时忽略的字段名（不可变） |
| `FTArgs` | `dict` | `{}` | 因子表默认参数（不可变） |
| `CheckWriteData` | `bool` | `False` | 写入时是否检查并校正数据（可变） |
| `AdjustTableName` | `bool` | `True` | 连接时是否调整表名大小写（不可变） |

### 配置文件

参数从配置文件 `~/QuantStudioConfig/ClickHouseDBConfig.json` 加载。示例：

```json
{
    "Name": "ClickHouseDB",
    "DBType": "ClickHouse",
    "DBName": "qsdata",
    "IPAddr": "localhost",
    "Port": 9000,
    "User": "shzq",
    "Pwd": "shzq#321",
    "InnerPrefix": "qs_",
    "CharSet": "utf8",
    "Connector": "default",
    "IDField": "code",
    "DTField": "datetime",
    "IgnoreFields": ["info", "id"]
}
```

> **注意**：`Port` 必须使用 ClickHouse 的原生 TCP 端口（默认 `9000`），而非 HTTP 端口（默认 `8123`）。`clickhouse-driver` 使用原生协议通信。

### SQL_Table 参数（通过 `getTable` 的 `args` 传入）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TableType` | `str` | 自动判断 | 因子表类型，可选 `WideTable`、`FeatureTable`、`NarrowTable`、`TimeSeriesTable`、`MappingTable` |
| `DTField` | `str` / `None` | 自动判断 | 时点字段名 |
| `IDField` | `str` / `None` | 自动判断 | ID 字段名 |
| `MultiMapping` | `bool` | 自动判断 | 是否允许多重映射 |
| `IgnoreTime` | `bool` | `False` | 是否忽略时间部分 |
| `LookBack` | `int` | `0` | 缺失填充回溯天数 |
| `FilterCondition` | `str` | `""` | 附加 SQL WHERE 条件 |
| `PreFilterID` | `bool` | `True` | 是否在 SQL 中预筛选 ID |

---

## 4. API 方法

### 4.1 连接管理

#### `connect() -> ClickHouseDB`

连接 ClickHouse 数据库，扫描表信息。返回 `self` 以支持链式调用。

```python
from QSExt.Factor.ClickHouseDB import ClickHouseDB

# 使用配置文件（默认路径）
FDB = ClickHouseDB().connect()

# 指定自定义配置文件
FDB = ClickHouseDB(config_file="/path/to/config.json").connect()

# 运行时覆盖参数
FDB = ClickHouseDB(args={"DBName": "my_db", "IPAddr": "192.168.1.100"}).connect()
```

#### `disconnect() -> int`

断开数据库连接。

```python
FDB.disconnect()
```

#### `Connection -> clickhouse_driver.Connection`

获取底层 `clickhouse_driver.Connection` 对象，可用于执行原生 SQL。

```python
pd.read_sql_query("SELECT * FROM qs_my_table", FDB.Connection)
```

### 4.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有表名（按字母排序）。

#### `getTable(table_name: str, args: dict = {}) -> SQL_Table`

获取指定名称的因子表对象。

```python
FT = FDB.getTable("stock_cn_day_bar")
FT = FDB.getTable("my_table", args={"MultiMapping": True})
```

#### `renameTable(old_table_name: str, new_table_name: str)`

重命名因子表。底层执行 `RENAME TABLE`。

#### `deleteTable(table_name: str)`

删除因子表。底层执行 `DROP TABLE IF EXISTS`。

#### `createTable(table_name: str, field_types: Dict[str, str])`

手动创建因子表。`field_types` 格式为 `{因子名: ClickHouse数据类型}`，会自动添加 `DTField` 和 `IDField`。表引擎为 MergeTree，以 `IDField` 作为排序键。

```python
FDB.createTable("my_table", {
    "factor1": "Float64",
    "factor2": "Nullable(String)",
})
```

### 4.3 因子操作

#### `addFactor(table_name: str, field_types: Dict[str, str])`

向已有表添加新因子列。底层逐列执行 `ALTER TABLE ... ADD COLUMN`。

#### `renameFactor(table_name, old_factor_name, new_factor_name)`

重命名因子。底层执行 `ALTER TABLE ... RENAME COLUMN`。

#### `deleteFactor(table_name, factor_names: List[str])`

删除因子。底层逐列执行 `ALTER TABLE ... DROP COLUMN`。

### 4.4 数据写入

#### `writeData(data: Panel, table_name: str, if_exists="update", data_type={}) -> int`

批量写入因子表数据。如果表不存在则自动创建，如果写入的因子列不存在则自动添加。

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | `Panel` | 因子数据，items=因子名，major_axis=时点，minor_axis=ID |
| `table_name` | `str` | 表名 |
| `if_exists` | `"update"` / `"append"` / `"update_notnull"` | 写入方式 |
| `data_type` | `dict` | `{因子名: "double"/"string"}`，未指定时根据 dtype 自动识别 |

写入方式说明：

| 方式 | 行为 |
|------|------|
| `update` | 覆盖写入指定的时点 x ID 范围内的数据，未指定的因子列保留旧值 |
| `append` | 仅填充原有 NaN 位置，不覆盖已有非空值 |
| `update_notnull` | 新数据非空时覆盖旧值，新数据为空时保留旧值 |

写入流程：先执行 `DELETE` 删除指定范围的数据，再执行 `INSERT` 写入新数据。ClickHouse 的 `DELETE` 是异步 Mutation，不立即释放磁盘空间。

```python
from QuantStudio.Core.QSObject import Panel

Data = Panel({
    "close": pd.DataFrame(...),
    "volume": pd.DataFrame(...),
})
FDB.writeData(data=Data, table_name="stock_cn_day_bar", if_exists="update")
```

#### `deleteData(table_name, ids=None, dts=None, dt_ids=None)`

删除指定条件的数据。

- `ids=None` 且 `dts=None`：清空整张表（`TRUNCATE TABLE`）
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
FT = FDB.getTable("stock_cn_day_bar")
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

from QSExt.Factor.ClickHouseDB import ClickHouseDB
from QuantStudio.Core.QSObject import Panel

# 连接因子库
FDB = ClickHouseDB().connect()

# 准备数据
nDT, nID = 100, 20
IDs = [f"{i:06d}.SZ" for i in range(1, nID + 1)]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]

Data = {
    "close": pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTs, columns=IDs),
    "volume": pd.DataFrame(np.random.rand(nDT, nID) * 100, index=DTs, columns=IDs),
}
FDB.writeData(data=Panel(Data), table_name="stock_cn_day_bar", if_exists="update")

# 读取数据
FT = FDB.getTable("stock_cn_day_bar")
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

### 5.2 增量更新数据

```python
# 首次写入
FDB.writeData(data=Panel({"factor1": initial_data}), table_name="my_table")

# 增量追加（不覆盖已有非空值）
FDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="append"
)

# 增量覆盖（仅更新非空值到已有数据）
FDB.writeData(
    data=Panel({"factor1": new_data}),
    table_name="my_table",
    if_exists="update_notnull"
)
```

### 5.3 管理操作

```python
# 查看所有表
print(FDB.TableNames)

# 重命名表
FDB.renameTable("old_name", "new_name")

# 删除表
FDB.deleteTable("table_to_delete")

# 重命名因子
FDB.renameFactor("my_table", "old_factor", "new_factor")

# 删除因子
FDB.deleteFactor("my_table", ["factor_to_remove"])

# 为已有表添加新因子
FDB.addFactor("my_table", {"new_factor": "Float64"})

# 删除指定 ID 的数据
FDB.deleteData("my_table", ids=["000001.SZ"])
```

### 5.4 字符串因子写入

```python
Data = pd.DataFrame(
    [["hello", "world"], [None, "test"]],
    index=[dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 2)],
    columns=["000001.SZ", "600000.SH"],
    dtype=object,
)
FDB.writeData(
    data=Panel({"str_factor": Data}),
    table_name="my_table",
    data_type={"str_factor": "string"},
)
```

### 5.5 断开连接

```python
FDB.disconnect()
```

---

## 6. Docker 部署

### 6.1 启动 ClickHouse 容器

推荐使用 Docker 命名卷存储数据：

```bash
# 创建命名卷
docker volume create clickhouse-data

# 启动容器
docker run -d --name clickhouse-server \
  -v clickhouse-data:/var/lib/clickhouse \
  -p 9000:9000 \
  -p 8123:8123 \
  clickhouse/clickhouse-server:latest
```

### 6.2 Windows 环境注意事项

在 Windows + Docker 环境下，**不要**使用绑定挂载（bind mount）作为 ClickHouse 的数据目录：

```bash
# 错误：绑定挂载不支持 MergeTree
docker run -d -v C:/data/clickhouse:/var/lib/clickhouse ...

# 正确：使用 Docker 命名卷
docker run -d -v clickhouse-data:/var/lib/clickhouse ...
```

**原因**：MergeTree 引擎在写入数据部件（data part）时依赖 Linux 的原子目录重命名操作（`rename`）。Windows 的 NTFS 文件系统不支持此操作，会导致 `DiskLocal::moveDirectory` 错误。Docker 命名卷使用 WSL2 的 ext4 文件系统，支持原子操作。

### 6.3 端口说明

| 端口 | 协议 | 用途 |
|------|------|------|
| `9000` | 原生 TCP | `clickhouse-driver` 连接使用 |
| `8123` | HTTP | Web 界面、curl 请求使用 |

本因子库使用 `clickhouse-driver`，必须连接 `9000` 端口。

---

## 7. 依赖

| 包 | 用途 |
|---|------|
| `clickhouse-driver` | ClickHouse 原生 TCP 协议驱动 |
| `numpy` | 数值计算 |
| `pandas` | 数据框操作 |
| `pydantic` | 参数校验 |
| `QuantStudio.Core` | `__QS_Error__`、`Panel` 等基础类 |
| `QuantStudio.Factor.SQLDB` | `SQLDB` 基类 |
| `QuantStudio.Factor.FactorUtils` | `SQL_*` 因子表类 |
| `QuantStudio.Tools.SQLDBFun` | `genSQLInCondition` SQL 工具函数 |
| `QSExt.Tools.ClickHouseFun` | `QSClickHouseObject` ClickHouse 对象基类 |

---

## 8. 注意事项

1. **端口**：必须使用原生 TCP 端口 `9000`，而非 HTTP 端口 `8123`
2. **Docker 存储**：Windows 环境下必须使用 Docker 命名卷，不支持绑定挂载
3. **DELETE 语义**：ClickHouse 的 `DELETE` 是异步 Mutation，不会立即释放磁盘空间，大量小批量删除会影响性能
4. **主键**：MergeTree 以 `IDField`（默认 `code`）作为排序键，按 ID 查询效率最高；按 `DTField` 范围查询为全表扫描
5. **数据类型**：写入时自动识别为 `Float64` 或 `Nullable(String)`，不支持 ClickHouse 特有类型（如 `Array`、`Tuple`）的自动推断
6. **并发写入**：ClickHouse 不支持对同一 MergeTree 表的高并发写入，建议批量写入
7. **字段名冲突**：`DTField` 和 `IDField` 为保留字段名，不应与因子名重复

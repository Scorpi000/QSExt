# MongoDB — 基于 MongoDB 的因子库

## 1. 概述

MongoDB 是基于 [MongoDB](https://www.mongodb.com/) 文档数据库的因子库实现，继承自 `WritableFactorDB`，支持因子数据的读写、追加更新和管理功能。MongoDB 使用 BSON 文档存储数据，具备灵活的文档模型和良好的水平扩展能力。

- **类名**：`MongoDB`
- **模块**：`QSExt.Factor.MongoDB`
- **基类**：`QuantStudio.Factor.FactorDB.WritableFactorDB`
- **因子表类**：`_WideTable`（内部类，仅支持宽表）

---

## 2. 存储结构

### 集合映射

每张 QS 因子表对应 MongoDB 中的一个集合（collection），集合名 = `InnerPrefix` + 表名（默认前缀 `qs_`）。

每份文档为一条记录，包含时点、ID 和所有因子值。

### 文档结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `datetime` | `datetime` | 时点字段 |
| `code` | `str` | ID 字段 |
| 自定义因子字段 | `float` / `str` | 因子数据列 |

### 元数据文档

每个集合中包含一条特殊的元数据文档，以 `code="_TableInfo"` 标识：

```json
{
    "datetime": null,
    "code": "_TableInfo",
    "factor1": {"DataType": "double"},
    "factor2": {"DataType": "string"}
}
```

`connect()` 时扫描所有符合前缀的集合，读取各集合的 `_TableInfo` 文档，获得每个因子表包含的因子及其数据类型。

### 索引

创建表时自动建立两个索引：

| 索引 | 字段 | 说明 |
|------|------|------|
| `datetime_code` | `(datetime ASC, code ASC)` | 复合索引，加速按时点和 ID 的联合查询 |
| `code` | `(code HASHED)` | 哈希索引，加速按 ID 查询 |

### 字段类型映射

| 写入数据 dtype | MongoDB 存储类型 | 说明 |
|---------------|-----------------|------|
| 数值类型（`float64`、`int64` 等） | `double` | 数值型因子 |
| 其他（`object`） | `string` | 字符串型因子 |

---

## 3. 参数说明

### MongoDB 参数

继承自 `WritableFactorDB.__QS_ArgClass__`，增加以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"MongoDB"` | 因子库名称（不可变） |
| `DBType` | `str` | `"Mongo"` | 数据库类型（不可变） |
| `DBName` | `str` | `"Scorpion"` | 数据库名 |
| `IPAddr` | `str` | `"127.0.0.1"` | IP 地址 |
| `Port` | `int` | `27017` | 端口 |
| `User` | `str` | `"root"` | 用户名 |
| `Pwd` | `str` | `""` | 密码 |
| `CharSet` | `str` | `"utf8"` | 字符集 |
| `Connector` | `str` | `"default"` | 连接器，可选 `"pymongo"` |
| `InnerPrefix` | `str` | `"qs_"` | 内部集合名前缀 |
| `IgnoreFields` | `list` | `[]` | 扫描时忽略的字段名 |

### 配置文件

参数从配置文件 `~/QuantStudioConfig/MongoDBConfig.json` 加载。示例：

```json
{
    "Name": "MongoDB",
    "DBType": "Mongo",
    "DBName": "QSData",
    "IPAddr": "localhost",
    "Port": 27017,
    "User": "root",
    "Pwd": "",
    "InnerPrefix": "qs_",
    "CharSet": "utf8",
    "Connector": "default"
}
```

### _WideTable 参数（通过 `getTable` 的 `args` 传入）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TableType` | `str` | `"宽表"` | 因子表类型（不可变，仅支持 `"宽表"`） |
| `LookBack` | `float` | `0` | 回溯天数，`inf` 表示回溯全部历史填充缺失值 |
| `FilterCondition` | `list` | `[]` | MongoDB 筛选条件列表，额外的查询过滤 |
| `DTField` | `str` | `"datetime"` | 时点字段名 |
| `IDField` | `str` | `"code"` | ID 字段名 |

---

## 4. API 方法

### 4.1 连接管理

#### `connect() -> MongoDB`

连接 MongoDB 数据库，扫描所有集合以建立因子表索引。返回 `self` 以支持链式调用。

```python
from QSExt.Factor.MongoDB import MongoDB

# 使用配置文件（默认路径 ~/QuantStudioConfig/MongoDBConfig.json）
FDB = MongoDB().connect()

# 指定自定义配置文件
FDB = MongoDB(config_file="/path/to/config.json").connect()

# 运行时覆盖参数
FDB = MongoDB(args={"DBName": "my_db", "IPAddr": "192.168.1.100"}).connect()
```

连接过程：
1. 调用 `_connect()` 创建 pymongo `MongoClient`
2. 遍历数据库中所有集合，筛选以 `InnerPrefix` 开头的集合
3. 读取每个集合的 `_TableInfo` 元数据文档
4. 构建内存中的 `_TableFactorDict`：`{表名: pd.Series(数据类型, index=[因子名])}`

#### `disconnect() -> int`

断开数据库连接（由基类 `FactorDB` 提供，返回 `0`）。

```python
FDB.disconnect()
```

#### `Connection -> pymongo.MongoClient`

获取底层 `pymongo.MongoClient` 对象，可用于执行原生 MongoDB 操作。如果进程号发生变化，会自动重连。

```python
# 获取数据库对象
db = FDB.Connection[FDB._QSArgs.DBName]
# 直接使用 collection
collection = db["qs_my_table"]
```

### 4.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有表名（按字母排序）。

```python
print(FDB.TableNames)
```

#### `getTable(table_name: str, args: dict = {}) -> _WideTable`

获取指定名称的因子表对象。仅支持宽表（`TableType="宽表"`）。

```python
# 默认宽表
FT = FDB.getTable("stock_cn_day_bar")

# 指定回溯天数
FT = FDB.getTable("my_table", args={"LookBack": 5})

# 指定字段名
FT = FDB.getTable("my_table", args={"DTField": "trade_date", "IDField": "symbol"})
```

#### `renameTable(old_table_name: str, new_table_name: str)`

重命名因子表。底层执行 MongoDB 集合的 `rename` 操作，同时更新内存中的索引。

```python
FDB.renameTable("old_name", "new_name")
```

#### `deleteTable(table_name: str)`

删除因子表。底层执行 `drop_collection`。

```python
FDB.deleteTable("table_to_delete")
```

#### `createTable(table_name: str, field_types: Dict[str, str])`

手动创建因子表，`field_types` 格式为 `{因子名: "double"/"string"}`。自动创建集合、插入元数据文档并建立索引。

```python
FDB.createTable("my_table", {
    "factor1": "double",
    "factor2": "string",
})
```

### 4.3 因子操作

#### `addFactor(table_name: str, field_types: Dict[str, str])`

向已有表的元数据文档中添加新因子的 `DataType` 信息。新因子不会立即在已有文档中创建字段，而是在后续写入数据时自然添加。

```python
FDB.addFactor("my_table", {"new_factor": "double"})
```

#### `renameFactor(table_name, old_factor_name, new_factor_name)`

重命名因子。底层对所有文档执行 `$rename` 操作，同时更新元数据文档。

```python
FDB.renameFactor("my_table", "old_factor", "new_factor")
```

#### `deleteFactor(table_name, factor_names: List[str])`

删除因子。底层对所有文档执行 `$unset` 操作移除指定字段，同时更新元数据文档。如果删除后表内再无因子，整张表会被删除。

```python
FDB.deleteFactor("my_table", ["factor_to_remove"])
```

### 4.4 数据写入

#### `writeData(data: Panel, table_name: str, if_exists="update", data_type={}) -> int`

批量写入因子表数据。如果表不存在则自动创建，如果写入的因子列不存在则自动添加。

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | `Panel` | 因子数据，items=因子名，major_axis=时点，minor_axis=ID |
| `table_name` | `str` | 表名 |
| `if_exists` | `"update"` / `"append"` / `"update_notnull"` | 写入方式 |
| `data_type` | `dict` | 可选，`{因子名: "double"/"string"}`，未指定时根据 dtype 自动识别 |

写入方式说明：

| 方式 | 行为 |
|------|------|
| `update` | 覆盖写入指定的时点×ID 范围内的数据，未指定的因子列保留旧值 |
| `append` | 仅填充原有 NaN 位置，不覆盖已有非空值 |
| `update_notnull` | 新数据非空时覆盖旧值，新数据为空时保留旧值 |

写入流程：
1. 若要写入的因子列不存在，自动调用 `addFactor` 添加
2. 若为 `update`，读回已有数据中本次未覆盖的因子列值，与本次数据合并
3. 若为 `append` / `update_notnull`，读回所有已有因子数据，按规则合并
4. 删除指定 `(datetime, code)` 范围内的旧数据
5. 通过 `insert_many` 批量插入新数据

```python
from QuantStudio.Core.QSObject import Panel

Data = Panel({
    "close": pd.DataFrame(...),
    "volume": pd.DataFrame(...),
})
FDB.writeData(data=Data, table_name="stock_cn_day_bar", if_exists="update")
```

#### `deleteData(table_name, ids=None, dts=None) -> int`

删除指定条件的数据。

- `ids=None` 且 `dts=None`：删除整张表
- 指定 `ids`：删除指定 ID 的所有数据
- 指定 `dts`：删除指定时点的所有数据
- 同时指定 `ids` 和 `dts`：精确删除指定 ID 和时点的数据

```python
# 删除指定 ID 的数据
FDB.deleteData("my_table", ids=["000001.SZ"])

# 删除指定时点的数据
FDB.deleteData("my_table", dts=[dt.datetime(2025, 1, 15)])
```

### 4.5 数据读取（_WideTable）

因子表对象提供标准的 QuantStudio 数据读取接口：

#### `FactorNames -> List[str]`

返回表中的所有因子名（不含 `datetime` 和 `code`）。

```python
FT = FDB.getTable("stock_cn_day_bar")
print(FT.FactorNames)
```

#### `getID(ifactor_name=None, idt=None, args={}) -> List[str]`

获取 ID 序列。指定 `idt` 时仅返回该时点有数据的 ID；指定 `ifactor_name` 时仅返回该因子非空的 ID。

```python
IDs = FT.getID()
IDs = FT.getID(idt=dt.datetime(2025, 1, 1))
```

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None, args={}) -> List[datetime]`

获取时点序列，支持时间范围过滤和 ID 过滤。

```python
DTs = FT.getDateTime(start_dt=dt.datetime(2025, 1, 1), end_dt=dt.datetime(2025, 12, 31))
DTs = FT.getDateTime(iid="000001.SZ")
```

#### `readData(factor_names, ids, dts) -> Panel`

读取因子数据。返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`。

通过 `args` 中的 `LookBack` 参数可以设置缺失填充回溯天数——当某个 ID 在 `dts[0]` 处无数据时，向前回溯查找最近的有效数据来填充。

```python
FT = FDB.getTable("stock_cn_day_bar")
Data = FT.readData(
    factor_names=["close", "volume"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 2)]
)
```

#### `getFactorMetaData(factor_names=None, key=None, args={}) -> pd.DataFrame | pd.Series`

获取因子元数据。`key=None` 时返回所有元数据的 DataFrame，指定 `key`（如 `"DataType"`）时返回对应值的 Series。

```python
FT = FDB.getTable("my_table")
meta = FT.getFactorMetaData(factor_names=["factor1", "factor2"])
dtype = FT.getFactorMetaData(factor_names=["factor1"], key="DataType")
```

---

## 5. 使用示例

### 5.1 基本流程

```python
import datetime as dt
import numpy as np
import pandas as pd

from QSExt.Factor.MongoDB import MongoDB
from QuantStudio.Core.QSObject import Panel

# 连接因子库
FDB = MongoDB().connect()

# 准备数据
nDT, nID = 5, 10
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
    ids=IDs[:3],
    dts=DTs[:3]
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
FDB.addFactor("my_table", {"new_factor": "double"})

# 删除指定 ID 的数据
FDB.deleteData("my_table", ids=["000001.SZ"])

# 删除指定时点的数据
FDB.deleteData("my_table", dts=[dt.datetime(2025, 1, 15)])
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

### 5.5 使用 LookBack 回溯填充

```python
# 当某个 ID 在请求的起始时点无数据时，向前回溯查找
FT = FDB.getTable("my_table", args={"LookBack": 30})

# LookBack=inf 时，回溯全部历史
FT = FDB.getTable("my_table", args={"LookBack": float("inf")})
```

### 5.6 使用 FilterCondition 过滤

```python
# FilterCondition 为 MongoDB 查询条件列表
FT = FDB.getTable("my_table", args={
    "FilterCondition": [{"code": {"$gte": "600000.SH"}}]
})
```

### 5.7 断开连接

```python
FDB.disconnect()
```

---

## 6. 数据读取流程

MongoDB 宽表的 `readData` 内部流程：

1. **`__QS_prepareRawData__`**：从 MongoDB 集合中查询指定 `(datetime, code)` 范围的因子数据。若 `LookBack=inf` 且存在在 `start_dt` 处无数据的 ID，额外查询最近的历史值作为填充
2. **`__QS_calcData__`**：调用 `_QS_calcData_WideTable` 将原始 DataFrame 转换为 `Panel` 对象，处理重复索引和数据类型转换
3. 返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`

---

## 7. 依赖

| 包 | 用途 |
|---|------|
| `pymongo` | MongoDB 驱动（需 `pip install pymongo`） |
| `numpy` | 数值计算 |
| `pandas` | 数据框操作 |
| `pydantic` | 参数校验 |
| `QuantStudio.Core` | `__QS_Error__`、`Panel` 等基础类 |
| `QuantStudio.Factor.FactorDB` | `WritableFactorDB` 基类 |
| `QuantStudio.Factor.FactorTable` | `FactorTable` 基类 |
| `QuantStudio.Factor.FactorUtils` | `_QS_calcData_WideTable` 宽表计算函数 |

---

## 8. 注意事项

1. **仅支持宽表**：当前仅实现了 `_WideTable`，不支持窄表、映射表等其他表类型
2. **数据类型**：仅支持 `double` 和 `string` 两种数据类型，不支持数组、嵌套文档等 MongoDB 特有类型
3. **文档级写入**：`writeData` 采用"先删后插"策略——先删除指定范围内的旧数据，再通过 `insert_many` 批量插入新数据
4. **元数据一致性**：添加/重命名/删除因子时，不仅更新数据文档，还会同步更新 `_TableInfo` 元数据文档
5. **进程感知重连**：`Connection` 属性在每次访问时检查当前进程号，若发生变化则自动重连（支持多进程场景）
6. **序列化支持**：实现了 `__getstate__` / `__setstate__`，支持 pickle 序列化，反序列化后自动重连
7. **字段名保留**：`datetime` 和 `code` 为保留字段名，`_TableInfo` 为保留 ID，不应与因子名或证券代码冲突
8. **LookBack 语义**：`LookBack=inf` 时向前回溯全部历史填充缺失值；`LookBack=N` 时向前回溯 N 天

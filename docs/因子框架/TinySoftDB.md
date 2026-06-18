# TinySoftDB — 基于天软的因子库

## 1. 概述

TinySoftDB 是基于 [天软（TinySoft）](http://www.tinysoft.com.cn/) 金融数据服务的因子库实现，继承自 `FactorDB`，通过 `pyTSL` 包连接天软服务器，提供 A 股行情、财务、指数成份等金融数据的读取功能。天软是一个提供中国金融市场数据的远程数据服务平台，支持 TSL（TinySoft Language）脚本查询。

- **类名**：`TinySoftDB`
- **模块**：`QSExt.Factor.TinySoftDB`
- **基类**：`QuantStudio.Factor.FactorDB.FactorDB`
- **因子表类**：
  - `_CalendarTable`（交易日历）
  - `_QuoteTable`（分时和日线数据，继承自 `_TSTable`）
  - `_TradeTable`（交易明细，继承自 `_TSTable`）
  - `_WideTable`（宽因子表，继承自 `_TS_SQL_Table` + `SQL_WideTable`）
  - `_FeatureTable`（特征因子表，继承自 `_TS_SQL_Table` + `SQL_FeatureTable`）
  - `_MappingTable`（映射因子表，继承自 `_TS_SQL_Table` + `SQL_MappingTable`）

---

## 2. 数据源结构

### 远程数据服务

TinySoftDB 连接天软远程服务器获取数据，本地不存储实际数据。所有数据查询通过 `pyTSL.Client` 发送 TSL 脚本到服务器执行。

### 元数据管理

元数据从本地 Excel 资源文件 `QSExt/Resource/TinySoftDBInfo.xlsx` 加载，首次导入后缓存为 HDF5 文件 `QSExt/TinySoftDBInfo.hdf5`。

| 元数据 | 变量 | 索引 | 说明 |
|--------|------|------|------|
| `_TableInfo` | `DataFrame` | `TableName` | 表名 → `DBTableName`、`TableClass`、`DefaultArgs`、`SecurityType`、`提取方式`、`Description` |
| `_FactorInfo` | `DataFrame` | `(TableName, FieldName)` | 因子名 → `DBFieldName`、`DataType`、`FieldType`、`Supplementary`、`Description` |

### 因子表类型

| 类型 | TSL 数据源 | 说明 |
|------|-----------|------|
| `CalendarTable` | `MarketTradeDayQk` | 交易日历，按交易所查询 |
| `QuoteTable` | `markettable` | 分钟线、日线等行情数据 |
| `TradeTable` | `tradetable` | Level1 交易明细数据 |
| `WideTable` | `INFOTABLE` SQL | 宽表结构的因子数据（名称变更、分红送股等） |
| `FeatureTable` | `INFOTABLE` SQL | 特征数据（股票基本信息、发行上市等） |
| `MappingTable` | `INFOTABLE` SQL | 映射数据（董事监事高管持股变动、指数成份等） |

### ID 格式

天软使用 `SH600000` / `SZ000001` 格式，QuantStudio 使用 `600000.SH` / `000001.SZ` 格式。内部通过 `_adjustID` 和 `__QS_adjustID__` 自动转换。

---

## 3. 参数说明

### TinySoftDB 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"TinySoftDB"` | 因子库名称（不可变） |
| `IPAddr` | `str` | `"tsl.tinysoft.com.cn"` | 服务器地址（不可变） |
| `Port` | `int` | `443` | 端口（不可变） |
| `User` | `str` | `""` | 用户名（不可变） |
| `Pwd` | `str` | `""` | 密码（不可变） |
| `DBInfoFile` | `str` | `""` | 自定义库信息文件路径，为空时使用默认资源文件（不可变） |
| `FTArgs` | `dict` | `{}` | 因子表默认参数（不可变） |

### 配置文件

参数从配置文件 `~/QuantStudioConfig/TinySoftDBConfig.json` 加载。示例：

```json
{
    "Name": "TinySoftDB",
    "IPAddr": "tsl.tinysoft.com.cn",
    "Port": 443,
    "User": "your_username",
    "Pwd": "your_password"
}
```

### 因子表参数（通过 `getTable` 的 `args` 传入）

#### QuoteTable 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Cycle` | `int` / `str` | `60` | 周期数值（单位由 `CycleUnit` 决定），或天软特殊周期字符串如 `"day"` |
| `CycleUnit` | `str` | `"s"` | `"s"` 秒（如 60=1 分钟线），`"d"` 天 |

```python
# 5 分钟线
FT = FDB.getTable("分时和日线数据", args={"Cycle": 300, "CycleUnit": "s"})

# 日线（字符串周期）
FT = FDB.getTable("分时和日线数据", args={"Cycle": "day"})
```

#### SQL 类因子表参数（WideTable / FeatureTable / MappingTable）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `MultiMapping` | `bool` | 由 DefaultArgs 决定 | 是否允许多重映射 |
| `DTField` | `str` / `None` | 自动判断 | 时点字段名 |
| `IDField` | `str` / `None` | 自动判断 | ID 字段名 |
| `PublDTField` | `str` / `None` | 自动判断 | 公告时点字段名（WideTable） |
| `LookBack` | `int` | `0` | 缺失填充回溯天数 |
| `FilterCondition` | `str` | `""` | 附加筛选条件 |
| `EndDateASC` | `bool` | `False` | 是否要求截止日期递增（WideTable） |

---

## 4. API 方法

### 4.1 连接管理

#### `connect() -> TinySoftDB`

连接天软服务器。返回 `self` 以支持链式调用。

```python
from QSExt.Factor.TinySoftDB import TinySoftDB

# 使用配置文件（默认路径）
FDB = TinySoftDB().connect()

# 运行时覆盖参数
FDB = TinySoftDB(args={"User": "user", "Pwd": "pass"}).connect()
```

#### `disconnect() -> int`

断开服务器连接。

```python
FDB.disconnect()
```

#### `isAvailable() -> bool`

检查连接是否可用，通过发送 `return "ping"` 测试。

```python
if FDB.isAvailable():
    print("连接正常")
```

### 4.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有可用表名。

```python
print(FDB.TableNames)
# ['交易日历', '分时和日线数据', '交易明细', '股票基本信息', '名称变更', ...]
```

#### `getTable(table_name: str, args: dict = {}) -> FactorTable`

获取指定名称的因子表对象。

```python
FT = FDB.getTable("分时和日线数据")
FT = FDB.getTable("分时和日线数据", args={"Cycle": 300, "CycleUnit": "s"})  # 5 分钟线
FT = FDB.getTable("分时和日线数据", args={"Cycle": "day"})  # 日线
```

### 4.3 交易日历

#### `getTradeDay(start_date=None, end_date=None, exchange="SSE", **kwargs) -> List`

获取交易日序列。

| 参数 | 类型 | 说明 |
|------|------|------|
| `start_date` | `date` / `None` | 起始日期，默认 `1900-01-01` |
| `end_date` | `date` / `None` | 结束日期，默认今天 |
| `exchange` | `str` | 交易所，`"SSE"` 或 `"SZSE"` |
| `output_type` | `str` | `"datetime"`（默认）返回 `datetime`，`"date"` 返回 `date` |

```python
import datetime as dt

# 获取 2026 年 6 月的交易日
DTs = FDB.getTradeDay(start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 30))

# 获取 date 类型
Dates = FDB.getTradeDay(start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 30), output_type="date")
```

### 4.4 证券列表

#### `getStockID(index_id, date=None, is_current=True) -> List[str]`

获取指数成份股列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| `index_id` | `str` | 指数代码（如 `"000001.SH"`）或特殊值 `"全体A股"` |
| `date` | `date` / `None` | 查询日期，默认今天 |

```python
# 获取全体 A 股
IDs = FDB.getStockID("全体A股")

# 获取上证指数成份股
IDs = FDB.getStockID("000001.SH", date=dt.date(2025, 12, 31))
```

#### `getFutureID(future_code="IF", date=None, is_current=True) -> List`

获取期货合约列表。

```python
IDs = FDB.getFutureID("IF")
```

### 4.5 数据读取

因子表对象提供标准的 QuantStudio 数据读取接口：

#### `FactorNames -> List[str]`

返回表中的所有因子名。

#### `getID(ifactor_name=None, idt=None) -> List[str]`

获取 ID 序列。

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None) -> List[datetime]`

获取时点序列。

#### `readData(factor_names, ids, dts) -> Panel`

读取因子数据。返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`。

```python
FT = FDB.getTable("分时和日线数据", args={"Cycle": "day"})
Data = FT.readData(
    factor_names=["收盘价", "成交量"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11)]
)
```

#### `readDayData(factor_names, ids, start_date, end_date) -> Panel`

按日期范围读取日线数据（仅 `QuoteTable` 和 `TradeTable` 支持）。

```python
FT = FDB.getTable("交易明细")
Data = FT.readDayData(
    factor_names=["成交价", "成交量"],
    ids=["000001.SZ"],
    start_date=dt.datetime(2026, 6, 1),
    end_date=dt.datetime(2026, 6, 30)
)
```

---

## 5. 使用示例

### 5.1 基本流程

```python
import datetime as dt
from QSExt.Factor.TinySoftDB import TinySoftDB

# 连接因子库
FDB = TinySoftDB().connect()

# 查看可用表
print("可用表:", FDB.TableNames)

# 获取交易日历
FT = FDB.getTable("交易日历")
print("交易所:", FT.getID())
DTs = FT.getDateTime(start_dt=dt.datetime(2026, 6, 1), end_dt=dt.datetime(2026, 6, 30))
print(f"2026 年 6 月共 {len(DTs)} 个交易日")

# 读取日线行情
FT = FDB.getTable("分时和日线数据", args={"Cycle": "day"})
Data = FT.readData(
    factor_names=FT.FactorNames[:3],
    ids=["000001.SZ"],
    dts=[dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11), dt.datetime(2026, 6, 12)]
)
print(Data)

FDB.disconnect()
```

### 5.2 读取交易明细

```python
FDB = TinySoftDB().connect()

FT = FDB.getTable("交易明细")
print("因子列表:", FT.FactorNames)

# 获取某只股票的交易时点
DTs = FT.getDateTime(iid="000001.SZ", start_dt=dt.datetime(2026, 6, 10), end_dt=dt.datetime(2026, 6, 15))
print(f"可用时点: {len(DTs)} 个")

# 读取数据
Data = FT.readData(
    factor_names=FT.FactorNames[:2],
    ids=["000001.SZ"],
    dts=DTs[:3]
)
print(Data)

FDB.disconnect()
```

### 5.3 读取宽表数据（名称变更）

```python
FDB = TinySoftDB().connect()

FT = FDB.getTable("名称变更")
print("因子列表:", FT.FactorNames)

# 读取指定 ID 和时点的数据
Data = FT.readData(
    factor_names=FT.FactorNames[:2],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 15)]
)
print(Data)

FDB.disconnect()
```

### 5.4 获取全体 A 股列表

```python
FDB = TinySoftDB().connect()

IDs = FDB.getStockID("全体A股")
print(f"全体 A 股共 {len(IDs)} 只")
print("前 10 只:", IDs[:10])

FDB.disconnect()
```

### 5.5 分钟线数据

```python
FDB = TinySoftDB().connect()

# 5 分钟线
FT = FDB.getTable("分时和日线数据", args={"Cycle": 300, "CycleUnit": "s"})
DTs = FT.getDateTime(iid="000001.SZ", start_dt=dt.datetime(2026, 6, 15), end_dt=dt.datetime(2026, 6, 15))
print(f"5 分钟线时点数: {len(DTs)}")

Data = FT.readData(
    factor_names=FT.FactorNames[:2],
    ids=["000001.SZ"],
    dts=DTs[:10]
)
print(Data)

FDB.disconnect()
```

### 5.6 交易日历因子表

```python
FDB = TinySoftDB().connect()

FT = FDB.getTable("交易日历")
print("交易所:", FT.getID())  # ['SSE', 'SZSE']

# 读取交易日标记
Data = FT.readData(
    factor_names=["交易日"],
    ids=["SSE", "SZSE"],
    dts=[dt.datetime(2026, 6, 10), dt.datetime(2026, 6, 11), dt.datetime(2026, 6, 14)]
)
print(Data)  # 1 表示交易日，NaN 表示非交易日

FDB.disconnect()
```

---

## 6. 依赖

| 包 | 用途 |
|---|------|
| `pyTSL` | 天软 Python 客户端，连接天软服务器执行 TSL 脚本 |
| `numpy` | 数值计算 |
| `pandas` | 数据框操作 |
| `openpyxl` | 读取 Excel 格式的元数据资源文件 |
| `pydantic` | 参数校验 |
| `QuantStudio.Core` | `__QS_Error__`、`Panel` 等基础类 |
| `QuantStudio.Factor.FactorDB` | `FactorDB` 基类 |
| `QuantStudio.Factor.FactorTable` | `FactorTable` 基类 |
| `QuantStudio.Factor.FactorUtils` | `SQL_Table`、`importInfo`、`updateInfo` 等工具 |

安装 `pyTSL`：

```bash
pip install pyTSL
```

---

## 7. 注意事项

1. **账号权限**：不同账号的数据访问权限不同，部分功能（如指数成份股查询）可能因账号权限限制返回空结果
2. **数据量控制**：读取数据时应避免过长的时间范围或过多的证券，以免请求超时或服务器限流
3. **连接管理**：`connect()` / `disconnect()` 应成对使用；`isAvailable()` 会向服务器发送测试请求，不宜高频调用
4. **ID 格式**：内部自动转换天软格式（`SH600000`）和 QuantStudio 格式（`600000.SH`），用户始终使用 QuantStudio 格式
5. **元数据缓存**：首次导入元数据后缓存为 HDF5 文件，若资源文件更新需删除 `QSExt/TinySoftDBInfo.hdf5` 重新生成
6. **旧版兼容**：配置文件中的 `InstallDir` 键是旧版 TSLPy3 遗留字段，新版本（pyTSL）不再需要，会被自动忽略
7. **周期设置**：`QuoteTable` 的 `Cycle` 参数支持整数（配合 `CycleUnit` 使用）或天软特殊周期字符串（如 `"day"`）

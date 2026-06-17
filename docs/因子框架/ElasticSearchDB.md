# ElasticSearchDB — 基于 Elasticsearch 的因子库

## 1. 概述

ElasticSearchDB 是基于 [Elasticsearch](https://www.elastic.co/elasticsearch) 的因子库实现，继承自 `WritableFactorDB`，支持因子数据的读写、追加更新和管理功能。Elasticsearch 是一个分布式全文搜索和分析引擎，适合大规模数据的检索和聚合场景。

- **类名**：`ElasticSearchDB`
- **模块**：`QSExt.Factor.ElasticSearchDB`
- **基类**：`QuantStudio.Factor.FactorDB.WritableFactorDB`
- **因子表类**：`_WideTable`（仅支持宽表模式）

---

## 2. 存储结构

### 索引结构

每张 QS 因子表对应一个 Elasticsearch 索引，索引名 = `InnerPrefix` + 表名（默认前缀 `qs_`）。

每个索引的文档结构：

| 字段 | ES 类型 | 说明 |
|------|---------|------|
| `DTField`（默认 `datetime`） | `date` | 时点字段 |
| `IDField`（默认 `code`） | `keyword` | ID 字段 |
| 自定义因子字段 | `keyword` 或 `double` | 因子数据列 |

### 元数据管理

元数据在 `connect()` 时从 Elasticsearch 动态读取，存储于内存中的 `pd.DataFrame`：

| 元数据 | 变量 | 索引 | 说明 |
|--------|------|------|------|
| `_TableInfo` | `DataFrame` | `TableName` | 表名 → `DBTableName`、`TableClass`、`Description` |
| `_FactorInfo` | `DataFrame` | `(TableName, FieldName)` | 因子名 → `DataType`、`FieldType`、`Keyword`、`Supplementary`、`Description` |

`connect()` 时通过 `indices.get_settings` 获取所有匹配前缀的索引，再通过 `indices.get_mapping` 逐索引读取字段映射信息。

### 字段类型映射

| ES 类型 | QS DataType |
|---------|-------------|
| `keyword` | `string` |
| `text` | `string` |
| `float` / `double` / `integer` / `long` / `short` / `byte` / `half_float` | `double` |
| `date` | `object` |

数据类型推断规则：包含 `object` 类型的字段自动映射为 `keyword`，其余映射为 `double`。

---

## 3. 连接配置

配置文件路径：`~/QuantStudioConfig/ElasticSearchDBConfig.json`

### 连接参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | `str` | `"localhost"` | ES 服务地址 |
| `port` | `int` | `9200` | ES 服务端口 |
| `http_auth` | `list` | `None` | HTTP 认证，格式 `[username, password]` |

连接时自动将 `host`/`port` 拼接为 `http://{host}:{port}`，并将 `http_auth` 转换为 elasticsearch 9.x 的 `basic_auth` 格式。

### 初始化参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"ElasticSearchDB"` | 因子库名称 |
| `ConnectArgs` | `dict` | `{}` | 连接参数（host、port、http_auth 等） |
| `InnerPrefix` | `str` | `"qs_"` | 索引名内部前缀 |
| `DTField` | `str` | `"datetime"` | 默认时点字段名 |
| `IDField` | `str` | `"code"` | 默认 ID 字段名 |
| `IgnoreFields` | `list` | `[]` | 忽略的字段列表 |
| `FTArgs` | `dict` | `{}` | 因子表默认参数 |
| `SearchRetryNum` | `int` | `10"` | 查询超时重试次数 |

### 因子表参数（_WideTable）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `PreFilterID` | `bool` | `True` | 查询时是否预筛选 ID（使用 `terms` 查询） |
| `FilterCondition` | `list` | `[]` | 额外的 ES 查询过滤条件 |
| `DTField` | `str` | `"datetime"` | 时点字段名 |
| `IDField` | `str` | `"code"` | ID 字段名 |
| `LookBack` | `float` | `0` | 回溯天数，`0` 不回溯，`inf` 向前填充 |
| `KeywordSuffix` | `bool` | `False` | ID 字段查询时是否加 `.keyword` 后缀 |

---

## 4. 核心方法

### 4.1 连接管理

#### `connect()`

连接 Elasticsearch，读取所有匹配 `InnerPrefix*` 的索引元信息和字段映射。

```python
from QSExt.Factor.ElasticSearchDB import ElasticSearchDB

fdb = ElasticSearchDB(config_file="path/to/config.json")
fdb.connect()
```

#### `disconnect()`

关闭连接。

### 4.2 查询方法

#### `search(index, query, sort, ...)`

基于 PIT（Point In Time）+ `search_after` 的分页查询，返回生成器。适用于大数据量查询，避免深分页性能问题。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `index` | `str` | - | 索引名 |
| `query` | `dict` | - | ES 查询 DSL |
| `sort` | `list` | - | 排序规则 |
| `only_source` | `bool` | `True` | 仅返回 `_source` 字段 |
| `return_size` | `int` | `None` | 限制返回总数 |
| `size` | `int` | `3000` | 每批返回数量 |
| `keep_alive` | `str` | `"10m"` | PIT 保持时间 |

#### `search_scroll(index, query, sort, ...)`

基于 Scroll API 的分页查询，返回生成器。功能与 `search` 类似，但使用传统 Scroll 机制。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `scroll` | `str` | `"10m"` | Scroll 上下文保持时间 |

### 4.3 因子表管理

#### `getTable(table_name, args={})`

获取因子表对象。

```python
ft = fdb.getTable("my_table")
```

#### `createTable(table_name, field_types)`

创建新的因子表（ES 索引）。`field_types` 为 `{字段名: ES类型}` 字典。

```python
fdb.createTable("stock_daily", {"pe": "double", "pb": "double", "name": "keyword"})
```

#### `deleteTable(table_name)`

删除因子表（删除对应的 ES 索引）。

#### `renameTable(old_name, new_name)`

重命名因子表。内部通过 reindex 实现：创建新索引 → 复制数据 → 删除旧索引。

#### `addFactor(table_name, field_types)`

向已有因子表添加新字段。若表不存在则自动创建。

#### `deleteFactor(table_name, factor_names)`

删除因子表中的指定字段。由于 ES 不支持直接删除字段映射，内部通过备份索引 → 重建映射 → reindex 恢复数据的方式实现。

#### `renameFactor(table_name, old_name, new_name)`

重命名因子字段。同样通过备份索引 → 重建 → reindex 的方式实现。

### 4.4 数据操作

#### `writeData(data, table_name, if_exists="update", data_type={})`

写入因子数据。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data` | `Panel` | - | 因子数据，`items`=因子名，`major_axis`=时点，`minor_axis`=ID |
| `table_name` | `str` | - | 目标因子表名 |
| `if_exists` | `str` | `"update"` | 写入方式：`"update"` / `"replace"` / `"append"` |
| `data_type` | `dict` | `{}` | 强制指定因子数据类型 |

写入方式说明：

| 模式 | 行为 |
|------|------|
| `update` | 覆盖写入。保留本次未写入的旧因子数据（合并后写入） |
| `replace` | 全量替换。先删除表中所有数据，再写入新数据 |
| `append` | 追加写入。已有非空值不会被覆盖，仅填充空值 |

写入流程：
1. 若表不存在则自动创建，若有新因子则自动添加字段
2. 根据 `if_exists` 策略合并数据
3. 将 Panel 展开为 DataFrame，过滤掉全 NaN 行
4. 删除目标范围的旧数据（`delete_by_query`）
5. 使用 `helpers.bulk` 批量写入新数据
6. 刷新索引使数据立即可搜索

#### `deleteData(table_name, ids=None, dts=None)`

删除指定因子表的数据。可按 ID、时点或两者组合筛选删除范围。不指定则删除全部数据。

### 4.5 因子表查询方法（_WideTable）

#### `getID(ifactor_name=None, idt=None)`

获取因子表中的 ID 列表。支持按因子名和时点筛选。

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None)`

获取因子表中的时点列表。支持按因子名、ID 和时间范围筛选。

#### `readData(factor_names, ids, dts)`

读取因子数据，返回 Panel 对象。继承自 `FactorTable`，内部调用 `__QS_prepareRawData__` 和 `__QS_calcData__`。

---

## 5. 查询机制

### PIT + search_after 分页

`__QS_prepareRawData__` 使用 `fdb.search()` 方法进行数据查询，底层采用 Elasticsearch 的 PIT（Point In Time）+ `search_after` 机制：

1. 打开 PIT 快照，保证查询期间数据一致性
2. 首次查询获取第一批数据
3. 使用最后一条记录的排序值作为 `search_after` 参数继续查询
4. 循环直到获取所有数据或达到 `return_size` 限制
5. 关闭 PIT

### LookBack 回溯

`LookBack` 参数控制数据回溯行为：

| 值 | 行为 |
|----|------|
| `0` | 不回溯，仅查询指定时间范围 |
| 正数 | 查询时间范围向前扩展 N 天，缺失数据使用 `fillNaByLookback` 填充 |
| `inf` | 向前无限回溯，缺失数据使用前向填充（`pad`） |

### ID 预筛选

当 `PreFilterID=True`（默认）时，查询使用 `terms` 过滤器预先筛选 ID，减少返回数据量。对于 ID 基数很高的场景可关闭此选项。

---

## 6. 使用示例

### 基本使用

```python
from QSExt.Factor.ElasticSearchDB import ElasticSearchDB

# 初始化并连接
fdb = ElasticSearchDB(config_file="~/QuantStudioConfig/ElasticSearchDBConfig.json")
fdb.connect()

# 查看可用因子表
print(fdb.TableNames)

# 获取因子表
ft = fdb.getTable("stock_daily")

# 查看因子列表
print(ft.FactorNames)

# 读取因子数据
data = ft.readData(
    factor_names=["pe", "pb"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[datetime(2026, 1, 2), datetime(2026, 1, 3)]
)

# 断开连接
fdb.disconnect()
```

### 创建表并写入数据

```python
import pandas as pd
from QuantStudio.Core.QSObject import Panel

# 创建因子表
fdb.createTable("stock_daily", {"pe": "double", "pb": "double", "name": "keyword"})

# 构造 Panel 数据
data = Panel(...)
# items=["pe", "pb"], major_axis=[datetime1, datetime2], minor_axis=["000001.SZ", "000002.SZ"]

# 写入数据
fdb.writeData(data, "stock_daily", if_exists="update")

# 追加写入（不覆盖已有值）
fdb.writeData(data, "stock_daily", if_exists="append")
```

### 自定义查询

```python
# 使用 search 方法进行自定义查询
results = list(fdb.search(
    index="qs_stock_daily",
    query={"bool": {"filter": [
        {"terms": {"code": ["000001.SZ"]}},
        {"range": {"datetime": {"gte": "2026-01-01", "lte": "2026-06-01"}}}
    ]}},
    sort=[{"code": "asc"}, {"datetime": "asc"}],
    only_source=True
))
```

---

## 7. 注意事项

1. **ES 版本兼容性**：代码基于 elasticsearch-py 9.x API 编写，连接时自动将旧版 `http_auth` 转换为 `basic_auth` 格式。
2. **NaN 处理**：ES 不接受 `NaN` 值，写入时自动过滤掉空值字段。
3. **字段重命名/删除成本**：由于 ES 不支持直接修改映射，`renameFactor` 和 `deleteFactor` 需要通过备份索引 → 重建 → reindex 实现，大数据量时耗时较长。
4. **深分页**：使用 PIT + `search_after` 代替传统的 `from` + `size` 分页，避免深分页性能问题。
5. **超时重试**：查询超时时自动重试（最多 `SearchRetryNum` 次），重试间隔随次数递增。
6. **datetime 格式**：存储格式为 `%Y-%m-%dT%H:%M:%S`，读取时通过 `strptime` 解析。
7. **索引刷新**：写入数据后自动调用 `indices.refresh`，确保数据立即可搜索。

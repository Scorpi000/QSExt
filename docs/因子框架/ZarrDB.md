# ZarrDB — 基于 Zarr 的因子库

## 1. 概述

ZarrDB 是基于 [Zarr](https://zarr.readthedocs.io/en/stable/) 文件格式的因子数据库实现，继承自 `WritableFactorDB`，支持因子数据的读写、追加更新、元数据管理等功能。

- **类名**：`ZarrDB`
- **模块**：`QSExt.Factor.ZarrDB`
- **基类**：`QuantStudio.Factor.FactorDB.WritableFactorDB`
- **因子表类**：`ZarrFactorTable`（继承自 `QuantStudio.Factor.FactorTable.FactorTable`）

---

## 2. 存储结构

主目录下的每个子目录表示一张因子表。每张表是一个 Zarr group，表的元数据存储在 group 的 `attrs` 中。

每个因子是表 group 下的一个子 group，包含三个 Dataset：

| Dataset | 形状 | 数据类型 | 说明 |
|---------|------|---------|------|
| `ID` | `(n_ids,)` | object (VLenUTF8) | 因子 ID 序列 |
| `DateTime` | `(n_dts,)` | M8[ns] | 因子时点序列 |
| `Data` | `(n_dts, n_ids)` | 取决于因子类型 | 因子数据矩阵 |

因子类型的 `Data` 存储方式：

| 类型 | dtype | fill_value | 说明 |
|------|-------|-----------|------|
| `double` | float64 | NaN | 数值型因子 |
| `string` | object (VLenUTF8) | — | 字符串因子，`None`/`""` 统一为 `None` |
| `object` | object (Pickle) | — | 复杂 Python 对象，以 pickle 序列化 |

因子的元数据存储在因子 group 的 `attrs` 中，其中 `DataType` 键固定用于标识因子数据类型。

**目录结构示例：**

```
MainDir/
├── _FDB.lock                  # 库级锁文件
├── stock_cn_day_bar/          # 因子表 (zarr group)
│   ├── _Table.lock            # 表级锁文件
│   ├── open/                  # 因子 "open" (zarr sub-group)
│   │   ├── ID                 # dataset
│   │   ├── DateTime           # dataset
│   │   └── Data               # dataset
│   ├── close/
│   │   └── ...
│   └── ...
└── stock_cn_factor_value/
    └── ...
```

### 锁机制

| 锁级别 | 锁文件 | 适用操作 |
|--------|--------|---------|
| 库锁 | `MainDir/_FDB.lock` | 创建/删除/重命名表 |
| 表锁 | `MainDir/{table}/_Table.lock` | 读写因子数据、修改元数据 |

---

## 3. 参数说明

### ZarrDB 参数

继承自 `WritableFactorDB.__QS_ArgClass__`，增加以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Name` | `str` | `"ZarrDB"` | 因子库名称（不可变） |
| `MainDir` | `DirectoryPath` | 必填 | 存放数据的主目录（不可变） |

### ZarrFactorTable 参数

继承自 `FactorTable.__QS_ArgClass__`，增加以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `LookBack` | `int` | `0` | 缺失填充回溯天数，`0` 表示不填充，`inf` 表示全量前向填充 |
| `OnlyStartLookBack` | `bool` | `False` | 仅对起始时点回溯填充 |
| `OnlyLookBackNontarget` | `bool` | `False` | 仅用非目标时点的数据回溯 |
| `OnlyLookBackDT` | `bool` | `False` | 所有 ID 统一沿时点回溯，不单独填充 |
| `TargetDT` | `datetime` | `None` | 固定返回时点，非 None 时所有时点返回该时点数据 |

---

## 4. API 方法

### 4.1 连接管理

#### `connect() -> ZarrDB`

连接因子库，验证主目录存在。返回 `self` 以支持链式调用。

```python
ZDB = ZarrDB(args={"MainDir": "/path/to/data"}).connect()
```

### 4.2 表操作

#### `TableNames -> List[str]`

返回因子库中所有表名。

#### `getTable(table_name: str, args: dict = {}) -> ZarrFactorTable`

获取指定名称的因子表对象。

```python
FT = ZDB.getTable("stock_cn_day_bar")
# 带参数的调用
FT = ZDB.getTable("stock_cn_day_bar", args={"LookBack": 5})
```

#### `renameTable(old_table_name: str, new_table_name: str) -> int`

重命名因子表。

#### `deleteTable(table_name: str) -> int`

删除因子表。

#### `setTableMetaData(table_name, key=None, value=None, meta_data=None) -> int`

设置表的元数据。支持三种调用方式：

```python
# 单个键值
ZDB.setTableMetaData("stock_cn_day_bar", key="Description", value="股票日K线")
# 批量设置
ZDB.setTableMetaData("stock_cn_day_bar", meta_data={"Description": "...", "Version": 1})
```

表元数据支持的类型：`int`、`float`、`str`、`np.ndarray`、`pd.Series`、`pd.DataFrame`。其中 `Series` 和 `DataFrame` 以 JSON 格式存储。

### 4.3 因子操作

#### `renameFactor(table_name, old_factor_name, new_factor_name) -> int`

重命名因子。

#### `deleteFactor(table_name, factor_names: List[str]) -> int`

删除因子。若删除后表内无因子，则表目录一并删除。

#### `setFactorMetaData(table_name, ifactor_name, key=None, value=None, meta_data=None) -> int`

设置因子的元数据。调用方式同 `setTableMetaData`。

### 4.4 数据写入

#### `writeFactorData(factor_data, table_name, ifactor_name, if_exists="update", data_type=None) -> int`

写入单个因子数据。

| 参数 | 类型 | 说明 |
|------|------|------|
| `factor_data` | `pd.DataFrame` | 因子数据，index 为时点，columns 为 ID |
| `table_name` | `str` | 表名 |
| `ifactor_name` | `str` | 因子名 |
| `if_exists` | `"update"` / `"append"` / `"update_notnull"` | 写入方式 |
| `data_type` | `"double"` / `"string"` / `"object"` | 数据类型，None 时自动识别 |

写入方式说明：

| 方式 | 行为 |
|------|------|
| `update` | 覆盖已有数据，新增时点和 ID |
| `append` | 仅填充原有 NaN 位置，不覆盖已有非空值 |
| `update_notnull` | 仅用非空值覆盖，保留原有的非 NaN 数据 |

#### `writeData(data, table_name, if_exists="update", data_type={}) -> int`

批量写入因子表数据。

```python
from QuantStudio.Core.QSObject import Panel

Data = Panel({
    "close": pd.DataFrame(...),
    "volume": pd.DataFrame(...),
})
ZDB.writeData(data=Data, table_name="stock_cn_day_bar", if_exists="update")
```

### 4.5 数据读取（ZarrFactorTable）

#### `FactorNames -> List[str]`

返回表中的所有因子名称。

#### `getMetaData(key=None) -> Union[Any, pd.Series]`

获取表元数据。`key=None` 时返回所有元数据的 Series。

#### `getFactorMetaData(factor_names=None, key=None) -> Union[pd.DataFrame, pd.Series]`

获取因子元数据。

```python
# 获取所有因子的全部元数据
FT.getFactorMetaData()
# 获取指定因子的 DataType
FT.getFactorMetaData(factor_names=["close", "volume"], key="DataType")
```

#### `getID(ifactor_name=None, idt=None) -> List[str]`

获取 ID 序列。指定 `idt` 时仅返回该时点有数据的 ID。

#### `getDateTime(ifactor_name=None, iid=None, start_dt=None, end_dt=None) -> List[datetime]`

获取时点序列，支持时间范围过滤和 ID 过滤。

#### `readData(factor_names, ids, dts) -> Panel`

读取因子表数据。返回 `Panel(items=factor_names, major_axis=dts, minor_axis=ids)`。

```python
FT = ZDB.getTable("stock_cn_day_bar")
Data = FT.readData(
    factor_names=["close", "volume"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2025, 1, 1), dt.datetime(2025, 1, 2)]
)
```

#### `readFactorData(ifactor_name, ids, dts) -> pd.DataFrame`

读取单个因子的数据，支持 LookBack 缺失填充。

---

## 5. 使用示例

### 5.1 基本流程

```python
import datetime as dt
import numpy as np
import pandas as pd

from QSExt.Factor.ZarrDB import ZarrDB
from QuantStudio.Core.QSObject import Panel

# 连接因子库
ZDB = ZarrDB(args={"MainDir": "C:/Data/ZarrDB"}).connect()

# 写入数据
nDT, nID = 100, 20
IDs = [f"{i:06d}.SZ" for i in range(1, nID + 1)]
DTs = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]

Data = {
    "close": pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTs, columns=IDs),
    "volume": pd.DataFrame(np.random.rand(nDT, nID) * 100, index=DTs, columns=IDs),
}
ZDB.writeData(data=Panel(Data), table_name="stock_cn_day_bar", if_exists="update")

# 写入表元数据
ZDB.setTableMetaData("stock_cn_day_bar", key="Description", value="股票日K线")

# 读取数据
FT = ZDB.getTable("stock_cn_day_bar")
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

### 5.2 带 LookBack 的读取

```python
# 获取带 5 天回溯填充的因子表
FT = ZDB.getTable("stock_cn_day_bar", args={"LookBack": 5})

# 读取时自动向前回溯填充缺失值
Data = FT.readData(
    factor_names=["close"],
    ids=["000001.SZ", "000002.SZ"],
    dts=[dt.datetime(2025, 2, 1)]
)
```

### 5.3 使用 TargetDT 取固定时点

```python
# 创建 TargetDT 模式的表，所有时点返回同一目标时点的值
FT = ZDB.getTable("stock_cn_day_bar", args={
    "TargetDT": dt.datetime(2025, 1, 15)
})

# 无论传入什么 dts，都返回 2025-01-15 的数据
Data = FT.readData(
    factor_names=["close"],
    ids=["000001.SZ"],
    dts=[dt.datetime(2025, 3, 1), dt.datetime(2025, 3, 2)]
)
# Data 中两个时点的值相同，均为 2025-01-15 的值
```

### 5.4 增量更新数据

```python
# 首次写入
ZDB.writeData(data=Panel({"factor1": data1}), table_name="my_table")

# 增量追加（不覆盖已有非空值）
ZDB.writeData(data=Panel({"factor1": new_data}), table_name="my_table", if_exists="append")

# 增量覆盖（仅覆盖空值）
ZDB.writeData(data=Panel({"factor1": new_data}), table_name="my_table", if_exists="append")
```

### 5.5 元数据管理

```python
# 写入表的多种类型元数据
ZDB.setTableMetaData("my_table", key="int_val", value=42)
ZDB.setTableMetaData("my_table", key="str_val", value="描述文本")
ZDB.setTableMetaData("my_table", key="series_val", value=pd.Series([1, 2, 3], index=list("abc")))
ZDB.setTableMetaData("my_table", key="df_val", value=pd.DataFrame({"x": [1, 2], "y": [3, 4]}))

# 批量写入
ZDB.setTableMetaData("my_table", meta_data={
    "Author": "quant",
    "Version": 2,
})

# 读取
FT = ZDB.getTable("my_table")
print(FT.getMetaData())                # 所有元数据
print(FT.getMetaData(key="Author"))    # 单个键

# 因子元数据
ZDB.setFactorMetaData("my_table", "factor1", key="Description", value="收盘价因子")
print(FT.getFactorMetaData(factor_names=["factor1"], key="Description"))
```

### 5.6 管理操作

```python
# 表重命名
ZDB.renameTable("old_name", "new_name")

# 表删除
ZDB.deleteTable("table_to_delete")

# 因子重命名
ZDB.renameFactor("my_table", "old_factor", "new_factor")

# 因子删除
ZDB.deleteFactor("my_table", ["factor_to_remove"])

# 查看所有表
print(ZDB.TableNames)
```

### 5.7 生成 Demo 数据

```bash
# 生成到默认目录
python -m test_ZarrDB --gen-data

# 生成到指定目录
python -m test_ZarrDB --gen-data /path/to/target
```

Demo 数据包含以下表：

| 表名 | 内容 | 因子 |
|------|------|------|
| `stock_cn_day_bar` | 股票日K线 | open, close, high, low, volume, amount |
| `stock_cn_status` | 股票状态信息 | if_listed |
| `stock_cn_industry` | 行业分类 | industry |
| `stock_cn_factor_value` | 股票价值因子 | ep_ttm, bp_lr |
| `index_cn_day_bar` | 指数日K线 | open, close, high, low, volume, amount |

---

## 6. 与 HDF5DB 的对比

| 特性 | ZarrDB | HDF5DB |
|------|--------|--------|
| 存储格式 | Zarr (directory store) | HDF5 文件 |
| 因子存储 | 每个因子是表 group 下的子 group | 每个因子是独立的 `.hdf5` 文件 |
| 元数据存储 | group attrs | HDF5 attrs + `_TableInfo.h5` |
| 表元数据序列化 | JSON (pd.Series/DataFrame) | HDF5 nested dict |
| 部分读取 | `get_orthogonal_selection` | h5py 数组切片 |
| 锁粒度 | 库锁 + 表锁 | 库锁 + 表锁 + 因子锁 |
| 并发写入 | 表级互斥 | 因子级互斥（更细粒度） |
| 数据压缩 | 依赖 numcodecs | 依赖 HDF5 内置压缩 |
| 读取性能 | 正交选择高效 | 小数据量高效，大量切片需读全量 |
| 跨平台 | 良好 | 良好 |

---

## 7. 依赖

| 包 | 最低版本 | 用途 |
|---|---------|------|
| `zarr` | ≥2.0, <3.0 | 数据存储引擎 |
| `numcodecs` | ≥0.10.0 | VLenUTF8 / Pickle 编解码 |
| `filelock` | — | 进程间文件锁 |
| `numpy` | ≥1.24 | 数值计算 |
| `pandas` | — | 数据框 |
| `pydantic` | — | 参数校验 |

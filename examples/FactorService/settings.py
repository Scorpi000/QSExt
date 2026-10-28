"""远程因子库服务配置示例。

使用环境变量 QS_FACTOR_DATA_ROOT 指定已有数据目录，使用
QS_FACTOR_SERVICE_TOKEN 提供服务令牌；客户端令牌环境变量的值需与其一致。
数据库凭据使用服务器自身的 QuantStudio 配置，不返回给客户端。
market 使用磁盘元信息库和协调模式，可与同机 QSWeb 共享；QSWeb 和更新
脚本须使用相同 DBFile 并同时启用 CoordinatedAccess。纯内存 Parquet 库
请移除 DBFile 和 CoordinatedAccess，不需要跨进程协调同一个内存库。
"""

import os
from pathlib import Path

data_root = Path(os.environ["QS_FACTOR_DATA_ROOT"]).expanduser().resolve()

FACTOR_DATABASES = [
    {"name": "market", "class": "QSExt.Factor.DuckDB.DuckDB", "role": "source",
     "args": {"ParquetDir": str(data_root / "market"),
              "DBFile": str((data_root / "market" / "_metadata.duckdb").resolve()),
              "CoordinatedAccess": True, "LockTimeout": 30}},
    {"name": "research", "class": "HDF5DB", "role": "target",
     "args": {"MainDir": str(data_root / "research")}},
]

FACTOR_SERVICE = {
    "ServiceID": "research-factor-service",
    "Host": "127.0.0.1",
    "Port": 8765,
    "Auth": {"TokenEnv": "QS_FACTOR_SERVICE_TOKEN"},
    "Databases": {
        "market": {"ResourceID": "market-primary", "Access": "read"},
        "research": {"ResourceID": "research-primary", "Access": "read_write"},
    },
}

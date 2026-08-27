# ============================================================
# QSExt 统一运行时配置 (示例)
# ============================================================
# 复制此文件为 ~/QuantStudioConfig/settings.py 并根据实际环境修改。
#
# 或使用链式继承:
#   __INHERIT_FROM__ = "~/QuantStudioConfig/settings.py"
#   # 只写需要覆盖的变量
#
# 覆盖优先级 (由低到高):
#   1. __INHERIT_FROM__ 父模块
#   2. 本文件变量
#   3. settings_local.py (不入库，本地覆盖)
#   4. QS_* 环境变量
#   5. 命令行 --xxx 参数


# ============================================================
# 0. 可选：链式继承
# ============================================================
# __INHERIT_FROM__ = "~/QuantStudioConfig/settings.py"


# ============================================================
# 1. 运行模式
# ============================================================
DEBUG = False
UPDATE_DATA = True
REGISTER_GRAPH = False
DRY_RUN = False


# ============================================================
# 2. 因子数据库 (FACTOR_DATABASES)
# ============================================================
FACTOR_DATABASES = [
    {
        "name": "BSDB",
        "class": "BaoStockDB",               # 支持短名 (JYDB, HDF5DB, SQLDB 等)
        "role": "source",
        "args": {},
    },
    {
        "name": "TDB",
        "class": "HDF5DB",
        "role": "target",
        "args": {
            "MainDir": r"D:\Data\HDF5DB_Test",
        },
    },
    {
        "name": "ProxyDB",
        "class": "HDF5DB",
        "role": "proxy",
        "args": {
            "MainDir": r"D:\Data\HDF5DB",
        },
    },
]

# 代理表名映射
PROXY_TABLE_MAPPING = {}

# 风险数据库 (factor_databases 已覆盖连接定义，此处为风险库专用)
RISK_DATABASES = [
    # {
    #     "name": "Barra 风险库",
    #     "db_type": "HDF5FRDB",
    #     "description": "",
    #     "args": {"MainDir": "D:/Data/HDF5RDB"},
    # },
]


# ============================================================
# 3. 数据源
# ============================================================
# 交易日历数据源 (name 匹配 FACTOR_DATABASES 中的库名)
TRADING_DAY_SOURCE = {
    "name": "BSDB",
    "method": "getTradeDay",
    "method_args": {"exchange": "SSE"},
}

# 截面 ID 数据源 (按 IDType，name 匹配 FACTOR_DATABASES 中的库名)
# 自定义 IDType 只需添加对应条目，method_args 中的参数会透传给 method
SECTION_ID_SOURCES = {
    "A股": {
        "name": "BSDB",
        "method": "getStockID",
        "method_args": {},
    }
}


# ============================================================
# 4. 时间范围
# ============================================================
END_DT = "last_friday"
START_DT = None
LOOKBACK = 15
MAX_LOOKBACK = 365 * 10          # DTRuler 最大回溯天数
DT_TYPE = "交易日"               # 交易日 | 自然日
DT_FREQ = "1d"                   # 1d | 1w | 2w | 1m | 1q | 1y


# ============================================================
# 5. ID 类型与模块 (ID_PROFILES)
# ============================================================
ID_PROFILES = [
    {
        "id_type": "A股",
        "id_selection": {"type": "list", "ids": ["000001.SZ", "000002.SZ", "000003.SZ"]},
        "factor_modules": [
            "QSExt.FactorDef.stock_cn_factor_example1",
            "QSExt.FactorDef.stock_cn_factor_example2",
        ],
        "strategy_modules": [
            # "QSExt.StrategyDef.example_strategy",
        ],
        # "section_id_list": ["000001.SZ", "600000.SH"],
        # "proxy_tables": ["stock_cn_status", "stock_cn_day_bar_nafilled"],
    },
]


# ============================================================
# 6. 输出
# ============================================================
TARGET_DB = "TDB"
FACTOR_STORER_CONFIG = {
    "IfExists": "update",
    "UpdateMeta": True,
}


# ============================================================
# 7. 缓存
# ============================================================
CACHE_DIR = r"D:\Data\Cache\FactorTaskCache"
USE_TEMP_CACHE = True
CACHE_START_MODE = "new"         # new | read | all
CACHE_SUFFIX = ".pkl"


# ============================================================
# 8. 执行 & 引擎
# ============================================================
WORKERS = 8
PID_FORMAT = "0-{i}"
ENGINE = {
    "type": "CalcEngine",
    "params": {},
}


# ============================================================
# 9. 图数据库
# ============================================================
NEO4J_CONFIG_PATH = "~/QuantStudioConfig/Neo4jDBConfig.json"
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024
SKIP_EMBEDDING = False


# ============================================================
# 10. 日志
# ============================================================
LOG_LEVEL = "INFO"


# ============================================================
# 11. 钩子函数 (可选)
# ============================================================
# def init_db(pool):
#     """库连接后的自定义初始化。"""
#     pool["BSDB"].setOutputMode("pandas")

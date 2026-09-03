# -*- coding: utf-8 -*-
"""运行时配置示例 —— 根据实际环境修改后放到 ~/QuantStudioConfig/settings.py。

配置继承链（优先级从低到高）：
    1. __INHERIT_FROM__ 父模块
    2. 当前模块变量
    3. settings_local.py（不入库，本地覆盖）
    4. QS_* 环境变量
    5. 命令行 --xxx 参数
"""
import os


# ============================================================
# 配置继承
# ============================================================
# __INHERIT_FROM__ = os.path.expanduser("~/QuantStudioConfig/settings.py")


# ============================================================
# 运行模式
# ============================================================

DEBUG = False
UPDATE_DATA = True
DRY_RUN = False

# ============================================================
# 因子库定义
# ============================================================

FACTOR_DATABASES = [
    {
        "name": "JYDB",
        "class": "JYDB",
        "role": "source",
        "config_file": os.path.expanduser("~/QuantStudioConfig/JYDBConfig.json"),
    },
    {
        "name": "BSDB",
        "class": "BaoStockDB",
        "role": "source",
    },
    {
        "name": "LDB",
        "class": "HDF5DB",
        "role": "target",
        "args": {"MainDir": r"D:\Data\HDF5DB"},
    },
    {
        "name": "TDB",
        "class": "HDF5DB",
        "role": "target",
        "args": {"MainDir": r"D:\Data\HDF5DB_Test"},
    },
    {
        "name": "ProxyDB",
        "class": "HDF5DB",
        "role": "proxy",
        "args": {"MainDir": r"D:\Data\HDF5DB"},
    },
]

# ============================================================
# 代理表
# ============================================================

PROXY_TABLE_MAPPING = {
    # "源表名": "代理表名",
}

# ============================================================
# 数据源
# ============================================================

# 交易日历数据源
TRADING_DAY_SOURCE = {
    "name": "JYDB",
    "method": "getTradeDay",
    "method_args": {},
}

# 截面 ID 定义集合 —— 命名截面，供 FACTOR_PROFILES / STRATEGY_PROFILES / REPORT_PROFILES 引用
# 支持两种格式:
#   {"type": "list", "ids": [...]}                              — 显式 ID 列表
#   {"type": "fdb_method", "name": "...", "method": "...", "method_args": {...}} — 数据源方法调用
SECTION_ID_SOURCES = {
    "全部A股": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getStockID",
        "method_args": {},
    },
    "当前A股": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getStockID",
        "method_args": {"is_current": True},
    },
    "沪深300": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getIndexConstituent",
        "method_args": {"index_code": "000300.SH"},
    },
    "中证500": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getIndexConstituent",
        "method_args": {"index_code": "000905.SH"},
    },
    # 自定义截面示例
    "自选股": {
        "type": "list",
        "ids": ["000001.SZ", "000002.SZ", "000003.SZ", "600519.SH"],
    },
}

# ============================================================
# 时间范围
# ============================================================

END_DT = "last_friday"
START_DT = None
LOOKBACK = 252
MAX_LOOKBACK = 3650
DT_TYPE = "交易日"
DT_FREQ = "1d"

# ============================================================
# 因子 Profile —— 定义因子计算的维度分组
# ============================================================
# id_selection:    引用 SECTION_ID_SOURCES 的 key → FactorLocalContext.IDs（最终输出的因子 ID 序列）
# section_id_list: 引用 SECTION_ID_SOURCES 的 key → FactorLocalContext.SectionIDs（计算时使用的截面）

FACTOR_PROFILES = [
    {
        "id_selection": "自选股",
        "section_id_list": "自选股",
        "factor_modules": [
            "QSExt.FactorDef.stock_cn_factor_example1",
            "QSExt.FactorDef.stock_cn_factor_example2",
        ],
        "proxy_tables": None,
        # 以下两项可选，配置则覆盖全局 TARGET_DB / FACTOR_STORER_CONFIG
        "target_db": "TDB",
        "factor_storer_config": {"IfExists": "update", "UpdateMeta": True},
    },
]

# ============================================================
# 策略 Profile —— 定义策略计算的维度分组
# ============================================================
# section_id_list: 引用 SECTION_ID_SOURCES 的 key → FactorLocalContext.SectionIDs
#                  策略的 IDs 与 SectionIDs 相同

STRATEGY_PROFILES = [
    {
        "section_id_list": "自选股",
        "strategy_modules": [
            "QSExt.StrategyDef.stock_cn_strategy_example",
        ],
        # 可选，覆盖全局 TARGET_DB / FACTOR_STORER_CONFIG
        # "target_db": "TDB",
        # "factor_storer_config": {"IfExists": "update", "UpdateMeta": True},
    },
]

# ============================================================
# 输出
# ============================================================

TARGET_DB = "TDB"

FACTOR_STORER_CONFIG = {
    "IfExists": "update",
    "UpdateMeta": True,
}

# 回测结果存储（StrategyDef 专用，None 则不存储）
BT_STORE = {
    "name": "BTResultDB",
    "class": "HDF5BTResultDB",
    "role": "target",
    "args": {"MainDir": r"D:\Data\HDF5BTResult"},
}

# ============================================================
# 报告
# ============================================================
# section_id_list: 引用 SECTION_ID_SOURCES 的 key，指定报告的截面范围
# factors: 目标因子列表，每项格式：
#   - db: 因子库名
#   - table: 因子表名
#   - factor: 因子选择，支持三种格式：
#       "*"                                              — 全部因子
#       ["close", "volume"]                              — 指定因子名列表
#       [{"Name": "close", "Alias": "收盘价", "Order": "升序"}, ...]  — 带配置的因子列表
#         Alias: 可选，重命名后的因子名
#         Order: 可选，"升序" 表示取负值（默认 "降序" 不处理）
# ref_factors: 参考因子来源 {逻辑名: {db, table, factor}}

REPORT_PROFILES = {
    "a_stock_full": {
        "scenario": "single_factor",
        "section_id_list": "全部A股",
        "config": "",
        "factors": [
            # {"db": "LDB", "table": "stock_cn_factor_size", "factor": "*"},  # 全部因子
            {"db": "LDB", "table": "stock_cn_factor_size", "factor": [
                "float_cap",
                {"Name": "total_cap", "Alias": "总市值", "Order": "升序"},
            ]},  # 带重命名和升序配置
        ],
        "ref_factors": {
            "price": {"db": "LDB", "table": "stock_cn_day_bar_adj_backward_nafilled", "factor": "close"},
            "mask": {"db": "LDB", "table": "stock_cn_status", "factor": "if_listed"},
        },
    },
}

REPORT_OUTPUT_DIR = r"D:\Data\QSReport"

# ============================================================
# 缓存
# ============================================================

CACHE_DIR = ""
USE_TEMP_CACHE = True
CACHE_START_MODE = "new"
CACHE_SUFFIX = ".pkl"

# ============================================================
# 执行 & 引擎
# ============================================================

WORKERS = 8
PID_FORMAT = "0-{i}"

ENGINE = {
    "type": "CalcEngine",
    "params": {},
}

# ============================================================
# 图数据库
# ============================================================

NEO4J_CONFIG_PATH = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024
SKIP_EMBEDDING = False

# ============================================================
# 日志
# ============================================================

LOG_LEVEL = "INFO"

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
# 指向父配置文件路径，当前配置会继承父配置的所有变量
# 未设置的变量使用父配置的值，已设置的变量覆盖父配置
# __INHERIT_FROM__ = os.path.expanduser("~/QuantStudioConfig/settings.py")


# ============================================================
# 运行模式
# ============================================================

DEBUG = False           # True: 调试模式，输出详细日志
UPDATE_DATA = True      # True: 更新数据，False: 仅计算不写入
DRY_RUN = False         # True: 仅打印配置，不实际执行


# ============================================================
# 因子库定义
# ============================================================
# 定义所有可用的因子数据库连接
# 每个数据库定义包含：
#   - name: 数据库逻辑名称，在因子定义中通过 FDB["name"] 引用
#   - class: 数据库类名（JYDB / BaoStockDB / HDF5DB / ClickHouseDB / MongoDB 等）
#   - role: 角色
#       "source"  — 数据源（只读，用于读取原始数据）
#       "target"  — 目标库（可写，用于存储计算结果）
#       "proxy"   — 代理库（增量更新时复用上次计算结果）
#   - config_file: 配置文件路径（可选，部分数据库需要）
#   - args: 数据库初始化参数（可选）

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
# 代理表映射关系，用于增量更新时复用上次计算结果
# key: 源表名，value: 代理表名
# 留空则不使用代理

PROXY_TABLE_MAPPING = {
    # "源表名": "代理表名",
}


# ============================================================
# 数据源
# ============================================================

# 交易日历数据源配置
# 用于获取交易日序列，支持所有因子库的 getTradeDay 方法
TRADING_DAY_SOURCE = {
    "name": "JYDB",         # 因子库名称
    "method": "getTradeDay", # 获取交易日的方法名
    "method_args": {},       # 方法参数
}

# 截面 ID 定义集合 —— 命名截面，供 FACTOR_PROFILES / STRATEGY_PROFILES / REPORT_PROFILES 引用
# 支持两种格式:
#   {"type": "list", "ids": [...]}
#       显式 ID 列表，直接指定证券代码
#
#   {"type": "fdb_method", "name": "...", "method": "...", "method_args": {...}}
#       数据源方法调用，动态获取 ID 列表
#       - name: 因子库名称（引用 FACTOR_DATABASES 中的 name）
#       - method: 调用的方法名
#       - method_args: 方法参数

SECTION_ID_SOURCES = {
    "全部A股": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getStockID",
        "method_args": {},  # 无参数，获取全部历史 A 股
    },
    "当前A股": {
        "type": "fdb_method",
        "name": "JYDB",
        "method": "getStockID",
        "method_args": {"is_current": True},  # 仅当前在市股票
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
# 控制因子计算和回测的时间范围

END_DT = "last_friday"  # 结束日期，支持: "today", "last_friday", "last_month_end", 或具体日期 "2025-01-01"
START_DT = None         # 起始日期，None 则由 LOOKBACK 推算
LOOKBACK = 252          # 回溯天数（约1年交易日），当 START_DT 为 None 时使用
MAX_LOOKBACK = 3650     # 最大回溯天数，用于生成 DTRuler
DT_TYPE = "交易日"      # 时点类型: "交易日" / "自然日"
DT_FREQ = "1d"          # 时点频率: "1d"(日), "1w"(周), "1m"(月)


# ============================================================
# 因子 Profile —— 定义因子计算的维度分组
# ============================================================
# 每个 Profile 定义一组因子的计算配置：
#   - id_selection:    引用 SECTION_ID_SOURCES 的 key
#                      → FactorLocalContext.IDs（最终输出的因子 ID 序列）
#   - section_id_list: 引用 SECTION_ID_SOURCES 的 key
#                      → FactorLocalContext.SectionIDs（计算时使用的截面）
#   - factor_modules:  因子定义模块列表（Python 模块路径）
#   - proxy_tables:    代理表配置
#                      None   — 不使用代理
#                      "*"    — 全部表使用代理
#                      ["t1", "t2"] — 指定表使用代理
#   - target_db:       可选，覆盖全局 TARGET_DB
#   - factor_storer_config: 可选，覆盖全局 FACTOR_STORER_CONFIG

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
# 每个 Profile 定义一组策略的计算配置：
#   - section_id_list: 引用 SECTION_ID_SOURCES 的 key
#                      → FactorLocalContext.SectionIDs（计算时使用的截面）
#                      策略的 IDs 与 SectionIDs 相同
#   - strategy_modules: 策略定义模块列表（Python 模块路径）
#   - target_db:        可选，覆盖全局 TARGET_DB
#   - factor_storer_config: 可选，覆盖全局 FACTOR_STORER_CONFIG

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

# 全局目标数据库（因子计算结果写入的库）
# 可在 FACTOR_PROFILES / STRATEGY_PROFILES 中通过 target_db 覆盖
TARGET_DB = "TDB"

# 全局因子存储配置
# 可在 FACTOR_PROFILES / STRATEGY_PROFILES 中通过 factor_storer_config 覆盖
FACTOR_STORER_CONFIG = {
    "IfExists": "update",   # 表已存在时的处理: "update"(更新), "rewrite"(重写), "skip"(跳过)
    "UpdateMeta": True,     # True: 同时更新因子元信息
}

# 回测结果存储配置（StrategyDef 专用，None 则不存储）
# 配置回测结果库，用于存储策略回测的净值、交易记录等
BT_STORE = {
    "name": "BTResultDB",
    "class": "HDF5BTResultDB",
    "role": "target",
    "args": {"MainDir": r"D:\Data\HDF5BTResult"},
}


# ============================================================
# 报告
# ============================================================
# REPORT_PROFILES 定义报告生成配置，每个 key 是一个报告配置名称
#
# 通用配置项：
#   - scenario:        报告场景名称（如 "single_factor", "single_strategy"）
#   - section_id_list: 引用 SECTION_ID_SOURCES 的 key，指定报告的截面范围
#   - config:          YAML 配置文件路径，留空使用场景内置默认配置
#   - ref_factors:     参考因子，用于报告生成
#       {逻辑名: {"db": "因子库名", "table": "因子表名", "factor": "因子名"}}
#
# 因子类场景（single_factor / multi_factor）专用：
#   - factors:         目标因子列表，每项格式：
#       {
#           "db": "因子库名",
#           "table": "因子表名",
#           "factor": 因子选择，支持三种格式：
#               "*"         — 全部因子
#               ["f1", "f2"] — 因子名列表
#               [{"Name": "f1", "Alias": "别名", "Order": "升序"}, ...] — 带配置的因子列表
#       }
#
# 策略类场景（single_strategy / multi_strategy）专用：
#   - strategies:      策略列表，支持两种模式：
#       模式 A — 从 FactorDB 加载预计算信号：
#           {"db": "因子库名", "table": "因子表名", "signal_factor": "信号因子名",
#            "name": "策略名称", "signal_type": "目标权重", "init_cash": 1000000,
#            "price_db": "...", "price_table": "...", "price_factor": "close"}
#       模式 B — 动态导入 StrategyDef 模块：
#           {"module": "模块路径", "name": "策略名称",
#            "model_args": {"key": "value"}, "settings_path": ""}

REPORT_PROFILES = {
    # ---- 因子类报告示例 ----
    "a_stock_full": {
        "scenario": "single_factor",
        "section_id_list": "全部A股",
        "config": "",  # 留空使用场景内置默认配置
        "factors": [
            # 全部因子
            # {"db": "LDB", "table": "stock_cn_factor_size", "factor": "*"},
            # 指定因子列表
            {"db": "LDB", "table": "stock_cn_factor_size", "factor": [
                "float_cap",
                {"Name": "total_cap", "Alias": "总市值", "Order": "升序"},
            ]},
        ],
        "ref_factors": {
            "price": {"db": "LDB", "table": "stock_cn_day_bar_adj_backward_nafilled", "factor": "close"},
            "mask": {"db": "LDB", "table": "stock_cn_status", "factor": "if_listed"},
        },
    },

    # ---- 策略类报告示例（模式 A：从 FactorDB 加载信号） ----
    # "strategy_from_db": {
    #     "scenario": "single_strategy",
    #     "section_id_list": "全部A股",
    #     "config": "",
    #     "strategies": [
    #         {
    #             "db": "LDB",
    #             "table": "stock_cn_strategy_example",
    #             "signal_factor": "signal",
    #             "price_db": "LDB",
    #             "price_table": "stock_cn_day_bar_adj_backward_nafilled",
    #             "price_factor": "close",
    #             "name": "均线策略",
    #             "signal_type": "目标权重",
    #             "init_cash": 1000000,
    #         },
    #     ],
    #     "ref_factors": {
    #         "bmk_nv": {"db": "LDB", "table": "benchmark_nv", "factor": "nv"},
    #     },
    # },

    # ---- 策略类报告示例（模式 B：动态导入策略模块） ----
    # "strategy_from_module": {
    #     "scenario": "single_strategy",
    #     "section_id_list": "全部A股",
    #     "config": "",
    #     "strategies": [
    #         {
    #             "module": "stock_cn_strategy_example",
    #             "name": "均线策略",
    #             "model_args": {"short_window": 5, "long_window": 20},
    #         },
    #     ],
    #     "ref_factors": {
    #         "bmk_nv": {"db": "LDB", "table": "benchmark_nv", "factor": "nv"},
    #     },
    # },
}

# 报告输出目录
REPORT_OUTPUT_DIR = r"D:\Data\QSReport"


# ============================================================
# 缓存
# ============================================================
# 因子计算缓存配置，避免重复计算

CACHE_DIR = ""              # 缓存目录，留空则不使用缓存
USE_TEMP_CACHE = True       # True: 使用临时缓存（进程结束删除）
CACHE_START_MODE = "new"    # 缓存模式: "new"(新建), "read"(只读), "append"(追加)
CACHE_SUFFIX = ".pkl"       # 缓存文件后缀


# ============================================================
# 执行 & 引擎
# ============================================================

WORKERS = 8                 # 并行工作进程数（0 或 1 表示单进程）
PID_FORMAT = "0-{i}"       # 进程 ID 格式

# 计算引擎配置
# type: 引擎类型
#   "Engine"          — 顺序执行引擎（单进程）
#   "ParallelEngine"  — 多进程并行引擎
# params: 引擎参数
#   - IOConcurrentNum: IO 并发数（默认 None，自动决定）

ENGINE = {
    "type": "ParallelEngine",
    "params": {},
}


# ============================================================
# 图数据库
# ============================================================
# QSRegistry 计算图注册中心配置

NEO4J_CONFIG_PATH = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
EMBEDDING_MODEL = "bge-m3"     # 语义向量模型名称
EMBEDDING_DIM = 1024           # 向量维度
SKIP_EMBEDDING = False         # True: 跳过语义向量生成


# ============================================================
# 日志
# ============================================================

LOG_LEVEL = "INFO"  # 日志级别: "DEBUG", "INFO", "WARNING", "ERROR"

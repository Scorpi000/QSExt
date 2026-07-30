# ============================================================
# QSExt FactorDef 运行时配置（示例）
# ============================================================
# 复制此文件为 settings.py 并根据实际环境修改。
#
# 环境切换:
#   python run_factor_def.py --settings settings_prod
# 或设置环境变量:
#   FACTORDEF_SETTINGS_MODULE=settings_prod python run_factor_def.py
#
# 所有大写变量均可被以下方式覆盖（优先级由低到高）：
#   1. 本文件默认值
#   2. settings_local.py（不入库，用于本地覆盖）
#   3. FACTORDEF_* 环境变量
#   4. 命令行 --xxx 参数
#
# 注意：默认加载路径为 QSResearch.FactorDef.conf.settings，
# 若将配置文件放在其他位置，需通过绝对路径或完整模块路径指定：
#   python run_factor_def.py --settings /path/to/my_settings.py


# ============================================================
# 1. 运行模式
# ============================================================
DEBUG = False                  # 调试模式（只取 3 只股票）
UPDATE_DATA = True             # 是否更新因子数据
REGISTER_GRAPH = False         # 是否注册到图数据库
DRY_RUN = False                # 仅分析不执行


# ============================================================
# 2. 因子数据库定义 (FACTOR_DATABASES)
# ============================================================
# 每个元素对应一个 FactorDB 实例，role 决定用途：
#   "source" — 数据源（如 JYDB）
#   "target" — 输出目标（如 HDF5DB）
#   "proxy"  — 代理缓存（复用已计算的因子值）
FACTOR_DATABASES = [
    # 数据源：聚源数据库
    {
        "name": "JYDB",
        "class": "JYDB",                    # 类名或完整 Python 路径
        "role": "source",
        "args": {
            "FTArgs": {"PreFilterID": False},
        },
        # "config_file": "path/to/config.json",  # 可选，JSON 配置文件路径
    },
    # 输出目标：本地 HDF5
    {
        "name": "TDB",
        "class": "HDF5DB",
        "role": "target",
        "args": {
            "MainDir": r"D:\Data\HDF5DB",
        },
    },
    # 代理缓存：复用已计算的因子值
    {
        "name": "ProxyDB",
        "class": "HDF5DB",
        "role": "proxy",
        "args": {
            "MainDir": r"D:\Data\HDF5DB",   # 通常与 target 目录一致
        },
    },
]

# 代理表名映射：{因子表名: 代理库中的表名}
# 留空表示代理库表名与源表名一致
PROXY_TABLE_MAPPING = {}


# ============================================================
# 3. 时间范围
# ============================================================
END_DT = "last_friday"         # 截止日期，支持: "today", "last_friday", "2026-06-30"
START_DT = None                # 起始日期（None 表示由 lookback 推算）
LOOKBACK = 15                  # 交易日回溯天数（START_DT 为 None 时生效）
MAX_LOOKBACK = 365 * 10        # DTRuler 最大回溯天数
DT_TYPE = "交易日"              # 时点类型: "交易日" 或 "自然日"
DT_FREQ = "1d"                 # DTs 和 DTRuler 的时点频率: "1d", "1w", "2w", "1m"


# ============================================================
# 4. 数据源指定
# ============================================================
DT_SOURCE = "JYDB"             # 提供 getTradeDay 的数据源名称
ID_SOURCE = "JYDB"             # 提供 getStockID 的数据源名称


# ============================================================
# 5. ID 类型与因子模块 (ID_PROFILES)
# ============================================================
# 每个 profile 指定一个 IDType 维度的因子模块分组。
# 所有 profile 的因子汇总后一次性提交给执行引擎。
#
# factor_modules 支持两种格式：
#   字符串 — 模块路径，支持 glob:
#     "QSResearch.FactorDef.JY.stock_cn_status"
#     "QSResearch.FactorDef.JY.stock_cn_*"
#
#   字典 — 带 model_args 和 factor_meta 覆盖:
#     {
#         "module": "QSResearch.FactorDef.JY.industry_cn_factor_from_stock",
#         "model_args": {"industry_factor": "sw2021_code_level1"},
#         "factor_meta": {                     # 可选，覆盖 __FACTOR_META__ 字段
#             "TargetTable": "custom_table_name",
#             "Description": "自定义描述",
#         },
#     }
#
#
# id_selection 支持三种类型:
#   {"type": "all"}              — 全部 ID（含历史退市）
#   {"type": "current"}          — 当前存续 ID
#   {"type": "list", "ids": [...]} — 指定 ID 列表
#
# proxy_tables 代理表控制（需配合 --use-proxy 命令行参数）:
#   None                         — 不代理（默认）
#   "*"                          — 该 profile 下全部依赖表走代理
#   ["table1", "table2"]         — 指定表走代理

ID_PROFILES = [
    {
        "id_type": "A股",
        "id_selection": {"type": "all"},
        "factor_modules": [
            "QSResearch.FactorDef.JY.stock_cn_status",
            # glob 模式:
            # "QSResearch.FactorDef.JY.stock_cn_factor_*",
            # 带 model_args 的字典格式:
            # {
            #     "module": "QSResearch.FactorDef.JY.industry_cn_factor_from_stock",
            #     "model_args": {
            #         "industry_factor": "sw2021_code_level1",
            #         "stock_ids": "$stock_ids",
            #     },
            #     "factor_meta": {
            #         "TargetTable": "industry_cn_factor_sw2021",
            #     },
            # },
        ],
        # "section_id_list": ["000001.SZ", "600000.SH"],  # 可选，自定义截面证券列表
        # "proxy_tables": ["stock_cn_status", "stock_cn_day_bar_nafilled"],  # 可选，指定表代理
    },
    # {
    #     "id_type": "行业",
    #     "id_selection": {"type": "all"},
    #     "factor_modules": [...],
    #     "proxy_tables": "*",  # 全部代理
    # },
]


# ============================================================
# 6. 输出配置
# ============================================================
TARGET_DB = "TDB"              # 输出目标库名（或列表 ["TDB1", "TDB2"]）
FACTOR_STORER_CONFIG = {
    "IfExists": "update",      # 因子已存在时的处理: "update" | "append" | "skip"
    "UpdateMeta": True,        # 是否更新因子元信息
}


# ============================================================
# 7. 缓存
# ============================================================
CACHE_DIR = r"D:\Data\Cache\FactorTaskCache"
# 缓存起始模式: "new" | "read" | "all"
CACHE_START_MODE = "new"
CACHE_SUFFIX = ".pkl"


# ============================================================
# 8. 执行引擎
# ============================================================
WORKERS = 8                   # 并发 worker 数
PID_FORMAT = "0-{i}"          # PID 格式模板


# ============================================================
# 9. 图数据库（register_factors_to_graphdb.py 使用）
# ============================================================
NEO4J_CONFIG_PATH = r"~/QuantStudioConfig/Neo4jDBConfig.json"
EMBEDDING_MODEL = "bge-m3"     # 嵌入模型名称
EMBEDDING_DIM = 1024           # 嵌入维度
SKIP_EMBEDDING = False         # 是否跳过向量嵌入


# ============================================================
# 10. 日志
# ============================================================
LOG_LEVEL = "INFO"             # 日志级别: "DEBUG" | "INFO" | "WARNING" | "ERROR"


# ============================================================
# 11. 钩子函数（可选）
# ============================================================
# def init_db(pool):
#     """库连接后的自定义初始化"""
#     pool["JYDB"].setOutputMode("pandas")

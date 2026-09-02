# -*- coding: utf-8 -*-
"""QSExt 统一运行时配置基类。

提供:
  - DBDef: 单条因子库/风险库连接定义
  - DBPool: 因子库连接池（创建、连接、访问、断开）
  - RuntimeSettings: 统一运行时配置基类
    - from_module(): 从 Python 模块加载，支持 __INHERIT_FROM__ 链式继承
    - 配置覆盖优先级（从低到高）:
      1. 继承链中的父模块默认值
      2. 当前模块值
      3. settings_local.py（不入库，本地覆盖）
      4. QS_* 环境变量
      5. 命令行 --xxx 参数
"""

import importlib
import json
import os
import sys
from typing import Dict, List, Optional, Union

from pydantic import Field

from QuantStudio.Core import __QS_Args__

# ---- 内置 DB 类型短名映射 ----

_BUILTIN_DB_CLASSES = {
    "JYDB": "QuantStudio.Factor.JYDB.JYDB",
    "BaoStockDB": "QuantStudio.Factor.BaoStockDB.BaoStockDB",
    "HDF5DB": "QuantStudio.Factor.HDF5DB.HDF5DB",
    "SQLDB": "QuantStudio.Factor.SQLDB.SQLDB",
}


# ============================================================
# DBDef — 单条数据库连接定义
# ============================================================

class DBDef(__QS_Args__):
    """单条数据库连接定义。

    对应 FACTOR_DATABASES 配置中的一个元素。
    """

    name: str = Field(default="", title="逻辑名称")
    class_path: str = Field(default="", title="类路径，支持短名如 JYDB、HDF5DB")
    role: str = Field(default="source", title="角色: source / target / proxy")
    args: dict = Field(default={}, title="构造参数")
    config_file: Optional[str] = Field(default=None, title="外部配置文件路径（JSON）")

    @property
    def resolved_class_name(self) -> str:
        """解析后的完整类路径。"""
        return _BUILTIN_DB_CLASSES.get(self.class_path, self.class_path)


# ============================================================
# DBPool — 因子库连接池
# ============================================================

class DBPool:
    """因子库连接池 —— 统一管理所有 FactorDB 实例的创建、连接、访问和断开。

    使用示例:
        pool = DBPool(settings.factor_databases)
        pool.create_all()
        pool.connect_all()
        jydb = pool["JYDB"]
        pool.disconnect_all()

    上下文管理器:
        with DBPool(db_defs) as pool:
            db = pool["JYDB"]
    """

    def __init__(self, db_defs: List[DBDef]):
        self._defs = db_defs
        self._instances: Dict[str, object] = {}
        self._connected: Dict[str, bool] = {}

    # ---- 创建 ----

    def create_all(self) -> None:
        """实例化所有 DB 对象（不连接）。"""
        for db_def in self._defs:
            self._instances[db_def.name] = self._create_one(db_def)
            self._connected[db_def.name] = False

    def _create_one(self, db_def: DBDef):
        """根据单条定义创建一个 FactorDB 实例。"""
        cls = self._resolve_class(db_def.resolved_class_name)

        kwargs = {"args": db_def.args}
        if db_def.config_file:
            kwargs["config_file"] = os.path.expanduser(db_def.config_file)

        # HDF5DB: 确保输出目录存在
        if db_def.role in ("target", "proxy") and "MainDir" in db_def.args:
            os.makedirs(db_def.args["MainDir"], exist_ok=True)

        return cls(**kwargs)

    # ---- 连接 ----

    def connect_all(self) -> None:
        """连接所有已创建的库。"""
        for name in list(self._instances.keys()):
            self.connect_one(name)

    def connect_one(self, name: str):
        """连接指定库。"""
        if name not in self._instances:
            raise KeyError(f"因子库 '{name}' 未创建")
        if not self._connected.get(name, False):
            self._instances[name].connect()
            self._connected[name] = True
        return self._instances[name]

    # ---- 访问 ----

    def __getitem__(self, name: str):
        """通过 name 获取实例。"""
        if name not in self._instances:
            raise KeyError(
                f"因子库 '{name}' 不存在。可用: {list(self._instances.keys())}"
            )
        return self._instances[name]

    def __contains__(self, name: str) -> bool:
        """支持 `name in pool` 操作。"""
        return name in self._instances

    def get_source(self, name: Optional[str] = None):
        """获取数据源库。name=None 时返回第一个 role='source' 的库。"""
        if name:
            return self[name]
        for db_def in self._defs:
            if db_def.role == "source":
                return self[db_def.name]
        raise KeyError("没有配置 role='source' 的因子库")

    def get_target(self, name: Optional[str] = None):
        """获取目标库。name=None 时返回第一个 role='target' 的库。"""
        if name:
            return self[name]
        for db_def in self._defs:
            if db_def.role == "target":
                return self[db_def.name]
        raise KeyError("没有配置 role='target' 的因子库")

    def get_proxy(self):
        """获取代理库，无代理时返回 None。"""
        for db_def in self._defs:
            if db_def.role == "proxy":
                return self[db_def.name]
        return None

    # ---- 生命周期 ----

    def disconnect_all(self) -> None:
        """断开所有连接。"""
        for name, instance in self._instances.items():
            if self._connected.get(name, False):
                try:
                    instance.disconnect()
                except Exception:
                    pass
                self._connected[name] = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect_all()

    # ---- 内省 ----

    @property
    def source_names(self) -> List[str]:
        return [d.name for d in self._defs if d.role == "source"]

    @property
    def target_names(self) -> List[str]:
        return [d.name for d in self._defs if d.role == "target"]

    # ---- 内部 ----

    @staticmethod
    def _resolve_class(class_path: str) -> type:
        """解析类路径字符串 -> 类对象。"""
        if class_path in _BUILTIN_DB_CLASSES:
            class_path = _BUILTIN_DB_CLASSES[class_path]

        parts = class_path.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"无效的类路径: {class_path}")

        module_name, class_name = parts
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ImportError(f"无法导入模块 '{module_name}': {e}")

        if not hasattr(module, class_name):
            raise AttributeError(
                f"模块 '{module_name}' 中不存在类 '{class_name}'"
            )
        return getattr(module, class_name)


# ============================================================
# RuntimeSettings — 统一运行时配置基类
# ============================================================

class RuntimeSettings(__QS_Args__):
    """统一运行时配置基类。

    FactorDefSettings 和 StrategyDefSettings 直接继承此类。
    QSWeb 通过 from_module() 加载后按需读取字段。
    """

    # ---- 运行模式 ----
    debug: bool = Field(default=False, title="调试模式")
    update_data: bool = Field(default=True, title="更新因子/策略数据")
    register_graph: bool = Field(default=False, title="注册到图数据库")
    dry_run: bool = Field(default=False, title="仅分析不执行")

    # ---- 数据库 ----
    factor_databases: List[DBDef] = Field(default=[], title="因子库定义列表")
    proxy_table_mapping: dict = Field(default={}, title="代理表名映射")
    risk_databases: list = Field(default=[], title="风险库定义")

    # ---- 数据源 ----
    trading_day_source: dict = Field(
        default={"name": "JYDB", "method": "getTradeDay", "method_args": {}},
        title="交易日历数据源",
    )
    section_id_sources: dict = Field(
        default={
            "A股": {"name": "JYDB", "method": "getStockID", "method_args": {}}
        },
        title="截面 ID 数据源（按 IDType），自定义 IDType 只需添加对应条目",
    )

    # ---- 时间范围 ----
    end_dt: str = Field(default="last_friday", title="截止日期")
    start_dt: Optional[str] = Field(default=None, title="起始日期")
    lookback: int = Field(default=15, title="交易日回溯天数")
    max_lookback: int = Field(default=365 * 10, title="DTRuler 最大回溯天数")
    dt_type: str = Field(default="交易日", title="时点类型: 交易日 | 自然日")
    dt_freq: str = Field(default="1d", title="DTs 和 DTRuler 的时点频率")

    # ---- ID 类型与模块 ----
    id_profiles: List[dict] = Field(default=[], title="ID 类型与模块配置列表")

    # ---- 输出 ----
    target_db: Union[str, List[str]] = Field(default="TDB", title="输出目标库名")
    factor_storer_config: dict = Field(
        default={"IfExists": "update", "UpdateMeta": True},
        title="FactorStorer 参数",
    )

    # ---- 缓存 ----
    cache_dir: str = Field(default="", title="缓存目录")
    use_temp_cache: bool = Field(default=True, title="使用临时缓存")
    cache_start_mode: str = Field(default="new", title="缓存起始模式")
    cache_suffix: str = Field(default=".pkl", title="缓存文件后缀")

    # ---- 执行 & 引擎 ----
    workers: int = Field(default=8, title="并发 worker 数")
    pid_format: str = Field(default="0-{i}", title="PID 格式")
    engine: dict = Field(
        default={"type": "CalcEngine", "params": {}},
        title="计算引擎配置",
    )

    # ---- 图数据库 ----
    neo4j_config_path: str = Field(
        default="~/QuantStudioConfig/Neo4jDBConfig.json",
        title="Neo4j 配置路径",
    )
    embedding_model: str = Field(default="bge-m3", title="嵌入模型")
    embedding_dim: int = Field(default=1024, title="嵌入维度")
    skip_embedding: bool = Field(default=False, title="跳过向量嵌入")

    # ---- 日志 ----
    log_level: str = Field(default="DEBUG", title="日志级别")

    # ============================================================
    # 工厂方法
    # ============================================================

    @classmethod
    def from_module(cls, module_path: str = "settings", **cmd_overrides) -> "RuntimeSettings":
        """从 Python 模块加载配置。

        加载流程:
          1. 解析模块路径并加载
          2. 若模块定义了 __INHERIT_FROM__，递归加载父模块
          3. 提取 UPPERCASE 变量
          4. settings_local.py 覆盖（若存在）
          5. QS_ 环境变量覆盖
          6. 命令行参数覆盖

        Args:
            module_path: 模块路径或文件路径。
                         "settings" -> 解析为 QSExt.RuntimeConfig.conf.settings
            **cmd_overrides: 命令行覆盖参数，如 debug=True

        Returns:
            RuntimeSettings 实例
        """
        # 解析模块路径
        if not module_path.startswith("QSExt") and not os.path.isabs(module_path):
            # 尝试在当前 conf 目录下查找
            module_path = f"QSExt.RuntimeConfig.conf.{module_path}"

        # 加载模块并递归处理继承链
        settings_dict, hooks = cls._load_module_with_inheritance(module_path)

        # settings_local 覆盖（在最终叶子模块的同目录）
        if not os.path.isabs(module_path):
            try:
                # 点号路径 -> 找同目录
                local_module_path = ".".join(
                    module_path.split(".")[:-1] + ["settings_local"]
                )
                local_module = importlib.import_module(local_module_path)
                cls._extract_settings(local_module, settings_dict, hooks)
            except ImportError:
                pass

        # QS_ 环境变量覆盖
        for env_key, env_val in dict(os.environ).items():
            if env_key.startswith("QS_"):
                setting_key = env_key[len("QS_"):].lower()
                try:
                    settings_dict[setting_key] = json.loads(env_val)
                except (json.JSONDecodeError, ValueError):
                    settings_dict[setting_key] = env_val

        # 命令行覆盖
        settings_dict.update(cmd_overrides)

        return cls.from_dict(settings_dict, hooks)

    @classmethod
    def _load_module_with_inheritance(
        cls, module_path: str, _chain: Optional[set] = None
    ) -> tuple:
        """加载模块并递归处理 __INHERIT_FROM__ 链。

        Args:
            module_path: 模块路径
            _chain: 内部用，已加载的模块路径集合（检测循环引用）

        Returns:
            (settings_dict, hooks_dict)

        Raises:
            RuntimeError: 检测到循环继承
        """
        if _chain is None:
            _chain = set()

        module = cls._load_module(module_path)

        # 检查 __INHERIT_FROM__
        inherit_from = getattr(module, "__INHERIT_FROM__", None)
        if inherit_from:
            inherit_path = os.path.expanduser(inherit_from)
            if inherit_path in _chain:
                chain_str = " -> ".join(_chain) + f" -> {inherit_path}"
                raise RuntimeError(f"检测到配置循环继承: {chain_str}")
            _chain.add(inherit_path)

            # 递归加载父配置
            parent_dict, hooks = cls._load_module_with_inheritance(
                inherit_path, _chain
            )
        else:
            parent_dict = {}
            hooks = {}

        # 当前模块覆盖父配置
        cls._extract_settings(module, parent_dict, hooks)
        return parent_dict, hooks

    @staticmethod
    def _load_module(module_path: str):
        """加载 Python 模块（支持模块路径和文件路径）。"""
        try:
            return importlib.import_module(module_path)
        except ImportError:
            if os.path.isfile(module_path):
                spec = importlib.util.spec_from_file_location(
                    "_runtime_settings", module_path
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules["_runtime_settings"] = module
                spec.loader.exec_module(module)
                return module
            raise FileNotFoundError(f"无法加载配置模块: {module_path}")

    @staticmethod
    def _extract_settings(module, settings_dict: dict, hooks: dict) -> None:
        """从模块中提取 UPPERCASE 变量和钩子函数到 settings_dict/hooks。"""
        for key in dir(module):
            if key.isupper() and not key.startswith("_"):
                settings_dict[key.lower()] = getattr(module, key)

        for hook_name in ("init_db",):
            if hasattr(module, hook_name) and callable(getattr(module, hook_name)):
                hooks[hook_name] = getattr(module, hook_name)

    @classmethod
    def from_dict(cls, data: dict, hooks: Optional[dict] = None) -> "RuntimeSettings":
        """从字典构造 RuntimeSettings，处理嵌套类型转换。

        Args:
            data: 配置字典
            hooks: 钩子函数字典

        Returns:
            RuntimeSettings 实例
        """
        data = dict(data)  # 浅拷贝

        # 转换 factor_databases: list[dict] -> List[DBDef]
        db_defs = []
        for item in data.pop("factor_databases", []):
            if isinstance(item, DBDef):
                db_defs.append(item)
            elif isinstance(item, dict):
                db_defs.append(DBDef(
                    name=item.get("name", ""),
                    class_path=item.get("class", item.get("class_path", "")),
                    role=item.get("role", "source"),
                    args=item.get("args", {}),
                    config_file=item.get("config_file"),
                ))
        data["factor_databases"] = db_defs

        instance = cls(**data)
        if hooks:
            object.__setattr__(instance, "_hooks", hooks)
        return instance

    def get_hook(self, hook_name: str):
        """获取 settings 模块中定义的钩子函数。"""
        hooks = getattr(self, "_hooks", {})
        return hooks.get(hook_name)

    # ============================================================
    # 便捷方法
    # ============================================================

    @property
    def has_profiles(self) -> bool:
        """是否配置了多 IDType profiles。"""
        return len(self.id_profiles) > 0

    def iter_profiles(self) -> list:
        """将 id_profiles 转换为 Profile 对象列表。

        返回的 Profile 是普通的命名对象，包含:
          id_type, id_selection, factor_modules, strategy_modules,
          section_id_list, proxy_tables
        """
        from types import SimpleNamespace

        profiles = []
        for p in self.id_profiles:
            profiles.append(SimpleNamespace(
                id_type=p.get("id_type", "A股"),
                id_selection=p.get("id_selection", {"type": "all"}),
                factor_modules=p.get("factor_modules", []),
                strategy_modules=p.get("strategy_modules", []),
                section_id_list=p.get("section_id_list", {}),
                proxy_tables=p.get("proxy_tables", None),
            ))
        return profiles

    def to_db_pool(self) -> "DBPool":
        """根据 factor_databases 创建 DBPool。"""
        return DBPool(self.factor_databases)

    def get_trading_day_source_name(self) -> str:
        """获取交易日历数据源的库名。"""
        return self.trading_day_source.get("name", "JYDB")

    def get_section_id_source_name(self, id_type: str = "A股") -> str:
        """获取指定 IDType 的截面 ID 数据源库名。"""
        source = self.section_id_sources.get(id_type, {})
        return source.get("name", "JYDB")

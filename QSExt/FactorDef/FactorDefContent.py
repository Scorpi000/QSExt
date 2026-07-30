# -*- coding: utf-8 -*-
import os
import sys
import re
import importlib
import traceback
import datetime as dt
from typing import List, Dict, Optional, Tuple, Union, Literal

import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Args__, __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB

# ---- 内置 FactorDB 类名映射 ----
_BUILTIN_DB_CLASSES = {
    "JYDB": "QuantStudio.Factor.JYDB.JYDB",
    "BaoStockDB": "QuantStudio.Factor.BaoStockDB.BaoStockDB",
    "HDF5DB": "QuantStudio.Factor.HDF5DB.HDF5DB",
    "SQLDB": "QuantStudio.Factor.SQLDB.SQLDB",
}


class FactorDefInput(__QS_Args__):
    """因子定义输入对象"""
    Debug: bool = Field(default=False, title="调试环境", frozen=True)
    FDB: Dict[str, FactorDB] = Field(default={}, title="可用因子库")
    ModelArgs: Dict = Field(default={}, title="模型参数")
    DTs: List[dt.datetime] = Field(default=[], title="计算时点")
    DTRuler: List[dt.datetime] = Field(default=[], title="时点标尺")
    IDs: List[str] = Field(default=[], title="ID序列")
    SectionIDs: List[str] = Field(default=[], title="截面ID")
    TDB: Optional[WritableFactorDB] = Field(default=None, title="写入因子库")
    Factors: Dict[str, Factor] = Field(default={}, title="已解析的依赖因子")


class FactorMeta(__QS_Args__):
    """因子定义的静态元信息 —— 描述一个因子定义模块的固有属性

    与 FactorDef 分离，使得无需连接 JYDB 即可发现和筛选模块。
    所有字段均设有默认值，支持从空 dict 构造（用于 List[Factor] 模式缺少 __FACTOR_META__ 的情况）。
    """
    TargetTable: str = Field(default="", title="因子表")
    IDType: str = Field(default="", title="ID类型")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述信息")
    MaxLookBack: int = Field(default=365, title="最大回溯期")
    DefaultStartDT: dt.datetime = Field(default=dt.datetime(2002, 1, 1), title="默认起始日")
    DTType: str = Field(default="自定义", title="时点类型")
    Freq: str = Field(default="1d", title="时点频率")
    DefScriptPath: str = Field(default="", title="定义脚本路径")

    # ---- 分类与发现 ----
    Tags: List[str] = Field(default=[], title="检索标签")
    FactorDeps: Dict[str, List[Union[str, dict]]] = Field(default={}, title="依赖因子声明")
    DBDeps: Dict[str, str] = Field(default={}, title="因子库依赖", description="键为 fdi.FDB 中的逻辑名称，值为用途说明")
    ModelArgs: Dict[str, str] = Field(default={}, title="期望的模型参数", description="键为参数名，值为参数说明")


class FactorDef(__QS_Args__):
    """因子定义对象 —— 组合静态元信息与动态产物

    构造方式:
      FactorDef(FactorList=Factors, Meta=FactorMeta(**__FACTOR_META__))
    """
    FactorList: List[Factor] = Field(title="因子列表")
    Meta: FactorMeta = Field(title="静态元信息")

    @property
    def FactorNames(self) -> List[str]:
        return [iFactor._QSArgs.Name for iFactor in self.FactorList]

    def getFactor(self, factor_name:Optional[str]=None, def_path:str="...", factor_id:Optional[str]=None, only_one:bool=True) -> Factor | List[Factor]:
        """查找因子对象

        Args:
            factor_name: 因子名称, None 表示忽略该检索条件
            def_path: 以/分割的因子查找路径, 比如 年化收益率/0/1/..., 其中 ... 表示只在这层搜索，不查询该层的描述子
            factor_id: 因子 QSID, None 表示忽略该检索条件
            only_one: 查找到一个符合要求的因子对象后即返回, False 表示找到所有符合要求的因子对象后才返回

        Returns: 如果 only_one=True 则返回找到的一个因子, 如果 only_one=False 则返回找到的因子列表
        """
        if (factor_id is None) and (factor_name is None):
            raise __QS_Error__(f"入参 factor_id、factor_name 不可同时为 None")

        def _searchFactor(factors, factor_id, factor_name, recursive=True):
            Factors = {}
            for iFactor in factors:
                if ((factor_id is None) or (iFactor.QSID == factor_id)) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)):
                    Factors[iFactor.QSID] = iFactor
                if recursive:
                    Factors = Factors | {iFactor.QSID: iFactor for iFactor in _searchFactor(iFactor.Descriptors, factor_id, factor_name, recursive=recursive)}
            return list(Factors.values())

        DefPath = def_path.strip().split("/")
        LastPos = DefPath[-1]
        if LastPos in ("", "..."): DefPath = DefPath[:-1]
        if DefPath:
            iFactor = self
            for i, iIdx in enumerate(DefPath):
                try:
                    iIdx = int(iIdx)
                except:
                    try:
                        iIdx = [iDep._QSArgs.Name for iDep in iFactor.Descriptors].index(iIdx)
                    except:
                        raise __QS_Error__(f"查找不到因子 path='{'/'.join(DefPath[:i+1])}': {traceback.format_exc()}")
                try:
                    iFactor = iFactor.Descriptors[iIdx]
                except:
                    raise __QS_Error__(f"查找不到因子 path='{'/'.join(DefPath[:i+2])}': {traceback.format_exc()}")
            if (LastPos not in ("", "...")) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)) and ((factor_id is None) or (iFactor.QSID==factor_id)):
                return (iFactor if only_one else [iFactor])
            elif LastPos in ("", "..."):
                Factors = _searchFactor(factors=iFactor.Descriptors, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
            else:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
        else:
            Factors = _searchFactor(factors=self.FactorList, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
        if only_one:
            if (len(Factors) == 1) or ((len(Factors) > 1) and (factor_id is not None)):
                return Factors[0]
            elif len(Factors) == 0:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
            else:
                raise __QS_Error__(f"查找到的因子 (Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}') 不止一个!")
        else:
            return Factors


# ============================================================
# 运行时配置与 FactorDefInput 构造
# ============================================================

class FactorDBDef(__QS_Args__):
    """单条因子库定义 —— 对应 FACTOR_DATABASES 配置中的一个元素"""
    name: str = Field(default="", title="逻辑名称")
    class_path: str = Field(default="", title="类路径")
    role: str = Field(default="source", title="角色: source / target / proxy")
    args: dict = Field(default={}, title="构造参数")
    config_file: Optional[str] = Field(default=None, title="配置文件路径")


class FactorDBPool:
    """因子库连接池 —— 统一管理所有 FactorDB 实例的创建、连接、访问和断开

    使用示例:
        pool = FactorDBPool(settings.factor_databases)
        pool.create_all()
        pool.connect_all()
        jydb = pool["JYDB"]
        pool.disconnect_all()
    """

    def __init__(self, db_defs: List[FactorDBDef]):
        self._defs = db_defs
        self._instances: Dict[str, FactorDB] = {}
        self._connected: Dict[str, bool] = {}

    # ---- 创建 ----
    def create_all(self) -> None:
        """实例化所有 FactorDB 对象（不连接）"""
        for db_def in self._defs:
            self._instances[db_def.name] = self._create_one(db_def)
            self._connected[db_def.name] = False

    def _create_one(self, db_def: FactorDBDef) -> FactorDB:
        """根据单条定义创建一个 FactorDB 实例"""
        cls = self._resolve_class(db_def.class_path)

        kwargs = {"args": db_def.args}
        if db_def.config_file:
            kwargs["config_file"] = os.path.expanduser(db_def.config_file)

        # HDF5DB: 确保输出目录存在
        if db_def.role in ("target", "proxy") and "MainDir" in db_def.args:
            os.makedirs(db_def.args["MainDir"], exist_ok=True)

        return cls(**kwargs)

    @staticmethod
    def _resolve_class(class_path: str) -> type:
        """解析类路径字符串 → FactorDB 子类"""
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
            raise AttributeError(f"模块 '{module_name}' 中不存在类 '{class_name}'")
        return getattr(module, class_name)

    # ---- 连接 ----
    def connect_all(self) -> None:
        """连接所有已创建的库"""
        for name in list(self._instances.keys()):
            self.connect_one(name)

    def connect_one(self, name: str) -> FactorDB:
        """连接指定库"""
        if name not in self._instances:
            raise KeyError(f"因子库 '{name}' 未创建")
        if not self._connected.get(name, False):
            self._instances[name].connect()
            self._connected[name] = True
        return self._instances[name]

    # ---- 访问 ----
    def __getitem__(self, name: str) -> FactorDB:
        """通过 name 获取 FactorDB 实例"""
        if name not in self._instances:
            raise KeyError(f"因子库 '{name}' 不存在。可用: {list(self._instances.keys())}")
        return self._instances[name]

    def get_source(self, name: str = None) -> FactorDB:
        """获取数据源库。name=None 时返回第一个 role='source' 的库"""
        if name:
            return self[name]
        for db_def in self._defs:
            if db_def.role == "source":
                return self[db_def.name]
        raise KeyError("没有配置 role='source' 的因子库")

    def get_target(self, name: str = None) -> WritableFactorDB:
        """获取目标库。name=None 时返回第一个 role='target' 的库"""
        if name:
            return self[name]
        for db_def in self._defs:
            if db_def.role == "target":
                return self[db_def.name]
        raise KeyError("没有配置 role='target' 的因子库")

    def get_proxy(self) -> Optional[FactorDB]:
        """获取代理库，无代理时返回 None"""
        for db_def in self._defs:
            if db_def.role == "proxy":
                return self[db_def.name]
        return None

    # ---- 生命周期 ----
    def disconnect_all(self) -> None:
        """断开所有连接"""
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


class FactorDefProfile(__QS_Args__):
    """单个 IDType 维度的因子模块分组 —— 用于多 IDType 统一调度"""
    id_type: str = Field(default="A股", title="证券类型")
    id_selection: dict = Field(default={"type": "all"}, title="ID 选择策略")
    factor_modules: list = Field(default=[], title="因子模块列表")
    section_id_list: List[str] = Field(default=[], title="自定义截面证券列表")
    proxy_tables: Union[List[str], str, None] = Field(default=None, title="代理表", description="None=不代理, '*'=全部代理, ['t1','t2']=指定表代理")


class FactorDefSettings(__QS_Args__):
    """因子定义运行时配置 —— 从 settings.py 模块加载并验证"""

    # 运行模式
    debug: bool = Field(default=False, title="调试模式")
    update_data: bool = Field(default=True, title="更新因子数据")
    register_graph: bool = Field(default=False, title="注册到图数据库")
    dry_run: bool = Field(default=False, title="仅分析不执行")

    # 因子数据库
    factor_databases: List[FactorDBDef] = Field(default=[], title="因子库定义列表")
    proxy_table_mapping: dict = Field(default={}, title="代理表名映射")

    # 时间与 ID 数据源
    dt_source: str = Field(default="JYDB", title="提供 getTradeDay 的数据源")
    id_source: str = Field(default="JYDB", title="提供 getStockID 的数据源")

    # 时间范围
    end_dt: str = Field(default="last_friday", title="截止日期")
    start_dt: Optional[str] = Field(default=None, title="起始日期")
    lookback: int = Field(default=15, title="交易日回溯天数")
    max_lookback: int = Field(default=365 * 10, title="DTRuler 最大回溯天数")
    dt_type: str = Field(default="交易日", title="时点类型: 交易日 | 自然日")
    dt_freq: str = Field(default="1d", title="DTs 和 DTRuler 的时点频率")

    # ID 类型与因子模块 — ID_PROFILES 统一配置
    id_profiles: List[dict] = Field(default=[], title="ID 类型与因子模块配置列表")

    # 输出
    target_db: Union[str, List[str]] = Field(default="TDB", title="输出目标库名")
    factor_storer_config: dict = Field(default={}, title="FactorStorer 参数")

    # 缓存
    cache_dir: str = Field(default="", title="缓存目录")
    cache_start_mode: str = Field(default="new", title="缓存模式")
    cache_suffix: str = Field(default=".pkl", title="缓存文件后缀")

    # 执行
    workers: int = Field(default=8, title="并发 worker 数")
    pid_format: str = Field(default="0-{i}", title="PID 格式")

    # 图数据库
    neo4j_config_path: str = Field(default="~/QuantStudioConfig/Neo4jDBConfig.json", title="Neo4j 配置路径")
    embedding_model: str = Field(default="bge-m3", title="嵌入模型")
    embedding_dim: int = Field(default=1024, title="嵌入维度")
    skip_embedding: bool = Field(default=False, title="跳过向量嵌入")

    # 日志
    log_level: str = Field(default="DEBUG", title="日志级别")

    # ---- 工厂方法 ----
    @classmethod
    def from_module(cls, module_path: str = "settings", **cmd_overrides) -> "FactorDefSettings":
        """从 Python 模块加载配置

        Args:
            module_path: 模块路径。"settings" 解析为 QSResearch.FactorDef.conf.settings
            **cmd_overrides: 命令行覆盖参数，如 debug=True, end_dt="2026-06-30"

        Returns:
            FactorDefSettings 实例
        """
        # 解析模块路径
        if not module_path.startswith("QSResearch") and not os.path.isabs(module_path):
            module_path = f"QSResearch.FactorDef.conf.{module_path}"

        # 加载模块
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            if os.path.isfile(module_path):
                spec = importlib.util.spec_from_file_location("_factor_def_settings", module_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules["_factor_def_settings"] = module
                spec.loader.exec_module(module)
            else:
                raise FileNotFoundError(f"无法加载配置模块: {module_path}")

        # 提取 UPPERCASE 变量
        settings_dict = {}
        for key in dir(module):
            if key.isupper() and not key.startswith("_"):
                settings_dict[key.lower()] = getattr(module, key)

        # 提取钩子函数
        hooks = {}
        for hook_name in ("init_db",):
            if hasattr(module, hook_name) and callable(getattr(module, hook_name)):
                hooks[hook_name] = getattr(module, hook_name)

        # 尝试加载 settings_local 覆盖
        try:
            local_module = importlib.import_module("QSResearch.FactorDef.conf.settings_local")
            for key in dir(local_module):
                if key.isupper() and not key.startswith("_"):
                    settings_dict[key.lower()] = getattr(local_module, key)
            for hook_name in ("init_db",):
                if hasattr(local_module, hook_name) and callable(getattr(local_module, hook_name)):
                    hooks[hook_name] = getattr(local_module, hook_name)
        except ImportError:
            pass

        # 环境变量覆盖 (FACTORDEF_ 前缀)
        for env_key, env_val in os.environ.items():
            if env_key.startswith("FACTORDEF_"):
                setting_key = env_key[len("FACTORDEF_"):].lower()
                try:
                    import json
                    settings_dict[setting_key] = json.loads(env_val)
                except (json.JSONDecodeError, ValueError):
                    settings_dict[setting_key] = env_val

        # 命令行覆盖
        settings_dict.update(cmd_overrides)

        return cls.from_dict(settings_dict, hooks)

    @classmethod
    def from_dict(cls, data: dict, hooks: dict = None) -> "FactorDefSettings":
        """从字典构造 FactorDefSettings，处理嵌套类型转换"""
        data = dict(data)  # 浅拷贝，避免修改原始 dict

        # 转换 factor_databases: list[dict] → List[FactorDBDef]
        db_defs = []
        for item in data.pop("factor_databases", []):
            if isinstance(item, FactorDBDef):
                db_defs.append(item)
            elif isinstance(item, dict):
                db_defs.append(FactorDBDef(
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
        """获取 settings 模块中定义的钩子函数"""
        hooks = getattr(self, "_hooks", {})
        return hooks.get(hook_name)

    @property
    def has_profiles(self) -> bool:
        """是否配置了多 IDType profiles"""
        return len(self.id_profiles) > 0

    def iter_profiles(self) -> List["FactorDefProfile"]:
        """将 id_profiles 转换为 FactorDefProfile 列表"""
        profiles = []
        for p in self.id_profiles:
            profiles.append(FactorDefProfile(
                id_type=p.get("id_type", "A股"),
                id_selection=p.get("id_selection", {"type": "all"}),
                factor_modules=p.get("factor_modules", []),
                section_id_list=p.get("section_id_list", []),
                proxy_tables=p.get("proxy_tables", None),
            ))
        return profiles

    def to_db_pool(self) -> "FactorDBPool":
        """根据 factor_databases 创建 FactorDBPool"""
        return FactorDBPool(self.factor_databases)


class FactorDefInputBuilder:
    """根据 FactorDefSettings 构造 FactorDefInput

    生命周期:
        with FactorDefInputBuilder(settings) as builder:
            fdi = builder.build()
            # ... 使用 fdi 运行因子定义 ...

    职责:
        1. 创建并连接所有因子库 (FactorDBPool)
        2. 解析时间范围 → DTs, DTRuler
        3. 解析 ID 选择策略 → IDs, SectionIDs
        4. 组装 FDB 字典 和 FactorDefInput
        5. 解析因子模块列表
    """

    def __init__(self, settings: FactorDefSettings):
        self.settings = settings
        self._pool: Optional[FactorDBPool] = None

    # ---- 初始化 ----
    def init(self) -> None:
        """创建并连接所有因子库，然后执行钩子"""
        self._pool = self.settings.to_db_pool()
        self._pool.create_all()
        self._pool.connect_all()
        self._run_hooks()

    def _run_hooks(self) -> None:
        """执行 settings 模块中定义的钩子函数"""
        hook = self.settings.get_hook("init_db")
        if hook:
            hook(self._pool)

    # ---- 日期解析 ----
    @staticmethod
    def _parse_end_dt(end_dt: str) -> dt.datetime:
        """解析截止日期字符串"""
        today = dt.datetime.combine(dt.date.today(), dt.time(0))
        if end_dt == "today":
            return today
        elif end_dt == "yesterday":
            return today - dt.timedelta(1)
        elif end_dt == "last_friday":
            return today - dt.timedelta(dt.date.today().weekday() + 3)
        elif end_dt == "last_month_end":
            return today - dt.timedelta(dt.date.today().day)
        else:
            return pd.to_datetime(end_dt)

    # ---- 解析 ----
    def _fetch_dates(self, start_date: dt.datetime, end_date: dt.datetime) -> List[dt.datetime]:
        """根据 DT_TYPE 获取日期序列

        Args:
            start_date: 起始日期
            end_date: 截止日期

        Returns:
            "交易日" 时返回交易日期序列, "自然日" 时返回自然日序列
        """
        if self.settings.dt_type == "自然日":
            return pd.date_range(start=start_date, end=end_date, freq='D').tolist()
        else:
            dt_source = self._pool[self.settings.dt_source]
            return dt_source.getTradeDay(start_date=start_date, end_date=end_date)

    def resolve_dts(self) -> Tuple[List[dt.datetime], List[dt.datetime]]:
        """解析 DTs 和 DTRuler"""
        end_dt = self._parse_end_dt(self.settings.end_dt)

        if self.settings.start_dt:
            start_dt = pd.to_datetime(self.settings.start_dt)
        else:
            start_dt = end_dt - dt.timedelta(self.settings.lookback)

        dts = self._fetch_dates(start_date=start_dt, end_date=end_dt)
        dtruler = self._fetch_dates(
            start_date=start_dt - dt.timedelta(self.settings.max_lookback),
            end_date=end_dt,
        )
        dts = self.apply_dt_freq(dts, self.settings.dt_freq)
        dtruler = self.apply_dt_freq(dtruler, self.settings.dt_freq)
        return dts, dtruler

    @staticmethod
    def apply_dt_freq(dts: List[dt.datetime], freq: str) -> List[dt.datetime]:
        """根据频率过滤时点列表，保留每个周期内的最后一个时点

        Args:
            dts: 时点列表
            freq: 频率字符串, 如 "1d", "1w", "2w", "1m", "1q", "1y"

        Returns:
            按频率过滤后的时点列表
        """
        if not dts or freq == "1d":
            return dts
        m = re.match(r'^(\d+)([dwmqy])$', freq)
        if not m:
            raise ValueError(f"无效的频率格式: {freq}，期望如 '1d', '1w', '2w', '1m'")
        n, unit = m.groups()
        n = int(n)
        unit_map = {'d': 'D', 'w': 'W', 'm': 'ME', 'q': 'QE', 'y': 'YE'}
        pd_freq = f"{n}{unit_map[unit]}"
        s = pd.Series(range(len(dts)), index=pd.DatetimeIndex(dts))
        resampled = s.resample(pd_freq).last().dropna()
        return [dts[int(i)] for i in resampled.values]

    def _get_ids_from_source(self, id_type: str, is_current: bool = False) -> List[str]:
        """根据 id_type 从数据源获取证券 ID 列表

        Args:
            id_type: 证券类型
            is_current: True 表示仅当前有效的证券, False 表示全历史

        Returns:
            对应类型的证券 ID 列表
        """
        id_source = self._pool[self.settings.id_source]

        if id_type == "A股":
            return id_source.getStockID(is_current=is_current)
        elif id_type == "公募基金":
            return id_source.getMutualFundID(is_current=is_current)
        elif id_type == "期货":
            return id_source.getFutureID(is_current=is_current)
        elif id_type == "期权":
            return id_source.getOptionID(is_current=is_current)
        elif id_type == "ETF":
            return id_source.getMutualFundID(type="ETF", is_current=is_current)
        elif id_type == "申万一级行业指数":
            return id_source.getIndexID(type="申万一级行业指数", is_current=is_current)
        elif id_type == "申万一级行业":
            return id_source.getIndustryID(standard="申万行业分类(新)", level=1, is_current=is_current)
        elif id_type == "指数":
            return id_source.getIndexID(is_current=is_current)
        else:
            raise ValueError(f"不支持的 ID_TYPE: {id_type}，可选: A股 | 公募基金 | 期货 | 期权 | ETF | 指数 | 申万一级行业指数 | 申万一级行业")

    def resolve_ids_for(self, profile: "FactorDefProfile") -> Tuple[List[str], List[str]]:
        """根据 FactorDefProfile 解析 IDs 和 SectionIDs"""
        sel = profile.id_selection
        stype = sel.get("type", "all")

        if stype == "all":
            ids = self._get_ids_from_source(id_type=profile.id_type, is_current=False)
        elif stype == "current":
            ids = self._get_ids_from_source(id_type=profile.id_type, is_current=True)
        elif stype == "list":
            ids = sel.get("ids", [])
        else:
            ids = self._get_ids_from_source(id_type=profile.id_type, is_current=False)

        if profile.section_id_list:
            section_ids = profile.section_id_list
        else:
            section_ids = ids
        return ids, section_ids

    def resolve_fdb(self) -> Dict[str, FactorDB]:
        """构造 FDB 字典: {source_name: source_instance, ...}"""
        return {name: self._pool[name] for name in self._pool.source_names}

    def resolve_modules(self) -> List[Tuple[object, dict, Optional[str]]]:
        """解析所有 ID_PROFILES 中的因子模块列表（合并所有 profile 的模块）

        用于 register_factors_to_graphdb.py 等不需要区分 IDType 的场景。
        """
        all_modules = []
        for profile in self.settings.iter_profiles():
            all_modules.extend(self.resolve_modules_for(profile.factor_modules))
        return all_modules

    def _resolve_module(self, name: str) -> object:
        """直接按完整路径导入模块"""
        return importlib.import_module(name)

    def resolve_modules_for(self, factor_modules: list) -> List[Tuple[object, dict, dict]]:
        """根据指定的因子模块列表解析模块（用于 ID_PROFILES 模式）

        Args:
            factor_modules: 因子模块列表，每项支持三种格式:

                字符串::

                    "QSResearch.FactorDef.JY.stock_cn_status"

                字典::

                    {
                        "module": "QSResearch.FactorDef.JY.industry_cn_factor_from_stock",
                        "model_args": {"industry_factor": "sw2021_code_level1", ...},
                        "factor_meta": {                   # 可选，覆盖 __FACTOR_META__ 字段
                            "TargetTable": "...",
                            "Description": "...",
                        },
                    }

        Returns:
            List[(module, model_args, factor_meta)]
            其中 factor_meta 为 __FACTOR_META__ 的覆盖字典，可能为空 {}
        """
        from QSExt.FactorDef.utils import expand_glob

        modules = []
        raw_modules = factor_modules
        if isinstance(raw_modules, str):
            raw_modules = [raw_modules]

        for item in raw_modules:
            # ---- 解析为 (mod_ref, model_args, factor_meta) ----
            if isinstance(item, dict):
                mod_ref = item["module"]
                model_args = item.get("model_args", {})
                factor_meta = dict(item.get("factor_meta", {}))
                if "target_table" in item and "TargetTable" not in factor_meta:
                    factor_meta["TargetTable"] = item["target_table"]
            else:
                mod_ref, model_args, factor_meta = item, {}, {}

            # ---- glob 展开 ----
            if isinstance(mod_ref, str) and ("*" in mod_ref or "?" in mod_ref):
                names = expand_glob(mod_ref)
            else:
                names = [mod_ref]

            # ---- 解析模块对象并合并 ModelArgs ----
            for name in names:
                module = self._resolve_module(name) if isinstance(name, str) else name
                modules.append((module, dict(model_args), factor_meta))

        return modules

    # ---- 构造 ----
    def build(self) -> "FactorDefInput":
        """组装 FactorDefInput（使用第一个 ID_PROFILES 的配置）"""
        if self._pool is None:
            self.init()

        profiles = self.settings.iter_profiles()
        if not profiles:
            raise ValueError("ID_PROFILES 为空，无法构建 FactorDefInput")

        return self.build_for_profile(profiles[0])

    def build_for_profile(
        self,
        profile: "FactorDefProfile",
        dts: List[dt.datetime] = None,
        dtruler: List[dt.datetime] = None,
    ) -> "FactorDefInput":
        """根据 FactorDefProfile 构建 FactorDefInput（用于 ID_PROFILES 模式）

        Args:
            profile: IDType 维度配置
            dts: 共享的 DTs（由调用方提供，避免重复查询）
            dtruler: 共享的 DTRuler

        Returns:
            FactorDefInput 实例，IDs 和 SectionIDs 来自 profile
        """
        if self._pool is None:
            self.init()

        if dts is None or dtruler is None:
            dts, dtruler = self.resolve_dts()

        fdb = self.resolve_fdb()
        ids, section_ids = self.resolve_ids_for(profile)
        return FactorDefInput(
            Debug=self.settings.debug,
            FDB=fdb,
            DTs=dts,
            IDs=ids,
            SectionIDs=section_ids,
            DTRuler=dtruler,
        )

    # ---- 清理 ----
    def disconnect(self) -> None:
        if self._pool:
            self._pool.disconnect_all()

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, *args):
        self.disconnect()


# ---- dep_fd 预构建 ----

def resolve_dep_module(dep_name: str, caller_module) -> object:
    """将依赖名解析为模块对象。

    依次尝试:
      1. 作为完整路径直接 import
      2. 拼接 caller 所在包路径再 import
    """
    try:
        return importlib.import_module(dep_name)
    except ImportError:
        pass
    caller_pkg = caller_module.__name__.rsplit(".", 1)[0]
    try:
        return importlib.import_module(f"{caller_pkg}.{dep_name}")
    except ImportError:
        pass
    raise ImportError(
        f"无法解析依赖 '{dep_name}'（调用者: {caller_module.__name__}），"
        f"已尝试: import '{dep_name}' 和 import '{caller_pkg}.{dep_name}'"
    )


def _get_proxy_factor(
    proxy_db: FactorDB,
    proxy_table_mapping: dict,
    source_table: str,
    factor_name: str,
) -> Optional[Factor]:
    """从代理因子库查找替代因子。

    Args:
        proxy_db: 代理因子库
        proxy_table_mapping: 代理表名映射 {源表名: 代理表名}
        source_table: 源因子表名（__FACTOR_META__["TargetTable"]）
        factor_name: 要查找的因子名

    Returns:
        代理因子，未找到时返回 None
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger

    if proxy_db is None:
        return None
    proxy_table = proxy_table_mapping.get(source_table, source_table)
    if proxy_table not in proxy_db.TableNames:
        _Logger.warning(f"代理查找失败: 表 {proxy_table} 不存在于代理库中")
        return None
    proxy_ft = proxy_db.getTable(proxy_table)
    if factor_name in proxy_ft.FactorNames:
        return proxy_ft.getFactor(factor_name)
    _Logger.warning(f"代理查找失败: 因子 {source_table}/{factor_name} 不存在于代理表 {proxy_table} 中")
    return None


def _build_factors(
    meta: dict,
    dep_fd: Dict[str, "FactorDef"],
    fdi: "FactorDefInput",
    proxy_db: Optional[FactorDB] = None,
    proxy_table_mapping: Optional[dict] = None,
    proxy_tables: Optional[Union[List[str], str]] = None,
) -> Dict[str, Factor]:
    """根据 FactorDeps 声明构建扁平因子字典。

    FactorDeps entry 两种格式：

    - 字符串: ``"close"`` — 因子名。``"*"`` 表示该表全部因子
    - 字典: ``{"Name": "close", "Alias": "price"}``

      - Name: 因子名（必填），``"*"`` 表示该表全部因子
      - Alias: 注入到 fdi.Factors 时的别名（可选，默认用 Name，仅单因子时有效）
      - ModelArgs: 传递给依赖模块 defFactor 的参数（可选），值以 ``"$"`` 开头时从父模块 fdi.ModelArgs 中查找

    Args:
        meta: 模块的 __FACTOR_META__ 字典
        dep_fd: 已解析的 FactorDef 映射
        fdi: 因子定义输入（用于访问 ModelArgs）
        proxy_db: 代理因子库（可选，不传则不使用代理）
        proxy_table_mapping: 代理表名映射（可选）
        proxy_tables: 代理表控制（可选），``"*"`` 全部代理，列表指定表名，None 不代理

    Returns:
        {因子名: Factor} 扁平字典
    """
    proxy_table_mapping = proxy_table_mapping or {}
    use_all_proxy = proxy_tables == "*"
    proxy_table_set = set(proxy_tables) if isinstance(proxy_tables, list) else set()

    factors = {}
    for table_name, entries in meta.get("FactorDeps", {}).items():
        fd = dep_fd.get(table_name)
        if fd is None:
            continue

        table_use_proxy = use_all_proxy or table_name in proxy_table_set

        def _resolve(name):
            """查找因子，可选代理替换"""
            if table_use_proxy and proxy_db:
                proxy = _get_proxy_factor(proxy_db, proxy_table_mapping, table_name, name)
                if proxy is not None:
                    from QuantStudio.Core import __QS_Logger__ as _Logger
                    _Logger.info(f"代理因子替换: {table_name}/{name} → {table_name}/{name}")
                    return proxy
            return fd.getFactor(factor_name=name)

        for entry in entries:
            if isinstance(entry, dict):
                raw_name = entry["Name"]
                name = raw_name
                if name.startswith("$"):
                    name = fdi.ModelArgs.get(name[1:], name[1:])
                if name == "*":
                    for f in fd.FactorList:
                        factors[f._QSArgs.Name] = _resolve(f._QSArgs.Name)
                else:
                    alias = entry.get("Alias", raw_name)
                    factors[alias] = _resolve(name)
            elif isinstance(entry, str):
                name = entry
                if name.startswith("$"):
                    name = fdi.ModelArgs.get(name[1:], name[1:])
                if name == "*":
                    for f in fd.FactorList:
                        factors[f._QSArgs.Name] = _resolve(f._QSArgs.Name)
                else:
                    factors[entry] = _resolve(name)
    return factors


def _extract_dep_model_args(
    entries: list,
    parent_model_args: dict,
) -> dict:
    """从 FactorDeps 的 entries 列表中提取并解析 ModelArgs。

    支持 ``"$key"`` 语法：值以 ``$`` 开头时，从 parent_model_args 中查找对应 key。
    多个 entry 同时声明 ModelArgs 时合并，后者覆盖前者。

    Args:
        entries: FactorDeps 中单个表对应的 entry 列表（str 或 dict）
        parent_model_args: 父模块的 fdi.ModelArgs，用于解析 ``$`` 前缀

    Returns:
        解析后的 ModelArgs 字典
    """
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_args = entry.get("ModelArgs")
        if not raw_args:
            continue
        for k, v in raw_args.items():
            if isinstance(v, str) and v.startswith("$"):
                result[k] = parent_model_args.get(v[1:], v[1:])
            else:
                result[k] = v
    return result


def _check_model_args_refs(meta: dict, module) -> None:
    """校验 FactorDeps 中的 $ 引用是否在 ModelArgs 中声明。

    仅输出警告日志，不阻断执行。未声明 ModelArgs 的模块跳过检查。
    """
    declared = meta.get("ModelArgs", {})
    if not declared:
        return
    from QuantStudio.Core import __QS_Logger__ as _Logger
    for dep_name, entries in meta.get("FactorDeps", {}).items():
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for v in entry.get("ModelArgs", {}).values():
                if isinstance(v, str) and v.startswith("$"):
                    ref_key = v[1:]
                    if ref_key not in declared:
                        mod_name = getattr(module, '__name__', str(module))
                        _Logger.warning(
                            f"模块 {mod_name} 的 FactorDeps 引用了 ${ref_key}，"
                            f"但 ModelArgs 声明中未包含该参数"
                        )


def build_dep_fd(
    modules: List[Tuple[object, dict, dict]],
    fdi: "FactorDefInput",
    proxy_db: Optional[FactorDB] = None,
    proxy_table_mapping: Optional[dict] = None,
    proxy_tables: Optional[Union[List[str], str]] = None,
) -> Tuple[Dict[str, "FactorDef"], List[Tuple["FactorDef", dict]]]:
    """根据 __FACTOR_META__['FactorDeps'] 预构建 dep_fd。

    递归解析依赖链：读取模块的 __FACTOR_META__["FactorDeps"] 的 key，
    找到对应的依赖模块并递归执行其 defFactor，确保调用目标模块时
    dep_fd 已包含所有声明过的依赖。

    依赖名支持两种写法：
      - 完整路径: "QSResearch.FactorDef.JY.stock_cn_status"
      - 短名（同包下）: "stock_cn_status"

    Args:
        modules: resolve_modules_for() 返回的模块列表，每项为 (module, model_args, factor_meta)
        fdi: 运行时上下文（ModelArgs 和 Factors 会在调用期间被临时修改并恢复）
        proxy_db: 代理因子库，用于因子替换
        proxy_table_mapping: 代理表名映射
        proxy_tables: 代理表控制，``"*"`` 全部代理，列表指定表名，None 不代理

    Returns:
        (dep_fd, requested_results):
          - dep_fd: TargetTable → FactorDef 的完整映射（含依赖模块）
          - requested_results: 显式请求的模块结果列表（保持 modules 原顺序），
            (FactorDef, factor_meta)，失败时为 (None, factor_meta)

    Raises:
        RuntimeError: 检测到循环依赖
        ImportError: 依赖模块无法解析
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger

    dep_fd: Dict[str, FactorDef] = {}
    _resolving: set = set()

    # ---- 递归执行 ----
    def _ensure(module, model_args, factor_meta=None):
        if factor_meta is None:
            factor_meta = {}
        meta = getattr(module, '__FACTOR_META__', None)

        if meta and isinstance(meta, dict) and meta.get('TargetTable'):
            # 去重 key: 优先用 factor_meta 覆盖值，否则用模块级 TargetTable
            tt = factor_meta.get("TargetTable") or meta['TargetTable']
            if tt in dep_fd:
                return
            if tt in _resolving:
                chain = " → ".join(_resolving)
                raise RuntimeError(f"检测到循环依赖: {chain} → {tt}")

            _resolving.add(tt)
            try:
                # 合并 factor_meta 覆盖（提前，以便 FactorDeps 等字段也能被覆盖）
                effective_meta = dict(meta)
                effective_meta.update(factor_meta)

                # 校验 FactorDeps 中的 $ 引用是否在 ModelArgs 中声明
                _check_model_args_refs(effective_meta, module)

                # 校验 DBDeps 中声明的因子库是否在 FDB 中存在
                for db_name in effective_meta.get("DBDeps", {}):
                    if db_name not in fdi.FDB:
                        mod_name = getattr(module, '__name__', str(module))
                        raise KeyError(
                            f"模块 '{mod_name}' 声明依赖因子库 '{db_name}'，"
                            f"但该库未在 FACTOR_DATABASES 中配置为 source 角色。"
                            f" 当前可用: {list(fdi.FDB.keys())}"
                        )

                # 提前注入当前模块的 ModelArgs，使依赖解析时 $ 引用能正确指向当前层
                saved_args = fdi.ModelArgs
                saved_factors = fdi.Factors
                fdi.ModelArgs = model_args
                try:
                    # 递归解析该模块声明的依赖（用合并后的 FactorDeps）
                    for dep_name, entries in effective_meta.get('FactorDeps', {}).items():
                        dep_mod = resolve_dep_module(dep_name, module)
                        # $ 前缀的值从当前模块的 fdi.ModelArgs 中查找
                        dep_model_args = _extract_dep_model_args(entries, fdi.ModelArgs)
                        _ensure(dep_mod, dep_model_args, {})

                    # 注入 Factors 并执行自身
                    fdi.Factors = _build_factors(effective_meta, dep_fd, fdi, proxy_db, proxy_table_mapping, proxy_tables)
                    factor_list = module.defFactor(fdi=fdi)
                finally:
                    fdi.ModelArgs = saved_args
                    fdi.Factors = saved_factors

                # 包装为 FactorDef
                result = FactorDef(
                    FactorList=factor_list,
                    Meta=FactorMeta(**effective_meta),
                )

                dep_fd[result.Meta.TargetTable] = result
                _Logger.debug(
                    f"  ✓ {result.Meta.TargetTable} "
                    f"({len(result.FactorList)} 因子)"
                )
            finally:
                _resolving.discard(tt)
        else:
            # 无 __FACTOR_META__ 的模块：直接调用
            saved_args = fdi.ModelArgs
            saved_factors = fdi.Factors
            fdi.ModelArgs = model_args
            fdi.Factors = {}
            try:
                factor_list = module.defFactor(fdi=fdi)
            finally:
                fdi.ModelArgs = saved_args
                fdi.Factors = saved_factors

            result = FactorDef(
                FactorList=factor_list,
                Meta=FactorMeta(**factor_meta),
            )
            dep_fd[result.Meta.TargetTable] = result
            mod_name = (
                module.__name__.split(".")[-1]
                if hasattr(module, '__name__') else str(module)
            )
            _Logger.debug(
                f"  ✓ {result.Meta.TargetTable} "
                f"({len(result.FactorList)} 因子) [无 __FACTOR_META__: {mod_name}]"
            )

    # ---- 执行所有显式请求的模块 ----
    for mod, model_args, factor_meta in modules:
        _ensure(mod, model_args, factor_meta)

    # ---- 递归计算 MaxLookBack ----
    compute_max_lookback(dep_fd)

    # ---- 收集显式请求的结果 ----
    requested = []
    for mod, model_args, factor_meta in modules:
        meta = getattr(mod, '__FACTOR_META__', None)
        tt = factor_meta.get("TargetTable") or (meta.get('TargetTable') if (meta and isinstance(meta, dict)) else None)
        # 优先用 factor_meta 的 tt 查找，找不到时按模块源文件路径匹配
        if tt and tt in dep_fd:
            requested.append((dep_fd[tt], factor_meta))
        else:
            mod_path = getattr(mod, '__file__', '') or ''
            found = None
            for fd in dep_fd.values():
                if fd.Meta.DefScriptPath and os.path.normcase(os.path.abspath(fd.Meta.DefScriptPath)) == os.path.normcase(os.path.abspath(mod_path)):
                    found = fd
                    break
            requested.append((found, factor_meta))
            if found is None:
                _Logger.warning(f"模块 {getattr(mod, '__name__', mod)} 的结果未在 dep_fd 中找到")

    return dep_fd, requested


def compute_max_lookback(dep_fd: Dict[str, "FactorDef"]) -> None:
    """递归计算所有 FactorDef 的 MaxLookBack。

    对 dep_fd 中每个 FactorDef，根据 Meta.FactorDeps 的 key 声明的依赖关系，
    递归计算: MaxLookBack = max(自身声明的值, 各依赖模块的 MaxLookBack)。

    Args:
        dep_fd: TargetTable → FactorDef 的映射（由 build_dep_fd 构建）
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger

    memo: Dict[str, int] = {}
    resolving: set = set()

    def _resolve(tt: str) -> int:
        if tt in memo:
            return memo[tt]
        if tt in resolving:
            raise RuntimeError(
                f"compute_max_lookback 检测到循环依赖: {' -> '.join(resolving)} -> {tt}"
            )

        resolving.add(tt)
        try:
            fd = dep_fd[tt]
            mlb = fd.Meta.MaxLookBack
            dep_names = list(fd.Meta.FactorDeps.keys())
            for dep_name in dep_names:
                if dep_name in dep_fd:
                    mlb = max(mlb, _resolve(dep_name))
                else:
                    _Logger.debug(
                        f"compute_max_lookback: 依赖 '{dep_name}' "
                        f"未在 dep_fd 中找到，跳过"
                    )
            memo[tt] = mlb
            if mlb != fd.Meta.MaxLookBack:
                _Logger.debug(
                    f"compute_max_lookback: {tt} MaxLookBack "
                    f"{fd.Meta.MaxLookBack} → {mlb}"
                )
                fd.Meta.MaxLookBack = mlb
            return mlb
        finally:
            resolving.discard(tt)

    for tt in list(dep_fd.keys()):
        _resolve(tt)

    _Logger.info(f"compute_max_lookback: 已处理 {len(dep_fd)} 个 FactorDef")

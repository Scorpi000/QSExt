# -*- coding: utf-8 -*-
"""
DefModule 核心模块 —— 统一计算图定义框架，兼容因子和策略流程。

将因子定义和策略定义合并为单一模块，支持：
- 统一输入对象 DefInput（因子和策略共用）
- 统一元信息 DefMeta（合并 FactorMeta + StrategyMeta 超集字段）
- 统一定义容器 Def（同时持有 FactorList 和 StrategyList，自动归类）
- 统一配置 DefSettings / DefProfile（支持 FACTOR_PROFILES / STRATEGY_PROFILES / DEF_PROFILES）
- 统一构建器 DefInputBuilder（合并两个 Builder，消除重复代码）
- 通用 GraphDef、build_graph_def；旧 build_dep 系列接口复用统一依赖解析核心

入口函数优先级：defNode > defFactor > defStrategy（三者等价）
"""
import os
import re
import json
import importlib
import importlib.util
import traceback
import datetime as dt
from typing import List, Dict, Optional, Tuple, Union

import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Args__, __QS_Error__
from QuantStudio.Core.Node import Node
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB
from QSExt.RuntimeConfig.config import DBDef, DBPool, RuntimeSettings
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount


# ============================================================
# 统一输入对象
# ============================================================

class DefInput(__QS_Args__):
    """统一定义输入对象 —— 因子和策略共用。

    是因子定义和策略定义输入的统一超集。
    Strategies 字段默认为 {}，因子模块可忽略。
    """
    Debug: bool = Field(default=False, title="调试环境", frozen=True)
    FDB: Dict[str, FactorDB] = Field(default={}, title="可用因子库")
    ModelArgs: Dict = Field(default={}, title="模型参数")
    DTs: List[dt.datetime] = Field(default=[], title="计算时点")
    DTRuler: List[dt.datetime] = Field(default=[], title="时点标尺")
    IDs: List[str] = Field(default=[], title="ID序列")
    SectionIDs: List[str] = Field(default=[], title="截面ID")
    TDB: Optional[WritableFactorDB] = Field(default=None, title="写入因子库")
    Factors: Dict[str, Factor] = Field(default={}, title="已解析的依赖因子")
    Strategies: Dict[str, Factor] = Field(default={}, title="已解析的依赖策略")
    Nodes: Dict[str, Node] = Field(default_factory=dict, title="已解析的依赖节点")


# ============================================================
# 统一元信息
# ============================================================

class DefMeta(__QS_Args__):
    """统一元信息 —— 合并 FactorMeta + StrategyMeta 超集字段。

    策略特有字段（OperatorConfig, StrategyDeps, ResultKey）默认空值，
    因子特有字段（DefaultStartDT, DTType, Freq）保留默认值。
    """
    TargetTable: str = Field(default="", title="因子表/策略信号输出表")
    NodeDeps: List[dict] = Field(default_factory=list, title="计算图节点依赖")
    RequireDates: bool = Field(default=False, title="构图需要日期")
    IDType: str = Field(default="", title="ID类型")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述信息")
    MaxLookBack: int = Field(default=365, title="最大回溯期")
    DefaultStartDT: dt.datetime = Field(default=dt.datetime(2002, 1, 1), title="默认起始日")
    DTType: str = Field(default="自定义", title="时点类型")
    Freq: str = Field(default="1d", title="时点频率")
    DefScriptPath: str = Field(default="", title="定义脚本路径")

    # ---- 策略特有 ----
    OperatorConfig: Dict = Field(
        default={}, title="策略算子默认配置",
        description="策略特有，如 SignalType/InitCash/ShortAllowed",
    )

    # ---- 分类与发现 ----
    Tags: List[str] = Field(default=[], title="检索标签")
    FactorDeps: Dict[str, List[Union[str, dict]]] = Field(default={}, title="依赖因子声明")
    StrategyDeps: Dict[str, List[Union[str, dict]]] = Field(
        default={}, title="依赖策略声明",
        description="策略特有：key 为依赖策略的模块路径，value 为 [{Name, Alias, ModelArgs}]",
    )
    DBDeps: Dict[str, str] = Field(default={}, title="因子库依赖")
    ModelArgs: Dict[str, str] = Field(default={}, title="期望的模型参数")

    # ---- 回测结果存储（策略特有） ----
    ResultKey: Optional[str] = Field(
        default=None, title="回测结果键名模板",
        description="策略特有：控制 BTStorer 的 GroupName 格式",
    )


# ============================================================
# 统一定义容器
# ============================================================

def _classify(items: List[Factor]) -> Tuple[List[Factor], List[Factor]]:
    """将返回的因子/策略实例自动分类。

    检测算子是否为 MakeAccount 实例（MakeStrategy 继承自 MakeAccount），
    是则归入策略列表，否则归入因子列表。
    """
    factors, strategies = [], []
    for item in items:
        if not isinstance(item, Factor):
            raise TypeError("旧因子/策略流程不支持普通节点输出，请使用 build_graph_def 或计算图导入")
        operator = getattr(item, '_Operator', None)
        if operator is None and hasattr(item, '_QSArgs'):
            operator = getattr(item._QSArgs, 'Operator', None)
        if isinstance(operator, MakeAccount):
            strategies.append(item)
        else:
            factors.append(item)
    return factors, strategies


class Def(__QS_Args__):
    """统一定义对象 —— 同时持有因子和策略实例。

    一个模块通过 defNode/defFactor/defStrategy 返回 List[Factor]，
    框架根据算子类型自动归类到 FactorList 和 StrategyList。
    """
    FactorList: List[Factor] = Field(default=[], title="因子列表")
    StrategyList: List[Factor] = Field(default=[], title="策略实例列表")
    Meta: DefMeta = Field(title="静态元信息")

    @property
    def FactorNames(self) -> List[str]:
        return [f._QSArgs.Name for f in self.FactorList]

    @property
    def StrategyNames(self) -> List[str]:
        return [s.Name for s in self.StrategyList]

    def getFactor(self, factor_name: Optional[str] = None, def_path: str = "...",
                  factor_id: Optional[str] = None, only_one: bool = True) -> Factor | List[Factor]:
        """查找因子对象（逻辑与 getFactor 方法一致）"""
        if (factor_id is None) and (factor_name is None):
            raise __QS_Error__(f"入参 factor_id、factor_name 不可同时为 None")

        def _searchFactor(factors, factor_id, factor_name, recursive=True):
            Factors = {}
            for iFactor in factors:
                if ((factor_id is None) or (iFactor.QSID == factor_id)) and \
                   ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)):
                    Factors[iFactor.QSID] = iFactor
                if recursive:
                    Factors = Factors | {iFactor.QSID: iFactor for iFactor in _searchFactor(iFactor.Descriptors, factor_id, factor_name, recursive=recursive)}
            return list(Factors.values())

        DefPath = def_path.strip().split("/")
        LastPos = DefPath[-1]
        if LastPos in ("", "..."):
            DefPath = DefPath[:-1]
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
            if (LastPos not in ("", "...")) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)) and ((factor_id is None) or (iFactor.QSID == factor_id)):
                return (iFactor if only_one else [iFactor])
            elif LastPos in ("", "..."):
                Factors = _searchFactor(factors=iFactor.Descriptors, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos == ""))
            else:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
        else:
            Factors = _searchFactor(factors=self.FactorList, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos == ""))
        if only_one:
            if (len(Factors) == 1) or ((len(Factors) > 1) and (factor_id is not None)):
                return Factors[0]
            elif len(Factors) == 0:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
            else:
                raise __QS_Error__(f"查找到的因子 (Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}') 不止一个!")
        else:
            return Factors

    def getStrategy(self, name: str) -> Factor:
        """按名称查找策略实例"""
        for s in self.StrategyList:
            if s.Name == name:
                return s
        raise __QS_Error__(f"策略定义中找不到策略 '{name}'，可用: {self.StrategyNames}")


# ============================================================
# Profile 和 Settings
# ============================================================

class DefProfile(__QS_Args__):
    """统一 Profile —— 同时支持因子和策略模块。"""
    id_selection: str = Field(default="", title="ID 选择策略", description="引用 SECTION_ID_SOURCES 的 key")
    factor_modules: list = Field(default=[], title="因子模块列表")
    strategy_modules: list = Field(default=[], title="策略模块列表")
    section_id_list: str = Field(default="", title="截面 ID 列表")
    proxy_tables: Union[List[str], str, None] = Field(default=None, title="代理表")
    target_db: str = Field(default="", title="输出目标库名")
    factor_storer_config: dict = Field(default={}, title="FactorStorer 参数")
    collect_mode: str = Field(default="both", title="收集模式", description="factor | strategy | both")


class DefSettings(RuntimeSettings):
    """统一运行时配置 —— 继承 RuntimeSettings，新增 bt_store 和 def_profiles。"""
    bt_store: Optional[DBDef] = Field(default=None, title="回测结果存储库定义")
    def_profiles: List[dict] = Field(default=[], title="混合 Profile 列表", description="DEF_PROFILES 配置")

    @classmethod
    def from_module(cls, module_path: str = "settings", **cmd_overrides) -> "DefSettings":
        if not module_path.startswith("QSExt") and not os.path.isabs(module_path):
            module_path = f"QSExt.RuntimeConfig.conf.{module_path}"
        return super().from_module(module_path, **cmd_overrides)

    @classmethod
    def from_dict(cls, data: dict, hooks: dict = None) -> "DefSettings":
        data = dict(data)
        # 转换 bt_store: dict → DBDef（与 RuntimeSettings.from_dict 中 factor_databases 的转换对齐）
        if "bt_store" in data and isinstance(data["bt_store"], dict):
            bt = data["bt_store"]
            data["bt_store"] = DBDef(
                name=bt.get("name", ""),
                class_path=bt.get("class", bt.get("class_path", "")),
                role=bt.get("role", "target"),
                args=bt.get("args", {}),
                config_file=bt.get("config_file"),
            )
        # 保存 DEF_PROFILES（大写 → 小写映射）
        if "DEF_PROFILES" in data and "def_profiles" not in data:
            data["def_profiles"] = data.pop("DEF_PROFILES")
        return super().from_dict(data, hooks=hooks)

    def iter_profiles(self) -> List[DefProfile]:
        """将配置中的 profiles 转换为 DefProfile 列表。

        优先级：DEF_PROFILES > (FACTOR_PROFILES + STRATEGY_PROFILES 合并)
        """
        profiles = []

        # DEF_PROFILES — 混合模式（存储为 def_profiles 字段）
        def_profiles = self.def_profiles
        if def_profiles:
            for p in def_profiles:
                profiles.append(DefProfile(
                    id_selection=p.get("id_selection", ""),
                    factor_modules=p.get("factor_modules", []),
                    strategy_modules=p.get("strategy_modules", []),
                    section_id_list=p.get("section_id_list", ""),
                    proxy_tables=p.get("proxy_tables", None),
                    target_db=p.get("target_db", ""),
                    factor_storer_config=p.get("factor_storer_config", {}),
                    collect_mode="both",
                ))
            return profiles

        # 回退：合并 FACTOR_PROFILES + STRATEGY_PROFILES
        for p in self.factor_profiles:
            profiles.append(DefProfile(
                id_selection=p.get("id_selection", ""),
                factor_modules=p.get("factor_modules", []),
                section_id_list=p.get("section_id_list", ""),
                proxy_tables=p.get("proxy_tables", None),
                target_db=p.get("target_db", ""),
                factor_storer_config=p.get("factor_storer_config", {}),
                collect_mode="factor",
            ))
        for p in self.strategy_profiles:
            profiles.append(DefProfile(
                section_id_list=p.get("section_id_list", ""),
                strategy_modules=p.get("strategy_modules", []),
                target_db=p.get("target_db", ""),
                factor_storer_config=p.get("factor_storer_config", {}),
                collect_mode="strategy",
            ))
        return profiles


# ============================================================
# 统一 InputBuilder
# ============================================================

class DefInputBuilder:
    """根据 DefSettings 构造 DefInput。

    合并因子定义和策略定义的 Builder，消除重复代码。
    """

    def __init__(self, settings: DefSettings):
        self.settings = settings
        self._pool: Optional[DBPool] = None

    # ---- 初始化 ----
    def init(self) -> None:
        self._pool = self.settings.to_db_pool()
        self._pool.create_all()
        self._pool.connect_all()
        self._run_hooks()

    def _run_hooks(self) -> None:
        hook = self.settings.get_hook("init_db")
        if hook:
            hook(self._pool)

    # ---- 日期解析 ----
    @staticmethod
    def _parse_end_dt(end_dt: str) -> dt.datetime:
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

    def _fetch_dates(self, start_date: dt.datetime, end_date: dt.datetime) -> List[dt.datetime]:
        if self.settings.dt_type == "自然日":
            return pd.date_range(start=start_date, end=end_date, freq='D').tolist()
        else:
            tds = self.settings.trading_day_source
            tds_name = tds.get("name", "JYDB")
            tds_method = tds.get("method", "getTradeDay")
            tds_method_args = tds.get("method_args", {})
            dt_source = self._pool[tds_name]
            method = getattr(dt_source, tds_method)
            return method(start_date=start_date, end_date=end_date, **tds_method_args)

    def resolve_dts(self) -> Tuple[List[dt.datetime], List[dt.datetime]]:
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

    def resolve_section_ids(self, section_key: str) -> List[str]:
        source = self.settings.section_id_sources.get(section_key)
        if source is None:
            available = list(self.settings.section_id_sources.keys())
            raise KeyError(
                f"SECTION_ID_SOURCES 中未找到 '{section_key}'，可用: {available}"
            )
        stype = source.get("type", "fdb_method")
        if stype == "list":
            return source.get("ids", [])
        elif stype == "fdb_method":
            db_name = source.get("name", "JYDB")
            method_name = source.get("method", "getStockID")
            method_args = source.get("method_args", {})
            db = self._pool[db_name]
            return getattr(db, method_name)(**method_args)
        else:
            raise ValueError(f"截面 '{section_key}' 的类型 '{stype}' 不支持，期望 'list' 或 'fdb_method'")

    def resolve_ids_for(self, profile: DefProfile) -> Tuple[List[str], List[str]]:
        """根据 profile 解析 IDs 和 SectionIDs。

        若 id_selection 非空则走因子模式（IDs 和 SectionIDs 分别解析），
        否则走策略模式（IDs == SectionIDs）。
        """
        if profile.id_selection:
            ids = self.resolve_section_ids(profile.id_selection)
            section_ids = self.resolve_section_ids(profile.section_id_list) if profile.section_id_list else ids
        else:
            ids = self.resolve_section_ids(profile.section_id_list) if profile.section_id_list else []
            section_ids = ids
        return ids, section_ids

    def resolve_fdb(self) -> Dict[str, FactorDB]:
        return {name: self._pool[name] for name in self._pool.source_names}

    def resolve_modules(self) -> List[Tuple[object, dict, Optional[str]]]:
        """解析所有 profiles 中的模块列表（合并所有 profile）"""
        all_modules = []
        for profile in self.settings.iter_profiles():
            if profile.factor_modules:
                all_modules.extend(self.resolve_modules_for(profile.factor_modules, kind="factor"))
            if profile.strategy_modules:
                all_modules.extend(self.resolve_modules_for(profile.strategy_modules, kind="strategy"))
        return all_modules

    def _resolve_module(self, name: str) -> object:
        """导入模块，支持 .ipynb"""
        if isinstance(name, str) and name.endswith(".ipynb"):
            from QSExt.DefModule.utils import load_notebook_as_module
            return load_notebook_as_module(name)
        return importlib.import_module(name)

    def resolve_modules_for(self, modules: list, kind: str = "factor") -> List[Tuple[object, dict, dict]]:
        """解析模块列表。

        Args:
            modules: 模块列表（字符串或字典）
            kind: "factor" | "strategy" | "both"，决定读取 factor_meta 还是 strategy_meta key
        """
        from QSExt.DefModule.utils import expand_glob

        result = []
        raw_modules = modules
        if isinstance(raw_modules, str):
            raw_modules = [raw_modules]

        meta_key = "strategy_meta" if kind == "strategy" else "factor_meta"

        for item in raw_modules:
            if isinstance(item, dict):
                mod_ref = item["module"]
                model_args = item.get("model_args", {})
                meta_override = dict(item.get(meta_key, item.get("factor_meta", item.get("strategy_meta", {}))))
                if "target_table" in item and "TargetTable" not in meta_override:
                    meta_override["TargetTable"] = item["target_table"]
            else:
                mod_ref, model_args, meta_override = item, {}, {}

            if isinstance(mod_ref, str) and ("*" in mod_ref or "?" in mod_ref):
                names = expand_glob(mod_ref)
            else:
                names = [mod_ref]

            for name in names:
                module = self._resolve_module(name) if isinstance(name, str) else name
                result.append((module, dict(model_args), meta_override))

        return result

    def build_for_profile(self, profile: DefProfile, dts=None, dtruler=None) -> DefInput:
        if self._pool is None:
            self.init()
        if dts is None or dtruler is None:
            dts, dtruler = self.resolve_dts()
        fdb = self.resolve_fdb()
        ids, section_ids = self.resolve_ids_for(profile)
        return DefInput(
            Debug=self.settings.debug,
            FDB=fdb,
            DTs=dts,
            IDs=ids,
            SectionIDs=section_ids,
            DTRuler=dtruler,
        )

    def disconnect(self) -> None:
        if self._pool:
            self._pool.disconnect_all()

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, *args):
        self.disconnect()


# ============================================================
# 依赖解析工具函数
# ============================================================

def resolve_dep_module(dep_name: str, caller_module) -> object:
    """将依赖名解析为模块对象。"""
    if dep_name.startswith("."):
        return importlib.import_module(dep_name, package=caller_module.__package__)
    # Web 导入使用独立命名空间，同名上传依赖必须优先于进程已有模块。
    if getattr(caller_module, "__name__", "").startswith("_qs_def_import_"):
        caller_pkg = caller_module.__name__.rsplit(".", 1)[0]
        name = f"{caller_pkg}.{dep_name}"
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            spec = None
        if spec is not None:
            return importlib.import_module(name)
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


def make_def_key(module, model_args: dict) -> str:
    """根据模块路径和 ModelArgs 生成唯一的 DefKey。"""
    file_path = os.path.abspath(module.__file__)
    if not model_args:
        return file_path
    return f"{file_path}@{json.dumps(model_args, sort_keys=True, default=str)}"


def _dep_key_to_def_key(dep_name: str, target_dict: dict) -> Optional[str]:
    """将依赖声明中的模块路径映射到 target_dict 中的 DefKey。"""
    if not target_dict:
        return None
    try:
        dep_mod = resolve_dep_module(dep_name, os)
    except ImportError:
        dep_mod = None
    candidates = [dep_mod] if dep_mod is not None else []
    # 上传定义的相对模块不注册为全局短名，通过本次依赖字典的文件键定位。
    import sys
    candidates += [module for name, module in list(sys.modules.items())
                   if name.startswith("_qs_def_import_") and name.endswith("." + dep_name)]
    for module in candidates:
        dep_file = os.path.normcase(os.path.abspath(module.__file__))
        for def_key in target_dict:
            key_file = os.path.normcase(def_key.split("@")[0])
            if key_file == dep_file:
                return def_key
    return None


def _get_proxy_factor(proxy_db, proxy_table_mapping, source_table, factor_name) -> Optional[Factor]:
    """从代理因子库查找替代因子。"""
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


def _build_factors(resolved_deps, dep_fd, fdi, proxy_db=None, proxy_table_mapping=None, proxy_tables=None) -> Dict[str, Factor]:
    """根据预解析的依赖映射构建扁平因子字典。"""
    proxy_table_mapping = proxy_table_mapping or {}
    use_all_proxy = proxy_tables == "*"
    proxy_table_set = set(proxy_tables) if isinstance(proxy_tables, list) else set()

    factors = {}
    for def_key, entries in resolved_deps.items():
        fd = dep_fd.get(def_key)
        if fd is None:
            continue
        table_name = fd.Meta.TargetTable
        table_use_proxy = use_all_proxy or table_name in proxy_table_set

        def _resolve(name):
            if table_use_proxy and proxy_db:
                proxy = _get_proxy_factor(proxy_db, proxy_table_mapping, table_name, name)
                if proxy is not None:
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


def _build_factors_for_strategy(meta, dep_fd, sdi, module=None) -> Dict[str, Factor]:
    """根据 FactorDeps 声明从 dep_fd 构建因子字典（策略场景）。"""
    factors = {}
    for dep_name, entries in meta.get("FactorDeps", {}).items():
        if module is not None:
            dep_mod = resolve_dep_module(dep_name, module)
            def_key = make_def_key(dep_mod, _extract_dep_model_args(entries, sdi.ModelArgs))
        else:
            def_key = _dep_key_to_def_key(dep_name, dep_fd)
        if def_key is None:
            continue
        fd = dep_fd.get(def_key)
        if fd is None:
            continue
        for entry in entries:
            if isinstance(entry, dict):
                raw_name = entry["Name"]
                name = raw_name
                if name.startswith("$"):
                    name = sdi.ModelArgs.get(name[1:], name[1:])
                if name == "*":
                    for f in fd.FactorList:
                        factors[f.Name] = fd.getFactor(factor_name=f.Name)
                else:
                    alias = entry.get("Alias", raw_name)
                    factors[alias] = fd.getFactor(factor_name=name)
            elif isinstance(entry, str):
                name = entry
                if name.startswith("$"):
                    name = sdi.ModelArgs.get(name[1:], name[1:])
                if name == "*":
                    for f in fd.FactorList:
                        factors[f.Name] = fd.getFactor(factor_name=f.Name)
                else:
                    factors[entry] = fd.getFactor(factor_name=name)
    return factors


def _extract_dep_model_args(entries: list, parent_model_args: dict) -> dict:
    """从依赖的 entries 列表中提取并解析 ModelArgs。"""
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
    """校验 FactorDeps 中的 $ 引用是否在 ModelArgs 中声明。"""
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
                        _Logger.warning(f"模块 {mod_name} 的 FactorDeps 引用了 ${ref_key}，但 ModelArgs 声明中未包含该参数")


# ============================================================
# MaxLookBack 计算
# ============================================================

def compute_max_lookback(dep_fd: Dict[str, Def]) -> None:
    """递归计算所有因子定义的 MaxLookBack。"""
    from QuantStudio.Core import __QS_Logger__ as _Logger
    memo: Dict[str, int] = {}
    resolving: set = set()

    def _resolve(def_key: str) -> int:
        if def_key in memo:
            return memo[def_key]
        if def_key in resolving:
            raise RuntimeError(f"compute_max_lookback 检测到循环依赖: {' -> '.join(resolving)} -> {def_key}")
        resolving.add(def_key)
        try:
            fd = dep_fd[def_key]
            mlb = fd.Meta.MaxLookBack
            for dep_name in list(fd.Meta.FactorDeps.keys()):
                dep_def_key = _dep_key_to_def_key(dep_name, dep_fd)
                if dep_def_key and dep_def_key in dep_fd:
                    mlb = max(mlb, _resolve(dep_def_key))
            memo[def_key] = mlb
            if mlb != fd.Meta.MaxLookBack:
                fd.Meta.MaxLookBack = mlb
            return mlb
        finally:
            resolving.discard(def_key)

    for def_key in list(dep_fd.keys()):
        _resolve(def_key)
    _Logger.info(f"compute_max_lookback: 已处理 {len(dep_fd)} 个因子定义")


def compute_max_lookback_sd(dep_sd: Dict[str, Def], dep_fd: Dict = None) -> None:
    """递归计算所有策略定义的 MaxLookBack。"""
    from QuantStudio.Core import __QS_Logger__ as _Logger
    dep_fd = dep_fd or {}
    memo: Dict[str, int] = {}
    resolving: set = set()

    def _resolve(def_key: str) -> int:
        if def_key in memo:
            return memo[def_key]
        if def_key in resolving:
            raise RuntimeError(f"compute_max_lookback_sd 检测到循环依赖: {' -> '.join(resolving)} -> {def_key}")
        resolving.add(def_key)
        try:
            sd = dep_sd[def_key]
            mlb = sd.Meta.MaxLookBack
            for dep_name in sd.Meta.FactorDeps:
                dep_def_key = _dep_key_to_def_key(dep_name, dep_fd)
                if dep_def_key and dep_def_key in dep_fd:
                    mlb = max(mlb, dep_fd[dep_def_key].Meta.MaxLookBack)
                elif dep_def_key and dep_def_key in dep_sd:
                    mlb = max(mlb, _resolve(dep_def_key))
            for dep_module_path in sd.Meta.StrategyDeps:
                dep_def_key = _dep_key_to_def_key(dep_module_path, dep_sd)
                if dep_def_key and dep_def_key in dep_sd:
                    mlb = max(mlb, _resolve(dep_def_key))
            memo[def_key] = mlb
            if mlb != sd.Meta.MaxLookBack:
                sd.Meta.MaxLookBack = mlb
            return mlb
        finally:
            resolving.discard(def_key)

    for def_key in list(dep_sd.keys()):
        _resolve(def_key)
    _Logger.info(f"compute_max_lookback_sd: 已处理 {len(dep_sd)} 个策略定义")


# ============================================================
# 入口调用与旧接口适配
# ============================================================

def _call_definition(entry_fn, di):
    """统一输入位置，不依赖入口把参数命名为 fdi 还是 sdi。"""
    import inspect
    signature = inspect.signature(entry_fn)
    try:
        signature.bind(di)
    except TypeError:
        for name in ("fdi", "sdi", "di"):
            if name in signature.parameters:
                signature.bind(**{name: di})
                return entry_fn(**{name: di})
        raise TypeError("定义入口必须接收一个 DefInput 参数")
    return entry_fn(di)


def __getattr__(name):
    if name in ("GraphDef", "GraphBuildResult", "GraphDefinitionPlan"):
        from . import GraphDefinition
        return getattr(GraphDefinition, name)
    raise AttributeError(name)


def build_graph_def(modules, di, *, prepare_input=None):
    from .GraphDefinition import build_graph_def as build
    return build(modules, di, prepare_input=prepare_input)


def _legacy_graph_results(modules, di, proxy_db=None, proxy_table_mapping=None, proxy_tables=None):
    from .GraphDefinition import GraphDefinitionPlan
    plan = GraphDefinitionPlan(modules)
    def resolve_factor(node, definition):
        table = definition.Meta.TargetTable
        if proxy_db is not None and (proxy_tables == "*" or table in (proxy_tables or [])):
            replacement = _get_proxy_factor(proxy_db, proxy_table_mapping or {}, table, node.Name)
            if replacement is not None:
                return replacement
        return node
    built = plan.execute(di, factor_resolver=resolve_factor)
    definitions = {}
    for key, result in built.definitions.items():
        request = plan.requests[key]
        legacy_key = make_def_key(request.module, request.args)
        if legacy_key in definitions:
            raise ValueError("旧定义接口不能表达同模块同参数的多个元信息覆盖，请使用 build_graph_def")
        definitions[legacy_key] = result.as_legacy()
    requested = [(result.as_legacy(), override) for result, (_, _, override) in zip(built.requested, modules)]
    return definitions, requested


def build_dep_fd(modules, fdi, proxy_db=None, proxy_table_mapping=None, proxy_tables=None):
    """使用统一解析核心，返回兼容的因子定义字典和请求列表。"""
    return _legacy_graph_results(modules, fdi, proxy_db, proxy_table_mapping, proxy_tables)


def build_dep_sd(modules, sdi):
    """使用统一解析核心，返回兼容的策略定义字典和请求列表。"""
    return _legacy_graph_results(modules, sdi)


def build_dep(modules, di, collect_mode="both", proxy_db=None, proxy_table_mapping=None, proxy_tables=None):
    """按旧四元组返回结果；both 模式在同一次构图中复用全部实例。"""
    if collect_mode not in ("factor", "strategy", "both"):
        raise ValueError(f"未知收集模式: {collect_mode}")
    definitions, requested = _legacy_graph_results(modules, di, proxy_db, proxy_table_mapping, proxy_tables)
    return (definitions if collect_mode != "strategy" else {}, requested if collect_mode != "strategy" else [],
            definitions if collect_mode != "factor" else {}, requested if collect_mode != "factor" else [])

# -*- coding: utf-8 -*-
"""
DefModule 核心模块 —— 统一因子定义和策略定义框架。

将因子定义和策略定义合并为单一模块，支持：
- 统一输入对象 DefInput（因子和策略共用）
- 统一元信息 DefMeta（合并 FactorMeta + StrategyMeta 超集字段）
- 统一定义容器 Def（同时持有 FactorList 和 StrategyList，自动归类）
- 统一配置 DefSettings / DefProfile（支持 FACTOR_PROFILES / STRATEGY_PROFILES / DEF_PROFILES）
- 统一构建器 DefInputBuilder（合并两个 Builder，消除重复代码）
- 统一依赖解析 build_dep（内部复用 build_dep_fd + build_dep_sd）

入口函数优先级：defNode > defFactor > defStrategy（三者等价）
"""
import os
import re
import json
import importlib
import traceback
import datetime as dt
from typing import List, Dict, Optional, Tuple, Union

import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Args__, __QS_Error__
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


# ============================================================
# 统一元信息
# ============================================================

class DefMeta(__QS_Args__):
    """统一元信息 —— 合并 FactorMeta + StrategyMeta 超集字段。

    策略特有字段（OperatorConfig, StrategyDeps, ResultKey）默认空值，
    因子特有字段（DefaultStartDT, DTType, Freq）保留默认值。
    """
    TargetTable: str = Field(default="", title="因子表/策略信号输出表")
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
        return None
    dep_file = os.path.normcase(os.path.abspath(dep_mod.__file__))
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


def _build_factors_for_strategy(meta, dep_fd, sdi) -> Dict[str, Factor]:
    """根据 FactorDeps 声明从 dep_fd 构建因子字典（策略场景）。"""
    factors = {}
    for dep_name, entries in meta.get("FactorDeps", {}).items():
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
# 核心依赖解析：build_dep_fd
# ============================================================

def build_dep_fd(
    modules: List[Tuple[object, dict, dict]],
    fdi: DefInput,
    proxy_db=None, proxy_table_mapping=None, proxy_tables=None,
) -> Tuple[Dict[str, Def], List[Tuple[Def, dict]]]:
    """根据 __FACTOR_META__ 递归解析因子依赖链并执行 defFactor/defNode/defStrategy。"""
    from QuantStudio.Core import __QS_Logger__ as _Logger

    dep_fd: Dict[str, Def] = {}
    _resolving: set = set()

    def _ensure(module, model_args, factor_meta=None):
        if factor_meta is None:
            factor_meta = {}
        meta = getattr(module, '__FACTOR_META__', None)

        if meta and isinstance(meta, dict) and meta.get('TargetTable'):
            def_key = make_def_key(module, model_args)
            if def_key in dep_fd:
                return
            if def_key in _resolving:
                chain = " → ".join(_resolving)
                raise RuntimeError(f"检测到循环依赖: {chain} → {def_key}")

            _resolving.add(def_key)
            try:
                effective_meta = dict(meta)
                effective_meta.update(factor_meta)
                _check_model_args_refs(effective_meta, module)

                for db_name in effective_meta.get("DBDeps", {}):
                    if db_name not in fdi.FDB:
                        mod_name = getattr(module, '__name__', str(module))
                        raise KeyError(f"模块 '{mod_name}' 声明依赖因子库 '{db_name}'，但该库未在 FDB 中配置。当前可用: {list(fdi.FDB.keys())}")

                saved_args = fdi.ModelArgs
                saved_factors = fdi.Factors
                fdi.ModelArgs = model_args
                try:
                    resolved_deps = {}
                    for dep_name, entries in effective_meta.get('FactorDeps', {}).items():
                        dep_mod = resolve_dep_module(dep_name, module)
                        dep_model_args = _extract_dep_model_args(entries, fdi.ModelArgs)
                        _ensure(dep_mod, dep_model_args, {})
                        dep_def_key = make_def_key(dep_mod, dep_model_args)
                        resolved_deps[dep_def_key] = entries

                    fdi.Factors = _build_factors(resolved_deps, dep_fd, fdi, proxy_db, proxy_table_mapping, proxy_tables)
                    # 查找入口函数：defNode > defFactor > defStrategy
                    entry_fn = getattr(module, 'defNode', None) or getattr(module, 'defFactor', None) or getattr(module, 'defStrategy', None)
                    items = entry_fn(fdi=fdi)
                finally:
                    fdi.ModelArgs = saved_args
                    fdi.Factors = saved_factors

                factor_list, strategy_list = _classify(items)
                result = Def(FactorList=factor_list, StrategyList=strategy_list, Meta=DefMeta(**effective_meta))
                dep_fd[def_key] = result
                _Logger.debug(f"  ✓ {def_key} ({len(result.FactorList)} 因子, {len(result.StrategyList)} 策略)")
            finally:
                _resolving.discard(def_key)
        else:
            saved_args = fdi.ModelArgs
            saved_factors = fdi.Factors
            fdi.ModelArgs = model_args
            fdi.Factors = {}
            try:
                entry_fn = getattr(module, 'defNode', None) or getattr(module, 'defFactor', None) or getattr(module, 'defStrategy', None)
                items = entry_fn(fdi=fdi)
            finally:
                fdi.ModelArgs = saved_args
                fdi.Factors = saved_factors

            factor_list, strategy_list = _classify(items)
            result = Def(FactorList=factor_list, StrategyList=strategy_list, Meta=DefMeta(**factor_meta))
            def_key = make_def_key(module, model_args)
            dep_fd[def_key] = result
            mod_name = module.__name__.split(".")[-1] if hasattr(module, '__name__') else str(module)
            _Logger.debug(f"  ✓ {def_key} ({len(result.FactorList)} 因子, {len(result.StrategyList)} 策略) [无 __FACTOR_META__: {mod_name}]")

    for mod, model_args, factor_meta in modules:
        _ensure(mod, model_args, factor_meta)

    compute_max_lookback(dep_fd)

    requested = []
    for mod, model_args, factor_meta in modules:
        def_key = make_def_key(mod, model_args)
        if def_key in dep_fd:
            requested.append((dep_fd[def_key], factor_meta))
        else:
            requested.append((None, factor_meta))
            _Logger.warning(f"模块 {getattr(mod, '__name__', mod)} 的结果未在 dep_fd 中找到")

    return dep_fd, requested


# ============================================================
# 核心依赖解析：build_dep_sd
# ============================================================

def build_dep_sd(
    modules: List[Tuple[object, dict, dict]],
    sdi: DefInput,
) -> Tuple[Dict[str, Def], List[Tuple[Def, dict]]]:
    """根据 __STRATEGY_META__ 递归解析策略依赖链。"""
    from QuantStudio.Core import __QS_Logger__ as _Logger

    dep_sd: Dict[str, Def] = {}
    _resolving: set = set()

    # Step 1: 收集所有 FactorDeps，统一解析因子依赖
    all_factor_modules = []
    for module, model_args, strategy_meta in modules:
        meta = getattr(module, '__STRATEGY_META__', None)
        if meta and isinstance(meta, dict):
            effective_meta = dict(meta)
            effective_meta.update(strategy_meta)
            for dep_name in effective_meta.get("FactorDeps", {}):
                dep_mod = resolve_dep_module(dep_name, module)
                all_factor_modules.append((dep_mod, {}, {}))

    dep_fd: Dict[str, Def] = {}
    if all_factor_modules:
        _Logger.info(f"解析策略因子依赖: {len(all_factor_modules)} 个因子模块")
        dep_fd, _ = build_dep_fd(all_factor_modules, sdi)

    # Step 2: 递归解析策略依赖并执行 defStrategy/defNode
    def _ensure(module, model_args, strategy_meta=None):
        if strategy_meta is None:
            strategy_meta = {}
        meta = getattr(module, '__STRATEGY_META__', None)

        if meta and isinstance(meta, dict) and meta.get('TargetTable'):
            def_key = make_def_key(module, model_args)
            if def_key in dep_sd:
                return
            if def_key in _resolving:
                chain = " → ".join(_resolving)
                raise RuntimeError(f"检测到策略循环依赖: {chain} → {def_key}")

            _resolving.add(def_key)
            try:
                effective_meta = dict(meta)
                effective_meta.update(strategy_meta)

                for db_name in effective_meta.get("DBDeps", {}):
                    if db_name not in sdi.FDB:
                        mod_name = getattr(module, '__name__', str(module))
                        raise KeyError(f"策略模块 '{mod_name}' 声明依赖因子库 '{db_name}'，但该库未在 FDB 中配置。当前可用: {list(sdi.FDB.keys())}")

                saved_args = sdi.ModelArgs
                saved_factors = sdi.Factors
                saved_strategies = sdi.Strategies
                sdi.ModelArgs = model_args
                try:
                    strategies = {}
                    for dep_module_path, entries in effective_meta.get('StrategyDeps', {}).items():
                        dep_mod = resolve_dep_module(dep_module_path, module)
                        dep_model_args = {}
                        for entry in entries:
                            if not isinstance(entry, dict):
                                continue
                            raw_args = entry.get("ModelArgs")
                            if not raw_args:
                                continue
                            for k, v in raw_args.items():
                                if isinstance(v, str) and v.startswith("$"):
                                    dep_model_args[k] = sdi.ModelArgs.get(v[1:], v[1:])
                                else:
                                    dep_model_args[k] = v
                        _ensure(dep_mod, dep_model_args, {})
                        dep_def_key = _dep_key_to_def_key(dep_module_path, dep_sd)
                        dep_sd_entry = dep_sd.get(dep_def_key) if dep_def_key else None
                        if dep_sd_entry is None:
                            dep_meta = getattr(dep_mod, '__STRATEGY_META__', {}) or {}
                            dep_tt = dep_meta.get('TargetTable', dep_module_path)
                            raise KeyError(f"依赖策略 '{dep_module_path}' (TargetTable='{dep_tt}') 解析失败，未在 dep_sd 中找到")
                        for entry in entries:
                            if isinstance(entry, dict):
                                signal_name = entry.get("Name", entry.get("name", ""))
                                alias = entry.get("Alias", signal_name)
                            else:
                                signal_name = entry
                                alias = entry
                            strategies[alias] = dep_sd_entry.getStrategy(signal_name)
                    sdi.Strategies = strategies

                    sdi.Factors = _build_factors_for_strategy(effective_meta, dep_fd, sdi)

                    # 查找入口函数
                    entry_fn = getattr(module, 'defNode', None) or getattr(module, 'defStrategy', None) or getattr(module, 'defFactor', None)
                    if hasattr(module, 'StrategyObjects'):
                        items = list(module.StrategyObjects)
                    else:
                        items = entry_fn(sdi=sdi)
                finally:
                    sdi.ModelArgs = saved_args
                    sdi.Factors = saved_factors
                    sdi.Strategies = saved_strategies

                if not isinstance(items, list):
                    items = [items]
                factor_list, strategy_list = _classify(items)
                result = Def(FactorList=factor_list, StrategyList=strategy_list, Meta=DefMeta(**effective_meta))
                dep_sd[def_key] = result
                _Logger.debug(f"  ✓ {def_key} ({len(result.FactorList)} 因子, {len(result.StrategyList)} 策略)")
            finally:
                _resolving.discard(def_key)
        else:
            saved_args = sdi.ModelArgs
            saved_factors = sdi.Factors
            saved_strategies = sdi.Strategies
            sdi.ModelArgs = model_args
            sdi.Factors = {}
            sdi.Strategies = {}
            try:
                entry_fn = getattr(module, 'defNode', None) or getattr(module, 'defStrategy', None) or getattr(module, 'defFactor', None)
                if hasattr(module, 'StrategyObjects'):
                    items = list(module.StrategyObjects)
                else:
                    items = entry_fn(sdi=sdi)
            finally:
                sdi.ModelArgs = saved_args
                sdi.Factors = saved_factors
                sdi.Strategies = saved_strategies

            if not isinstance(items, list):
                items = [items]
            factor_list, strategy_list = _classify(items)
            result = Def(FactorList=factor_list, StrategyList=strategy_list, Meta=DefMeta(**strategy_meta))
            def_key = make_def_key(module, model_args)
            dep_sd[def_key] = result
            mod_name = module.__name__.split(".")[-1] if hasattr(module, '__name__') else str(module)
            _Logger.debug(f"  ✓ {def_key} ({len(result.FactorList)} 因子, {len(result.StrategyList)} 策略) [无 __STRATEGY_META__: {mod_name}]")

    for mod, model_args, strategy_meta in modules:
        _ensure(mod, model_args, strategy_meta)

    compute_max_lookback_sd(dep_sd, dep_fd)

    requested = []
    for mod, model_args, strategy_meta in modules:
        def_key = make_def_key(mod, model_args)
        if def_key in dep_sd:
            requested.append((dep_sd[def_key], strategy_meta))
        else:
            requested.append((None, strategy_meta))
            _Logger.warning(f"策略模块 {getattr(mod, '__name__', mod)} 的结果未在 dep_sd 中找到")

    return dep_sd, requested


# ============================================================
# 统一入口 build_dep
# ============================================================

def build_dep(
    modules: List[Tuple[object, dict, dict]],
    di: DefInput,
    collect_mode: str = "both",
    proxy_db=None, proxy_table_mapping=None, proxy_tables=None,
) -> Tuple[Dict[str, Def], List[Tuple[Def, dict]], Dict[str, Def], List[Tuple[Def, dict]]]:
    """统一依赖解析入口。

    Args:
        modules: 模块列表
        di: 统一输入对象
        collect_mode: "factor" | "strategy" | "both"
        proxy_db, proxy_table_mapping, proxy_tables: 代理因子库参数

    Returns:
        (dep_fd, factor_results, dep_sd, strategy_results)
    """
    dep_fd, factor_results = {}, []
    dep_sd, strategy_results = {}, []

    if collect_mode in ("factor", "both"):
        # 将所有模块当作因子模块解析
        dep_fd, factor_results = build_dep_fd(modules, di, proxy_db=proxy_db, proxy_table_mapping=proxy_table_mapping, proxy_tables=proxy_tables)

    if collect_mode in ("strategy", "both"):
        # 将所有模块当作策略模块解析
        dep_sd, strategy_results = build_dep_sd(modules, di)

    return dep_fd, factor_results, dep_sd, strategy_results

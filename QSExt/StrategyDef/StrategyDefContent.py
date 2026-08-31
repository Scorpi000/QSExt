# -*- coding: utf-8 -*-
import os
import sys
import importlib
import traceback
import datetime as dt
from typing import List, Dict, Optional, Tuple, Union

from pydantic import Field

from QuantStudio.Core import __QS_Args__, __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB
from QSExt.RuntimeConfig.config import DBDef, DBPool, RuntimeSettings


# ============================================================
# StrategyDefInput — 策略定义输入上下文
# ============================================================

class StrategyDefInput(__QS_Args__):
    """策略定义输入对象 —— 与 FactorDefInput 对齐，新增 Strategies 字段"""
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
# StrategyMeta — 策略静态元信息
# ============================================================

class StrategyMeta(__QS_Args__):
    """策略定义的静态元信息 —— 描述一个策略定义模块的固有属性

    与 FactorMeta 对齐，新增 OperatorConfig 和 StrategyDeps 字段。
    所有字段均设有默认值，支持从空 dict 构造。
    """
    TargetTable: str = Field(default="", title="策略信号输出因子表")
    IDType: str = Field(default="", title="证券类型")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述信息")
    MaxLookBack: int = Field(default=365, title="最大回溯期")
    DefScriptPath: str = Field(default="", title="定义脚本路径")

    # ---- 算子配置 ----
    OperatorConfig: Dict = Field(
        default={"SignalType": "目标权重", "InitCash": 1e6, "ShortAllowed": False},
        title="策略算子默认配置",
    )

    # ---- 分类与发现 ----
    Tags: List[str] = Field(default=[], title="检索标签")
    FactorDeps: Dict[str, List[Union[str, dict]]] = Field(default={}, title="依赖因子声明")
    StrategyDeps: Dict[str, List[Union[str, dict]]] = Field(
        default={}, title="依赖策略声明",
        description="key 为依赖策略的模块路径，value 为 [{Name: 信号因子名, Alias: 本地别名, ModelArgs: {...}}]",
    )
    DBDeps: Dict[str, str] = Field(default={}, title="因子库依赖")
    ModelArgs: Dict[str, str] = Field(default={}, title="期望的模型参数")


# ============================================================
# StrategyDef — 策略定义包装类
# ============================================================

class StrategyDef(__QS_Args__):
    """策略定义对象 —— 组合策略列表和元信息

    与 FactorDef 对齐：一个模块可产出多个策略实例，统一包装在一个 StrategyDef 中。

    构造方式:
      StrategyDef(StrategyList=[s1, s2], Meta=StrategyMeta(**__STRATEGY_META__))
    """
    StrategyList: List[Factor] = Field(title="策略实例列表")
    Meta: StrategyMeta = Field(title="静态元信息")

    @property
    def StrategyNames(self) -> List[str]:
        """策略输出的信号因子名列表"""
        return [s.Name for s in self.StrategyList]

    def getStrategy(self, name: str) -> Factor:
        """按名称查找策略实例

        Args:
            name: 策略名称（_QSArgs.Name）

        Returns:
            策略实例
        """
        for s in self.StrategyList:
            if s.Name == name:
                return s
        raise __QS_Error__(f"策略定义中找不到策略 '{name}'，可用: {self.StrategyNames}")


# ============================================================
# 依赖解析 — build_dep_sd
# ============================================================

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


def _build_factors_for_strategy(
    meta: dict,
    dep_fd: Dict[str, "FactorDef"],
    sdi: "StrategyDefInput",
) -> Dict[str, Factor]:
    """根据 FactorDeps 声明从 dep_fd 构建因子字典。

    与 FactorDefContent._build_factors 逻辑一致，适配策略场景。
    使用 _dep_key_to_def_key 将 FactorDeps key 映射到 dep_fd 的 DefKey。

    Args:
        meta: 模块的 __STRATEGY_META__ 字典
        dep_fd: 已解析的 FactorDef 映射 (DefKey → FactorDef)
        sdi: 策略定义输入

    Returns:
        {因子名: Factor} 扁平字典
    """
    from QSExt.FactorDef.FactorDefContent import _dep_key_to_def_key

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


def build_dep_sd(
    modules: List[Tuple[object, dict, dict]],
    sdi: "StrategyDefInput",
) -> Tuple[Dict[str, "StrategyDef"], List[Tuple["StrategyDef", dict]]]:
    """根据 __STRATEGY_META__ 递归解析策略依赖链。

    解析顺序：
    1. 收集所有策略模块的 FactorDeps，通过 build_dep_fd 统一解析因子依赖
    2. 按拓扑序递归解析 StrategyDeps，调用依赖策略的 defStrategy
    3. 将依赖因子和依赖策略注入 sdi.Factors / sdi.Strategies
    4. 调用目标模块的 defStrategy(sdi) 获取策略实例

    Args:
        modules: 策略模块列表，每项为 (module, model_args, strategy_meta)
        sdi: 策略定义输入上下文（ModelArgs 和 Factors/Strategies 会在调用期间被临时修改并恢复）

    Returns:
        (dep_sd, requested_results):
          - dep_sd: DefKey → StrategyDef 的完整映射（含依赖模块）
          - requested_results: 显式请求的模块结果列表（保持 modules 原顺序），
            (StrategyDef, strategy_meta)，失败时为 (None, strategy_meta)

    Raises:
        RuntimeError: 检测到循环依赖
        ImportError: 依赖模块无法解析
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger
    from QSExt.FactorDef.FactorDefContent import build_dep_fd, FactorDef, make_def_key, _dep_key_to_def_key

    dep_sd: Dict[str, StrategyDef] = {}
    _resolving: set = set()

    # ---- Step 1: 收集所有 FactorDeps，统一解析因子依赖 ----
    all_factor_modules = []
    for module, model_args, strategy_meta in modules:
        meta = getattr(module, '__STRATEGY_META__', None)
        if meta and isinstance(meta, dict):
            effective_meta = dict(meta)
            effective_meta.update(strategy_meta)
            for dep_name in effective_meta.get("FactorDeps", {}):
                dep_mod = resolve_dep_module(dep_name, module)
                all_factor_modules.append((dep_mod, {}, {}))

    dep_fd: Dict[str, FactorDef] = {}
    if all_factor_modules:
        _Logger.info(f"解析策略因子依赖: {len(all_factor_modules)} 个因子模块")
        dep_fd, _ = build_dep_fd(all_factor_modules, sdi)

    # ---- Step 2: 递归解析策略依赖并执行 defStrategy ----
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

                # 校验 DBDeps
                for db_name in effective_meta.get("DBDeps", {}):
                    if db_name not in sdi.FDB:
                        mod_name = getattr(module, '__name__', str(module))
                        raise KeyError(
                            f"策略模块 '{mod_name}' 声明依赖因子库 '{db_name}'，"
                            f"但该库未在 FDB 中配置。当前可用: {list(sdi.FDB.keys())}"
                        )

                saved_args = sdi.ModelArgs
                saved_factors = sdi.Factors
                saved_strategies = sdi.Strategies
                sdi.ModelArgs = model_args
                try:
                    # 2a. 解析 StrategyDeps（递归执行依赖策略的 defStrategy）
                    strategies = {}
                    for dep_module_path, entries in effective_meta.get('StrategyDeps', {}).items():
                        dep_mod = resolve_dep_module(dep_module_path, module)
                        # 从 entries 中提取 ModelArgs（与 _extract_dep_model_args 对齐）
                        #   entry 格式: {"Name": "信号名", "Alias": "别名", "ModelArgs": {...}}
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
                        # 通过 _dep_key_to_def_key 在 dep_sd 中查找依赖模块
                        dep_def_key = _dep_key_to_def_key(dep_module_path, dep_sd)
                        dep_sd_entry = dep_sd.get(dep_def_key) if dep_def_key else None
                        if dep_sd_entry is None:
                            dep_meta = getattr(dep_mod, '__STRATEGY_META__', {}) or {}
                            dep_tt = dep_meta.get('TargetTable', dep_module_path)
                            raise KeyError(
                                f"依赖策略 '{dep_module_path}' (TargetTable='{dep_tt}') 解析失败，未在 dep_sd 中找到"
                            )
                        # 提取依赖策略的信号因子
                        for entry in entries:
                            if isinstance(entry, dict):
                                signal_name = entry.get("Name", entry.get("name", ""))
                                alias = entry.get("Alias", signal_name)
                            else:
                                signal_name = entry
                                alias = entry
                            strategies[alias] = dep_sd_entry.getStrategy(signal_name)
                    sdi.Strategies = strategies

                    # 2b. 注入 Factors
                    sdi.Factors = _build_factors_for_strategy(effective_meta, dep_fd, sdi)

                    # 2c. 调用 defStrategy 或使用 StrategyObjects（notebook 模式）
                    if hasattr(module, 'defStrategy'):
                        strategy_instances = module.defStrategy(sdi=sdi)
                        if not isinstance(strategy_instances, list):
                            strategy_instances = [strategy_instances]
                    elif hasattr(module, 'StrategyObjects'):
                        strategy_instances = list(module.StrategyObjects)
                    else:
                        mod_name = getattr(module, '__name__', str(module))
                        raise AttributeError(
                            f"策略模块 '{mod_name}' 既没有 defStrategy 函数也没有 StrategyObjects 属性"
                        )
                finally:
                    sdi.ModelArgs = saved_args
                    sdi.Factors = saved_factors
                    sdi.Strategies = saved_strategies

                # 包装为 StrategyDef（与 FactorDef 对齐：一个模块一个 StrategyDef，内含多个策略实例）
                result = StrategyDef(
                    StrategyList=strategy_instances,
                    Meta=StrategyMeta(**effective_meta),
                )
                dep_sd[def_key] = result
                _Logger.debug(
                    f"  ✓ {def_key} "
                    f"({len(result.StrategyList)} 个策略)"
                )
            finally:
                _resolving.discard(def_key)
        else:
            # 无 __STRATEGY_META__ 的模块：直接调用
            saved_args = sdi.ModelArgs
            saved_factors = sdi.Factors
            saved_strategies = sdi.Strategies
            sdi.ModelArgs = model_args
            sdi.Factors = {}
            sdi.Strategies = {}
            try:
                if hasattr(module, 'defStrategy'):
                    strategy_instances = module.defStrategy(sdi=sdi)
                    if not isinstance(strategy_instances, list):
                        strategy_instances = [strategy_instances]
                elif hasattr(module, 'StrategyObjects'):
                    strategy_instances = list(module.StrategyObjects)
                else:
                    mod_name = getattr(module, '__name__', str(module))
                    raise AttributeError(
                        f"策略模块 '{mod_name}' 既没有 defStrategy 函数也没有 StrategyObjects 属性"
                    )
            finally:
                sdi.ModelArgs = saved_args
                sdi.Factors = saved_factors
                sdi.Strategies = saved_strategies

            results = []
            for strategy_instance in strategy_instances:
                strategy_class = getattr(strategy_instance, '__class__', type(strategy_instance))
                result = StrategyDef(
                    StrategyList=strategy_instances,
                    Meta=StrategyMeta(**strategy_meta),
                )
                results.append(result)

            def_key = make_def_key(module, model_args)
            dep_sd[def_key] = result

            mod_name = (
                module.__name__.split(".")[-1]
                if hasattr(module, '__name__') else str(module)
            )
            _Logger.debug(f"  ✓ {def_key} [无 __STRATEGY_META__: {mod_name}] ({len(result.StrategyList)} 个策略)")

    # ---- 执行所有显式请求的模块 ----
    for mod, model_args, strategy_meta in modules:
        _ensure(mod, model_args, strategy_meta)

    # ---- 递归计算 MaxLookBack ----
    compute_max_lookback_sd(dep_sd, dep_fd)

    # ---- 收集显式请求的结果 ----
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
# MaxLookBack 计算
# ============================================================

def compute_max_lookback_sd(
    dep_sd: Dict[str, "StrategyDef"],
    dep_fd: Dict = None,
) -> None:
    """递归计算所有 StrategyDef 的 MaxLookBack。

    对 dep_sd 中每个 StrategyDef，根据 Meta.FactorDeps 和 Meta.StrategyDeps 的依赖关系，
    递归计算: MaxLookBack = max(自身声明的值, 各依赖的 MaxLookBack)。

    Args:
        dep_sd: DefKey → StrategyDef 的映射
        dep_fd: DefKey → FactorDef 的映射（可选，用于因子依赖的 MaxLookBack）
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger
    from QSExt.FactorDef.FactorDefContent import _dep_key_to_def_key

    dep_fd = dep_fd or {}
    memo: Dict[str, int] = {}
    resolving: set = set()

    def _resolve(def_key: str) -> int:
        if def_key in memo:
            return memo[def_key]
        if def_key in resolving:
            raise RuntimeError(
                f"compute_max_lookback_sd 检测到循环依赖: {' -> '.join(resolving)} -> {def_key}"
            )

        resolving.add(def_key)
        try:
            sd = dep_sd[def_key]
            mlb = sd.Meta.MaxLookBack

            # 考虑因子依赖的 MaxLookBack
            for dep_name in sd.Meta.FactorDeps:
                dep_def_key = _dep_key_to_def_key(dep_name, dep_fd)
                if dep_def_key and dep_def_key in dep_fd:
                    mlb = max(mlb, dep_fd[dep_def_key].Meta.MaxLookBack)
                elif dep_def_key and dep_def_key in dep_sd:
                    mlb = max(mlb, _resolve(dep_def_key))

            # 考虑策略依赖的 MaxLookBack
            for dep_module_path in sd.Meta.StrategyDeps:
                dep_def_key = _dep_key_to_def_key(dep_module_path, dep_sd)
                if dep_def_key and dep_def_key in dep_sd:
                    mlb = max(mlb, _resolve(dep_def_key))

            memo[def_key] = mlb
            if mlb != sd.Meta.MaxLookBack:
                _Logger.debug(
                    f"compute_max_lookback_sd: {def_key} MaxLookBack "
                    f"{sd.Meta.MaxLookBack} → {mlb}"
                )
                sd.Meta.MaxLookBack = mlb
            return mlb
        finally:
            resolving.discard(def_key)

    for def_key in list(dep_sd.keys()):
        _resolve(def_key)

    _Logger.info(f"compute_max_lookback_sd: 已处理 {len(dep_sd)} 个 StrategyDef")


# ============================================================
# 运行时配置与 StrategyDefInput 构造
# ============================================================

class StrategyDefProfile(__QS_Args__):
    """单个 IDType 维度的策略模块分组"""
    id_type: str = Field(default="A股", title="证券类型")
    id_selection: dict = Field(default={"type": "all"}, title="ID 选择策略")
    strategy_modules: list = Field(default=[], title="策略模块列表")
    section_id_list: List[str] = Field(default=[], title="自定义截面证券列表")


class StrategyDefSettings(RuntimeSettings):
    """策略定义运行时配置 —— 继承统一 RuntimeSettings，无专属字段。"""

    @classmethod
    def from_module(cls, module_path: str = "settings", **cmd_overrides) -> "StrategyDefSettings":
        """从 Python 模块加载配置。

        若 module_path 为短名（不以 QSExt. 或 / 开头），默认查找 QSExt.StrategyDef.conf.<name>。
        """
        if not module_path.startswith("QSExt") and not os.path.isabs(module_path):
            module_path = f"QSExt.StrategyDef.conf.{module_path}"
        return super().from_module(module_path, **cmd_overrides)

    def iter_profiles(self) -> List["StrategyDefProfile"]:
        """将 id_profiles 转换为 StrategyDefProfile 列表"""
        profiles = []
        for p in self.id_profiles:
            profiles.append(StrategyDefProfile(
                id_type=p.get("id_type", "A股"),
                id_selection=p.get("id_selection", {"type": "all"}),
                strategy_modules=p.get("strategy_modules", []),
                section_id_list=p.get("section_id_list", []),
            ))
        return profiles


class StrategyDefInputBuilder:
    """根据 StrategyDefSettings 构造 StrategyDefInput

    生命周期:
        with StrategyDefInputBuilder(settings) as builder:
            sdi = builder.build()
            # ... 使用 sdi 运行策略定义 ...

    职责:
        1. 创建并连接所有因子库 (DBPool)
        2. 解析时间范围 → DTs, DTRuler
        3. 解析 ID 选择策略 → IDs, SectionIDs
        4. 组装 FDB 字典和 StrategyDefInput
        5. 解析策略模块列表
    """

    def __init__(self, settings: StrategyDefSettings):
        self.settings = settings
        self._pool: Optional[DBPool] = None

    def init(self) -> None:
        self._pool = self.settings.to_db_pool()
        self._pool.create_all()
        self._pool.connect_all()
        self._run_hooks()

    def _run_hooks(self) -> None:
        hook = self.settings.get_hook("init_db")
        if hook:
            hook(self._pool)

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
            import pandas as pd
            return pd.to_datetime(end_dt)

    def _fetch_dates(self, start_date: dt.datetime, end_date: dt.datetime) -> List[dt.datetime]:
        if self.settings.dt_type == "自然日":
            import pandas as pd
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
        import pandas as pd
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
        dts = self._apply_dt_freq(dts, self.settings.dt_freq)
        dtruler = self._apply_dt_freq(dtruler, self.settings.dt_freq)
        return dts, dtruler

    @staticmethod
    def _apply_dt_freq(dts: List[dt.datetime], freq: str) -> List[dt.datetime]:
        if not dts or freq == "1d":
            return dts
        import re
        import pandas as pd
        m = re.match(r'^(\d+)([dwmqy])$', freq)
        if not m:
            raise ValueError(f"无效的频率格式: {freq}")
        n, unit = m.groups()
        n = int(n)
        unit_map = {'d': 'D', 'w': 'W', 'm': 'ME', 'q': 'QE', 'y': 'YE'}
        pd_freq = f"{n}{unit_map[unit]}"
        s = pd.Series(range(len(dts)), index=pd.DatetimeIndex(dts))
        resampled = s.resample(pd_freq).last().dropna()
        return [dts[int(i)] for i in resampled.values]

    def _get_ids_from_source(self, id_type: str, is_current: bool = False) -> List[str]:
        """根据 id_type 从数据源获取证券 ID 列表。

        使用 settings.section_id_sources 中配置的数据源名称、方法和方法参数。
        自定义 id_type 只需在 settings.py 的 section_id_sources 中添加对应条目即可。
        """
        section_source = self.settings.section_id_sources.get(id_type, {})
        if not section_source:
            raise ValueError(
                f"IDType '{id_type}' 未在 settings.section_id_sources 中配置，"
                f"请添加对应的 {{name, method, method_args}} 配置项"
            )
        source_name = section_source.get("name", "JYDB")
        source_method = section_source.get("method", "getStockID")
        source_method_args = section_source.get("method_args", {})
        id_source = self._pool[source_name]
        method = getattr(id_source, source_method)
        return method(is_current=is_current, **source_method_args)

    def resolve_ids_for(self, profile: "StrategyDefProfile") -> Tuple[List[str], List[str]]:
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
        section_ids = profile.section_id_list if profile.section_id_list else ids
        return ids, section_ids

    def resolve_fdb(self) -> Dict[str, FactorDB]:
        return {name: self._pool[name] for name in self._pool.source_names}

    def resolve_modules(self) -> List[Tuple[object, dict, dict]]:
        all_modules = []
        for profile in self.settings.iter_profiles():
            all_modules.extend(self._resolve_modules_for(profile.strategy_modules))
        return all_modules

    def _resolve_module(self, name: str) -> object:
        if isinstance(name, str) and name.endswith(".ipynb"):
            from QSExt.StrategyDef.utils import load_notebook_as_module
            if not os.path.isabs(name):
                name = os.path.abspath(name)
            return load_notebook_as_module(name)
        return importlib.import_module(name)

    def _resolve_modules_for(self, strategy_modules: list) -> List[Tuple[object, dict, dict]]:
        from QSExt.StrategyDef.utils import expand_glob

        modules = []
        raw_modules = strategy_modules
        if isinstance(raw_modules, str):
            raw_modules = [raw_modules]

        for item in raw_modules:
            if isinstance(item, dict):
                mod_ref = item["module"]
                model_args = item.get("model_args", {})
                strategy_meta = dict(item.get("strategy_meta", {}))
                if "target_table" in item and "TargetTable" not in strategy_meta:
                    strategy_meta["TargetTable"] = item["target_table"]
            else:
                mod_ref, model_args, strategy_meta = item, {}, {}

            if isinstance(mod_ref, str) and ("*" in mod_ref or "?" in mod_ref):
                names = expand_glob(mod_ref)
            else:
                names = [mod_ref]

            for name in names:
                module = self._resolve_module(name) if isinstance(name, str) else name
                modules.append((module, dict(model_args), strategy_meta))

        return modules

    def build(self) -> "StrategyDefInput":
        if self._pool is None:
            self.init()
        profiles = self.settings.iter_profiles()
        if not profiles:
            raise ValueError("ID_PROFILES 为空，无法构建 StrategyDefInput")
        return self.build_for_profile(profiles[0])

    def build_for_profile(
        self,
        profile: "StrategyDefProfile",
        dts: List[dt.datetime] = None,
        dtruler: List[dt.datetime] = None,
    ) -> "StrategyDefInput":
        if self._pool is None:
            self.init()
        if dts is None or dtruler is None:
            dts, dtruler = self.resolve_dts()
        fdb = self.resolve_fdb()
        ids, section_ids = self.resolve_ids_for(profile)
        return StrategyDefInput(
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

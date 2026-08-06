# -*- coding: utf-8 -*-
import os
import json
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
from QSExt.RuntimeConfig.config import DBDef, DBPool, RuntimeSettings


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

class FactorDefProfile(__QS_Args__):
    """单个 IDType 维度的因子模块分组 —— 用于多 IDType 统一调度"""
    id_type: str = Field(default="A股", title="证券类型")
    id_selection: dict = Field(default={"type": "all"}, title="ID 选择策略")
    factor_modules: list = Field(default=[], title="因子模块列表")
    section_id_list: List[str] = Field(default=[], title="自定义截面证券列表")
    proxy_tables: Union[List[str], str, None] = Field(default=None, title="代理表", description="None=不代理, '*'=全部代理, ['t1','t2']=指定表代理")


class FactorDefSettings(RuntimeSettings):
    """因子定义运行时配置 —— 继承统一 RuntimeSettings，无专属字段。"""

    @classmethod
    def from_module(cls, module_path: str = "settings", **cmd_overrides) -> "FactorDefSettings":
        """从 Python 模块加载配置。

        若 module_path 为短名（不以 QSExt. 或 / 开头），默认查找 QSExt.FactorDef.conf.<name>。
        """
        if not module_path.startswith("QSExt") and not os.path.isabs(module_path):
            module_path = f"QSExt.FactorDef.conf.{module_path}"
        return super().from_module(module_path, **cmd_overrides)

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


class FactorDefInputBuilder:
    """根据 FactorDefSettings 构造 FactorDefInput

    生命周期:
        with FactorDefInputBuilder(settings) as builder:
            fdi = builder.build()
            # ... 使用 fdi 运行因子定义 ...

    职责:
        1. 创建并连接所有因子库 (DBPool)
        2. 解析时间范围 → DTs, DTRuler
        3. 解析 ID 选择策略 → IDs, SectionIDs
        4. 组装 FDB 字典 和 FactorDefInput
        5. 解析因子模块列表
    """

    def __init__(self, settings: FactorDefSettings):
        self.settings = settings
        self._pool: Optional[DBPool] = None

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
        """根据 DT_TYPE 获取日期序列"""
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
        """根据 id_type 从数据源获取证券 ID 列表。

        使用 settings.section_id_sources 中配置的数据源名称和方法。
        """
        section_source = self.settings.section_id_sources.get(id_type, {})
        source_name = section_source.get("name", "JYDB")
        source_method = section_source.get("method", "getStockID")
        source_method_args = section_source.get("method_args", {})
        id_source = self._pool[source_name]
        method = getattr(id_source, source_method)

        if id_type == "A股":
            return method(is_current=is_current, **source_method_args)
        elif id_type == "公募基金":
            return method(is_current=is_current, **source_method_args)
        elif id_type == "期货":
            return method(is_current=is_current, **source_method_args)
        elif id_type == "期权":
            return method(is_current=is_current, **source_method_args)
        elif id_type == "ETF":
            return method(type="ETF", is_current=is_current, **source_method_args)
        elif id_type == "申万一级行业指数":
            return method(type="申万一级行业指数", is_current=is_current, **source_method_args)
        elif id_type == "申万一级行业":
            return method(standard="申万行业分类(新)", level=1, is_current=is_current, **source_method_args)
        elif id_type == "指数":
            return method(is_current=is_current, **source_method_args)
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

                    "QSExt.FactorDef.example_factor"

                字典::

                    {
                        "module": "QSExt.FactorDef.example_factor",
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


def make_def_key(module, model_args: dict) -> str:
    """根据模块路径和 ModelArgs 生成唯一的 DefKey。

    DefKey = ``os.path.abspath(module.__file__)`` + ModelArgs JSON 序列化。
    model_args 为空时省略 ``@...`` 部分，ModelArgs 按 key 排序确保一致性。

    Args:
        module: Python 模块对象（需有 ``__file__`` 属性）
        model_args: 模块的 ModelArgs 字典

    Returns:
        DefKey 字符串，如 ``D:\\factors\\my_status.py`` 或
        ``D:\\factors\\my_status.py@{"lookback":20}``
    """
    file_path = os.path.abspath(module.__file__)
    if not model_args:
        return file_path
    return f"{file_path}@{json.dumps(model_args, sort_keys=True, default=str)}"


def _dep_key_to_def_key(dep_name: str, target_dict: dict) -> Optional[str]:
    """将 FactorDeps/StrategyDeps 声明的依赖名映射到 target_dict 中的 DefKey。

    通过 resolve_dep_module 导入依赖模块获取 ``__file__``，
    再以 ``os.path.normcase`` 与 target_dict 中各 DefKey 的文件路径部分匹配。

    Args:
        dep_name: 依赖声明中的模块路径（如 ``"my_status"`` 或完整路径）
        target_dict: DefKey → xxxDef 的字典（dep_fd 或 dep_sd）

    Returns:
        匹配到的 DefKey，若 target_dict 为空或无法解析则返回 None
    """
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
    resolved_deps: Dict[str, list],
    dep_fd: Dict[str, "FactorDef"],
    fdi: "FactorDefInput",
    proxy_db: Optional[FactorDB] = None,
    proxy_table_mapping: Optional[dict] = None,
    proxy_tables: Optional[Union[List[str], str]] = None,
) -> Dict[str, Factor]:
    """根据预解析的依赖映射构建扁平因子字典。

    FactorDeps entry 两种格式：

    - 字符串: ``"close"`` — 因子名。``"*"`` 表示该表全部因子
    - 字典: ``{"Name": "close", "Alias": "price"}``

      - Name: 因子名（必填），``"*"`` 表示该表全部因子
      - Alias: 注入到 fdi.Factors 时的别名（可选，默认用 Name，仅单因子时有效）
      - ModelArgs: 传递给依赖模块 defFactor 的参数（可选），值以 ``"$"`` 开头时从父模块 fdi.ModelArgs 中查找

    Args:
        resolved_deps: DefKey → entries 的映射（由调用方从 FactorDeps 预解析）
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
    for def_key, entries in resolved_deps.items():
        fd = dep_fd.get(def_key)
        if fd is None:
            continue

        table_name = fd.Meta.TargetTable
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
      - 完整路径: "QSExt.FactorDef.example_factor"
      - 短名（同包下）: "stock_cn_status"

    Args:
        modules: resolve_modules_for() 返回的模块列表，每项为 (module, model_args, factor_meta)
        fdi: 运行时上下文（ModelArgs 和 Factors 会在调用期间被临时修改并恢复）
        proxy_db: 代理因子库，用于因子替换
        proxy_table_mapping: 代理表名映射
        proxy_tables: 代理表控制，``"*"`` 全部代理，列表指定表名，None 不代理

    Returns:
        (dep_fd, requested_results):
          - dep_fd: DefKey → FactorDef 的完整映射（含依赖模块）
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
            # 去重 key: 基于模块文件路径 + ModelArgs
            def_key = make_def_key(module, model_args)
            if def_key in dep_fd:
                return
            if def_key in _resolving:
                chain = " → ".join(_resolving)
                raise RuntimeError(f"检测到循环依赖: {chain} → {def_key}")

            _resolving.add(def_key)
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
                    # 递归解析该模块声明的依赖，并预构建 resolved_deps
                    resolved_deps = {}
                    for dep_name, entries in effective_meta.get('FactorDeps', {}).items():
                        dep_mod = resolve_dep_module(dep_name, module)
                        # $ 前缀的值从当前模块的 fdi.ModelArgs 中查找
                        dep_model_args = _extract_dep_model_args(entries, fdi.ModelArgs)
                        _ensure(dep_mod, dep_model_args, {})
                        dep_def_key = make_def_key(dep_mod, dep_model_args)
                        resolved_deps[dep_def_key] = entries

                    # 注入 Factors 并执行自身
                    fdi.Factors = _build_factors(resolved_deps, dep_fd, fdi, proxy_db, proxy_table_mapping, proxy_tables)
                    factor_list = module.defFactor(fdi=fdi)
                finally:
                    fdi.ModelArgs = saved_args
                    fdi.Factors = saved_factors

                # 包装为 FactorDef
                result = FactorDef(
                    FactorList=factor_list,
                    Meta=FactorMeta(**effective_meta),
                )

                dep_fd[def_key] = result
                _Logger.debug(
                    f"  ✓ {def_key} "
                    f"({len(result.FactorList)} 因子)"
                )
            finally:
                _resolving.discard(def_key)
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
            def_key = make_def_key(module, model_args)
            dep_fd[def_key] = result
            mod_name = (
                module.__name__.split(".")[-1]
                if hasattr(module, '__name__') else str(module)
            )
            _Logger.debug(
                f"  ✓ {def_key} "
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
        def_key = make_def_key(mod, model_args)
        if def_key in dep_fd:
            requested.append((dep_fd[def_key], factor_meta))
        else:
            requested.append((None, factor_meta))
            _Logger.warning(f"模块 {getattr(mod, '__name__', mod)} 的结果未在 dep_fd 中找到")

    return dep_fd, requested


def compute_max_lookback(dep_fd: Dict[str, "FactorDef"]) -> None:
    """递归计算所有 FactorDef 的 MaxLookBack。

    对 dep_fd 中每个 FactorDef，根据 Meta.FactorDeps 的 key 声明的依赖关系，
    递归计算: MaxLookBack = max(自身声明的值, 各依赖模块的 MaxLookBack)。

    Args:
        dep_fd: DefKey → FactorDef 的映射（由 build_dep_fd 构建）
    """
    from QuantStudio.Core import __QS_Logger__ as _Logger

    memo: Dict[str, int] = {}
    resolving: set = set()

    def _resolve(def_key: str) -> int:
        if def_key in memo:
            return memo[def_key]
        if def_key in resolving:
            raise RuntimeError(
                f"compute_max_lookback 检测到循环依赖: {' -> '.join(resolving)} -> {def_key}"
            )

        resolving.add(def_key)
        try:
            fd = dep_fd[def_key]
            mlb = fd.Meta.MaxLookBack
            dep_names = list(fd.Meta.FactorDeps.keys())
            for dep_name in dep_names:
                dep_def_key = _dep_key_to_def_key(dep_name, dep_fd)
                if dep_def_key and dep_def_key in dep_fd:
                    mlb = max(mlb, _resolve(dep_def_key))
                else:
                    _Logger.debug(
                        f"compute_max_lookback: 依赖 '{dep_name}' "
                        f"未在 dep_fd 中找到，跳过"
                    )
            memo[def_key] = mlb
            if mlb != fd.Meta.MaxLookBack:
                _Logger.debug(
                    f"compute_max_lookback: {def_key} MaxLookBack "
                    f"{fd.Meta.MaxLookBack} → {mlb}"
                )
                fd.Meta.MaxLookBack = mlb
            return mlb
        finally:
            resolving.discard(def_key)

    for def_key in list(dep_fd.keys()):
        _resolve(def_key)

    _Logger.info(f"compute_max_lookback: 已处理 {len(dep_fd)} 个 FactorDef")

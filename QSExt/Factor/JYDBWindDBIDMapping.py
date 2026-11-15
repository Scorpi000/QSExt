"""ID mappings between JYDB and WindDB security namespaces."""
from __future__ import annotations

import datetime as dt
import threading
from typing import Literal, Optional

import pandas as pd
from pydantic import Field

from QuantStudio.Core import __QS_Error__
from QuantStudio.Tools.DataTypeFun import dict2id
from QSExt.Factor.IDMapping import FactorDBIDMappingConfig, IDMapping, IDMappingFactorDB


# WindDB 表映射的手工配置：键为证券类型，值为强制归入该类型的表名。
# None 表示强制保持 WindDB 原生 ID。手工配置覆盖 TableInfo.SecurityType。
WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE = {
    "港股": (
        "香港股票基本资料",
        "香港股票日行情",
        "香港股票日行情估值指标",
        "香港股票概念板块分类",
        "香港股票指数基本资料",
    ),
    "公募基金": (
        "中国ETF申购赎回成份",
        "中国ETF申购赎回清单",
    ),
    None: (),
}

# 因子值本身是证券代码的字段配置：{表名: {字段名: 证券类型}}。
# 证券类型从 mapping_by_security_type 选择对应 IDMapping；None 表示该字段不转换。
# JYDBWindDBFactorDB 的 id_value_factors 参数可按表覆盖这里的配置。
WINDDB_MANUAL_ID_VALUE_FACTORS = {
    "中国ETF申购赎回成份": {
        "成份股Wind代码": "港股"
    }
}


class WindDBMutualFundIDMapping(IDMapping):
    """Map public mutual-fund IDs to Wind's internal fund codes."""

    class __QS_ArgClass__(IDMapping.__QS_ArgClass__):
        Name: str = Field(default="WindDB公募基金代码映射", frozen=True)
        UnmappedPolicy: Literal["empty", "raise", "passthrough"] = Field(
            default="passthrough", frozen=True, title="未映射ID策略"
        )

    def __init__(self, winddb, args: dict = {}, **kwargs):
        self._WindDB = winddb
        self._Mapping = None
        self._MappingInfo = None
        self._MappingID = None
        self._LoadLock = threading.Lock()
        super().__init__(args=args, **kwargs)

    @property
    def MappingID(self) -> str:
        self._load()
        return self._MappingID

    @property
    def MappingInfo(self) -> pd.DataFrame:
        self._load()
        return self._MappingInfo.copy()

    def refresh(self):
        with self._LoadLock:
            self._Mapping = self._MappingInfo = self._MappingID = None
        self._load()
        self._QS_ID = None
        return self

    def _mapping(self) -> dict[str, str]:
        self._load()
        return self._Mapping

    def _load(self):
        if self._Mapping is not None:
            return
        with self._LoadLock:
            if self._Mapping is not None:
                return
            sql = f"""SELECT s_info_outercode, f_info_windcode
            FROM {self._WindDB.Args.TablePrefix}ChinaMutualFundDescription
            """
            info = pd.DataFrame(
                self._WindDB.fetchall(sql), columns=["ID", "WindCode"]
            ).dropna(subset=["ID", "WindCode"])
            mapping = dict(info[["ID", "WindCode"]].itertuples(index=False, name=None))
            self._Mapping = mapping
            self._MappingInfo = info
            self._MappingID = dict2id({
                "class": type(self).__module__ + "." + type(self).__qualname__,
                "mapping": mapping,
                "unmapped_policy": self.Args.UnmappedPolicy,
            })


def _normalize_full(code: str) -> str:
    code = str(code).strip().upper()
    if code.endswith(".HK"):
        code = code[:-3]
    return str(int(code)) if code.isdigit() else code


def _normalize_base(code: str) -> str:
    code = str(code).strip().upper()
    if code.endswith(".HK"):
        code = code[:-3]
    code = code.split("!", 1)[0]
    return str(int(code)) if code.isdigit() else code


class JYDBWindDBHKStockIDMapping(IDMapping):
    """Map JYDB HK stock IDs to WindDB native HK stock IDs."""

    class __QS_ArgClass__(IDMapping.__QS_ArgClass__):
        Name: str = Field(default="JYDB-WindDB港股代码映射", frozen=True)
        AsOfDate: dt.date = Field(frozen=True, title="映射截止日期")

    def __init__(self, jydb, winddb, args: dict = {}, **kwargs):
        self._JYDB = jydb
        self._WindDB = winddb
        self._Mapping = None
        self._MappingInfo = None
        self._MappingID = None
        self._LoadLock = threading.Lock()
        super().__init__(args=args, **kwargs)

    @property
    def MappingID(self) -> str:
        self._load()
        return self._MappingID

    @property
    def MappingInfo(self) -> pd.DataFrame:
        """Return auditable mapped and unmapped JY security rows."""
        self._load()
        return self._MappingInfo.copy()

    def refresh(self):
        """Reload both source snapshots and recompute MappingID."""
        with self._LoadLock:
            self._Mapping = self._MappingInfo = self._MappingID = None
        self._load()
        self._QS_ID = None
        return self

    def _mapping(self) -> dict[str, str]:
        self._load()
        return self._Mapping

    @staticmethod
    def _clean(value):
        return None if pd.isna(value) or str(value).strip() == "" else str(value).strip()

    @classmethod
    def _isin_conflict(cls, jy_row, wind_row) -> bool:
        jy_isin = cls._clean(jy_row["jy_isin"])
        wind_isin = cls._clean(wind_row["wind_isin"])
        return (jy_isin is not None) and (wind_isin is not None) and (jy_isin != wind_isin)

    def _load_source(self):
        jy_prefix = self._JYDB.Args.TablePrefix
        wind_prefix = self._WindDB.Args.TablePrefix
        jy_sql = f"""SELECT InnerCode, SecuCode, ISIN, ListedDate, DelistingDate,
            SecuCategory, EngNameAbbr
        FROM {jy_prefix}HK_SecuMain
        WHERE SecuMarket=72 AND SecuCategory IN (3, 51, 53, 55, 78)
          AND ListedDate<='{self.Args.AsOfDate:%Y-%m-%d}'
        ORDER BY SecuCode, InnerCode"""
        wind_sql = f"""SELECT s_info_windcode, s_info_code, s_info_isincode,
            s_info_listdate, s_info_delistdate, s_info_name_eng
        FROM {wind_prefix}HKShareDescription
        WHERE s_info_windcode IS NOT NULL
        ORDER BY s_info_windcode"""
        jy = pd.DataFrame(self._JYDB.fetchall(jy_sql), columns=[
            "jy_innercode", "jy_secucode", "jy_isin", "jy_listeddate",
            "jy_delistingdate", "jy_secucategory", "jy_ename",
        ])
        wind = pd.DataFrame(self._WindDB.fetchall(wind_sql), columns=[
            "windcode", "wind_code", "wind_isin", "wind_listeddate",
            "wind_delistingdate", "wind_ename",
        ])
        for frame, columns in (
            (jy, ["jy_listeddate", "jy_delistingdate"]),
            (wind, ["wind_listeddate", "wind_delistingdate"]),
        ):
            for column in columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
        jy["full_code"] = jy["jy_secucode"].map(_normalize_full)
        jy["base_code"] = jy["jy_secucode"].map(_normalize_base)
        wind["full_code"] = wind["wind_code"].map(_normalize_full)
        wind["base_code"] = wind["wind_code"].map(_normalize_base)
        return jy, wind

    def _load(self):
        if self._Mapping is not None:
            return
        with self._LoadLock:
            if self._Mapping is not None:
                return
            jy, wind = self._load_source()
            matched = {}

            def choose(jy_index, candidates, method, confidence):
                candidates = candidates.drop_duplicates("windcode")
                if candidates.shape[0] != 1:
                    return False
                jy_row, wind_row = jy.loc[jy_index], candidates.iloc[0]
                if self._isin_conflict(jy_row, wind_row):
                    return False
                matched[jy_index] = (wind_row["windcode"], method, confidence)
                return True

            for index, row in jy.iterrows():
                isin = self._clean(row["jy_isin"])
                if isin is None:
                    continue
                choose(index, wind[(wind["wind_isin"] == isin) &
                                   (wind["base_code"] == row["base_code"])], "ISIN_BASE", "HIGH")

            for index, row in jy.loc[~jy.index.isin(matched)].iterrows():
                isin = self._clean(row["jy_isin"])
                if isin is None:
                    continue
                candidates = wind[wind["wind_isin"] == isin]
                if candidates.empty:
                    continue
                jy_name = self._clean(row["jy_ename"])
                wind_names = candidates["wind_ename"].map(self._clean)
                tiers = [
                    candidates[(candidates["wind_listeddate"] == row["jy_listeddate"]) &
                               (wind_names == jy_name)],
                    candidates[candidates["wind_listeddate"] == row["jy_listeddate"]],
                    candidates,
                ]
                for tier in tiers:
                    if choose(index, tier, "ISIN_MIGRATION", "HIGH"):
                        break

            for index, row in jy.loc[~jy.index.isin(matched)].iterrows():
                choose(index, wind[wind["full_code"] == row["full_code"]], "FULL_CODE", "HIGH")

            for index, row in jy.loc[~jy.index.isin(matched)].iterrows():
                base = wind[wind["base_code"] == row["base_code"]]
                same_delist = base["wind_delistingdate"] == row["jy_delistingdate"]
                if pd.isna(row["jy_delistingdate"]):
                    same_delist = base["wind_delistingdate"].isna()
                exact = base[(base["wind_listeddate"] == row["jy_listeddate"]) & same_delist]
                if choose(index, exact, "BASE_LIST_DELIST", "MEDIUM"):
                    continue
                choose(index, base[base["wind_listeddate"] == row["jy_listeddate"]], "BASE_LIST", "MEDIUM")

            info = jy.copy()
            info["windcode"] = [matched.get(i, (None, None, None))[0] for i in info.index]
            info["match_method"] = [matched.get(i, (None, None, None))[1] for i in info.index]
            info["confidence"] = [matched.get(i, (None, None, None))[2] for i in info.index]
            info["match_status"] = info["windcode"].notna().map({True: "MAPPED", False: "UNMAPPED"})
            info["external_id"] = info["jy_secucode"].astype(str) + ".HK"
            info["unmapped_reason"] = None
            for index, row in info[info["windcode"].isna()].iterrows():
                full = wind[wind["full_code"] == row["full_code"]]
                base = wind[wind["base_code"] == row["base_code"]]
                if any(self._isin_conflict(row, candidate) for _, candidate in full.iterrows()):
                    reason = "ISIN_CONFLICT"
                elif base.shape[0] > 1:
                    reason = "AMBIGUOUS_CANDIDATES"
                elif row["jy_secucategory"] == 78:
                    reason = "TEMPORARY_SECURITY_NOT_RETAINED"
                elif base.empty:
                    reason = "NO_WIND_RECORD"
                else:
                    reason = "INSUFFICIENT_IDENTIFIERS"
                info.at[index, "unmapped_reason"] = reason

            mapping = dict(info.loc[
                info["windcode"].notna(), ["external_id", "windcode"]
            ].itertuples(index=False, name=None))
            self._Mapping = mapping
            self._MappingInfo = info
            self._MappingID = dict2id({
                "class": type(self).__module__ + "." + type(self).__qualname__,
                "as_of_date": self.Args.AsOfDate,
                "mapping": mapping,
                "unmapped_policy": self.Args.UnmappedPolicy,
            })


class JYDBWindDBFactorDB(IDMappingFactorDB):
    """Expose a WindDB factor database with JYDB HK stock IDs.

    Besides wrapping factor tables, this adapter converts IDs returned by
    WindDB-level convenience methods such as ``getStockID``. Non-HK security
    IDs are outside this mapping's domain and pass through unchanged.
    """

    def __init__(
        self,
        jydb,
        winddb,
        as_of_date: dt.date = None,
        mapping_args: dict = {},
        id_value_factors: dict[str, dict[str, Optional[str]]] = {},
        id_value_ambiguity: str = "raise",
        args: dict = {},
        **kwargs,
    ):
        if as_of_date is None:
            as_of_date = dt.date.today()
        mapping = JYDBWindDBHKStockIDMapping(
            jydb=jydb,
            winddb=winddb,
            args={"AsOfDate": as_of_date} | mapping_args,
            logger=kwargs.get("logger"),
        )
        mutual_fund_mapping = WindDBMutualFundIDMapping(
            winddb=winddb,
            logger=kwargs.get("logger"),
        )
        table_info = getattr(winddb, "_TableInfo", None)
        if not isinstance(table_info, pd.DataFrame) or "SecurityType" not in table_info.columns:
            raise __QS_Error__("WindDB 的 TableInfo 缺少 SecurityType 列，无法配置港股代码映射")
        mapping_by_security_type = {
            "港股": mapping,
            "公募基金": mutual_fund_mapping,
        }
        effective_security_type = table_info["SecurityType"].copy()
        for security_type, table_names in WINDDB_MANUAL_TABLES_BY_SECURITY_TYPE.items():
            for table_name in table_names:
                effective_security_type.loc[table_name] = security_type
        table_mappings = {}
        for security_type, id_mapping in mapping_by_security_type.items():
            table_names = effective_security_type.index[effective_security_type == security_type]
            table_mappings.update({name: id_mapping for name in table_names})
        configured_id_value_factors = {
            table_name: dict(factor_security_types)
            for table_name, factor_security_types in WINDDB_MANUAL_ID_VALUE_FACTORS.items()
        }
        configured_id_value_factors.update({
            table_name: dict(factor_security_types)
            for table_name, factor_security_types in id_value_factors.items()
        })
        id_value_mappings = {}
        for table_name, factor_security_types in configured_id_value_factors.items():
            table_value_mappings = {}
            for factor_name, security_type in factor_security_types.items():
                if security_type is None:
                    continue
                if security_type not in mapping_by_security_type:
                    raise __QS_Error__(
                        f"表 '{table_name}' 的字段 '{factor_name}' 配置了未知证券类型: {security_type}"
                    )
                table_value_mappings[factor_name] = mapping_by_security_type[security_type]
            id_value_mappings[table_name] = table_value_mappings
        config = FactorDBIDMappingConfig(
            Default=None,
            Tables=table_mappings,
            IDValueMappings=id_value_mappings,
            IDValueAmbiguity=id_value_ambiguity,
        )
        values = {"IDMappingConfig": config} | args
        self._JYDB = jydb
        self._HKStockIDMapping = mapping
        self._MutualFundIDMapping = mutual_fund_mapping
        super().__init__(source_fdb=winddb, args=values, **kwargs)

    @property
    def JYDB(self):
        return self._JYDB

    @property
    def WindDB(self):
        return self.SourceFDB

    def connect(self):
        self._JYDB.connect()
        return super().connect()

    @property
    def IDMapping(self) -> JYDBWindDBHKStockIDMapping:
        return self._HKStockIDMapping

    @property
    def MutualFundIDMapping(self) -> WindDBMutualFundIDMapping:
        return self._MutualFundIDMapping

    def _restore_ids(self, native_ids):
        mapping = self.IDMapping._mapping()
        reverse = {}
        for external_id, native_id in mapping.items():
            reverse.setdefault(native_id, []).append(external_id)
        result, missing = [], []
        for native_id in native_ids:
            external_ids = reverse.get(native_id)
            if external_ids:
                result.extend(external_ids)
            elif not str(native_id).upper().endswith(".HK"):
                result.append(native_id)
            elif self.IDMapping.Args.UnmappedPolicy == "passthrough":
                result.append(native_id)
            elif self.IDMapping.Args.UnmappedPolicy == "raise":
                missing.append(native_id)
        if missing:
            sample = ", ".join(map(str, missing[:10]))
            suffix = " ..." if len(missing) > 10 else ""
            raise __QS_Error__(f"ID映射 '{self.IDMapping.Args.Name}' 无法反向映射 {len(missing)} 个ID: {sample}{suffix}")
        return result

    def getStockID(self, *args, **kwargs):
        return self._restore_ids(self.SourceFDB.getStockID(*args, **kwargs))

    def getMutualFundID(self, *args, **kwargs):
        return self._restore_ids(self.SourceFDB.getMutualFundID(*args, **kwargs))

    def getFutureID(self, *args, **kwargs):
        return self._restore_ids(self.SourceFDB.getFutureID(*args, **kwargs))

    def getOptionID(self, *args, **kwargs):
        return self._restore_ids(self.SourceFDB.getOptionID(*args, **kwargs))

    def getIndustryID(self, *args, **kwargs):
        return self._restore_ids(self.SourceFDB.getIndustryID(*args, **kwargs))

    def getTradeDay(self, *args, **kwargs):
        return self.SourceFDB.getTradeDay(*args, **kwargs)

    def getFutureCode(self, *args, **kwargs):
        return self.SourceFDB.getFutureCode(*args, **kwargs)

    def getIndustryInfo(self, *args, **kwargs):
        return self.SourceFDB.getIndustryInfo(*args, **kwargs)

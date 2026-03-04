# -*- coding: utf-8 -*-
import traceback
import datetime as dt
from typing import Literal, List, Dict, Optional

from pydantic import Field

from QuantStudio.Core import QSArgs, __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB


class FactorDefInput(QSArgs):
    Debug: bool = Field(default=False, title="调试环境", frozen=True)
    FDB: Dict[str, FactorDB] = Field(default={}, title="可用因子库")
    ModelArgs: Dict = Field(default={}, title="模型参数")
    DTs: List[dt.datetime] = Field(default=[], title="计算时点")
    DTRuler: List[dt.datetime] = Field(default=[], title="时点标尺")
    IDs: List[str] = Field(default=[], title="ID序列")
    SectionIDs: List[str] = Field(default=[], title="截面ID")
    TDB: Optional[WritableFactorDB] = Field(default=None, title="写入因子库")
    ProxyDB: Optional[FactorDB] = Field(default=None, title="代理因子库")
    ProxyTableMapping: Dict[str, str] = Field(default={}, title="代理表映射")

# 因子定义对象
class FactorDef(QSArgs):
    FactorList: List[Factor] = Field(title="因子列表")
    TargetTable: str = Field(title="因子表")
    IDType: str = Field(title="ID类型")
    DefaultStartDT: dt.datetime = Field(default=dt.datetime(2002, 1, 1), title="默认起始日")
    MaxLookBack: int = Field(default=365, title="最大回溯期")
    DTType: Literal["自定义", "交易日", "自然日"] = Field(default="自定义", title="时点类型")
    Freq: str = Field(default="1d", title="时点频率")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述信息")
    FDI: Optional[FactorDefInput] = Field(default=None, title="因子定义入参")

    @property
    def FactorNames(self):
        return [iFactor._QSArgs.Name for iFactor in self.FactorList]
    
    def getProxyFactor(self, factor_name: Optional[str]=None, factor_id:Optional[str]=None):
        if (self.FDI is None) or (self.FDI.ProxyDB is None): return None
        if factor_name is None and factor_id is None:
            self.Logger.warning(f"FactorDef.getProxyFactor: 表 '{self.TargetTable}' 的代理表 '{ProxyTable}' 在代理因子库 '{self.FDI.ProxyDB.Name}' 中不存在!")
            return None
        ProxyTable = self.FDI.ProxyTableMapping.get(self.TargetTable, self.TargetTable)
        if ProxyTable not in self.FDI.ProxyDB.TableNames:
            self.Logger.warning(f"FactorDef.getProxyFactor: 入参 factor_name, factor_id 同时为 None, 无法确定代理因子, 将返回 None")
            return None
        ProxyFT = self.FDI.ProxyDB.getTable(ProxyTable)
        if factor_id is not None:
            SourceFactorID = ProxyFT.getFactorMetaData(key="SourceFactorID")
            SourceFactorName = SourceFactorID[SourceFactorID==factor_id]
            if SourceFactorName.shape[0]==0:
                self.Logger.warning(f"FactorDef.getProxyFactor: 表 '{self.TargetTable}' 在代理因子库 '{self.FDI.ProxyDB.Name}' 中的代理表 '{ProxyTable}' 中不存在 SourceFactorID='{factor_id}' 的代理因子")
                return None
            SourceFactorNameList = SourceFactorName.index.tolist()
        else:
            SourceFactorNameList = ProxyFT.FactorNames
        if factor_name is not None:
            if factor_name in SourceFactorNameList:
                return ProxyFT.getFactor(factor_name)
            else:
                self.Logger.warning(f"FactorDef.getProxyFactor: 表 '{self.TargetTable}' 在代理因子库 '{self.FDI.ProxyDB.Name}' 中的代理表 '{ProxyTable}' 中不存在 SourceFactorID='{factor_id}', FactorName='{factor_name}' 的代理因子")
                return None
        else:
            if len(SourceFactorNameList)>1:
                self.Logger.warning(f"FactorDef.getProxyFactor: 表 '{self.TargetTable}' 在代理因子库 '{self.FDI.ProxyDB.Name}' 中的代理表 '{ProxyTable}' 中存在 SourceFactorID='{factor_id}' 的多个代理因子: {SourceFactorNameList}")
            return ProxyFT.getFactor(SourceFactorNameList[0])

    # 查找因子对象, def_path: 以/分割的因子查找路径, 比如 年化收益率/0/1/...， ...表示只在这层搜索，不查询该层的描述子
    def getFactor(self, factor_name: Optional[str]=None, def_path: str="...", factor_id: Optional[str]=None, only_one=True, use_proxy=True):
        if (factor_id is None) and (factor_name is None):
            raise __QS_Error__(f"入参 factor_id、factor_name 不可同时为 None")

        def _searchFactor(factors, factor_id, factor_name, recursive=True):
            Factors = []
            for iFactor in factors:
                if ((factor_id is None) or (iFactor.QSID == factor_id)) and ((factor_name is None) or (iFactor._QSArgs.Name == factor_name)):
                    Factors.append(iFactor)
                if recursive:
                    Factors += _searchFactor(iFactor.Descriptors, factor_id, factor_name)
            return Factors

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
                if use_proxy and (iProxyFactor := self.getProxyFactor(factor_name=iFactor.Name)) is not None: iFactor = iProxyFactor
                return (iFactor if only_one else [iFactor])
            elif LastPos in ("", "..."):
                Factors = _searchFactor(factors=iFactor.Descriptors, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
            else:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
        else:
            Factors = _searchFactor(factors=self.FactorList, factor_id=factor_id, factor_name=factor_name, recursive=(LastPos==""))
        if only_one:
            if (len(Factors) == 1) or ((len(Factors) > 1) and (factor_id is not None)):
                if use_proxy and (iProxyFactor := self.getProxyFactor(factor_name=Factors[0].Name)) is not None: return iProxyFactor
                else: return Factors[0]
            elif len(Factors) == 0:
                raise __QS_Error__(f"查找不到因子: Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}'")
            else:
                raise __QS_Error__(f"查找到的因子 (Name='{factor_name}', QSID='{factor_id}', def_path='{def_path}') 不止一个!")
        else:
            return [(iProxyFactor if use_proxy and (iProxyFactor := self.getProxyFactor(factor_name=iFactor.Name)) is not None else iFactor) for iFactor in Factors]

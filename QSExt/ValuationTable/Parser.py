# -*- coding: utf-8 -*-
import os
import re
import json
from collections import OrderedDict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
from traits.api import Instance, Callable, Float, File, Enum, Dict

from QuantStudio import __QS_Object__, __QS_Error__
from QSExt import __QS_MainPath__
from QSExt.ValuationTable import special_rule
from QSExt.ValuationTable.utils import find_date, checkLevel5VT


# 估值表数据解析，转换为标准格式
class ValuationTableParser(__QS_Object__):
    class __QS_ArgClass__(__QS_Object__.__QS_ArgClass__):
        SymbolInfo = Instance(pd.DataFrame, label="Symbol信息", arg_type="DataFrame", order=101)# DataFrame(columns=["symbol", "reg_code", "name", "abbr"])
        SymbolFunc = Callable(label="Symbol查询", arg_type="Function", order=102)# 输入 [product_id], 函数范围 DataFrame(index=[product_id], columns=["reg_code", "name", "abbr"])
        RuleFile = File(os.path.join(__QS_MainPath__, ""), label="规则文件", arg_type="File", order=103, mutable=False)
        # RuleName = Enum("自动判断", label="规则名称", arg_type="SingleOption", order=104, option_range=())
        RuleConfigFile = File(os.path.join(__QS_MainPath__, ""), label="规则配置文件", arg_type="File", order=105, mutable=False)
        AccountInfoFile = File(os.path.join(__QS_MainPath__, ""), label="科目文件", arg_type="File", order=106, mutable=False)
        # AccountSystem = Enum("自动判断", label="科目体系", arg_type="SingleOption", order=107, option_range=())
        MinAccountNameMatchRatio = Float(1, label="科目名最小相似度", arg_type="Float", order=108)
        ExternalInfo = Dict({}, label="外部信息", arg_type="Dict", order=109)

        def __QS_initArgs__(self, args={}):
            super().__QS_initArgs__(args=args)
            self.SymbolInfo = pd.DataFrame(columns=["symbol", "reg_code", "name", "abbr"])
            RuleFile = args.get("规则文件", self.RuleFile)
            if not os.path.isfile(RuleFile): raise __QS_Error__(f"找不到规则文件: {RuleFile}")
            with pd.ExcelFile(RuleFile, engine="openpyxl") as xls:
                Rules = ["自动判断"] + list(xls.sheet_names)
            self.add_trait("RuleName", Enum(*Rules, label="规则名称", arg_type="SingleOption", order=104, option_range=Rules))
            AccountInfoFile = args.get("科目文件", self.AccountInfoFile)
            if not os.path.isfile(AccountInfoFile):
                raise __QS_Error__(f"找不到科目文件: {AccountInfoFile}")
            with pd.ExcelFile(AccountInfoFile, engine="openpyxl") as xls:
                AccountSystems = ["自动判断"] + list(xls.sheet_names)
            self.add_trait("AccountSystem", Enum(*AccountSystems, label="科目体系", arg_type="SingleOption", order=107, option_range=AccountSystems))
            return

    def __init__(self, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self._RegCode2Symbol = {}# {reg_code: (symbol, reg_code, fund_name)}
        self._Name2Symbol = {}# {fund_name: (symbol, reg_code, fund_name)}
        self._QS_SourceLocation = None# 来源定位

        if os.path.isfile(self.Args["规则配置文件"]):
            with pd.ExcelFile(self.Args["规则配置文件"], engine="openpyxl") as xls:
                self._RuleConfig = pd.read_excel(xls, "解析规则", header=0, index_col=None)
                self._AccountConfig = pd.read_excel(xls, "科目规则", header=0, index_col=None)
                self._SymbolConfig = pd.read_excel(xls, "代码规则", header=0, index_col=None)
                self._SpecialRule = pd.read_excel(xls, "特殊处理", header=0, index_col=None)
            self._AccountConfig["symbol"] = self._AccountConfig["symbol"].astype(str)
            self._SymbolConfig["文件名"] = self._SymbolConfig["文件名"].apply(lambda s: re.compile(s))
            self._SymbolConfig["symbol"] = self._SymbolConfig["symbol"].astype(str)
            self._SpecialRule["symbol"] = self._SpecialRule["symbol"].astype(str)
        else:
            raise __QS_Error__(f"找不到规则配置文件: {self.Args['规则配置文件']}")
        self._AccountInfo = OrderedDict()
        with pd.ExcelFile(self.Args["科目文件"], engine="openpyxl") as xls:
            for iSystem in xls.sheet_names:
                self._AccountInfo[iSystem] = pd.read_excel(xls, iSystem, header=0, index_col=None)
                self._AccountInfo[iSystem]["account_code"] = self._AccountInfo[iSystem]["account_code"].atype(str)
                self._AccountInfo[iSystem]["level"] = self._AccountInfo[iSystem]["level"].astype(int)

    # 自动判断适用规则
    def matchRuleName(self, xls, args={}):
        if not self._MatchedRuleNames:
            Rslt = pd.DataFrame(index=list(self._Rules), columns=["if_applicative", "rule_priority"])
            for iRuleName, iRule in self._Rules.items():
                iRulePriority = iRule[iRule["条目"]=="rule_priority"]
                Rslt.loc[iRuleName, "rule_priority"] = (0 if iRulePriority.empty else int(iRulePriority["解析规则"].iloc[0]))
                iApplicative = iRule[iRule["条目"]=="if_applicative"]
                if iApplicative.empty:
                    Rslt.loc[iRuleName, "if_applicative"] = False
                else:
                    try:
                        rule_fun = eval(iApplicative["解析规则"].iloc[0])
                        Rslt.loc[iRuleName, "if_applicative"] = bool(rule_fun(xls))
                    except:
                        Rslt.loc[iRuleName, "if_applicative"] = False
            Rslt = Rslt[Rslt["if_applicative"]].sort_values(["rule_priority"], ascending=True)
            self._MatchedRuleNames = ("_QS_Default" if Rslt.empty else Rslt.index[-1])
        return self._MatchedRuleNames

    # 获取规则名称
    def getRuleName(self, xls, file_name=None, reg_code=None, fund_name=None, args={}):
        if args.get("规则名称", self.Args["规则名称"])=="自动判断":
            RuleName = self._RuleConfig[(self._RuleConfig["文件名"]==file_name) | (self._RuleConfig["备案编码"]==reg_code) | (self._RuleConfig["产品名称"]==fund_name)]
            if RuleName.empty:
                MatchedRuleName = self.matchRuleName(xls, args=args)
                return (list(self._Rules)[0] if MatchedRuleName=="_QS_Default" else MatchedRuleName)
            else:
                return RuleName["规则"].iloc[0]
        else:
            return args.get("规则名称", self.Args["规则名称"])

    # 获取科目体系名称
    def getAccountSystem(self, xls, file_name=None, reg_code=None, fund_name=None, symbol=None, args={}):
        AccountSystem = args.get("科目体系", self.Args["科目体系"])
        if AccountSystem=="自动判断":
            Rule = self._AccountConfig["规则"][self._AccountConfig["symbol"]==symbol]
            if not Rule.empty:
                AccountSystem = Rule.iloc[0]
            else:
                Rule = self._Rule[self._Rule["条目"]=="account_system"]
                if Rule.empty: Rule = self._DefaultRule[self._DefaultRule["条目"]=="account_system"]
                AccountSystem = (list(self._AccountConfig)[0] if Rule.empty else Rule["解析规则"].iloc[0])
        return AccountSystem

    # 定位单元格
    # 固定位置: 以给定的行号和列号进行定位单元格;
    # 完全匹配: 在给定的列表中使用给定的关键字（定位规则列）以完全相等的方式去匹配，以匹配成功的第一个位置作为行号;
    # 包含关键字: 在给定的列表中使用给定的关键字（定位规则列）以是否包含的方式去匹配，以匹配成功的第一个位置作为行号;
    # 匹配正则表达式: 在给定的列中使用给定的正则表达式（定位规则列）去匹配，以匹配成功的第一个位置作为行号；
    # 包含正则表达式: 在给定的列表中使用给定的正则表达式（定位规则列）以是否包含的方式去匹配，以匹配成功的第一个位置作为行号；
    # lambda:
    # series_lambda:
    def locateCell(self, xls, rule_type, rule, row_idx=None, col_idx=None, if_multi="first", args={}):
        if pd.notnull(row_idx) and pd.isnull(col_idx):
            row_idx = int(row_idx)
            s = xls.loc[row_idx]
        elif pd.isnull(row_idx) and pd.notnull(col_idx):
            col_idx = int(col_idx)
            s = xls.loc[:, col_idx]
        elif pd.isnull(row_idx) and pd.isnull(col_idx):
            s = xls.stack()
        elif rule_type=="固定位置":
            return int(row_idx), int(col_idx)
        else:
            raise __QS_Error__(f"不兼容的规则({rule_type}): {rule}, row_idx={row_idx}, col_idx={col_idx}")
        if rule_type=="完全匹配":
            Mask = (s==rule)
        elif rule_type=="包含关键字":
            Mask = s.str.contains(rule, regex=False).fillna(False)
        elif rule_type=="匹配正则表达式":
            Mask = s.str.fullmatch(rule).fillna(False)
        elif rule_type=="包含正则表达式":
            Mask = s.str.contains(rule, regex=True).fillna(False)
        elif rule_type=="lambda":
            rule_fun = eval(rule)
            Mask = s.apply(rule_fun).fillna(False)
        elif rule_type=="series_lambda":
            rule_fun = eval(rule)
            Mask = rule_fun(s).fillna(False)
        else:
            raise __QS_Error__(f"不支持的定位规则({rule_type}): {rule}")
        if not Mask.any():
            target_idx = None
        elif if_multi=="first":
            target_idx = s[Mask].index[0]
        elif if_multi=="last":
            target_idx = s[Mask].index[-1]
        elif if_multi=="all":
            target_idx = s[Mask].index.tolist()
        else:
            raise __QS_Error__(f"不支持的多重定位选项({if_multi}): {if_multi}")
        if pd.notnull(row_idx) and pd.isnull(col_idx):
            return (row_idx, col_idx)
        elif pd.isnull(row_idx) and pd.notnull(col_idx):
            return (target_idx, col_idx)
        else:
            return target_idx

    # 解析值
    def parseValue(self, v, rule_type, rule, unit, args={}):
        if isinstance(v, pd.Series):
            if rule_type=="系统规则":
                try:
                    Rslt = v.astype(float)
                except:
                    if pd.isnull(unit) and v.dropna().str.contains("%").all():
                        unit = "%"
                    Rslt = v.str.replace(",|\t|\n|\r|%| ", "", regex=True)
                    Rslt = Rslt.where(Rslt!="", np.nan).astype(float)
            elif rule_type=="str":
                Rslt = v.astype(str)
            elif rule_type=="float":
                Rslt = v.astype(float)
            elif rule_type=="正则表达式":
                Rslt = v.str.findall(rule).apply(lambda s: s[0] if s else None)
            elif rule_type=="lambda":
                rule_fun = eval(rule)
                Rslt = v.apply(rule_fun)
            else:
                raise __QS_Error__(f"不支持的解析规则({rule_type}): {rule}")
        else:
            if rule_type=="系统规则":
                if pd.isnull(unit) and ("%" in str(v)):
                    unit = "%"
                Rslt = float(re.sub(",|\t|\n|\r|%| ", str(v)))
            elif rule_type=="str":
                Rslt = str(v)
            elif rule_type=="float":
                Rslt = float(v)
            elif rule_type=="正则表达式":
                s = re.findall(rule, v)
                Rslt = (s[0] if s else None)
            elif rule_type=="lambda":
                rule_fun = eval(rule)
                Rslt = rule_fun(v)
            else:
                raise __QS_Error__(f"不支持的解析规则({rule_type}): {rule}")
        if pd.isnull(unit):
            return Rslt
        elif unit=="%":
            return Rslt / 100
        else:
            raise __QS_Error__(f"不支持的数据单位: {unit}")

    # 解析条目
    def parseItem(self, item_name, xls, file_name, sys_rule=None, args={}):
        Rule = self._Rule[self._Rule["条目"]==item_name]
        if Rule.empty: Rule = self._DefaultRule[self._DefaultRule["条目"]==item_name]
        for iIdx, iRule in Rule.iterrows():
            if iRule["定位规则类型"]=="文件名":
                iValue = file_name
                if iRule["解析规则类型"]=="系统规则":
                    iRslt = (sys_rule(iValue, args=args) if sys_rule is not None else None)
                else:
                    iRslt = self.parseValue(iValue, rule_type=iRule["解析规则类型"], rule=iRule["解析规则"], unit=iRule["单位"], args=args)
            else:
                iRowIdx, iColIdx = self.locateCell(xls, rule_type=iRule["定位规则类型"], rule=iRule["定位规则"], row_idx=iRule["行号"], col_idx=iRule["列号"])
                if (iRowIdx is not None) and (iColIdx is not None):
                    iValue = xls.loc[iRowIdx, iColIdx]
                    if iRule["解析规则类型"]=="系统规则":
                        iRslt = (sys_rule(iValue, args=args) if sys_rule is not None else None)
                    else:
                        iRslt = self.parseValue(iValue, rule_type=iRule["解析规则类型"], rule=iRule["解析规则"],unit=iRule["单位"], args=args)
                else:
                    if iRule["失败处理"]=="warning":
                        Msg = f"条目({item_name})定位失败, 相应的规则为: {iRule}"
                        self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "parse_rule_failed", "source": self._QS_SourceLocation})
                    elif iRule["失败处理"]=="error":
                        raise __QS_Error__(f"条目({item_name})定位失败, 相应的规则为: {iRule}")
                    continue
            if pd.notnull(iRslt):
                return iRslt
            else:
                if iRule["失败处理"]=="warning":
                    Msg = f"条目({item_name})解析失败, 待解析的值: {iValue}, 相应的规则为: {iRule}"
                    self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "parse_rule_failed", "source": self._QS_SourceLocation})
                elif iRule["失败处理"]=="error":
                    raise __QS_Error__(f"条目({item_name})解析失败, 待解析的值: {iValue}, 相应的规则为: {iRule}")
        return None

    # 系统规则下的日期解析方法
    def sysparseDateTime(self, v, args={}):
        return pd.to_datetime(find_date(v))

    # 解析表头
    def parseHeader(self, xls, header_idx, rule, ignore_error=False, args={}):
        Header = pd.Series(None, index=xls.columns)
        OldData = xls.loc[int(header_idx)].copy()
        xls.loc[int(header_idx)] = OldData.fillna(method="pad")
        for iItem in sorted(rule["条目"].unique()):
            iRule = rule[rule["条目"]==iItem]
            for ijIdx, ijRule in iRule.iterrows():
                ijRowIdx, ijColIdx = self.locateCell(xls, ijRule["定位规则类型"], ijRule["定位规则"], row_idx=header_idx, col_idx=ijRule["列号"], if_multi="all", args=args)
                if ijColIdx:
                    Header.loc[ijColIdx] = iItem
                    break
                elif ignore_error:
                    continue
                elif ijRule["失败处理"]=="error":
                    raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败")
                elif ijRule["失败处理"]=="warning":
                    Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败"
                    self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "locate_rule_failed", "source": self._QS_SourceLocation})
        xls.loc[int(header_idx)] = OldData
        return Header

    # 定位并解析表头, 返回: (表头, 表头行, 数据首行)
    def locparseHeader(self, xls, header_idx, rule, ignore_error=False, args={}):
        Header = pd.Series(None, index=xls.columns)
        OldData = xls.loc[int(header_idx)].copy()
        xls.loc[int(header_idx)] = OldData.fillna(method="pad")
        for iItem in sorted(rule["条目"].unique()):
            iRule = rule[rule["条目"]==iItem]
            for ijIdx, ijRule in iRule.iterrows():
                ijRowIdx, ijColIdx = self.locateCell(xls, ijRule["定位规则类型"], ijRule["定位规则"], row_idx=header_idx, col_idx=ijRule["列号"], if_multi="all", args=args)
                if ijColIdx:
                    Header.loc[ijColIdx] = iItem
                    break
                elif ignore_error:
                    continue
                elif ijRule["失败处理"]=="error":
                    raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败")
                elif ijRule["失败处理"]=="warning":
                    Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败"
                    self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "locate_rule_failed", "source": self._QS_SourceLocation})
            xls.loc[int(header_idx)] = OldData
            return Header

    # 定位并解析表头，返回: (表头, 表头行, 数据首行)
    def locparseHeader(self, xls, args={}):
        Rule = self._Rule[self._Rule["条目"]=="header_idx"]
        if Rule.empty: Rule = self._DefaultRule[self._DefaultRule["条目"]=="header_idx"]
        for iIdx, iRule in Rule.iterrows():
            header_idx, _ = self.locateCell(xls, rule_type=iRule["定位规则类型"], rule=iRule["定位规则"], row_idx=iRule["行号"], col_idx=iRule["列号"], if_multi="all")
            if header_idx is not None: break
        if not header_idx:
            raise __QS_Error__(f"{self._QS_SourceLocation}: 无法定位表头行")
        Rule, DefaultRule = self._Rule[self._Rule["条目类型"]=="数据列"], self._DefaultRule[self._DefaultRule["条目类型"]=="数据列"]
        Rule = pd.concat([Rule, DefaultRule[~DefaultRule["条目"].isin(Rule["条目"].tolist())]], axis=0, ignore_index=True)
        if len(header_idx)==1:
            header_idx, first_idx = header_idx[0], header_idx[0] + 1
            header = self.parseHeader(xls, header_idx, Rule, args=args)
            first_idx = xls[0].loc[first_idx:].first_valid_index()
        else:# 有多个疑似表头行, 每个表头行尝试解析表头, 选取能解析出表头最多的行
            AllItems = set(Rule["条目"].unique())
            Headers = {}
            ColCnt = pd.Series(index=header_idx)
            for iIdx in header_idx:
                iHeader = self.parseHeader(xls, iIdx, Rule, ignore_error=True, args=args)
                iCnt = len(AllItems.difference(iHeader[iHeader.notnull()].values))
                if iCnt==0:
                    first_idx = xls[0].loc[header_idx[-1] + 1:].first_valid_index()
                    header, header_idx = iHeader, iIdx
                    break
                ColCnt[iIdx] = iCnt
                Headers[iIdx] = iHeader
            else:
                first_idx = xls[0].loc[header_idx[-1] + 1:].first_valid_index()
                header_idx = ColCnt.idxmin()
                header = Headers[header_idx]
                MissingItems = AllItems.difference(header[header.notnull()].values)
                ErrorItems = Rule[(Rule["失败处理"]=="error") & Rule["条目"].isin(MissingItems)]["条目"].unique()
                if ErrorItems.shape[0]>0:
                    raise __QS_Error__(f"{self._QS_SourceLocation}: 无法解析出的表头 {sorted(ErrorItems)}")
                WarnItems = Rule[(Rule["失败处理"]=="warning") & Rule["条目"].isin(MissingItems)]["条目"].unique()
                if WarnItems.shape[0]>0:
                    raise __QS_Error__(f"{self._QS_SourceLocation}: 无法解析出的表头 {sorted(WarnItems)}")
        # 根据规则解析数据首行
        Rule = self._Rule[self._Rule["条目"]=="first_idx"]
        if Rule.empty: Rule = self._DefaultRule[self._DefaultRule["条目"]=="first_idx"]
        if not Rule.empty:
            for iIdx, iRule in Rule.iterrows():
                first_idx, _ = self.locateCell(xls, rule_type=iRule["定位规则类型"], rule=iRule["定位规则"], row_idx=iRule["行号"], col_idx=iRule["列号"], if_multi="first")
                if first_idx is not None: break
        if first_idx is None:
            raise __QS_Error__(f"{self._QS_SourceLocation}: 无法定位数据首行")
        return header, header_idx, first_idx

    # 定位明细结尾
    def locateTail(self, xls, first_idx, args={}):
        Rule = self._Rule[self._Rule["条目"]=="last_idx"]
        if Rule.empty: Rule = self._DefaultRule[self._DefaultRule["条目"]=="last_idx"]
        for iIdx, iRule in Rule.iterrows():
            last_idx, _ = self.locateCell(xls, rule_type=iRule["定位规则类型"], rule=iRule["定位规则"], row_idx=iRule["行号"], col_idx=iRule["列号"], if_multi="first")
            if last_idx is not None: break
        if last_idx is None:
            ifirst_idx = xls[0].loc[first_idx:].first_valid_index()
            last_idx = xls.index[ifirst_idx:][xls[0].loc[ifirst_idx:].isnull()][0]
        return last_idx

    # 解析估值表的类别，返回: 1级, 2级, 3级, 4级
    def parseAccountType(self, df, file_name):
        if df.empty: return None
        # 从数据中解析估值表类型
        MaxLevel = df["account_level"].dropna().max()
        if pd.notnull(MaxLevel):
            return f"{int(MaxLevel)}级"
        # 从名称中解析估值类型
        if re.findall("4级|四级", file_name):
            return "4级"
        elif re.findall("3级|三级", file_name):
            return "3级"
        elif re.findall("2级|二级", file_name):
            return "2级"
        elif re.findall("1级|一级", file_name):
            return "1级"
        else:
            return None

    # 解析衍生列
    def parseDerivativeCol(self, df, args={}):
        Rule, DefaultRule = self._Rule[self._Rule["条目类型"] == "衍生列"], self._DefaultRule[self._DefaultRule["条目类型"] == "衍生列"]
        Rule = pd.concat([Rule, DefaultRule[~DefaultRule["条目"].isin(Rule["条目"].tolist())]], axis=0, ignore_index=True)
        AllItems = sorted(Rule["条目"].unique())
        df = df.copy()
        for iItem in AllItems:
            iRule = Rule[Rule["条目"] == iItem].groupby(["解析规则类型", "解析规则"], as_index=False, dropna=False).apply(lambda df: df.iloc[-1])
            for ijIdx, ijRule in iRule.iterrows():
                if ijRule["定位规则类型"]=="数据列":
                    if ijRule["解析规则类型"]!="lambda":
                        raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 的解析规则不能为 '{ijRule['解析规则类型']}', 只能为 'lambda'")
                    try:
                        iSourceCols = ijRule["定位规则"].split(",")
                        rule_fun = eval(ijRule["解析规则"])
                        if len(iSourceCols)==1:
                            df[iItem] = df.loc[:, iSourceCols[0]].apply(rule_fun)
                        else:
                            df[iItem] = df.loc[:, iSourceCols].apply(rule_fun, axis=1)
                    except Exception as e:
                        if ijRule["失败处理"]=="warning":
                            Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}"
                            self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "parse_rule_failed", "source": self._QS_SourceLocation})
                        elif ijRule["失败处理"]=="error":
                            raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}")
                    else:
                        break
                else:
                    raise __QS_Error__(f"{self._QS_SourceLocation} 对于衍生列 {iItem} 的解析规则不能为 '{ijRule['解析规则类型']}', 只能为 'lambda'")
        df["account_type"] = self.parseAccountType(df, self._QS_SourceLocation)
        df["asset_type"] = None# TODO
        return df

    def adjustDuplicatedHeader(self, df: pd.DataFrame) -> pd.DataFrame:
        Cols = pd.Series(df.columns.tolist())
        DupCols = sorted(df.columns[df.columns.duplicated()].dropna().unique())
        for iCol in DupCols:
            idf = df.loc[:, iCol].copy()
            try:
                idf = idf.astype(float)
            except:
                iIdx = np.argmax(idf.notnull().sum().values)
            else:
                iIdx = np.argmax((idf.notnull() & (idf!=0)).sum().values)
            iOldIdx = Cols[Cols==iCol].index[iIdx]
            Cols[Cols==iCol] = iCol + "_dup"
            Cols.iloc[iOldIdx] = iCol
            df.iloc[:, iOldIdx] = idf.iloc[:, iIdx]
        df.columns = Cols.tolist()
        return df

    # 删除重复的表头，保留缺失和取值为0的数量最少得列
    def deleteDuplicatedHeader(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.adjustDuplicatedHeader(df)
        KeepMask = (~ df.columns.str.contains("_dup"))
        df = df.loc[:, KeepMask]
        return df, KeepMask

    def parseDetail(self, df, args={}):
        Rule, DefaultRule = self._Rule[self._Rule["条目类型"] == "数据列"], self._DefaultRule[self._DefaultRule["条目类型"] == "数据列"]
        Rule = pd.concat([Rule, DefaultRule[~DefaultRule["条目"].isin(Rule["条目"].tolist())]], axis=0, ignore_index=True)
        AllItems = sorted(Rule["条目"].unique())
        df = df.reindex(columns=AllItems)
        for iItem in AllItems:
            iRule = Rule[Rule["条目"]==iItem].groupby(["解析规则类型", "解析规则"], as_index=False, dropna=False).apply(lambda df: df.iloc[-1])
            for ijIdx, ijRule in iRule.iterrows():
                try:
                    df[iItem] = self.parseValue(df[iItem], rule_type=ijRule["解析规则类型"], rule=ijRule["解析规则"], unit=ijRule["单位"], args=args)
                except Exception as e:
                    if ijRule["失败处理"]=="warning":
                        Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}"
                        self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "parse_rule_failed", "source": self._QS_SourceLocation})
                    elif ijRule["失败处理"]=="error":
                        raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}")
                else:
                    break
            else:
                if (iRule["失败处理"]=="error").any():
                    raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则失败!")
                else:
                    df[iItem] = None
        return df

    def parseSummary(self, xls, header, args={}):
        Rule, DefaultRule = self._Rule[self._Rule["条目类型"] == "汇总项"], self._DefaultRule[self._DefaultRule["条目类型"] == "汇总项"]
        Rule = pd.concat([Rule, DefaultRule[~DefaultRule["条目"].isin(Rule["条目"].tolist())]], axis=0, ignore_index=True)
        AllItems = sorted(Rule["条目"].unique())
        summary = {}
        for iItem in AllItems:
            iRule = Rule[Rule["条目"]==iItem]
            for ijIdx, ijRule in iRule.iterrows():
                try:
                    ijRowIdx, ijColIdx = self.locateCell(xls, rule_type=ijRule["定位规则类型"], rule=ijRule["定位规则"], row_idx=None, col_idx=0, if_multi="first", args=args)
                    if pd.isnull(ijRowIdx):
                        if ijRule["失败处理"]=="warning":
                            Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败"
                            self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "locate_rule_failed", "source": self._QS_SourceLocation})
                        elif ijRule["失败处理"]=="error":
                            raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用定位规则({ijRule['定位规则类型']}: {ijRule['定位规则']}) 定位失败")
                        continue
                    ijColIdx = header[header==ijRule["列号"]]
                    if ijColIdx.empty:
                        ijColIdx = int(ijRule["列号"])
                    else:
                        ijColIdx = int(ijColIdx.index[-1])
                    ijValue = xls.loc[ijRowIdx, ijColIdx]
                    summary[iItem] = self.parseValue(ijValue, rule_type=ijRule["解析规则类型"], rule=ijRule["解析规则"], unit=ijRule["单位"], args=args)
                except Exception as e:
                    if ijRule["失败处理"] == "warning":
                        Msg = f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}"
                        self._QS_Logger.warning({"msg": Msg, "alarm": False, "name": "parse_rule_failed", "source": self._QS_SourceLocation})
                    elif ijRule["失败处理"] == "error":
                        raise __QS_Error__(f"{self._QS_SourceLocation} 对于条目 {iItem} 使用解析规则({ijRule['解析规则类型']}: {ijRule['解析规则']}) 解析失败: {e}")
                else:
                    break
        return pd.Series(summary)

    # 增加标准科目名称列并检查问题
    # account_info: DataFrame(columns=["account_code", "account_name", ...])
    def addStdAccountName(self, df, account_info, args={}):
        df = pd.merge(df, account_info.loc[:, ["account_code", "account_name", "别名"]], how="left", left_on=["account_code"], right_on=["account_code"], suffixes=("", "_std"))
        def _tmp(s):
            Name, NameStd, Alias = s["account_name"], s["account_name_std"], s["别名"]
            if isinstance(Name, str) and isinstance(NameStd, str):
                if isinstance(Alias, str) and (Name in Alias): return 1
                Name, NameStd = re.sub(",|\t|\n|\r|%| |-|_", "", Name), re.sub(",|\t|\n|\r|%| |-|_", "", NameStd)
                NameSet, NameStdSet = set(Name), set(NameStd)
                if NameSet.issubset(NameStdSet) or NameStdSet.issubset(NameSet): return 1
                return SequenceMatcher(None, Name, NameStd, autojunk=False).ratio()
            else:
                return 1
        df["account_name_match_ratio"] = df.apply(_tmp, axis=1)
        df = df.groupby(by=["account_code"], as_index=False).apply(lambda df: df[df["account_name_match_ratio"]==df["account_name_match_ratio"].max()].iloc[[0]]).reset_index(drop=True)
        # 检查科目代码
        df = pd.merge(df, df.set_index(["account_code"]).loc[:, ["account_name_std"]], how="left", left_on=["parent_code"], right_index=True, suffixes=("", "_p"))
        Tmp = pd.merge(df, account_info.set_index(["account_code", "account_name"]).loc[:, ["终解科目"]], how="left", left_on=["parent_code", "account_name_std_p"], right_index=True, suffixes=("", "_y"))
        NotKnownCodes = Tmp[(Tmp["account_level"]<4) & Tmp["account_name_std"].isnull() & (Tmp["终解科目"]!="是")]
        if not NotKnownCodes.empty:
            Msg = f"估值文件 {self._QS_SourceLocation} 中无法识别的科目代码: {NotKnownCodes.loc[:, ['account_code', 'account_name']]}"
            self._QS_Logger.warning({"msg": Msg, "alarm": True, "name": "not_known_code", "source": self._QS_SourceLocation})
        # 检查科目名称
        MinRatio = args.get("科目名最小相似度", self._QSArgs.MinAccountNameMatchRatio)
        AccountName = Tmp[Tmp["account_name_std"].notnull() & (Tmp["account_name_match_ratio"] < MinRatio) & (Tmp["终解科目"]!="是")]
        if not AccountName.empty:
            Msg = f"估值文件 {self._QS_SourceLocation} 中无法匹配的科目名称: {AccountName.loc[:, ['account_code', 'account_name', 'account_name_std', 'account_name_match_ratio']]}"
            self._QS_Logger.warning({"msg": Msg, "alarm": True, "name": "unmatched_account_name", "source": self._QS_SourceLocation})
        df["account_name_std"] = df["account_name_std"].where(df["account_name_std"].notnull(), None)
        return df.drop(labels=["account_name_match_ratio", "别名", "account_name_std_p"], axis=1)

    # 校正数据正确性和一致性
    def correctData(self, detail, summary):
        # 检查 weight_in_nv 的单位是否可靠
        Mask = (detail["account_level"]==1)
        TotalWeight = detail[Mask]["weight_in_nv"].sum()
        if TotalWeight > 90:# weight_in_nv 的单位可能是 %
            detail["weight_in_nv"] = detail["weight_in_nv"] / 100
            Msg = f"估值文件 {self._QS_SourceLocation} 中 weight_in_nv 列的单位根据推测应该是 %, 需要除以 100"
            self._QS_Logger.warning({"msg": Msg, "alarm": True, "name": "data_correction", "source": self._QS_SourceLocation})
        elif TotalWeight < 0.09:# weight_in_nv 可能多除了 100
            detail["weight_in_nv"] = detail["weight_in_nv"] * 100
            Msg = f"估值文件 {self._QS_SourceLocation} 中 weight_in_nv 列的值根据推测过于偏低，需要乘以 100"
            self._QS_Logger.warning({"msg": Msg, "alarm": True, "name": "data_correction", "source": self._QS_SourceLocation})
        return detail, summary

    # 解析内容
    def parseContent(self, xls, file_name, args={}):
        xls = xls.loc[:, xls.notnull().any(axis=0)]
        xls.columns = np.arange(xls.shape[1])

        self._MatchedRuleNames = None
        self._Rule = self._Rules.get(self.getRuleName(xls, file_name=file_name, args=args), pd.DataFrame(columns=self._DefaultRule.columns))

        # 解析可能存在的产品 ID
        ProductID = self.parseItem("product_id", xls, file_name, args=args)

        # 解析备案编码，产品代码，产品名称
        if not ProductID:
            reg_code = self._QSArgs.ExternalInfo.get("reg_code", None)
            if reg_code is None: reg_code = self.parseItem("reg_code", xls, file_name, args=args)
            reg_code = (reg_code.upper() if reg_code is not None else reg_code)
            fund_name = self._QSArgs.ExternalInfo.get("fund_name", None)
            if fund_name is None:
                fund_name = self.parseItem("fund_name", xls, file_name, args=args)
                if fund_name==reg_code: fund_name = None
            symbol = self._QSArgs.ExternalInfo.get("symbol", None)
            if symbol is None: symbol, reg_code, fund_name = self.parseSymbol(reg_code=reg_code, fund_name=fund_name, file_name=file_name)
        else:
            symbol, reg_code, fund_name = self.parseSymbol(reg_code=None, fund_name=None, file_name=file_name, product_id=ProductID)
        self._Rule = self._Rules.get(self.getRuleName(xls, file_name=file_name, reg_code=reg_code, fund_name=fund_name, args=args), pd.DataFrame(columns=self._DefaultRule.columns))

        # 解析估值日期
        idt = self.parseItem("the_datetime", xls, file_name, sys_rule=self.sysparseDateTime, args=args)

        # 解析表头
        header, header_idx, first_idx = self.locparseHeader(xls, args=args)

        # 解析明细结尾
        last_idx = self.locateTail(xls, first_idx, args=args)

        # 解析明细数据
        Mask = header.notnull()
        detail = xls.loc[:, Mask].loc[first_idx:last_idx-1].copy().reset_index(drop=True)
        specail_rule_config = self._SpecialRule[(self._SpecialRule["symbol"]==symbol) & (self._SpecialRule["执行位置"]=="明细解析前")]
        if not specail_rule_config.empty:
            for _, irow in specail_rule_config.iterrows():
                iargs = eval(irow["附加参数"])
                detail = getattr(special_rule, irow["特殊处理"])(detail, **iargs)
        detail = detail[detail.iloc[:, 0].notnull()]
        detail.columns = header[Mask].str.replace(" ", "").tolist()
        detail, KeepMask = self.deleteDuplicatedHeader(detail)# 删除重复列
        detail = self.parseDetail(detail, args=args)
        detail = detail[detail["account_code"].str.slice(0, 4).str.fullmatch(r"\d{4}").fillna(False)]
        detail["value"] = detail["market_value"].where(detail["market_value"].notnull(), detail["cost"])
        detail["the_datetime"] = idt
        detail["reg_code"] = reg_code
        detail["symbol"] = symbol
        detail["name"] = fund_name
        detail = self.parseDerivativeCol(detail, args=args)
        ExtInfo = {
            "file_name": file_name,
            "parse_rule": self.getRuleName(xls, file_name=file_name, reg_code=reg_code, fund_name=fund_name, args=args),
            "account_system": self.getAccountSystem(xls, file_name=file_name, reg_code=reg_code, fund_name=fund_name, symbol=symbol, args=args)
        }
        if ProductID: ExtInfo["product_id"] = ProductID
        ExtInfo.update(args.get("ext_info", {}))
        detail["ext_info"] = [json.dumps(ExtInfo, ensure_ascii=False)] * detail.shape[0]
        detail = self.addStdAccountName(detail, self._AccountInfo[ExtInfo["account_system"]], args=args)

        # 解析汇总数据
        summary = self.parseSummary(xls.loc[last_idx:], header, arsg=args).reset_index()
        summary.columns = ["factor", "value"]
        summary["the_datetime"] = idt
        summary["reg_code"] = reg_code
        summary["symbol"] = symbol
        summary["name"] = fund_name
        summary["asset_type"] = None# TODO
        summary["account_type"] = detail["account_type"].iloc[0]
        summary["ext_info"] = [json.dumps(ExtInfo, ensure_ascii=False)] * summary.shape[0]

        return self.correctData(detail, summary)

    # 解析产品代码和备案编码
    def parseSymbol(self, reg_code, fund_name, file_name, product_id=None):
        if file_name:
            Mask = self._SymbolConfig["文件名"].apply(lambda r: bool(r.fullmatch(file_name)))
            if Mask.any():
                Rslt = self._SymbolConfig[Mask].iloc[0]
                return Rslt["symbol"], (Rslt["reg_code"] if pd.notnull(Rslt["reg_code"]) else None), (Rslt["name"] if pd.notnull(Rslt["name"]) else None)
        if product_id and callable(self._QSArgs.SymbolFunc):
            df = self._QSArgs.SymbolFunc([product_id]).dropna(how="all")
            if not df.empty:
                try:
                    symbol, reg_code, fund_name = self.parseSymbol(df["reg_code"].iloc[0], df["name"].iloc[0], None)
                except:
                    symbol, reg_code, fund_name = self.parseSymbol(df["reg_code"].iloc[0], df["abbr"].iloc[0], None)
                else:
                    if symbol.startswith("NK_"):
                        symbol, reg_code, fund_name = self.parseSymbol(df["reg_code"].iloc[0], df["name"].iloc[0], file_name)
                if pd.notnull(df["name"].iloc[0]): fund_name = df["name"].iloc[0]
                if symbol.startswith("NK_"):
                    return f"NK_{product_id}", reg_code, fund_name
                else:
                    return symbol, reg_code, fund_name
        if isinstance(reg_code, list):
            for ireg_code in reg_code:
                iSymbol, iRegCode, iFundName = self.parseSymbol(ireg_code, None, None)
                if not iSymbol.startswith("NK_"):
                    return iSymbol, iRegCode, iFundName
            else:
                reg_code = None
        if reg_code in self._RegCode2Symbol: return self._RegCode2Symbol[reg_code]
        if fund_name in self._Name2Symbol: return self._Name2Symbol[fund_name]
        if reg_code:
            iInfo = self._QSArgs.SymbolInfo[self._QSArgs.SymbolInfo["reg_code"]==reg_code]
            if not iInfo.empty:
                self._RegCode2Symbol[reg_code] = (iInfo["symbol"].iloc[0], reg_code, iInfo["abbr"].iloc[0])
                return self._RegCode2Symbol[reg_code]
        if fund_name:
            iInfo = self._QSArgs.SymbolInfo[(self._QSArgs.SymbolInfo["name"] == fund_name) | (self._QSArgs.SymbolInfo["abbr"] == fund_name)]
            if not iInfo.empty:
                self._Name2Symbol[fund_name] = (iInfo["symbol"].iloc[0], iInfo["reg_code"].iloc[0] if reg_code is None else reg_code, fund_name)
                return self._Name2Symbol[fund_name]
        if file_name:
            Mask = self._QSArgs.SymbolInfo["name"].apply(lambda s: s in file_name)
            if not Mask.any():
                Mask = self._QSArgs.SymbolInfo["abbr"].apply(lambda s: s in file_name)
            iInfo = self._QSArgs.SymbolInfo[Mask]
            if not iInfo.empty:
                return iInfo["symbol"].iloc[0], iInfo["reg_code"].iloc[0] if reg_code is None else reg_code, iInfo["name"].iloc[0] if fund_name is None else fund_name
        if fund_name:
            iDefaultSymbol = f"NK_{fund_name}"
            Msg = f"估值文件 {self._QS_SourceLocation} 无法根据备案编号 {reg_code}, 基金名称 {fund_name} 以及文件名称 {file_name} 确定 symbol, 返回默认 symbol {iDefaultSymbol}"
            self._QS_Logger.error({"msg": Msg, "alarm": True, "name": "no_symbol", "source": self._QS_SourceLocation})
            return iDefaultSymbol, reg_code, fund_name

    # 解析转换为标准数据
    # 返回: (明细数据, 汇总数据)
    def parse(self, args={}):
        raise NotImplementedError
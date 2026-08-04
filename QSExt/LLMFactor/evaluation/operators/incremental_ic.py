# -*- coding: utf-8 -*-
"""组合增量 IC 计算算子（双残差法）。

对候选因子和收益率分别对基准因子池做 OLS 正交化，
计算残差之间的截面 RankIC。这是 v1 方案中多样性判定的主关卡。

算法来源：[[dual-residual-incremental-ic]]
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional, Literal

import numpy as np
import pandas as pd
from numpy.lib.recfunctions import unstructured_to_structured
import statsmodels.api as sm

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PanelOperator, PanelOperation


class CalcIncrementalIC(PanelOperator):
    """组合增量 IC 计算算子（双残差法）。

    对候选因子和收益率分别对基准因子池做 OLS 正交化，
    计算残差之间的截面相关系数。

    Parameters
    ----------
    descriptor_ids : List[str]
        截面 ID 序列（股票列表）
    lookback : int
        时间标尺上的回溯期数
    period_lookback : int
        计算标尺上的回溯期数
    corr_method : str
        相关性方法: "spearman"（默认）、"pearson"、"kendall"
    """

    def __init__(
        self,
        descriptor_ids: List[str],
        lookback: int = 31,
        period_lookback: int = 1,
        corr_method: Literal["spearman", "pearson", "kendall"] = "spearman",
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        Arity = args.get("Arity", None) or 1
        Args = {"Name": "calcIncrementalIC"} | args | {"DTMode": "多时点", "DataType": "object"}
        Args["ModelArgs"] = {
            "corr_method": corr_method,
            "period_lookback": period_lookback,
        } | Args.get("ModelArgs", {})
        Args["DescriptorSection"] = [Args.get("DescriptorSection", [descriptor_ids])[0]] * Arity
        Args["LookBack"] = [Args.get("LookBack", [lookback])[0]] * Arity
        Args["CompoundType"] = [("IC", "double"), ("MaxCorrelation", "double"), ("Breadth", "double")]
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(
        self, f: Factor, idt: List[dt.datetime], iid: List[str],
        x: List[np.ndarray], args: dict,
    ) -> np.ndarray:
        """计算增量 IC。

        输入数据排列：
        x[0]: price
        x[1]: mask (如果启用)
        x[2]: cat_data (如果启用)
        x[3:3+n_base]: base_factors (基准因子)
        x[3+n_base:]: candidate_factors (候选因子)

        Returns:
            结构化数组: (IC, MaxCorrelation, Breadth)
        """
        SectionIDs = self._QSArgs.DescriptorSection[0] if self._QSArgs.DescriptorSection[0] else iid

        # 解析价格数据
        Price, x = pd.DataFrame(x[0].T, columns=idt, index=SectionIDs), x[1:]
        if f._QSArgs.CalcDTRuler:
            DTs = sorted(set(idt).intersection(f._QSArgs.CalcDTRuler))
            Price = Price.reindex(columns=DTs)
        else:
            DTs = Price.columns

        # 计算收益率
        Return = Price.T.pct_change().T

        # 解析 mask
        if f._QSArgs.ModelArgs.get("mask"):
            Mask, x = pd.DataFrame(x[0].T == 1, columns=idt, index=SectionIDs).reindex(columns=DTs).astype(float).fillna(0).astype(bool), x[1:]
            Mask = Mask & Price.notnull()
        else:
            Mask = Price.notnull()

        # 解析 cat_data（行业中性化）
        if f._QSArgs.ModelArgs.get("cat_data"):
            CatData, x = pd.DataFrame(x[0].T, columns=idt, index=SectionIDs).reindex(columns=DTs), x[1:]
        else:
            CatData = None

        # 行业调整收益率
        if CatData is not None:
            Return = Return.where(CatData.notnull(), np.nan)
            AllCates = CatData.values.flatten()
            AllCates = np.unique(AllCates[pd.notnull(AllCates)])
            for iCate in AllCates:
                iMask = (CatData == iCate) & Mask
                iReturn = Return.where(iMask.shift(1, axis=1).astype(float).fillna(0).astype(bool), np.nan).mean(axis=0)
                Return = Return.where(~iMask.shift(1, axis=1).astype(float).fillna(0).astype(bool), Return - iReturn)

        # 解析基准因子和候选因子
        n_base = f._QSArgs.ModelArgs.get("n_base_factors", 0)
        BaseFactorNames = f._QSArgs.ModelArgs.get("base_factor_names", [])
        FactorNames = f._QSArgs.SectionIDs
        Mask = Mask.shift(args["period_lookback"], axis=1).astype(float).fillna(0).astype(bool)

        # 构建基准因子数据
        BaseFactorData = {}
        for i, iName in enumerate(BaseFactorNames):
            if i < len(x):
                BaseFactorData[iName] = pd.DataFrame(x[i].T, columns=idt, index=SectionIDs).reindex(columns=DTs).shift(args["period_lookback"])
        x = x[len(BaseFactorNames):]

        # 计算每个候选因子的增量 IC
        IC = pd.DataFrame(index=DTs, columns=iid)
        MaxCorr = pd.DataFrame(index=DTs, columns=iid)
        Breadth = pd.DataFrame(index=DTs, columns=iid)

        for iFactorName in iid:
            if iFactorName not in FactorNames:
                continue
            iIdx = FactorNames.index(iFactorName)
            if iIdx >= len(x):
                continue

            # 候选因子数据
            iFactorData = pd.DataFrame(x[iIdx].T, columns=idt, index=SectionIDs).reindex(columns=DTs).shift(args["period_lookback"])

            for iDT in DTs:
                # 获取当期截面数据
                iReturn = Return[iDT]
                iFactor = iFactorData[iDT]
                iMask = Mask[iDT] & iFactor.notnull() & iReturn.notnull()

                if iMask.sum() < 30:
                    continue

                # 收益率截面
                y = iReturn[iMask]

                # 候选因子截面
                candidate = iFactor[iMask]

                # 基准因子矩阵
                if BaseFactorData:
                    base_df = pd.DataFrame({
                        name: data[iDT][iMask] for name, data in BaseFactorData.items()
                    }).dropna(axis=1, how='all').fillna(0)

                    if base_df.shape[1] > 0 and base_df.shape[0] > base_df.shape[1]:
                        # 对基准因子正交化：候选因子残差
                        X_base = sm.add_constant(base_df)
                        try:
                            reg_cand = sm.OLS(candidate.values, X_base.values, missing='drop').fit()
                            residual_cand = pd.Series(reg_cand.resid, index=candidate.index)
                        except Exception:
                            residual_cand = candidate

                        # 对基准因子正交化：收益残差
                        try:
                            reg_ret = sm.OLS(y.values, X_base.values, missing='drop').fit()
                            residual_ret = pd.Series(reg_ret.resid, index=y.index)
                        except Exception:
                            residual_ret = y
                    else:
                        residual_cand = candidate
                        residual_ret = y
                else:
                    residual_cand = candidate
                    residual_ret = y

                # 计算残差 IC
                if len(residual_cand) > 10:
                    ic_val = residual_cand.corr(residual_ret, method=args["corr_method"])
                    IC.loc[iDT, iFactorName] = ic_val
                    Breadth.loc[iDT, iFactorName] = len(residual_cand)

                # 计算与已有因子的最大相关性
                if BaseFactorData:
                    corrs = []
                    for name, data in BaseFactorData.items():
                        iBaseFactor = data[iDT][iMask]
                        if iBaseFactor.notnull().sum() > 10:
                            corr = candidate.corr(iBaseFactor, method="spearman")
                            if pd.notnull(corr):
                                corrs.append(abs(corr))
                    if corrs:
                        MaxCorr.loc[iDT, iFactorName] = max(corrs)

        # 转为 numpy 数组输出
        IC_arr = IC.reindex(index=idt).values[self._QSArgs.LookBack[0]:]
        MaxCorr_arr = MaxCorr.reindex(index=idt).values[self._QSArgs.LookBack[0]:]
        Breadth_arr = Breadth.reindex(index=idt).values[self._QSArgs.LookBack[0]:]

        Rslt = np.array([IC_arr, MaxCorr_arr, Breadth_arr])
        return unstructured_to_structured(
            Rslt.swapaxes(0, -1),
            dtype=np.dtype([("IC", float), ("MaxCorrelation", float), ("Breadth", float)]),
        ).T.astype("O")

    def __call__(
        self,
        *x: Factor,
        price: Factor,
        base_factors: List[Factor],
        mask: Optional[Factor] = None,
        cat_data: Optional[Factor] = None,
        factor_name_list: Optional[List[str]] = None,
        base_factor_name_list: Optional[List[str]] = None,
        factor_args: dict = {},
        **kwargs,
    ) -> PanelOperation:
        """将算子作用在因子对象上。

        Args:
            x: 待计算增量 IC 的候选因子
            price: 价格/净值因子
            base_factors: 基准因子池（已有入库因子）
            mask: 筛选条件因子
            cat_data: 类别因子（如行业，用于中性化）
            factor_name_list: 候选因子名称列表
            base_factor_name_list: 基准因子名称列表
            factor_args: 传递给 IC 因子的参数集
            kwargs: 其他参数

        Returns:
            增量 IC 因子
        """
        Factors = [price]
        if mask is not None:
            Factors.append(mask)
        if cat_data is not None:
            Factors.append(cat_data)
        Factors += base_factors
        if not x:
            raise ValueError("候选因子列表 x 不可为空!")
        Factors += x

        # 处理候选因子名称
        if factor_name_list is not None:
            if factor_args.get("SectionIDs") is not None:
                factor_name_list = factor_args["SectionIDs"]
        elif factor_args.get("SectionIDs") is not None:
            factor_name_list = factor_args["SectionIDs"]
        else:
            factor_name_list = [iFactor.Name for iFactor in x]
            if len(set(factor_name_list)) != len(x):
                PosNum = int(np.log10(max(1, len(x) - 1))) + 1
                factor_name_list = [f"F{str(i).zfill(PosNum)}" for i in range(len(x))]

        # 处理基准因子名称
        if base_factor_name_list is None:
            base_factor_name_list = [f.Name for f in base_factors]

        factor_args = factor_args.copy()
        factor_args["SectionIDs"] = factor_name_list
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {
            "mask": mask is not None,
            "cat_data": cat_data is not None,
            "n_base_factors": len(base_factors),
            "base_factor_names": base_factor_name_list,
        }
        kwargs["operator_kwargs"] = {
            "descriptor_ids": self._QSArgs.DescriptorSection[0],
            "lookback": self._QSArgs.LookBack[0],
        } | kwargs.get("operator_kwargs", {})
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

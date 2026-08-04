# -*- coding: utf-8 -*-
"""子期稳健性分析算子。

将评测区间按年（或其他频率）拆分，每个子期独立计算 IC 统计，
用于评估因子在不同市场环境下的稳健性。

对应方案文档 5.3 节 Part 1：子期覆盖度。
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional, Literal

import numpy as np
import pandas as pd
from numpy.lib.recfunctions import unstructured_to_structured

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PanelOperator, PanelOperation


class CalcSubPeriodStats(PanelOperator):
    """子期稳健性统计算子。

    将评测区间按年拆分，每个子期独立计算 IC、ICIR、覆盖率等统计指标。

    Parameters
    ----------
    descriptor_ids : List[str]
        截面 ID 序列
    freq : str
        拆分频率: "yearly"（默认）、"quarterly"
    corr_method : str
        相关性方法
    lookback : int
        回溯期数
    period_lookback : int
        计算标尺回溯期数
    """

    def __init__(
        self,
        descriptor_ids: List[str],
        freq: str = "yearly",
        corr_method: Literal["spearman", "pearson", "kendall"] = "spearman",
        lookback: int = 31,
        period_lookback: int = 1,
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        Arity = args.get("Arity", None) or 1
        Args = {"Name": "calcSubPeriodStats"} | args | {"DTMode": "多时点", "DataType": "object"}
        Args["ModelArgs"] = {
            "corr_method": corr_method,
            "period_lookback": period_lookback,
            "freq": freq,
        } | Args.get("ModelArgs", {})
        Args["DescriptorSection"] = [Args.get("DescriptorSection", [descriptor_ids])[0]] * Arity
        Args["LookBack"] = [Args.get("LookBack", [lookback])[0]] * Arity
        Args["CompoundType"] = [("Stats", "object")]
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(
        self, f: Factor, idt: List[dt.datetime], iid: List[str],
        x: List[np.ndarray], args: dict,
    ) -> np.ndarray:
        """计算子期统计。

        输入数据排列：
        x[0]: price
        x[1]: mask (如果启用)
        x[2]: cat_data (如果启用)
        x[3:]: candidate_factors

        Returns:
            结构化数组: (Stats,)
        """
        SectionIDs = self._QSArgs.DescriptorSection[0] if self._QSArgs.DescriptorSection[0] else iid
        freq = args.get("freq", "yearly")

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

        # 解析 cat_data
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

        # 按频率拆分子期
        FactorNames = f._QSArgs.SectionIDs
        period_lookback = args.get("period_lookback", 1)
        corr_method = args.get("corr_method", "spearman")

        # 获取子期列表
        if freq == "yearly":
            periods = sorted(set(dt.year for dt in DTs))
            period_key = lambda d: d.year
        elif freq == "quarterly":
            periods = sorted(set((d.year, (d.month - 1) // 3 + 1) for d in DTs))
            period_key = lambda d: (d.year, (d.month - 1) // 3 + 1)
        else:
            periods = sorted(set(dt.year for dt in DTs))
            period_key = lambda d: d.year

        # 对每个因子计算各子期统计
        all_stats = {}
        for iFactorName in iid:
            if iFactorName not in FactorNames:
                continue
            iIdx = FactorNames.index(iFactorName)
            if iIdx >= len(x):
                continue

            iFactorData = pd.DataFrame(x[iIdx].T, columns=idt, index=SectionIDs).reindex(columns=DTs).shift(period_lookback)
            period_stats = []

            for period in periods:
                # 获取该子期的时点
                if freq == "yearly":
                    period_dts = [d for d in DTs if d.year == period]
                else:
                    period_dts = [d for d in DTs if (d.year, (d.month - 1) // 3 + 1) == period]

                if len(period_dts) < 5:
                    continue

                # 计算该子期的 IC
                ic_values = []
                for iDT in period_dts:
                    iReturn_dt = Return[iDT]
                    iFactor_dt = iFactorData[iDT]
                    iMask_dt = Mask[iDT] & iFactor_dt.notnull() & iReturn_dt.notnull()

                    if iMask_dt.sum() < 30:
                        continue

                    ic = iReturn_dt[iMask_dt].corr(iFactor_dt[iMask_dt], method=corr_method)
                    if pd.notnull(ic):
                        ic_values.append(ic)

                if len(ic_values) < 3:
                    continue

                ic_arr = np.array(ic_values)
                period_stats.append({
                    "period": str(period),
                    "IC均值": np.mean(ic_arr),
                    "IC标准差": np.std(ic_arr),
                    "ICIR": np.mean(ic_arr) / np.std(ic_arr) if np.std(ic_arr) > 0 else 0,
                    "t统计量": np.mean(ic_arr) * np.sqrt(len(ic_arr)) / np.std(ic_arr) if np.std(ic_arr) > 0 else 0,
                    "胜率": np.mean(ic_arr > 0),
                    "有效期数": len(ic_arr),
                    "平均截面宽度": 0,  # 简化处理
                })

            all_stats[iFactorName] = pd.DataFrame(period_stats) if period_stats else pd.DataFrame()

        # 输出为对象数组
        result = np.array([all_stats], dtype=object)
        return result

    def __call__(
        self,
        *x: Factor,
        price: Factor,
        mask: Optional[Factor] = None,
        cat_data: Optional[Factor] = None,
        factor_name_list: Optional[List[str]] = None,
        factor_args: dict = {},
        **kwargs,
    ) -> PanelOperation:
        """将算子作用在因子对象上。

        Args:
            x: 待分析的候选因子
            price: 价格/净值因子
            mask: 筛选条件因子
            cat_data: 类别因子（如行业）
            factor_name_list: 因子名称列表
            factor_args: 传递给因子的参数集
            kwargs: 其他参数

        Returns:
            子期统计因子
        """
        Factors = [price]
        if mask is not None:
            Factors.append(mask)
        if cat_data is not None:
            Factors.append(cat_data)
        if not x:
            raise ValueError("候选因子列表 x 不可为空!")
        Factors += x

        # 处理因子名称
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

        factor_args = factor_args.copy()
        factor_args["SectionIDs"] = factor_name_list
        factor_args["ModelArgs"] = factor_args.get("ModelArgs", {}) | {
            "mask": mask is not None,
            "cat_data": cat_data is not None,
        }
        kwargs["operator_kwargs"] = {
            "descriptor_ids": self._QSArgs.DescriptorSection[0],
            "lookback": self._QSArgs.LookBack[0],
            "freq": self._QSArgs.ModelArgs.get("freq", "yearly"),
        } | kwargs.get("operator_kwargs", {})
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

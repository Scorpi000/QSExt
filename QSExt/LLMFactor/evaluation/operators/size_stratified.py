# -*- coding: utf-8 -*-
"""规模分层 Alpha 计算算子。

按市值将股票分为若干组，每组内独立做多空回测，
提取各组的 CAPM Alpha 和 t 统计量。

对应方案文档 5.3 节 Part 4：规模分层 Alpha 检验。
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

import numpy as np
import pandas as pd
from numpy.lib.recfunctions import unstructured_to_structured
import statsmodels.api as sm

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PanelOperator, PanelOperation


class CalcSizeStratifiedAlpha(PanelOperator):
    """规模分层 Alpha 计算算子。

    按市值将股票分为若干组，每组内独立构造多空组合，
    计算各组的 CAPM Alpha 和 t 统计量。

    Parameters
    ----------
    descriptor_ids : List[str]
        截面 ID 序列
    group_num : int
        分组数（默认 5）
    lookback : int
        回溯期数
    period_lookback : int
        计算标尺回溯期数
    """

    def __init__(
        self,
        descriptor_ids: List[str],
        group_num: int = 5,
        lookback: int = 31,
        period_lookback: int = 1,
        args: dict = {},
        config_file: Optional[str] = None,
        **kwargs,
    ):
        Arity = args.get("Arity", None) or 1
        Args = {"Name": "calcSizeStratifiedAlpha"} | args | {"DTMode": "多时点", "DataType": "object"}
        Args["ModelArgs"] = {
            "group_num": group_num,
            "period_lookback": period_lookback,
        } | Args.get("ModelArgs", {})
        Args["DescriptorSection"] = [Args.get("DescriptorSection", [descriptor_ids])[0]] * Arity
        Args["LookBack"] = [Args.get("LookBack", [lookback])[0]] * Arity

        # 输出：每组的年化收益、Alpha、t统计量、Sharpe
        compound_types = []
        for i in range(group_num):
            compound_types.extend([
                (f"Return_G{i}", "double"),
                (f"Alpha_G{i}", "double"),
                (f"tStat_G{i}", "double"),
            ])
        Args["CompoundType"] = compound_types

        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(
        self, f: Factor, idt: List[dt.datetime], iid: List[str],
        x: List[np.ndarray], args: dict,
    ) -> np.ndarray:
        """计算规模分层 Alpha。

        输入数据排列：
        x[0]: price
        x[1]: market_cap
        x[2]: mask (如果启用)
        x[3]: market_return (如果提供，用于 CAPM 回归)

        Returns:
            结构化数组
        """
        SectionIDs = self._QSArgs.DescriptorSection[0] if self._QSArgs.DescriptorSection[0] else iid
        group_num = args.get("group_num", 5)

        # 解析价格数据
        Price, x = pd.DataFrame(x[0].T, columns=idt, index=SectionIDs), x[1:]
        if f._QSArgs.CalcDTRuler:
            DTs = sorted(set(idt).intersection(f._QSArgs.CalcDTRuler))
            Price = Price.reindex(columns=DTs)
        else:
            DTs = Price.columns

        # 计算收益率
        Return = Price.T.pct_change().T

        # 解析市值数据
        MarketCap, x = pd.DataFrame(x[0].T, columns=idt, index=SectionIDs).reindex(columns=DTs), x[1:]

        # 解析 mask
        if f._QSArgs.ModelArgs.get("mask"):
            Mask, x = pd.DataFrame(x[0].T == 1, columns=idt, index=SectionIDs).reindex(columns=DTs).astype(float).fillna(0).astype(bool), x[1:]
            Mask = Mask & Price.notnull()
        else:
            Mask = Price.notnull()

        # 解析市场收益率（如果提供）
        if f._QSArgs.ModelArgs.get("has_market_return") and len(x) > 0:
            MarketReturn, x = pd.DataFrame(x[0].T, columns=idt, index=SectionIDs).reindex(columns=DTs).mean(axis=0), x[1:]
        else:
            MarketReturn = Return.mean(axis=0)  # 等权平均作为市场收益

        # 解析候选因子数据
        FactorNames = f._QSArgs.SectionIDs
        period_lookback = args.get("period_lookback", 1)

        # 存储各组的收益率序列
        group_returns = {i: pd.Series(index=DTs, dtype=float) for i in range(group_num)}

        for iDT_idx, iDT in enumerate(DTs):
            if iDT_idx < period_lookback + 1:
                continue

            # 获取当期数据
            iReturn = Return[iDT]
            iMask = Mask[iDT]
            iMarketCap = MarketCap[iDT] if iDT in MarketCap.columns else pd.Series(np.nan, index=SectionIDs)

            # 获取当期因子值（使用 period_lookback 期前的因子值）
            dt_idx = list(DTs).index(iDT)
            if dt_idx < period_lookback:
                continue
            factor_dt = DTs[dt_idx - period_lookback]

            # 对每个候选因子
            for iFactorName in iid:
                if iFactorName not in FactorNames:
                    continue
                iIdx = FactorNames.index(iFactorName)

                # 因子值
                iFactor = pd.Series(x[iIdx][:, dt_idx - period_lookback], index=SectionIDs) if iIdx < len(x) else pd.Series(np.nan, index=SectionIDs)

                # 有效数据筛选
                valid = iMask & iFactor.notnull() & iReturn.notnull() & iMarketCap.notnull()
                if valid.sum() < group_num * 10:
                    continue

                # 按市值分组
                valid_cap = iMarketCap[valid]
                try:
                    groups = pd.qcut(valid_cap, group_num, labels=False, duplicates='drop')
                except ValueError:
                    continue

                # 每组构造多空组合
                for g in range(group_num):
                    g_mask = (groups == g)
                    if g_mask.sum() < 10:
                        continue

                    g_factor = iFactor[valid][g_mask]
                    g_return = iReturn[valid][g_mask]

                    # 按因子值分多空
                    try:
                        factor_rank = g_factor.rank(pct=True)
                        long_mask = factor_rank > 0.8
                        short_mask = factor_rank < 0.2

                        if long_mask.sum() >= 2 and short_mask.sum() >= 2:
                            long_ret = g_return[long_mask].mean()
                            short_ret = g_return[short_mask].mean()
                            ls_ret = long_ret - short_ret
                            group_returns[g][iDT] = ls_ret
                    except Exception:
                        continue

        # 计算各组的 Alpha 和 t 统计量
        result = np.full((len(iid), group_num * 3), np.nan)

        for iFactor_idx, iFactorName in enumerate(iid):
            if iFactorName not in FactorNames:
                continue

            for g in range(group_num):
                g_ret = group_returns[g].dropna()
                if len(g_ret) < 12:
                    continue

                # 年化收益
                annual_ret = g_ret.mean() * 12
                result[iFactor_idx, g * 3] = annual_ret

                # CAPM Alpha（对市场收益回归）
                mkt = MarketReturn.reindex(g_ret.index).dropna()
                common = g_ret.index.intersection(mkt.index)
                if len(common) < 12:
                    continue

                y = g_ret[common].values
                X = sm.add_constant(mkt[common].values)

                try:
                    model = sm.OLS(y, X, missing='drop').fit()
                    alpha = model.params[0] * 12  # 年化 Alpha
                    t_stat = model.tvalues[0]
                    result[iFactor_idx, g * 3 + 1] = alpha
                    result[iFactor_idx, g * 3 + 2] = t_stat
                except Exception:
                    continue

        return unstructured_to_structured(result).tolist()

    def __call__(
        self,
        *x: Factor,
        price: Factor,
        market_cap: Factor,
        mask: Optional[Factor] = None,
        market_return: Optional[Factor] = None,
        factor_name_list: Optional[List[str]] = None,
        factor_args: dict = {},
        **kwargs,
    ) -> PanelOperation:
        """将算子作用在因子对象上。

        Args:
            x: 待检验的候选因子
            price: 价格/净值因子
            market_cap: 市值因子
            mask: 筛选条件因子
            market_return: 市场收益率因子（可选）
            factor_name_list: 因子名称列表
            factor_args: 传递给因子的参数集
            kwargs: 其他参数

        Returns:
            规模分层 Alpha 因子
        """
        Factors = [price, market_cap]
        if mask is not None:
            Factors.append(mask)
        if market_return is not None:
            Factors.append(market_return)
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
            "has_market_return": market_return is not None,
        }
        kwargs["operator_kwargs"] = {
            "descriptor_ids": self._QSArgs.DescriptorSection[0],
            "lookback": self._QSArgs.LookBack[0],
            "group_num": self._QSArgs.ModelArgs.get("group_num", 5),
        } | kwargs.get("operator_kwargs", {})
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)

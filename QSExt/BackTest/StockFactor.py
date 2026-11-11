"""股票因子分析节点，支持串行和以 spawn 启动的并行引擎。"""
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field

from QuantStudio.Core.Input import DependencyModel
from QuantStudio.Core.Node import DTLocalContext
from QuantStudio.Factor.Factor import Factor, FactorInitData, FactorLocalContext
from QuantStudio.Factor.FactorOperation import SectionOperator
from QuantStudio.BackTest.BackTestModel import BTNode
from QuantStudio.BackTest.SectionFactor.IC import CalcIC
from QuantStudio.BackTest.SectionFactor.Correlation import CalcFactorTurnover
from QuantStudio.BackTest.SectionFactor.QuantilePortfolio import MultiPortfolio


class StockMultiPortfolio(MultiPortfolio):
    """记录分组方向，供报告展示实际组合口径。"""
    class __QS_ArgClass__(MultiPortfolio.__QS_ArgClass__):
        Ascending: bool = False


class StockSignal(SectionOperator):
    """剔除非有限值、无效价格和动态样本外证券，保留原因子名称。"""

    def __init__(self, minimum=3, args=None, **kwargs):
        super().__init__(args={"DTMode": "多时点", "DataType": "double",
            "ModelArgs": {"minimum": minimum}, **(args or {})}, **kwargs)

    def calculate(self, f, idt, iid, x, args):
        data, price = np.asarray(x[0], dtype=float), np.asarray(x[1], dtype=float)
        valid = np.isfinite(data) & np.isfinite(price) & (price > 0)
        if len(x) > 2:
            valid &= x[2] == 1
        result = np.where(valid, data, np.nan)
        for row in result:
            values = row[np.isfinite(row)]
            if len(values) < args["minimum"] or len(np.unique(values)) < 2:
                row[:] = np.nan
        return result


class StockPrice(SectionOperator):
    """无效价格统一转为空值，交由净值引擎按缺失价格估值。"""
    def __init__(self, args=None, **kwargs):
        super().__init__(args={"DTMode": "多时点", "DataType": "double", **(args or {})}, **kwargs)

    def calculate(self, f, idt, iid, x, args):
        price = np.asarray(x[0], dtype=float)
        return np.where(np.isfinite(price) & (price > 0), price, np.nan)


class StockCalcIC(CalcIC):
    """沿用原 IC 算法，按实际有限收益配对数屏蔽不足样本。"""

    def calculate(self, f, idt, iid, x, args):
        # 无效价格不作为收益率端点；基础实现的 Breadth 不检查收益的前端点。
        prices = np.asarray(x[0], dtype=float)
        x = [np.where(np.isfinite(prices) & (prices > 0), prices, np.nan), *x[1:]]
        result = super().calculate(f, idt, iid, x, args)
        dates = sorted(set(idt).intersection(f.Args.CalcDTRuler))
        price = pd.DataFrame(x[0], index=idt).reindex(dates)
        alpha = pd.DataFrame(x[-1], index=idt).reindex(dates).shift(args["period_lookback"])
        valid = np.isfinite(price.pct_change(fill_method=None)) & np.isfinite(alpha)
        counts = valid.sum(axis=1).reindex(idt).iloc[self.Args.LookBack[0]:].to_numpy()
        for i, count in enumerate(counts):
            for j in range(result.shape[1]):
                corr = result[i, j][0]
                result[i, j] = (corr if count >= args["min_samples"] else np.nan, float(count))
        return result


class StockCalcStability(CalcFactorTurnover):
    """复用自相关算法，剔除配对股票数量不足的观测。"""
    def calculate(self, f, idt, iid, x, args):
        result = super().calculate(f, idt, iid, x, args)
        dates = sorted(set(idt).intersection(f.Args.CalcDTRuler))
        data = pd.DataFrame(x[0], index=idt).reindex(dates)
        counts = (np.isfinite(data) & np.isfinite(data.shift())).sum(axis=1)
        valid = counts.reindex(idt).iloc[self.Args.LookBack[0]:].to_numpy() >= args["min_samples"]
        # pandas 的 Copy-on-Write 结果可能是只读视图，不修改上游返回的数据。
        return np.where(valid[:, None], result, np.nan)


class StockQuality(BTNode):
    """在同一计算图内取得原始输入，提供覆盖率与无效样本诊断。"""

    class __QS_DepClass__(DependencyModel):
        factor: Factor
        price: Factor
        mask: Factor | None = None

    class __QS_ArgClass__(BTNode.__QS_ArgClass__):
        CalcDates: list[datetime] = Field(default_factory=list)
        MinSamples: int = Field(default=20, ge=3)
        GroupNum: int = Field(default=5, ge=2, le=10)
        CalcRule: Literal["1d", "1w", "1m"] = "1m"

    def init_compute(self, path, init_data, context):
        requests = super().init_compute(path, init_data, context)
        return [FactorInitData(DTRange=item.DTRange, SectionIDs=context.SectionIDs) for item in requests]

    def forward_compute(self, path, fwd_data, context):
        return [FactorLocalContext(DTs=fwd_data.DTs, IDs=context.SectionIDs, SectionIDs=context.SectionIDs,
            PIDs=context.PIDList) for _ in self.Deps], DTLocalContext(DTs=fwd_data.DTs)

    def backward_compute(self, path, bwd_data_list, context, local_context=None):
        factor, price = bwd_data_list[:2]
        eligible = pd.DataFrame(True, index=factor.index, columns=factor.columns)
        if len(bwd_data_list) > 2:
            eligible &= bwd_data_list[2] == 1
        numeric = factor.apply(pd.to_numeric, errors="coerce")
        finite = np.isfinite(numeric)
        usable = finite & np.isfinite(price) & (price > 0) & eligible
        counts = usable.sum(axis=1)
        unique = numeric.where(usable).nunique(axis=1)
        table = pd.DataFrame({"候选股票数": eligible.sum(axis=1), "有效股票数": counts,
            "有效覆盖率": counts / eligible.sum(axis=1).replace(0, np.nan),
            "因子缺失或非有限值比例": 1 - (finite & eligible).sum(axis=1) / eligible.sum(axis=1).replace(0, np.nan),
            "不同因子值数量": unique})
        sampled = table.reindex(self.Args.CalcDates).dropna(how="all")
        valid = (sampled["有效股票数"] >= max(self.Args.MinSamples, self.Args.GroupNum)) & (sampled["不同因子值数量"] >= 2)
        if not valid.any():
            raise ValueError("股票测试没有有效采样截面：因子全部缺失、为常量或有效股票数不足")
        return {"每日覆盖": table, "采样覆盖": sampled,
            "无效采样期数": int((~valid).sum()), "股票数": len(factor.columns)}

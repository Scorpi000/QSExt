# -*- coding: utf-8 -*-
"""遗传规划因子挖掘的适应度评估模块。

本模块提供可扩展的适应度评估框架，用于评估遗传规划生成的因子质量。

架构设计:
    - FitnessEvaluator: 适应度评估器基类，定义统一接口
    - ICFitnessEvaluator: 基于 IC (Information Coefficient) 的评估器
    - 可扩展: 继承基类实现自定义评估器（如 IR、分组收益等）

典型用法:
    from QSExt.GPFactor.fitness import ICFitnessEvaluator

    evaluator = ICFitnessEvaluator(
        price_factor=Close,
        section_ids=IDs,
        dtruler=DTRuler,
        dts=DTs
    )
    fitness_values = evaluator(factors)  # 返回 ndarray
"""
from typing import List, Literal, Optional
import traceback

import numpy as np
from pydantic import Field

from QuantStudio.Core import __QS_Object__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor import FactorOperator as fo
from QuantStudio.BackTest.SectionFactor.IC import CalcIC
from QuantStudio.Tools.DateTimeFun import transformDateTime



# ============================================================================
#  基类
# ============================================================================

class FitnessEvaluator(__QS_Object__):
    """适应度评估器基类。

    所有自定义评估器应继承此类并实现 evaluate 方法。

    子类需要实现:
        evaluate(factors: List[Factor]) -> np.ndarray: 评估因子列表，返回适应度数组
    """

    def evaluate(self, factors: List[Factor]) -> np.ndarray:
        """评估一组因子的适应度。

        Args:
            factors: 因子对象列表

        Returns:
            每个因子的适应度值数组
        """
        raise NotImplementedError

    def __call__(self, factors: List[Factor]) -> np.ndarray:
        """可调用接口，兼容 GPLearner 的 fitness_fun 参数。"""
        return self.evaluate(factors)


# ============================================================================
#  IC 评估器
# ============================================================================

class ICFitnessEvaluator(FitnessEvaluator):
    """基于 IC 的适应度评估器

    使用 QuantStudio 的计算图引擎和 CalcIC 算子来批量计算因子的 IC 值，
    复用同一个 FactorContext 和缓存来提高效率。

    Args:
        price_factor: 价格因子（用于计算收益率）
        section_ids: 截面 ID 序列
        dtruler: 时点标尺（包含回溯期的完整交易日序列）
        dts: 计算时点序列（实际需要计算 IC 的交易日）

    示例:
        evaluator = ICFitnessEvaluator(
            price_factor=Close,
            section_ids=IDs,
            dtruler=DTRuler,
            dts=DTs,
            args=Args
        )
        fitness = evaluator([Factor1, Factor2, Factor3])
    """
    class __QS_ArgClass__(__QS_Object__.__QS_ArgClass__):
        Name: str = Field(default="ICFitnessEvaluator", frozen=True, title="名称")
        CorrMethod: Literal["spearman", "pearson", "kendall"] = Field(default="spearman", frozen=True, title="相关性计算方法")
        Freq: str = Field(default="1m", frozen=True, title="计算频率")
    
    def __init__(
        self,
        price_factor: Factor,
        section_ids: List[str],
        dtruler: list,
        dts: list,
        args: dict={},
        config_file: Optional[str]=None,
        **kwargs
    ):
        super().__init__(args=args, config_file=config_file, **kwargs)
        self._Price = price_factor
        self._SectionIDs = section_ids
        self._DTRuler = dtruler
        self._DTs = dts
        self._CalcDTRuler = transformDateTime(self._DTRuler, freq=self.Args.Freq)
        LookBack = min(np.max(np.diff(self._CalcDTRuler)).days, self._DTRuler.index(self._DTs[0]))

        # 创建 CalcIC 算子实例
        self._calcIC = CalcIC(
            descriptor_ids=section_ids,
            lookback=LookBack,
            period_lookback=1,
            corr_method=self.Args.CorrMethod,
        )
        self._fetch = fo.Fetch(pos=0, dtype="double")

    def evaluate(self, factors: List[Factor]) -> np.ndarray:
        """批量评估一组因子的 IC 值。

        将所有因子一次性传给 CalcIC 算子进行批量计算，提高效率。

        Args:
            factors: 因子对象列表

        Returns:
            每个因子的平均 IC 值数组
        """
        n_factors = len(factors)
        results = np.zeros(n_factors)
        # 为每个因子生成唯一的名称
        digit_num = int(np.log10(n_factors)) + 1
        factor_name_list = ["Factor_" + str(i).zfill(digit_num) for i in range(n_factors)]

        # try:
        # 使用 CalcIC 算子一次性创建所有因子的 IC 计算节点
        ic_factor = self._calcIC(
            *factors,
            price=self._Price,
            factor_name_list=factor_name_list,
            factor_args={"CalcDTRuler": self._CalcDTRuler}
        )
        ic_factor = self._fetch(ic_factor)

        # 执行计算
        ic_data = ic_factor.readData(dts=self._DTs, ids=factor_name_list)

        # 提取 IC 的平均值
        results = ic_data.mean().fillna(value=0.0).values
        # except Exception:
        #     # 如果批量计算失败，返回全零
        #     self.Logger.warning(f"ICFitnessEvaluator 适应度计算失败: {traceback.format_exc()}")

        return results

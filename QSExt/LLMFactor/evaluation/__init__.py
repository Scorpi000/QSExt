# -*- coding: utf-8 -*-
"""因子评测模块。

提供基于 QuantStudio 框架的因子评测能力：
  - operators: 评测算子（增量IC、规模分层、子期分析）
  - nodes: 评测节点（BTNode，用于 DAG 编排）
  - scoring: 五维度评分
  - decision: 入库决策规则
  - evaluator: 统一评测入口
  - cache_manager: 评测缓存管理器（FeatherFactorCache）
  - report: 报告生成（桥接 QSExt ReportGenerator）
"""
from QSExt.LLMFactor.evaluation.config import EvalConfig
from QSExt.LLMFactor.evaluation.cache_manager import EvalCacheManager
from QSExt.LLMFactor.evaluation.operators.incremental_ic import CalcIncrementalIC
from QSExt.LLMFactor.evaluation.operators.size_stratified import CalcSizeStratifiedAlpha
from QSExt.LLMFactor.evaluation.operators.sub_period import CalcSubPeriodStats
from QSExt.LLMFactor.evaluation.nodes.incremental_ic_node import IncrementalICNode
from QSExt.LLMFactor.evaluation.nodes.size_stratified_node import SizeStratifiedAlphaNode
from QSExt.LLMFactor.evaluation.nodes.sub_period_node import SubPeriodNode
from QSExt.LLMFactor.evaluation.evaluator import FactorEvaluator, EvalReport
from QSExt.LLMFactor.evaluation.report import generate_eval_report

# -*- coding: utf-8 -*-
"""Step 1 方向探索 Prompt 模板。

用于指导 LLM 综合知识库、已有因子库和历史挖掘记录，
提出有前景的候选研究方向。
"""

STEP1_SYSTEM = "你是一位资深量化因子研究策略师。分析当前研究状态，提出有前景的研究方向。"

STEP1_USER_TEMPLATE = """\
## 研究配置
- 目标因子类别: {target}
- 目标市场: {market}
- 数据频率: {frequency}
- 允许的数据域: {data_domains}
- 排除的数据域: {avoid_domains}

## 知识库检索结果（方法论）
{wiki_results}

## 已有因子库（同类因子）
{factor_results}

## 方向覆盖率（历史挖掘记录）
{coverage}

## 已知失败方向（需规避）
{failures}

## 任务
基于以上信息，提出 3~5 个候选研究方向。每个方向必须包含：
1. direction_tag: 方向标签（格式：类别/子方向）
2. category: 因子类别
3. description: 方向描述（100字以内）
4. rationale: 为什么这个方向有潜力（200字以内）
5. wiki_support: 支撑这个方向的知识库页面名列表
6. existing_factors: 参考的已有因子 QSID 列表
7. differentiation: 与已有因子的差异点

输出 JSON 数组，不要额外文字。
"""

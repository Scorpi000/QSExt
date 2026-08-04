# -*- coding: utf-8 -*-
"""Step 4 反思式规划 Prompt 模板。

包含两个阶段的提示词：
  - 批判阶段：对假设进行批判性审查
  - 精炼阶段：根据审查意见修正假设
"""

STEP4_CRITIQUE_SYSTEM = "你是严格的量化因子审查员。对假设进行批判性审查。"

STEP4_CRITIQUE_TEMPLATE = """\
## 待审查假设
{draft_yaml}

## 审查维度
1. **金融逻辑**：经济逻辑是否成立？是否有理论支撑？
2. **数据可行性**：所需数据字段是否全部在 JYDB 中可用？
3. **算子可实施性**：伪代码中的算子是否在 QuantStudio 中有对应实现？
4. **前瞻偏差风险**：是否存在隐含的未来信息使用？
5. **计算效率**：计算复杂度是否合理？

请输出 JSON：
```json
{{
  "critique_notes": "详细的审查意见",
  "issues": ["问题1", "问题2", ...],
  "risk_level": "low/medium/high"
}}
```
"""

STEP4_REFINE_SYSTEM = "你是量化因子研究专家。根据审查意见修正假设。"

STEP4_REFINE_TEMPLATE = """\
## 原始假设
{draft_yaml}

## 审查意见
{critique_notes}

## 发现的问题
{issues}

## 任务
根据审查意见修正假设，保留合理的部分，修正有问题的部分。
输出修正后的完整 YAML 格式假设文档（格式与原始假设相同）。
只输出 YAML，不要额外文字。
"""

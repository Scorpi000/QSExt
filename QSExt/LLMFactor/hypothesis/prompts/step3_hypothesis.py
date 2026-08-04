# -*- coding: utf-8 -*-
"""Step 3 假设生成 Prompt 模板。

用于指导 LLM 基于调研摘要生成创新的因子研究假设，
包含五种多样化模式的指令注入。
"""

STEP3_SYSTEM = "你是量化因子研究专家。基于调研摘要，生成创新的因子研究假设。"

STEP3_USER_TEMPLATE = """\
## 调研摘要

### 方法论参考
{wiki_results}

### 相近因子代码参考
{factor_code_snippets}

### 可用数据字段
{data_field_availability}

### 成功经验（few-shot 范例）
{successful_patterns}

### 历史教训（需规避）
{failure_lessons}

### 需规避的频繁结构
{forbidden_patterns}

## 创新指导
从以下四个角度之一出发生成假设：
- 文献驱动：借鉴学术论文中的因子构造逻辑
- 案例变异：基于成功因子的逻辑做变异/组合
- 数据驱动：基于可用数据字段提出新的因子构造
- 反事实推理：已有因子失效场景的补集

## 多样化指令（{div_mode} 模式）
{div_instruction}

## 输出要求
请输出严格的 YAML 格式，包含以下字段：

```yaml
hypothesis_id: "hyp_YYYYMMDD_NNN"
factor_name: "因子英文名"
category: "因子类别（动量/估值/质量/波动率等）"
market: "A股"
frequency: "日频"
economic_rationale: |
  经济逻辑描述（必须包含知识库引用 [[page_name]]）
calculation_pseudo: |
  ## 输入
  - 字段说明
  ## 计算步骤
  ### Step 1: ...
  （算子级别的伪代码）
data_requirements:
  fields:
    - name: "字段名"
      dtype: "float64"
      frequency: "日频"
      description: "字段说明"
  universe: "股票池"
  lookback_range: [min, max]
operator_suggestions: ["Lag", "RollingMean", ...]
expected_characteristics:
  ic_sign: "positive/negative"
  ic_magnitude: "0.03-0.06"
  icir: "> 0.5"
  turnover: "描述"
  market_cap_bias: "描述"
  expected_incremental_ic: "描述"
  susceptible_to: "描述"
novelty_rationale: "与已有因子的差异说明"
references: ["[[wiki_page_1]]", "[[wiki_page_2]]"]
forbidden_patterns: ["频繁结构1", "频繁结构2"]
```

只输出 YAML，不要额外文字。
"""

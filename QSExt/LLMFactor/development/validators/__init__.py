# -*- coding: utf-8 -*-
"""五 Agent 验证流水线。

各验证器职责：
  - Agent A (syntax_validator): 语法检查
  - Agent B (execution_validator): 执行验证
  - Agent C (leak_validator): 未来信息泄漏检测
  - Agent D (unit_validator): 单位检查
  - Agent E (semantic_validator): 语义审查 (LLM)
"""

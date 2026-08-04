# -*- coding: utf-8 -*-
"""Step 1: 因子代码生成器。

将假设文档转化为 QuantStudio 框架下可执行的因子定义代码。

职责：
    1. 检索经验库中的可复用组件（通过 MiningLogRetriever）
    2. 获取参考因子代码（通过 qs-registry MCP）
    3. 构建代码生成 prompt 并调用 LLM
    4. 解析 LLM 输出为 GeneratedCode
    5. 根据验证失败报告修复代码

使用示例::

    from QSExt.LLMFactor.development.code_generator import CodeGenerator
    from QSExt.LLMFactor.development.config import DevelopmentConfig

    config = DevelopmentConfig()
    generator = CodeGenerator(config)

    # 生成代码
    result = generator.generate(hypothesis_dict)

    # 修复代码
    fixed_code = generator.fix(code, hypothesis_dict, failed_validators)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import GeneratedCode
from QSExt.LLMFactor.development.prompts.code_generation import (
    SYSTEM_PROMPT,
    build_fix_prompt,
    build_generation_prompt,
    build_semantic_review_prompt,
)

__QS_Logger__ = logging.getLogger("QSR.development.code_generator")


class CodeGenerator:
    """因子代码生成器。

    将假设文档转化为 QuantStudio 因子定义代码，支持自动修复。

    Attributes:
        config: 开发配置
        llm: LangChain ChatModel 实例
        retriever: 经验检索器（可选）
    """

    def __init__(self, config: DevelopmentConfig):
        self.config = config
        self._llm = None
        self._retriever = None

    @property
    def llm(self):
        """懒加载 LLM 实例。"""
        if self._llm is None:
            from QSExt.LLMFactor.mining_log.llm_client import create_llm
            self._llm = create_llm(
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
            )
        return self._llm

    @property
    def retriever(self):
        """懒加载经验检索器。"""
        if self._retriever is None:
            try:
                from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever
                self._retriever = MiningLogRetriever()
            except Exception as e:
                __QS_Logger__.warning(f"无法初始化 MiningLogRetriever: {e}")
        return self._retriever

    def generate(self, hypothesis: dict) -> GeneratedCode:
        """从假设文档生成因子代码。

        Args:
            hypothesis: HypothesisDoc.to_development_input() 的输出

        Returns:
            GeneratedCode 包含代码、搜索空间、元数据
        """
        __QS_Logger__.info(f"开始生成因子代码: {hypothesis.get('factor_name', 'unknown')}")

        # 1. 检索相关经验组件
        components = self._retrieve_components(hypothesis)
        if components:
            __QS_Logger__.info(f"检索到 {len(components)} 个相关经验组件")

        # 2. 获取参考因子代码
        ref_codes = self._get_reference_codes(hypothesis)
        if ref_codes:
            __QS_Logger__.info(f"获取到 {len(ref_codes)} 个参考因子代码")

        # 3. 构建 prompt
        user_prompt = build_generation_prompt(hypothesis, components, ref_codes)

        # 4. 调用 LLM
        response = self._call_llm(SYSTEM_PROMPT, user_prompt)

        # 5. 解析输出
        result = self._parse_generation_response(response, hypothesis)
        __QS_Logger__.info(
            f"代码生成完成: {result.factor_module_name}, "
            f"搜索空间参数: {len(result.search_space)} 个"
        )
        return result

    def fix(self, code: str, hypothesis: dict, failed_validators: list[dict]) -> str:
        """根据验证失败报告修复代码。

        Args:
            code: 当前因子代码
            hypothesis: 原始假设文档
            failed_validators: 失败的验证器信息
                [{"name": "syntax", "issues": ["..."]}, ...]

        Returns:
            修复后的代码
        """
        __QS_Logger__.info(f"开始修复代码，失败验证器: {[v['name'] for v in failed_validators]}")

        prompt = build_fix_prompt(code, hypothesis, failed_validators)
        response = self._call_llm(SYSTEM_PROMPT, prompt)
        fixed_code = self._extract_code(response)

        if not fixed_code:
            __QS_Logger__.warning("修复后未提取到代码，返回原始代码")
            return code

        __QS_Logger__.info(f"代码修复完成，长度: {len(fixed_code)} 字符")
        return fixed_code

    def review(self, code: str, hypothesis: dict) -> str:
        """语义审查。

        Args:
            code: 因子代码
            hypothesis: 假设文档

        Returns:
            审查意见文本
        """
        prompt = build_semantic_review_prompt(code, hypothesis)
        response = self._call_llm(SYSTEM_PROMPT, prompt)
        return self._extract_review(response)

    # ============================================================
    # 经验检索
    # ============================================================

    def _retrieve_components(self, hypothesis: dict) -> list[dict]:
        """检索与当前假设相关的成功组件。"""
        if not self.retriever:
            return []

        try:
            category = hypothesis.get("category", "")
            description = hypothesis.get("factor_description", "")

            # 按类别检索成功组件
            components = self.retriever.get_successful_components(
                direction=category,
                min_quality=0.7,
                limit=5,
            )

            # 转为统一格式
            result = []
            for comp in components:
                result.append({
                    "name": getattr(comp, "name", ""),
                    "code": getattr(comp, "content", ""),
                    "description": getattr(comp, "description", ""),
                    "type": getattr(comp, "type", ""),
                })

            return result
        except Exception as e:
            __QS_Logger__.warning(f"检索经验组件失败: {e}")
            return []

    def _get_reference_codes(self, hypothesis: dict) -> list[dict]:
        """获取参考因子代码。"""
        # 尝试通过 qs-registry 获取已有因子代码
        try:
            from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever
            if not self.retriever:
                return []

            # 搜索同类别的已入库因子
            category = hypothesis.get("category", "")
            similar = self.retriever.search_similar_accepted(
                query=f"{category} {hypothesis.get('factor_description', '')}",
                limit=3,
            )

            result = []
            for run in similar:
                code = getattr(run, "code", None) or run.metadata.get("code", "")
                if code:
                    result.append({
                        "name": getattr(run, "factor_name", "") or run.metadata.get("factor_name", ""),
                        "code": code,
                        "description": getattr(run, "description", "") or run.metadata.get("description", ""),
                    })
            return result
        except Exception as e:
            __QS_Logger__.warning(f"获取参考因子代码失败: {e}")
            return []

    # ============================================================
    # LLM 调用
    # ============================================================

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM。

        Args:
            system_prompt: 系统 prompt
            user_prompt: 用户 prompt

        Returns:
            LLM 响应文本
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        __QS_Logger__.debug(f"调用 LLM: {self.config.llm_model}")
        response = self.llm.invoke(messages)
        return response.content

    # ============================================================
    # 输出解析
    # ============================================================

    def _parse_generation_response(self, response: str, hypothesis: dict) -> GeneratedCode:
        """解析 LLM 代码生成响应。

        Args:
            response: LLM 响应文本
            hypothesis: 原始假设文档

        Returns:
            GeneratedCode
        """
        # 提取三部分
        factor_code = self._extract_section(response, "FACTOR_CODE")
        search_space_str = self._extract_section(response, "SEARCH_SPACE")
        metadata_str = self._extract_section(response, "METADATA")

        # 解析 search_space
        search_space = self._parse_json(search_space_str or "{}", "search_space")

        # 解析 metadata
        metadata = self._parse_json(metadata_str or "{}", "metadata")

        # 补充 metadata 缺失字段
        metadata = self._fill_metadata(metadata, hypothesis)

        # 确定模块名
        factor_name = metadata.get("factor_name", hypothesis.get("factor_name", "unknown_factor"))
        module_name = self._to_module_name(factor_name)

        # DAG 描述（从代码中提取注释）
        dag_description = self._extract_dag_description(factor_code)

        return GeneratedCode(
            factor_code=factor_code or "",
            factor_module_name=module_name,
            search_space=search_space,
            metadata=metadata,
            dag_description=dag_description,
        )

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """从 LLM 输出中提取指定 section。

        格式: ===SECTION_NAME=== ... ===
        """
        pattern = rf"==={section_name}===\s*\n(.*?)(?=\n===|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 兜底：尝试从 markdown 代码块中提取
        if section_name == "FACTOR_CODE":
            code = self._extract_code(text)
            if code:
                return code

        return None

    def _extract_code(self, text: str) -> Optional[str]:
        """从文本中提取 Python 代码块。"""
        # 尝试提取 ```python ... ``` 代码块
        pattern = r"```python\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试提取 ``` ... ``` 代码块
        pattern = r"```\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果整个文本看起来像 Python 代码
        if "def defFactor" in text or "import " in text:
            # 剥离 ===...=== 标记前缀
            cleaned = re.sub(r"^===\w+===\s*\n?", "", text.strip())
            return cleaned.strip() if cleaned else None

        return None

    def _extract_review(self, text: str) -> str:
        """提取审查意见。"""
        section = self._extract_section(text, "REVIEW")
        if section:
            return section
        return text.strip()

    def _parse_json(self, text: str, context: str) -> dict:
        """解析 JSON 字符串。"""
        # 清理可能的 markdown 代码块标记
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        if not cleaned or cleaned == "{}":
            return {}

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            __QS_Logger__.warning(f"JSON 解析失败 ({context}): {e}")
            return {}

    def _fill_metadata(self, metadata: dict, hypothesis: dict) -> dict:
        """补充 metadata 缺失字段。"""
        defaults = {
            "factor_name": hypothesis.get("factor_name", "unknown_factor"),
            "category": hypothesis.get("category", ""),
            "market": hypothesis.get("market", "A股"),
            "frequency": hypothesis.get("frequency", "日频"),
            "description": hypothesis.get("factor_description", ""),
            "formula": hypothesis.get("formula", ""),
            "data_sources": {},
            "hypothesis_id": hypothesis.get("hypothesis_id"),
            "qsid": None,
            "status": "developed",
            "tags": [hypothesis.get("category", "")],
        }
        for key, default_val in defaults.items():
            if key not in metadata or not metadata[key]:
                metadata[key] = default_val

        # 确保 DefScriptPath 是占位符（实际路径在保存时设置）
        if "DefScriptPath" not in metadata:
            metadata["DefScriptPath"] = "__file__"

        return metadata

    def _to_module_name(self, factor_name: str) -> str:
        """将因子名称转为合法的 Python 模块名。"""
        # 替换非字母数字字符为下划线
        name = re.sub(r"[^a-zA-Z0-9_]", "_", factor_name.lower())
        # 去除连续下划线
        name = re.sub(r"_+", "_", name).strip("_")
        return name or "unknown_factor"

    def _extract_dag_description(self, code: str) -> str:
        """从代码注释中提取 DAG 描述。"""
        if not code:
            return ""
        # 提取以 # ---- 开头的注释块
        comments = re.findall(r"#\s*----\s*(.+?)\s*----", code)
        if comments:
            return " → ".join(comments)
        return ""

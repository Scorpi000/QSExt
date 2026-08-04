# -*- coding: utf-8 -*-
"""LangGraph 图节点实现（异步版本）。

包含假设生成流程中的所有节点：
  - explore_node: Step 1 方向探索（LLM 节点）
  - research_node: Step 2 深度调研（工具节点）
  - generate_node: Step 3 假设生成（LLM 节点）
  - reflect_node: Step 4a 反思批判（LLM 节点）
  - refine_node: Step 4b 精炼修正（LLM 节点）
  - check_node: Step 4c 新颖性校验（工具节点）
  - log_node: 记录到挖掘日志库（工具节点）

通过 langchain-mcp-adapters 直接调用 MCP 工具，无需 Python 桥接层。
所有节点均为异步函数，因为 MCP 工具只支持异步调用。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from QSExt import __QS_MainPath__
from QSExt.LLMFactor.hypothesis.graph.state import HypothesisState
from QSExt.LLMFactor.hypothesis.prompts.step1_direction import (
    STEP1_SYSTEM,
    STEP1_USER_TEMPLATE,
)
from QSExt.LLMFactor.hypothesis.prompts.step3_hypothesis import (
    STEP3_SYSTEM,
    STEP3_USER_TEMPLATE,
)
from QSExt.LLMFactor.hypothesis.prompts.step4_reflection import (
    STEP4_CRITIQUE_SYSTEM,
    STEP4_CRITIQUE_TEMPLATE,
    STEP4_REFINE_SYSTEM,
    STEP4_REFINE_TEMPLATE,
)
from QSExt.LLMFactor.hypothesis.divmode import DiversityModeSelector

logger = logging.getLogger(__name__)

# 加载环境变量
_ENV_FILE = os.path.join(__QS_MainPath__,"config",".env")
if os.path.isfile(_ENV_FILE):
    load_dotenv(_ENV_FILE)


# ============================================================
# MCP 工具管理器
# ============================================================

class MCPToolManager:
    """MCP 工具管理器。

    通过 langchain-mcp-adapters 连接 MCP servers，缓存工具列表，
    提供按名称调用工具的能力。
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}
        self._initialized = False

    def _load_connections(self) -> dict:
        """从 .mcp.json 加载 MCP server 连接配置。"""
        project_root = Path(__QS_MainPath__).parent
        mcp_json = project_root / ".mcp.json"
        if not mcp_json.exists():
            mcp_json = project_root / ".mcp.json.example"
        if not mcp_json.exists():
            logger.warning("未找到 .mcp.json 配置文件")
            return {}

        with open(mcp_json, "r", encoding="utf-8") as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        connections = {}

        for name, server_config in servers.items():
            if server_config.get("type") == "streamable-http":
                connections[name] = {
                    "url": server_config["url"],
                    "transport": "streamable_http",
                }
                if "headers" in server_config:
                    connections[name]["headers"] = server_config["headers"]
            elif "command" in server_config:
                conn = {
                    "command": server_config["command"],
                    "args": server_config.get("args", []),
                    "transport": "stdio",
                }
                if "env" in server_config:
                    conn["env"] = server_config["env"]
                if "cwd" in server_config:
                    conn["cwd"] = server_config["cwd"]
                connections[name] = conn

        return connections

    async def initialize(self):
        """异步初始化 MCP 客户端和工具。

        逐个连接 MCP server，失败的跳过，确保一个 server 故障不影响其他。
        """
        if self._initialized:
            return

        from langchain_mcp_adapters.client import MultiServerMCPClient

        connections = self._load_connections()
        if not connections:
            logger.warning("无 MCP 连接配置")
            self._initialized = True
            return

        for name, conn_config in connections.items():
            try:
                logger.info("连接 MCP server: %s", name)
                client = MultiServerMCPClient({name: conn_config})
                tools = await client.get_tools()
                for tool in tools:
                    self._tools[tool.name] = tool
                    logger.debug("加载 MCP 工具: %s", tool.name)
                logger.info("  → 成功加载 %d 个工具", len(tools))
            except Exception as e:
                logger.warning("  → 连接失败，跳过: %s", e)

        logger.info("MCP 初始化完成，共加载 %d 个工具", len(self._tools))
        self._initialized = True

    def get_tool(self, name: str):
        """获取指定名称的 MCP 工具。"""
        return self._tools.get(name)

    async def call_tool(self, name: str, **kwargs) -> Any:
        """异步调用指定名称的 MCP 工具。"""
        if not self._initialized:
            await self.initialize()
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("MCP 工具未找到: %s", name)
            return None
        return await tool.ainvoke(kwargs)


# 全局 MCP 工具管理器
_mcp_manager = MCPToolManager()


async def _call_mcp(tool_name: str, **kwargs) -> Any:
    """调用 MCP 工具的便捷函数。"""
    logger.debug("调用 MCP 工具: %s", tool_name)
    return await _mcp_manager.call_tool(tool_name, **kwargs)


# ============================================================
# LLM 工厂
# ============================================================

def _create_llm(temperature: float = 0.5):
    """创建 LLM 实例。"""
    from langchain_openai import ChatOpenAI

    provider = os.getenv("LLM_PROVIDER","openai").lower()

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL","http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY","ollama")
        model = os.getenv("OLLAMA_MODEL","qwen3:8b")
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
        )
    else:
        base_url = os.getenv("LLM_BASE_URL","")
        api_key = os.getenv("LLM_API_KEY","")
        model = os.getenv("LLM_MODEL","gpt-4o")
        kwargs = {"model": model,"temperature": temperature}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)


# ============================================================
# 辅助函数
# ============================================================

def _format_list(items: list, key: str = "") -> str:
    """格式化列表为可读字符串。"""
    if not items:
        return "（无）"
    if isinstance(items[0], dict):
        return "\n".join(f"- {json.dumps(item, ensure_ascii=False)}" for item in items)
    return "\n".join(f"- {item}" for item in items)


def _extract_json(text: str) -> dict | list:
    """从 LLM 输出中提取 JSON。"""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def _extract_yaml(text: str) -> str:
    """从 LLM 输出中提取 YAML 字符串。"""
    cleaned = text.strip()
    if cleaned.startswith("```yaml"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# ============================================================
# Step 1: 方向探索节点（LLM）
# ============================================================

async def explore_node(state: HypothesisState) -> dict:
    """Step 1: 方向探索节点。

    LLM 综合知识库、已有因子库和历史挖掘记录，提出候选研究方向。
    """
    logger.info("=== Step 1: 方向探索 ===")
    config = state["config"]
    target = config.get("target", "")

    # 1. 检索知识库
    wiki_results = await _call_mcp(
        "hybrid_search",
        kb_id=os.getenv("WEKNORA_KB_ID", ""),
        query=f"{target} 因子构造方法论",
        match_count=5,
    )
    wiki_text = _format_list(wiki_results if isinstance(wiki_results, list) else [])

    # 2. 检索已有因子库
    factor_results = await _call_mcp(
        "search_factors",
        query=target,
        limit=10,
    )
    factor_text = _format_list(factor_results if isinstance(factor_results, list) else [])

    # 3. 检索历史挖掘记录
    coverage = await _call_mcp("get_direction_coverage")
    coverage_text = _format_list(coverage.get("items", []) if isinstance(coverage, dict) else [])

    failures = await _call_mcp(
        "get_failure_lessons",
        query=target,
        limit=5,
    )
    failure_text = _format_list(failures.get("items", []) if isinstance(failures, dict) else [])

    # 4. LLM 综合分析
    user_msg = STEP1_USER_TEMPLATE.format(
        target=target,
        market=config.get("market", "A股"),
        frequency=config.get("frequency", "日频"),
        data_domains=_format_list(config.get("data_domains", [])),
        avoid_domains=_format_list(config.get("avoid_domains", [])),
        wiki_results=wiki_text,
        factor_results=factor_text,
        coverage=coverage_text,
        failures=failure_text,
    )

    llm = _create_llm(temperature=0.5)
    response = await llm.ainvoke([
        SystemMessage(content=STEP1_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    # 5. 解析结果
    try:
        candidates = _extract_json(response.content)
        if not isinstance(candidates, list):
            candidates = [candidates]
    except (json.JSONDecodeError, TypeError):
        logger.warning("LLM 输出解析失败，使用空列表")
        candidates = []

    logger.info("提出 %d 个候选方向", len(candidates))
    return {"candidates": candidates, "current_candidate_idx": 0}


# ============================================================
# Step 2: 深度调研节点（工具）
# ============================================================

async def research_node(state: HypothesisState) -> dict:
    """Step 2: 深度调研节点。

    纯确定性工具调用，对当前候选方向做全面信息收集。
    """
    logger.info("=== Step 2: 深度调研 ===")
    candidates = state.get("candidates", [])
    idx = state.get("current_candidate_idx", 0)

    if idx >= len(candidates):
        logger.warning("无候选方向可调研")
        return {"research_context": None}

    candidate = candidates[idx]
    direction_tag = candidate.get("direction_tag", "")
    description = candidate.get("description", "")
    query = f"{direction_tag} {description}"
    target = state["config"].get("target", "")

    logger.info("调研方向: %s", direction_tag)

    # 1. 知识库深度阅读
    wiki_pages = candidate.get("wiki_support", [])
    wiki_results = []
    for page in wiki_pages[:5]:
        page_content = await _call_mcp(
            "wiki_read_page",
            kb_id=os.getenv("WEKNORA_KB_ID", ""),
            slug=page,
        )
        if page_content:
            wiki_results.append(page_content)

    # 如果没有指定页面，用搜索补充
    if not wiki_results:
        search_results = await _call_mcp(
            "hybrid_search",
            kb_id=os.getenv("WEKNORA_KB_ID", ""),
            query=query,
            match_count=3,
        )
        if isinstance(search_results, list):
            for r in search_results:
                slug = r.get("slug", r.get("page_name", ""))
                if slug:
                    page_content = await _call_mcp(
                        "wiki_read_page",
                        kb_id=os.getenv("WEKNORA_KB_ID", ""),
                        slug=slug,
                    )
                    if page_content:
                        wiki_results.append(page_content)

    # 2. 因子代码
    factor_codes = []
    for qsid in candidate.get("existing_factor_qsids", [])[:3]:
        code_result = await _call_mcp("get_factor_code", qsid=qsid)
        if code_result:
            factor_codes.append({"qsid": qsid, "code": code_result})

    # 3. 数据字段可用性（jy_base_doc 可能不可用）
    data_fields = []
    try:
        keywords = [t for t in target.split("因子") if t]
        for kw in keywords[:2]:
            tables = await _call_mcp("search_table_list", query=kw, n_table=3)
            if isinstance(tables, dict):
                for t in tables.get("items", tables.get("results", [])):
                    table_name = t.get("table_name", "")
                    if table_name:
                        table_info = await _call_mcp("query_table", table=table_name)
                        if table_info:
                            data_fields.append(table_info)
    except Exception as e:
        logger.warning("数据字段查询失败（jy_base_doc 可能不可用）: %s", e)

    # 4. 历史记录
    successful_patterns_result = await _call_mcp(
        "get_successful_components",
        direction=direction_tag,
        limit=5,
    )
    successful_patterns = successful_patterns_result.get("items", []) if isinstance(successful_patterns_result, dict) else []

    failure_lessons_result = await _call_mcp(
        "get_failure_lessons",
        direction=direction_tag,
        limit=5,
    )
    failure_lessons = failure_lessons_result.get("items", []) if isinstance(failure_lessons_result, dict) else []

    # 构建调研上下文
    research_context = {
        "direction": candidate,
        "wiki_results": wiki_results,
        "factor_code_snippets": factor_codes,
        "data_field_availability": data_fields,
        "successful_patterns": successful_patterns,
        "failure_lessons": failure_lessons,
        "frequent_patterns": [],
        "exploration_trail": [
            {
                "step": "research",
                "direction": direction_tag,
                "timestamp": datetime.now().isoformat(),
                "wiki_pages_found": len(wiki_results),
                "factor_codes_found": len(factor_codes),
                "data_fields_found": len(data_fields),
            }
        ],
    }

    logger.info(
        "调研完成: wiki=%d, 因子代码=%d, 数据字段=%d",
        len(wiki_results), len(factor_codes), len(data_fields),
    )
    return {"research_context": research_context}


# ============================================================
# Step 3: 假设生成节点（LLM）
# ============================================================

async def generate_node(state: HypothesisState) -> dict:
    """Step 3: 假设生成节点。

    LLM 基于调研摘要生成因子研究假设。
    """
    logger.info("=== Step 3: 假设生成 ===")
    context = state.get("research_context", {})
    if not context:
        logger.warning("无调研上下文，跳过假设生成")
        return {"draft_hypothesis": None}

    # 选择多样化模式
    selector = DiversityModeSelector()
    mode = selector.select()
    temperature = selector.get_temperature(mode)
    instruction = selector.get_instruction(mode)
    logger.info("多样化模式: %s (温度 %.1f)", mode.value, temperature)

    # 格式化调研上下文
    wiki_text = _format_list(context.get("wiki_results", []))
    code_text = _format_list(context.get("factor_code_snippets", []))
    fields_text = _format_list(context.get("data_field_availability", []))
    success_text = _format_list(context.get("successful_patterns", []))
    failure_text = _format_list(context.get("failure_lessons", []))
    forbidden_text = _format_list(context.get("frequent_patterns", []))

    user_msg = STEP3_USER_TEMPLATE.format(
        wiki_results=wiki_text,
        factor_code_snippets=code_text,
        data_field_availability=fields_text,
        successful_patterns=success_text,
        failure_lessons=failure_text,
        forbidden_patterns=forbidden_text,
        div_mode=mode.value,
        div_instruction=instruction,
    )

    llm = _create_llm(temperature=temperature)
    response = await llm.ainvoke([
        SystemMessage(content=STEP3_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    yaml_str = _extract_yaml(response.content)
    logger.info("假设草稿生成完成")
    return {"draft_hypothesis": {"yaml": yaml_str, "raw_response": response.content}}


# ============================================================
# Step 4a: 反思批判节点（LLM）
# ============================================================

async def reflect_node(state: HypothesisState) -> dict:
    """Step 4a: 反思批判节点。

    LLM 对假设草稿进行批判性审查。
    """
    logger.info("=== Step 4a: 反思批判 ===")
    draft = state.get("draft_hypothesis", {})
    if not draft:
        logger.warning("无假设草稿，跳过批判")
        return {"critique": None}

    draft_yaml = draft.get("yaml", "")
    user_msg = STEP4_CRITIQUE_TEMPLATE.format(draft_yaml=draft_yaml)

    llm = _create_llm(temperature=0.3)
    response = await llm.ainvoke([
        SystemMessage(content=STEP4_CRITIQUE_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    try:
        critique = _extract_json(response.content)
    except (json.JSONDecodeError, TypeError):
        critique = {
            "critique_notes": response.content,
            "issues": [],
            "risk_level": "medium",
        }

    logger.info("批判完成，风险等级: %s", critique.get("risk_level", "unknown"))
    return {"critique": critique}


# ============================================================
# Step 4b: 精炼修正节点（LLM）
# ============================================================

async def refine_node(state: HypothesisState) -> dict:
    """Step 4b: 精炼修正节点。

    LLM 根据批判意见修正假设。
    """
    logger.info("=== Step 4b: 精炼修正 ===")
    draft = state.get("draft_hypothesis", {})
    critique = state.get("critique", {})

    if not draft or not critique:
        logger.warning("缺少草稿或批判结果，跳过精炼")
        return {"refined_hypothesis": None}

    user_msg = STEP4_REFINE_TEMPLATE.format(
        draft_yaml=draft.get("yaml", ""),
        critique_notes=critique.get("critique_notes", ""),
        issues=_format_list(critique.get("issues", [])),
    )

    llm = _create_llm(temperature=0.4)
    response = await llm.ainvoke([
        SystemMessage(content=STEP4_REFINE_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    refined_yaml = _extract_yaml(response.content)
    logger.info("精炼完成")
    return {"refined_hypothesis": {"yaml": refined_yaml, "raw_response": response.content}}


# ============================================================
# Step 4c: 新颖性校验节点（工具）
# ============================================================

async def check_node(state: HypothesisState) -> dict:
    """Step 4c: 新颖性校验节点。

    纯确定性检查，避免 LLM 自我确认偏差。
    """
    logger.info("=== Step 4c: 新颖性校验 ===")

    hypothesis = state.get("refined_hypothesis") or state.get("draft_hypothesis", {})
    if not hypothesis:
        logger.warning("无假设可校验")
        return {"novelty_result": {"passed": True, "warnings": [], "block_reason": None}}

    yaml_str = hypothesis.get("yaml", "")

    warnings = []
    block_reason = None
    similarity_scores = {}
    direction_overlap = []

    # 1. 搜索相似历史记录
    try:
        factor_name_match = re.search(r"factor_name:\s*[\"']?(\w+)", yaml_str)
        search_query = factor_name_match.group(1) if factor_name_match else yaml_str[:100]

        similar_result = await _call_mcp(
            "search_history",
            query=search_query,
            top_k=5,
        )
        similar_records = similar_result.get("items", []) if isinstance(similar_result, dict) else []

        for record in similar_records:
            if record.get("decision") == "accepted":
                score = 0.8
                similarity_scores[record.get("factor_name", "")] = score
                if score > 0.7:
                    warnings.append(
                        f"与已入库因子 {record.get('factor_name')} 高度相似 (score={score:.2f})"
                    )
    except Exception as e:
        logger.warning("搜索相似记录失败: %s", e)

    # 2. 检查失败方向重叠
    try:
        direction = state.get("research_context", {}).get("direction", {})
        direction_tag = direction.get("direction_tag", "")
        if direction_tag:
            failures_result = await _call_mcp(
                "get_failure_lessons",
                direction=direction_tag,
                limit=3,
            )
            failures = failures_result.get("items", []) if isinstance(failures_result, dict) else []
            for f in failures:
                direction_overlap.append(f.get("direction_tag", ""))
                warnings.append(f"与失败方向 {f.get('direction_tag')} 有重叠")
    except Exception as e:
        logger.warning("检查失败方向重叠失败: %s", e)

    # 3. 判断是否阻断
    high_similarity_count = sum(1 for s in similarity_scores.values() if s > 0.8)
    if high_similarity_count >= 2:
        block_reason = f"与 {high_similarity_count} 个已入库因子高度相似，缺乏差异化"

    passed = block_reason is None

    result = {
        "passed": passed,
        "warnings": warnings,
        "block_reason": block_reason,
        "similarity_scores": similarity_scores,
        "direction_overlap": direction_overlap,
    }

    if passed:
        if warnings:
            logger.info("新颖性校验通过，有 %d 条预警", len(warnings))
        else:
            logger.info("新颖性校验通过")
    else:
        logger.info("新颖性校验阻断: %s", block_reason)

    return {"novelty_result": result}


# ============================================================
# 记录节点（工具）
# ============================================================

async def log_node(state: HypothesisState) -> dict:
    """记录到挖掘日志库。"""
    logger.info("=== 记录假设 ===")

    hypothesis = state.get("refined_hypothesis") or state.get("draft_hypothesis", {})
    if not hypothesis:
        logger.warning("无假设可记录")
        return {}

    novelty = state.get("novelty_result", {})
    warnings = novelty.get("warnings", [])

    completed = {
        "yaml": hypothesis.get("yaml", ""),
        "direction": state.get("research_context", {}).get("direction", {}),
        "novelty_result": novelty,
        "warnings": warnings,
        "timestamp": datetime.now().isoformat(),
    }

    completed_hypotheses = state.get("completed_hypotheses", [])
    completed_hypotheses.append(completed)

    logger.info("假设已记录，共 %d 个完成的假设", len(completed_hypotheses))
    return {"completed_hypotheses": completed_hypotheses}


# ============================================================
# 辅助节点
# ============================================================

async def advance_candidate_node(state: HypothesisState) -> dict:
    """推进到下一个候选方向。"""
    idx = state.get("current_candidate_idx", 0) + 1
    logger.info("推进到候选方向 %d", idx)
    return {
        "current_candidate_idx": idx,
        "research_context": None,
        "draft_hypothesis": None,
        "critique": None,
        "refined_hypothesis": None,
        "novelty_result": None,
    }


async def skip_direction_node(state: HypothesisState) -> dict:
    """跳过当前方向（新颖性校验阻断时）。"""
    candidates = state.get("candidates", [])
    idx = state.get("current_candidate_idx", 0)
    direction = candidates[idx] if idx < len(candidates) else {}
    novelty = state.get("novelty_result", {})

    skipped = state.get("skipped_directions", [])
    skipped.append({
        "direction": direction,
        "reason": novelty.get("block_reason", "未知原因"),
        "timestamp": datetime.now().isoformat(),
    })

    logger.info("跳过方向: %s", direction.get("direction_tag", ""))
    return {"skipped_directions": skipped}

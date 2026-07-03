# -*- coding: utf-8 -*-
"""QSRegistry MCP Server — QuantStudio 计算图注册中心 MCP 服务

提供工具：
- search_factors: 语义/关键词检索因子
- get_factor_info: 查询因子详细信息
- get_factor_code: 返回因子定义 Python 源代码
- search_backtests: 按名称/类别/因子检索回测
- get_backtest_info: 查询回测详细信息及结果摘要
- get_backtest_result: 获取回测结果详细数据
- register_report: 注册报告文件
- search_reports: 搜索已注册报告
- get_report_info: 获取报告详细元信息
- search_risk_tables: 搜索风险表
- search_optimizers: 搜索组合优化器
"""
import os
import json
import re
import logging
from typing import Optional

from fastmcp import FastMCP

from QuantStudio.Core import setDefaultLogLevel
setDefaultLogLevel(logging.WARNING)
from QuantStudio.Core import __QS_Logger__
from QSExt.QSRegistry._serialization import _desanitizeFromJSON
from QSExt.QSRegistry.QSGraphDB import QSGraphDB


mcp = FastMCP("QSRegistry")
_GDB = None

# ─── 工具组管理 ──────────────────────────────────────────────

# 工具组定义：组名 → {工具函数名, ...}
_TOOL_GROUPS = {
    "factor": {
        "search_factors", "get_factor_info", "get_factor_code",
    },
    "backtest": {
        "search_backtests", "get_backtest_info", "get_backtest_result",
    },
    "report": {
        "register_report", "search_reports", "get_report_info",
    },
    "risk_table": {
        "search_risk_tables", "get_risk_table_info",
    },
    "optimizer": {
        "search_optimizers", "get_optimizer_info",
    },
}

_ALL_TOOLS = set().union(*_TOOL_GROUPS.values())


def _parse_tool_filter(raw: str) -> set:
    """解析 QS_TOOLS 环境变量，返回应启用的工具名集合。

    QS_TOOLS 格式：
      - 空 / "all": 全部启用
      - "factor,backtest": 仅启用指定组
      - "-report,-risk_table": 排除指定组

    每个 token 以 "-" 开头表示排除，否则表示包含。
    包含和排除的组名不能混用。
    """
    if not raw or raw.strip().lower() == "all":
        return _ALL_TOOLS.copy()

    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        return _ALL_TOOLS.copy()

    includes = [t for t in tokens if not t.startswith("-")]
    excludes = [t[1:] for t in tokens if t.startswith("-")]

    if includes and excludes:
        raise ValueError(
            f"QS_TOOLS 不能同时包含启用和排除: {raw}"
            "（要么全用 'group1,group2'，要么全用 '-group1,-group2'）"
        )

    if includes:
        enabled = set()
        for group in includes:
            if group not in _TOOL_GROUPS:
                raise ValueError(
                    f"未知工具组 '{group}'，可选: {list(_TOOL_GROUPS.keys())}"
                )
            enabled.update(_TOOL_GROUPS[group])
        return enabled

    if excludes:
        enabled = _ALL_TOOLS.copy()
        for group in excludes:
            if group not in _TOOL_GROUPS:
                raise ValueError(
                    f"未知工具组 '{group}'，可选: {list(_TOOL_GROUPS.keys())}"
                )
            enabled.difference_update(_TOOL_GROUPS[group])
        return enabled

    return _ALL_TOOLS.copy()


def _get_enabled_tools() -> set:
    """获取当前应启用的工具名集合（幂等，结果缓存）"""
    if _get_enabled_tools._cache is not None:
        return _get_enabled_tools._cache
    raw = os.getenv("QS_TOOLS", "all")
    _get_enabled_tools._cache = _parse_tool_filter(raw)
    # 日志输出启用的组
    enabled_groups = [g for g, tools in _TOOL_GROUPS.items()
                      if _get_enabled_tools._cache & tools]
    if not enabled_groups:
        __QS_Logger__.warning("QS_TOOLS: 未启用任何工具")
    else:
        __QS_Logger__.info(f"QS_TOOLS 启用组: {enabled_groups}")
    return _get_enabled_tools._cache


_get_enabled_tools._cache = None


def _get_gdb():
    """懒加载 QSGraphDB 单例"""
    global _GDB
    if _GDB is not None:
        return _GDB
    
    # 加载 Neo4j 配置
    neo4j_cfg = _load_neo4j_config()
    if neo4j_cfg is None:
        raise RuntimeError("无法加载 Neo4j 配置: ~/QuantStudioConfig/Neo4jDBConfig.json 不存在")
    neo4j_args = {
        "IPAddr": neo4j_cfg["IPAddr"],
        "Port": neo4j_cfg["Port"],
        "User": neo4j_cfg["User"],
        "Pwd": neo4j_cfg["Pwd"],
        "DBName": neo4j_cfg.get("DBName", "neo4j"),
        "OllamaBaseURL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OllamaAPIKey": os.getenv("OLLAMA_API_KEY", "ollama"),
        "EmbeddingModel": os.getenv("EMBEDDING_MODEL", "bge-m3"),
    }
    # 根据模型设置维度
    model = neo4j_args["EmbeddingModel"]
    if model == "bge-m3":
        neo4j_args["EmbeddingDim"] = 1024
    elif model == "qwen3-embedding:8b":
        neo4j_args["EmbeddingDim"] = 4096

    _GDB = QSGraphDB(args=neo4j_args)
    _GDB.connect()
    __QS_Logger__.info("QSRegistry MCP: QSGraphDB 已连接")
    return _GDB


def _load_neo4j_config() -> Optional[dict]:
    """加载 Neo4j 连接配置"""
    config_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
    if not os.path.exists(config_path):
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r",\s*([}\]])", r"\1", content)
    return json.loads(content)


def _parse_meta_json(meta_json_str: Optional[str]) -> dict:
    """安全解析 MetaJSON 字符串"""
    if not meta_json_str:
        return {}
    try:
        return _desanitizeFromJSON(json.loads(meta_json_str))
    except Exception:
        return {}


def _format_factor(f: dict, similarity: Optional[float] = None) -> dict:
    """格式化因子节点为统一输出格式"""
    result = {
        "name": f.get("Name", ""),
        "qsid": f.get("QSID", ""),
        "factor_class": f.get("FactorClass", ""),
        "data_type": f.get("DataType", ""),
        "operator_type": f.get("OperatorType", ""),
        "operator_name": f.get("OperatorName", ""),
    }
    if similarity is not None:
        result["similarity"] = similarity
    return result


# ─── MCP Tools ──────────────────────────────────────────────

def search_factors(query: str, limit: int = 20) -> list[dict]:
    """搜索因子列表。使用语义向量检索（若启用）或关键词匹配。

    Args:
        query: 查询文本，如 "动量因子"、"成交量相关"、"财务质量"
        limit: 返回结果数量上限，默认 20

    Returns:
        匹配的因子列表 [{name, qsid, factor_class, operator_type, data_type, similarity}]
    """
    gdb = _get_gdb()
    vector_results = []
    if gdb._QSArgs.EmbeddingModel:
        try:
            vector_results = gdb.searchFactorsByDescription(query, limit=limit)
        except Exception as e:
            __QS_Logger__.warning(f"向量检索失败，回退到关键词检索: {e}")
    # 关键词检索回退
    keyword_results = gdb.searchFactors(name=query, limit=limit)
    # 合并结果：向量结果优先
    seen = set()
    formatted = []
    for r in vector_results:
        item = _format_factor(r, similarity=r.get("Similarity"))
        formatted.append(item)
        seen.add(item["qsid"])
    for r in keyword_results:
        item = _format_factor(r)
        if item["qsid"] not in seen:
            formatted.append(item)
            seen.add(item["qsid"])
    return formatted[:limit]


def get_factor_info(qsid: str) -> dict:
    """查询因子的详细信息，包括名称、描述、数据类型、算子信息、依赖关系等。

    Args:
        qsid: 因子的 QSID（唯一标识符）

    Returns:
        因子详细信息字典，包含:
        - name, qsid, factor_class, data_type, module_path
        - description: 因子描述文本
        - operator_name, operator_type: 算子信息（仅 DerivativeFactor）
        - meta: 用户自定义元信息
        - descriptors: 直接依赖因子列表 [{name, qsid}]
        - dependents: 直接下游因子列表 [{name, qsid}]
        - dependency_depth: 依赖链深度
        - tags: 标签列表
    """
    gdb = _get_gdb()
    node = gdb.getFactorByQSID(qsid)
    if node is None:
        return {"error": f"未找到 QSID 为 {qsid} 的因子"}

    desc = gdb.getDescriptors(qsid)
    deps = gdb.getDependents(qsid, transitive=False)

    # 获取描述文本
    description = ""
    meta = _parse_meta_json(node.get("MetaJSON"))
    if isinstance(meta, dict):
        description = meta.get("Description", "")
    if not description:
        qs_args = _parse_meta_json(node.get("QSArgsJSON"))
        if isinstance(qs_args, dict):
            description = qs_args.get("Description", "")

    # 获取依赖深度
    dep_graph = gdb.getDependencyGraph(qsid, direction="down")
    depth = max((e.get("order", 0) for e in dep_graph.get("edges", [])), default=0)

    # 获取标签
    tags = []
    try:
        tag_results = gdb._runCypher(
            "MATCH (f:`因子` {QSID: $qsid})-[:`打标签`]->(t:`标签`) RETURN t.Name",
            {"qsid": qsid}
        )
        tags = [t["t.Name"] for t in tag_results]
    except Exception:
        pass

    return {
        "name": node.get("Name", ""),
        "qsid": node.get("QSID", qsid),
        "factor_class": node.get("FactorClass", ""),
        "data_type": node.get("DataType", ""),
        "module_path": node.get("ModulePath", ""),
        "description": description,
        "operator_name": node.get("OperatorName", ""),
        "operator_type": node.get("OperatorType", ""),
        "operator_qsid": node.get("OperatorQSID", ""),
        "meta": {k: str(v) for k, v in meta.items()} if isinstance(meta, dict) else {},
        "descriptors": [{"name": d.get("Name", ""), "qsid": d.get("QSID", "")} for d in desc],
        "dependents": [{"name": d.get("Name", ""), "qsid": d.get("QSID", "")} for d in deps],
        "dependency_depth": depth,
        "tags": tags,
    }


def get_factor_code(qsid: str) -> dict:
    """返回定义该因子的 Python 源代码。通过因子表追溯到 DefScriptPath 并读取文件。

    Args:
        qsid: 因子的 QSID（唯一标识符）

    Returns:
        {qsid, factor_name, script_path, source_code}
        若无法定位脚本，返回 {error: "..."}
    """
    gdb = _get_gdb()
    node = gdb.getFactorByQSID(qsid)
    if node is None:
        return {"error": f"未找到 QSID 为 {qsid} 的因子"}

    factor_name = node.get("Name", "")

    def_script_path = _resolve_def_script_path(gdb, qsid)

    if not def_script_path:
        # 通过标签推断脚本路径
        def_script_path = _infer_script_path_from_tags(gdb, qsid)

    if not def_script_path:
        return {
            "error": f"无法定位因子 '{factor_name}' 的定义脚本",
            "qsid": qsid,
            "factor_name": factor_name,
        }

    if not os.path.exists(def_script_path):
        return {
            "error": f"定义脚本文件不存在: {def_script_path}",
            "qsid": qsid,
            "factor_name": factor_name,
            "script_path": def_script_path,
        }

    try:
        with open(def_script_path, "r", encoding="utf-8") as f:
            source_code = f.read()
    except Exception as e:
        return {
            "error": f"读取脚本文件失败: {e}",
            "qsid": qsid,
            "script_path": def_script_path,
        }

    return {
        "qsid": qsid,
        "factor_name": factor_name,
        "script_path": def_script_path,
        "source_code": source_code,
    }


def _resolve_def_script_path(gdb, qsid: str) -> Optional[str]:
    """通过 FactorTable 的 MetaDataJSON 解析 DefScriptPath"""
    ft_results = gdb._runCypher(
        """
        MATCH (f:`因子` {QSID: $qsid})-[:`属于因子表`]->(t:`因子表`)
        RETURN t.MetaDataJSON, t.Name
        """,
        {"qsid": qsid}
    )
    if not ft_results:
        # 尝试通过标签查找关联表
        tag_results = gdb._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[:`打标签`]->(tag:`标签`)
            MATCH (t:`因子表`)
            WHERE t.Name CONTAINS tag.Name OR tag.Name CONTAINS t.Name
            RETURN DISTINCT t.MetaDataJSON, t.Name
            LIMIT 1
            """,
            {"qsid": qsid}
        )
        ft_results = tag_results

    if not ft_results:
        return None

    ft_data = ft_results[0]
    meta_json_str = ft_data.get("t.MetaDataJSON", "{}")
    table_meta = _parse_meta_json(meta_json_str)
    if isinstance(table_meta, dict):
        return table_meta.get("DefScriptPath")
    return None


def _infer_script_path_from_tags(gdb, qsid: str) -> Optional[str]:
    """通过因子标签推断定义脚本路径（标签名即模块文件名）"""
    try:
        tag_results = gdb._runCypher(
            "MATCH (f:`因子` {QSID: $qsid})-[:`打标签`]->(t:`标签`) RETURN t.Name",
            {"qsid": qsid}
        )
    except Exception:
        return None

    import importlib
    for row in tag_results:
        tag_name = row["t.Name"]
        # 标签匹配因子定义模块: e.g. "stock_cn_day_bar_nafilled"
        if not re.match(r'^[a-z][a-z0-9_]*$', tag_name):
            continue
        try:
            mod = importlib.import_module(f"QSResearch.FactorDef.JY.{tag_name}")
            if hasattr(mod, '__file__') and mod.__file__:
                return mod.__file__
        except Exception:
            continue
    return None


# ─── 回测相关 MCP Tools ────────────────────────────────────

def _format_backtest(b: dict) -> dict:
    """格式化回测节点为统一输出格式"""
    return {
        "name": b.get("Name", ""),
        "qsid": b.get("QSID", ""),
        "class_name": b.get("ClassName", ""),
        "category": b.get("BacktestCategory", ""),
        "created_at": b.get("CreatedAt", ""),
    }


def search_backtests(query: str = "", category: str = None,
                     factor_qsid: str = None, limit: int = 20) -> list[dict]:
    """搜索回测列表。支持按名称、类别、使用的因子来查找回测。

    Args:
        query: 查询文本，匹配回测名称（模糊匹配）；传空字符串查全部
        category: 回测类别筛选，可选: SectionFactor / Strategy / Risk /
                  TimeSeriesFactor / PerformanceAnalysis / Event
        factor_qsid: 因子 QSID，查找使用了该因子的所有回测
        limit: 返回结果数量上限，默认 20

    Returns:
        [{name, qsid, class_name, category, created_at}]
    """
    gdb = _get_gdb()
    results = gdb.searchBacktests(
        name=(query if query else None),
        category=category,
        factor_qsid=factor_qsid,
        limit=limit
    )
    return [_format_backtest(r) for r in results]


def get_backtest_info(qsid: str) -> dict:
    """查询回测的详细信息，包括配置参数、依赖因子和结果摘要。

    Args:
        qsid: 回测节点的 QSID（唯一标识符）

    Returns:
        回测详细信息字典，包含:
        - name, qsid, class_name, category, module_path
        - qs_args: 回测参数
        - factors: 依赖的因子列表 [{name, qsid}]
        - results: 结果摘要列表 [{result_id, key, data_type, summary}]
        - tags: 标签列表
    """
    gdb = _get_gdb()
    node = gdb.getBacktestByQSID(qsid)
    if node is None:
        return {"error": f"未找到 QSID 为 {qsid} 的回测"}

    # 解析参数
    qs_args = {}
    try:
        raw = json.loads(node.get("QSArgsJSON", "{}"))
        qs_args = _desanitizeFromJSON(raw)
    except Exception:
        pass

    # 获取依赖的因子
    factor_results = gdb._runCypher(
        """
        MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(f:`因子`)
        RETURN f.Name, f.QSID
        ORDER BY f.Name
        """,
        {"qsid": qsid}
    )
    factors = [{"name": r["f.Name"], "qsid": r["f.QSID"]} for r in factor_results]

    # 获取子回测依赖（BTReport 场景）
    bt_results = gdb._runCypher(
        """
        MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(dep:`回测`)
        RETURN dep.Name, dep.QSID
        ORDER BY dep.Name
        """,
        {"qsid": qsid}
    )
    sub_backtests = [{"name": r["dep.Name"], "qsid": r["dep.QSID"]} for r in bt_results]

    # 获取结果摘要
    result_nodes = gdb.getBacktestResults(qsid)
    results = []
    for r in result_nodes:
        summary = {}
        try:
            summary = json.loads(r.get("SummaryJSON", "{}"))
        except Exception:
            pass
        results.append({
            "result_id": r.get("ResultID", ""),
            "key": r.get("Key", ""),
            "data_type": r.get("DataType", ""),
            "dtrange": r.get("DTRangeJSON", ""),
            "summary": summary,
        })

    # 获取标签
    tags = []
    try:
        tag_results = gdb._runCypher(
            "MATCH (b:`回测` {QSID: $qsid})-[:`打标签`]->(t:`标签`) RETURN t.Name",
            {"qsid": qsid}
        )
        tags = [t["t.Name"] for t in tag_results]
    except Exception:
        pass

    return {
        "name": node.get("Name", ""),
        "qsid": node.get("QSID", qsid),
        "class_name": node.get("ClassName", ""),
        "category": node.get("BacktestCategory", ""),
        "module_path": node.get("ModulePath", ""),
        "qs_args": {k: str(v) for k, v in qs_args.items()} if isinstance(qs_args, dict) else {},
        "factors": factors,
        "sub_backtests": sub_backtests,
        "results": results,
        "tags": tags,
        "created_at": node.get("CreatedAt", ""),
        "updated_at": node.get("UpdatedAt", ""),
    }


def get_backtest_result(result_id: str) -> dict:
    """获取回测结果的详细数据。如果结果数据存储在 HDF5 文件中，会读取并返回。

    Args:
        result_id: 回测结果的 ResultID

    Returns:
        {result_id, key, data_type, summary, data (如果可读取)}
        若数据仅保存在 HDF5 中，data 字段包含 data_ref 文件路径提示
    """
    gdb = _get_gdb()
    node = gdb.getBacktestResult(result_id)
    if node is None:
        return {"error": f"未找到 ResultID 为 {result_id} 的回测结果"}

    summary = {}
    try:
        summary = json.loads(node.get("SummaryJSON", "{}"))
    except Exception:
        pass

    result = {
        "result_id": node.get("ResultID", result_id),
        "key": node.get("Key", ""),
        "data_type": node.get("DataType", ""),
        "dtrange": node.get("DTRangeJSON", ""),
        "created_at": node.get("CreatedAt", ""),
        "summary": summary,
    }

    # 尝试读取 HDF5 数据（使用框架的 readNestedDictFromHDF5，pickle 反序列化）
    data_ref = node.get("DataRef")
    if data_ref:
        result["data_ref"] = data_ref
        if os.path.exists(data_ref):
            try:
                from QuantStudio.Tools.DataTypeFun import readNestedDictFromHDF5
                data = readNestedDictFromHDF5(data_ref, ref="data")
                if isinstance(data, pd.DataFrame):
                    result["data_shape"] = list(data.shape)
                    result["data_preview"] = f"DataFrame: {data.shape[0]} rows × {data.shape[1]} cols"
                elif isinstance(data, pd.Series):
                    result["data_shape"] = list(data.shape)
                    result["data_preview"] = f"Series: {len(data)} items"
                elif isinstance(data, str):
                    result["data_preview"] = f"Text: {len(data)} chars"
                    if len(data) <= 5000:
                        result["data"] = data
                else:
                    result["data_preview"] = str(type(data).__name__)
            except Exception as e:
                result["data_error"] = str(e)
        else:
            result["data_error"] = "HDF5 文件不存在"

    return result


def register_report(report_path: str, factor_qsids: list[str],
                    bt_qsid: str = None, scenario_name: str = None,
                    name: str = None) -> dict:
    """将本地报告文件注册到计算图数据库。

    报告文件保留在本地，图数据库中只存储文件路径和相关元数据。
    通过 (因子)-[:有报告]->(报告) 和 (回测)-[:产生报告]->(报告) 关系进行关联。

    Args:
        report_path: 报告文件的本地绝对路径
        factor_qsids: 报告涉及的因子 QSID 列表
        bt_qsid: 产生此报告的回测 QSID（可选）
        scenario_name: 生成报告的场景名称（如 "single_factor"）
        name: 报告名称，默认使用文件名

    Returns:
        {report_id, name, file_path, format, file_size, factor_count}
    """
    gdb = _get_gdb()
    report_id = gdb.storeReport(
        report_path=report_path,
        factor_qsids=factor_qsids,
        bt_qsid=bt_qsid,
        scenario_name=scenario_name,
        name=name,
    )
    report = gdb.getReport(report_id)
    if not report:
        return {"error": "报告注册后无法读取"}

    return {
        "report_id": report_id,
        "name": report.get("Name", ""),
        "file_path": report.get("FilePath", ""),
        "format": report.get("Format", ""),
        "file_size": report.get("FileSize", 0),
        "scenario_name": report.get("ScenarioName", ""),
        "factor_names": json.loads(report.get("FactorNames", "[]")),
        "created_at": report.get("CreatedAt", ""),
    }


def search_reports(query: str = "", scenario_name: str = None,
                   factor_qsid: str = None, fmt: str = None,
                   limit: int = 20) -> list[dict]:
    """搜索已注册的报告列表。

    可按报告名称、场景、关联因子、格式进行组合查询。

    Args:
        query: 查询文本，匹配报告名称（模糊匹配）；传空字符串查全部
        scenario_name: 场景名称筛选，如 "single_factor"
        factor_qsid: 因子 QSID，查找关联该因子的所有报告
        fmt: 格式筛选，可选 html / markdown / pdf
        limit: 返回数量上限，默认 20

    Returns:
        [{report_id, name, file_path, format, file_size, scenario_name, created_at}, ...]
    """
    gdb = _get_gdb()
    reports = gdb.searchReports(
        name=query or None,
        scenario_name=scenario_name,
        factor_qsid=factor_qsid,
        fmt=fmt,
        limit=limit,
    )
    return [
        {
            "report_id": r.get("ReportID", ""),
            "name": r.get("Name", ""),
            "file_path": r.get("FilePath", ""),
            "format": r.get("Format", ""),
            "file_size": r.get("FileSize", 0),
            "scenario_name": r.get("ScenarioName", ""),
            "created_at": r.get("CreatedAt", ""),
        }
        for r in reports
    ]


def get_report_info(report_id: str) -> dict:
    """获取报告的详细元信息。

    注意：此接口只返回元数据（路径、大小、关联因子等），
    不返回报告文件内容。报告内容请通过文件路径直接读取。

    Args:
        report_id: 报告的 ReportID（唯一标识符）

    Returns:
        {report_id, name, file_path, format, file_size, scenario_name,
         factor_qsids, bt_qsid, file_mtime, created_at, updated_at}
    """
    gdb = _get_gdb()
    node = gdb.getReport(report_id)
    if node is None:
        return {"error": f"未找到 ReportID 为 {report_id} 的报告"}

    # 获取关联的因子 QSID 列表
    factor_results = gdb._runCypher(
        """
        MATCH (f:`因子`)-[:`有报告`]->(r:`报告` {ReportID: $report_id})
        RETURN f.QSID AS qsid
        """,
        {"report_id": report_id}
    )
    factor_qsids = [r["qsid"] for r in factor_results]

    # 获取关联的回测 QSID
    bt_results = gdb._runCypher(
        """
        MATCH (b:`回测`)-[:`产生报告`]->(r:`报告` {ReportID: $report_id})
        RETURN b.QSID AS qsid
        """,
        {"report_id": report_id}
    )
    bt_qsid = bt_results[0]["qsid"] if bt_results else None

    filepath = node.get("FilePath", "")
    file_exists = os.path.exists(filepath) if filepath else False

    return {
        "report_id": node.get("ReportID", report_id),
        "name": node.get("Name", ""),
        "file_path": filepath,
        "file_exists": file_exists,
        "format": node.get("Format", ""),
        "file_size": node.get("FileSize", 0),
        "scenario_name": node.get("ScenarioName", ""),
        "factor_qsids": factor_qsids,
        "bt_qsid": bt_qsid,
        "file_mtime": node.get("FileMtime", ""),
        "created_at": node.get("CreatedAt", ""),
        "updated_at": node.get("UpdatedAt", ""),
    }


# ─── 风险表相关 MCP Tools ────────────────────────────────────

def search_risk_tables(query: str = "", limit: int = 20) -> list[dict]:
    """搜索风险表列表。支持按名称模糊匹配。

    Args:
        query: 查询文本，匹配风险表名称（模糊匹配）；传空字符串查全部
        limit: 返回结果数量上限，默认 20

    Returns:
        [{name, qsid, class_name, module_path}]
    """
    gdb = _get_gdb()
    results = gdb.searchRiskTables(
        name=(query if query else None),
        limit=limit
    )
    return [
        {
            "name": r.get("Name", ""),
            "qsid": r.get("QSID", ""),
            "class_name": r.get("ClassName", ""),
            "module_path": r.get("ModulePath", ""),
        }
        for r in results
    ]


def get_risk_table_info(qsid: str) -> dict:
    """查询风险表的详细信息。

    Args:
        qsid: 风险表的 QSID（唯一标识符）

    Returns:
        风险表详细信息字典
    """
    gdb = _get_gdb()
    node = gdb.getRiskTableByQSID(qsid)
    if node is None:
        return {"error": f"未找到 QSID 为 {qsid} 的风险表"}

    qs_args = {}
    try:
        raw = json.loads(node.get("QSArgsJSON", "{}"))
        qs_args = _desanitizeFromJSON(raw)
    except Exception:
        pass

    return {
        "name": node.get("Name", ""),
        "qsid": node.get("QSID", qsid),
        "class_name": node.get("ClassName", ""),
        "module_path": node.get("ModulePath", ""),
        "qs_args": {k: str(v) for k, v in qs_args.items()} if isinstance(qs_args, dict) else {},
    }


# ─── 组合优化器相关 MCP Tools ────────────────────────────────

def search_optimizers(query: str = "", optimizer_type: str = None,
                       limit: int = 20) -> list[dict]:
    """搜索组合优化器列表。

    Args:
        query: 查询文本，匹配优化器名称（模糊匹配）；传空字符串查全部
        optimizer_type: 优化器类型筛选，如 CVXPC / MatlabPC
        limit: 返回结果数量上限，默认 20

    Returns:
        [{name, qsid, optimizer_type, class_name, created_at}]
    """
    gdb = _get_gdb()
    results = gdb.searchOptimizers(
        name=(query if query else None),
        optimizer_type=optimizer_type,
        limit=limit
    )
    return [
        {
            "name": r.get("Name", ""),
            "qsid": r.get("QSID", ""),
            "optimizer_type": r.get("OptimizerType", ""),
            "class_name": r.get("ClassName", ""),
            "created_at": r.get("CreatedAt", ""),
        }
        for r in results
    ]


def get_optimizer_info(qsid: str) -> dict:
    """查询组合优化器的详细信息。

    Args:
        qsid: 组合优化器的 QSID（唯一标识符）

    Returns:
        组合优化器详细信息字典
    """
    gdb = _get_gdb()
    node = gdb.getOptimizerByQSID(qsid)
    if node is None:
        return {"error": f"未找到 QSID 为 {qsid} 的组合优化器"}

    qs_args = {}
    try:
        raw = json.loads(node.get("QSArgsJSON", "{}"))
        qs_args = _desanitizeFromJSON(raw)
    except Exception:
        pass

    return {
        "name": node.get("Name", ""),
        "qsid": node.get("QSID", qsid),
        "optimizer_type": node.get("OptimizerType", ""),
        "class_name": node.get("ClassName", ""),
        "module_path": node.get("ModulePath", ""),
        "description": node.get("Description", ""),
        "qs_args": {k: str(v) for k, v in qs_args.items()} if isinstance(qs_args, dict) else {},
        "created_at": node.get("CreatedAt", ""),
        "updated_at": node.get("UpdatedAt", ""),
    }


# ─── 工具注册 ────────────────────────────────────────────────

def _register_tools():
    """按 QS_TOOLS 环境变量选择性注册工具到 MCP 实例"""
    enabled = _get_enabled_tools()
    tools = [
        # (函数引用, 工具名)
        (search_factors, "factor"),
        (get_factor_info, "factor"),
        (get_factor_code, "factor"),
        (search_backtests, "backtest"),
        (get_backtest_info, "backtest"),
        (get_backtest_result, "backtest"),
        (register_report, "report"),
        (search_reports, "report"),
        (get_report_info, "report"),
        (search_risk_tables, "risk_table"),
        (get_risk_table_info, "risk_table"),
        (search_optimizers, "optimizer"),
        (get_optimizer_info, "optimizer"),
    ]
    registered = 0
    for fn, group in tools:
        if fn.__name__ in enabled:
            mcp.tool(fn)
            registered += 1
        else:
            __QS_Logger__.debug(f"工具已禁用 ({group}): {fn.__name__}")
    __QS_Logger__.info(f"QSRegistry MCP: 已注册 {registered}/{len(tools)} 个工具")


_register_tools()


if __name__ == "__main__":
    mcp.run(transport="stdio")

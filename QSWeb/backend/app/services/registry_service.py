"""
QSRegistry 服务

桥接 QSGraphDB（Neo4j 计算图元数据）和 Web API，提供因子搜索、DAG、算子列表等功能。
"""

import asyncio
import importlib
import json
import os
import re
from typing import Optional, List, Dict, Any

import pandas as pd

from app.core.config import settings


class RegistryService:
    """QSRegistry 服务（单例模式，惰性加载 QSGraphDB）"""

    def __init__(self):
        self._gdb = None

    async def _get_gdb(self):
        """惰性加载 QSGraphDB 单例（connect 在 executor 中运行）"""
        if self._gdb is not None:
            return self._gdb

        neo4j_cfg = self._load_neo4j_config()
        if neo4j_cfg is None:
            raise RuntimeError("无法加载 Neo4j 配置")

        from QSExt.QSRegistry.QSGraphDB import QSGraphDB

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
        model = neo4j_args["EmbeddingModel"]
        if model == "bge-m3":
            neo4j_args["EmbeddingDim"] = 1024
        elif model == "qwen3-embedding:8b":
            neo4j_args["EmbeddingDim"] = 4096

        loop = asyncio.get_running_loop()

        def _connect():
            gdb = QSGraphDB(args=neo4j_args)
            gdb.connect()
            return gdb

        self._gdb = await loop.run_in_executor(None, _connect)
        return self._gdb

    @staticmethod
    def _load_neo4j_config() -> Optional[dict]:
        config_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
        if not os.path.exists(config_path):
            return None
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)

    # ─── 因子搜索 ─────────────────────────────────────────────

    async def search_factors(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """关键词搜索因子（通过 QSGraphDB.searchFactors）"""
        gdb = await self._get_gdb()

        def _sync():
            results = gdb.searchFactors(name=query, limit=limit)
            formatted = []
            for r in results:
                formatted.append({
                    "name": r.get("Name", ""),
                    "qsid": r.get("QSID", ""),
                    "factor_class": r.get("FactorClass", ""),
                    "data_type": r.get("DataType", ""),
                    "operator_type": r.get("OperatorType", ""),
                    "operator_name": r.get("OperatorName", ""),
                })
            return formatted

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def semantic_search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """语义搜索因子（通过 QSGraphDB.searchFactorsByDescription）"""
        gdb = await self._get_gdb()

        def _sync():
            results = gdb.searchFactorsByDescription(query, limit=limit)
            formatted = []
            for r in results:
                formatted.append({
                    "name": r.get("Name", ""),
                    "qsid": r.get("QSID", ""),
                    "factor_class": r.get("FactorClass", ""),
                    "data_type": r.get("DataType", ""),
                    "operator_type": r.get("OperatorType", ""),
                    "operator_name": r.get("OperatorName", ""),
                    "similarity": r.get("Similarity", 0.0),
                })
            return formatted

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    # ─── 因子详情 ─────────────────────────────────────────────

    async def get_factor_detail(self, qsid: str) -> Optional[Dict[str, Any]]:
        """获取因子详细信息（元信息 + 依赖）"""
        gdb = await self._get_gdb()

        def _sync():
            node = gdb.getFactorByQSID(qsid)
            if node is None:
                return None

            desc = gdb.getDescriptors(qsid)
            deps = gdb.getDependents(qsid, transitive=False)

            # 解析描述
            description = ""
            try:
                meta_str = node.get("MetaJSON")
                if meta_str:
                    meta = json.loads(meta_str)
                    if isinstance(meta, dict):
                        description = meta.get("Description", "")
            except Exception:
                pass

            if not description:
                try:
                    qs_args_str = node.get("QSArgsJSON")
                    if qs_args_str:
                        qs_args = json.loads(qs_args_str)
                        if isinstance(qs_args, dict):
                            description = qs_args.get("Description", "")
                except Exception:
                    pass

            # 依赖深度
            dep_graph = gdb.getDependencyGraph(qsid, direction="down")
            orders = [e.get("order") for e in dep_graph.get("edges", []) if e.get("order") is not None]
            depth = max(orders) if orders else 0

            # 标签
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
                "descriptors": [
                    {"name": d.get("Name", ""), "qsid": d.get("QSID", "")}
                    for d in desc
                ],
                "dependents": [
                    {"name": d.get("Name", ""), "qsid": d.get("QSID", "")}
                    for d in deps
                ],
                "dependency_depth": depth,
                "tags": tags,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    # ─── DAG ──────────────────────────────────────────────────

    async def get_factor_dag(self, qsid: str) -> Dict[str, Any]:
        """获取因子依赖 DAG 数据（节点 + 边，含布局信息）"""
        gdb = await self._get_gdb()

        def _sync():
            node = gdb.getFactorByQSID(qsid)
            if node is None:
                raise ValueError(f"因子不存在: {qsid}")

            dep_graph = gdb.getDependencyGraph(qsid, direction="both")

            nodes = []
            edges = []
            seen_nodes = set()

            for n in dep_graph.get("nodes", []):
                n_qsid = n.get("QSID", "")
                if n_qsid not in seen_nodes:
                    seen_nodes.add(n_qsid)
                    nodes.append({
                        "qsid": n_qsid,
                        "name": n.get("Name", ""),
                        "factor_class": n.get("FactorClass", ""),
                        "operator_type": n.get("OperatorType", ""),
                        "data_type": n.get("DataType", ""),
                    })

            for e in dep_graph.get("edges", []):
                source_qsid = e.get("source", "")
                target_qsid = e.get("target", "")
                order_val = e.get("order")
                if order_val is None:
                    order_val = 0
                edges.append({
                    "source": source_qsid,
                    "target": target_qsid,
                    "order": order_val,
                })

            # dagre 自动布局
            layout = _dagre_layout(nodes, edges)

            # 合并布局到节点
            for i, n in enumerate(nodes):
                if i < len(layout):
                    n["x"] = layout[i]["x"]
                    n["y"] = layout[i]["y"]

            return {
                "root_qsid": qsid,
                "nodes": nodes,
                "edges": edges,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    # ─── 算子列表 ─────────────────────────────────────────────

    async def list_operators(
        self,
        operator_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取已注册算子列表"""
        gdb = await self._get_gdb()

        def _sync():
            if operator_type:
                results = gdb._runCypher(
                    "MATCH (o:`算子`) WHERE o.OperatorType = $op_type "
                    "RETURN o ORDER BY o.Name",
                    {"op_type": operator_type}
                )
            else:
                results = gdb._runCypher(
                    "MATCH (o:`算子`) RETURN o ORDER BY o.Name"
                )

            operators = []
            for r in results:
                o = r["o"]
                operators.append({
                    "name": o.get("Name", ""),
                    "qsid": o.get("QSID", ""),
                    "operator_type": o.get("OperatorType", ""),
                    "class_name": o.get("ClassName", ""),
                    "module_path": o.get("ModulePath", ""),
                    "data_type": o.get("DataType", ""),
                    "arity": o.get("Arity"),
                    "description": o.get("Description", ""),
                })
            return operators

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    # ─── QSArgs JSON Schema ───────────────────────────────────

    async def get_args_schema(self, class_name: str) -> Optional[Dict[str, Any]]:
        """获取指定类的 QSArgs JSON Schema（基于 Pydantic model_json_schema()）"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_args_schema_sync, class_name)

    # ─── 衍生因子创建 ─────────────────────────────────────────

    async def create_derivative_factor(
        self,
        name: str,
        operator_qsid: str,
        descriptor_qsids: List[str],
        factor_args: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建衍生因子（直接在 Neo4j 中创建节点和关系，无需 QuantStudio 运行时）"""
        gdb = await self._get_gdb()

        def _sync():
            import hashlib
            import datetime as dt_mod

            # 获取算子信息
            op_results = gdb._runCypher(
                "MATCH (o:`算子` {QSID: $qsid}) RETURN o",
                {"qsid": operator_qsid}
            )
            if not op_results:
                raise ValueError(f"算子不存在: {operator_qsid}")
            op_data = op_results[0]["o"]

            # 验证描述子因子存在
            for d_qsid in descriptor_qsids:
                f_node = gdb.getFactorByQSID(d_qsid)
                if f_node is None:
                    raise ValueError(f"依赖因子不存在: {d_qsid}")

            # 生成 QSID
            raw = f"{name}|{operator_qsid}|{','.join(sorted(descriptor_qsids))}"
            qsid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

            # 检查是否已存在同名因子
            existing = gdb._runCypher(
                "MATCH (f:`因子` {QSID: $qsid}) RETURN f",
                {"qsid": qsid}
            )
            if existing:
                raise ValueError(f"因子已存在: {name} (QSID: {qsid})")

            now = dt_mod.datetime.now(dt_mod.timezone.utc).isoformat()

            # 序列化参数
            qs_args = factor_args or {}
            qs_args["Name"] = name
            qs_args_json = json.dumps(qs_args, ensure_ascii=False, default=str)

            meta_json = json.dumps({}, ensure_ascii=False)

            operator_name = op_data.get("Name", "")
            operator_type = op_data.get("OperatorType", "")
            data_type = op_data.get("DataType", "double")

            # 创建因子节点
            gdb._runCypher("""
                MERGE (f:`因子` {QSID: $qsid})
                SET f += {
                    Name: $name,
                    FactorClass: 'DerivativeFactor',
                    ClassName: 'DerivativeFactor',
                    ModulePath: 'QuantStudio.Factor.Factor',
                    OperatorName: $operator_name,
                    OperatorType: $operator_type,
                    OperatorQSID: $operator_qsid,
                    DataType: $data_type,
                    MetaJSON: $meta_json,
                    QSArgsJSON: $qs_args_json,
                    CreatedAt: $now,
                    UpdatedAt: $now
                }
            """, {
                "qsid": qsid,
                "name": name,
                "operator_name": operator_name,
                "operator_type": operator_type,
                "operator_qsid": operator_qsid,
                "data_type": data_type,
                "meta_json": meta_json,
                "qs_args_json": qs_args_json,
                "now": now,
            })

            # 创建 [:使用算子] 关系
            gdb._runCypher("""
                MATCH (f:`因子` {QSID: $f_qsid})
                MATCH (o:`算子` {QSID: $o_qsid})
                MERGE (f)-[:`使用算子`]->(o)
            """, {"f_qsid": qsid, "o_qsid": operator_qsid})

            # 创建 [:依赖] 关系到每个描述子因子（带 order 属性）
            for idx, d_qsid in enumerate(descriptor_qsids):
                gdb._runCypher("""
                    MATCH (f:`因子` {QSID: $f_qsid})
                    MATCH (d:`因子` {QSID: $d_qsid})
                    MERGE (f)-[r:`依赖`]->(d)
                    SET r.order = $order
                """, {"f_qsid": qsid, "d_qsid": d_qsid, "order": idx})

            return {
                "name": name,
                "qsid": qsid,
                "operator_qsid": operator_qsid,
                "operator_name": operator_name,
                "operator_type": operator_type,
                "data_type": data_type,
                "descriptors": descriptor_qsids,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)


# 全局实例
registry_service = RegistryService()


# ─── 工具函数 ─────────────────────────────────────────────────


def _get_args_schema_sync(class_name: str) -> Dict[str, Any]:
    """同步获取 QSArgs JSON Schema"""
    # class_name 格式: "module.path.ClassName" 或 "module.path:ClassName"
    if ":" in class_name:
        module_path, cls_name = class_name.rsplit(":", 1)
    else:
        parts = class_name.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"无效的类名格式: {class_name}，需要 module.path.ClassName")
        module_path, cls_name = parts

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(f"无法加载类 {class_name}: {e}")

    # 获取 __QS_ArgClass__（Pydantic BaseModel）
    qs_args_cls = None
    if hasattr(cls, '_QSArgs') and hasattr(cls._QSArgs, 'model_json_schema'):
        qs_args_cls = cls._QSArgs
    elif hasattr(cls, '__QS_ArgClass__') and hasattr(cls.__QS_ArgClass__, 'model_json_schema'):
        qs_args_cls = cls.__QS_ArgClass__
    else:
        raise ValueError(f"类 {class_name} 没有可用的 Pydantic QSArgs 属性")

    # 尝试调用 model_json_schema()，可能因不支持的类型（如 Logger）而失败
    try:
        schema = qs_args_cls.model_json_schema()
    except Exception:
        schema = _build_json_schema_manual(qs_args_cls)

    return schema


def _build_json_schema_manual(qs_args_cls) -> Dict[str, Any]:
    """手动构建 JSON Schema（当 model_json_schema() 因不兼容类型失败时的回退方案）"""

    from typing import get_origin, get_args, Literal
    import typing

    properties = {}
    required_list = []

    try:
        model_fields = getattr(qs_args_cls, 'model_fields', {})
    except Exception:
        model_fields = {}

    for field_name, field_info in model_fields.items():
        try:
            annotation = field_info.annotation
            default = field_info.default

            # 检查并处理 metadata
            frozen = False
            exclude = False
            description = getattr(field_info, 'description', None) or ""

            try:
                for meta_item in getattr(field_info, 'metadata', []):
                    if hasattr(meta_item, 'extra'):
                        extra = meta_item.extra
                        if extra.get("exclude"):
                            exclude = True
                        if extra.get("frozen"):
                            frozen = True
            except Exception:
                pass

            if exclude:
                continue

            # 解析类型
            origin = get_origin(annotation)
            args = get_args(annotation)

            prop_schema: Dict[str, Any] = {}
            if description:
                prop_schema["description"] = description

            # Optional[T] → Union[T, None]
            is_optional = origin is typing.Union and type(None) in args

            if is_optional:
                # 取第一个非 None 类型
                inner_types = [a for a in args if a is not type(None)]
                if inner_types:
                    annotation = inner_types[0]
                    origin = get_origin(annotation)
                    args = get_args(annotation)
                else:
                    annotation = str
                    origin = None
                    args = ()

            # 基本类型
            if annotation is int:
                prop_schema["type"] = "integer"
            elif annotation is float:
                prop_schema["type"] = "number"
            elif annotation is str:
                prop_schema["type"] = "string"
            elif annotation is bool:
                prop_schema["type"] = "boolean"
            elif origin is list or origin is List:
                prop_schema["type"] = "array"
                if args and args[0] is str:
                    prop_schema["items"] = {"type": "string"}
                else:
                    prop_schema["items"] = {"type": "string"}
            elif origin is dict or origin is Dict:
                prop_schema["type"] = "object"
            elif origin is Literal:
                prop_schema["type"] = "string"
                prop_schema["enum"] = list(args)
            elif isinstance(annotation, type) and issubclass(annotation, (str, int, float, bool)):
                if annotation is int:
                    prop_schema["type"] = "integer"
                elif annotation is float:
                    prop_schema["type"] = "number"
                elif annotation is bool:
                    prop_schema["type"] = "boolean"
                else:
                    prop_schema["type"] = "string"
            else:
                # 不支持的类型，跳过
                continue

            if frozen:
                prop_schema["readOnly"] = True

            # 判断是否必需
            is_required = True
            if default is not None:
                is_required = False
            elif hasattr(field_info, 'is_required'):
                is_required = field_info.is_required()
            else:
                # Pydantic v2: 检查 default 是否为 PydanticUndefined
                from pydantic.fields import PydanticUndefined
                if default is PydanticUndefined:
                    is_required = True
                else:
                    is_required = False

            if is_required:
                required_list.append(field_name)

            properties[field_name] = prop_schema

        except Exception:
            continue

    return {
        "type": "object",
        "properties": properties,
        "required": required_list,
        "title": qs_args_cls.__name__ if hasattr(qs_args_cls, '__name__') else "QSArgs",
    }


def _dagre_layout(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    node_width: int = 180,
    node_height: int = 50,
    horizontal_spacing: int = 80,
    vertical_spacing: int = 100,
) -> List[Dict[str, Any]]:
    """
    简化的 dagre 布局算法（分层 + 重心调整）。

    不依赖 dagre 库，使用纯 Python 实现基本的分层布局。
    """
    if not nodes:
        return []

    # 构建邻接表和入度
    node_ids = {n["qsid"] for n in nodes}
    adj = {nid: [] for nid in node_ids}
    in_degree = {nid: 0 for nid in node_ids}

    for e in edges:
        src, tgt = e["source"], e["target"]
        if src in node_ids and tgt in node_ids:
            adj[src].append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

    # 拓扑排序分层
    layers = []
    current = [nid for nid in node_ids if in_degree[nid] == 0]

    # 如果没有入度为 0 的节点（循环依赖），从所有节点开始
    if not current:
        current = list(node_ids)

    assigned = set()
    while current:
        layers.append(list(current))
        assigned.update(current)
        next_layer = []
        for nid in current:
            for child in adj.get(nid, []):
                if child not in assigned:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_layer.append(child)

        # 处理剩余节点
        if not next_layer:
            remaining = node_ids - assigned
            if remaining:
                next_layer = list(remaining)
                assigned.update(remaining)

        current = next_layer

    # 计算坐标
    layout = {}
    for layer_idx, layer in enumerate(layers):
        y = layer_idx * (node_height + vertical_spacing)
        total_width = len(layer) * (node_width + horizontal_spacing) - horizontal_spacing
        start_x = -total_width / 2

        # 重心调整：按上游节点的平均 x 排序
        if layer_idx > 0:
            def _barycenter(nid):
                parents = [p for p, children in adj.items() if nid in children]
                if not parents:
                    return 0
                parent_xs = [layout.get(p, {}).get("x", 0) for p in parents]
                return sum(parent_xs) / len(parent_xs)

            layer.sort(key=_barycenter)

        for node_idx, nid in enumerate(layer):
            x = start_x + node_idx * (node_width + horizontal_spacing)
            layout[nid] = {"x": x, "y": y}

    return [layout.get(n["qsid"], {"x": 0, "y": 0}) for n in nodes]

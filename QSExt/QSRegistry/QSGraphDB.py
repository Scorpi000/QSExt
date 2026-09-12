# -*- coding: utf-8 -*-
"""基于 Neo4j 的量化计算图数据库 — QuantStudio 计算图注册中心核心存储引擎"""
import os
import json
import html
import hashlib
import time
import base64
import importlib
import tempfile
import datetime as dt
try:
    import h5py
except ImportError:
    h5py = None
from typing import Optional, Any, Dict, List, Literal, Union
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import requests
from pydantic import Field

from QuantStudio import __QS_ConfigPath__
from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB
from QSExt.Tools.Neo4jFun import QSNeo4jObject
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Factor.Factor import Factor, DataFactor
from QuantStudio.Factor.FactorStorer import FactorStorer
from QuantStudio.Factor.FactorOperation import (
    FactorOperator, DerivativeFactor,
    PointOperator, TimeOperator, SectionOperator, PanelOperator
)
from QSExt.QSRegistry._serialization import (
    _sanitizeForJSON, _desanitizeFromJSON,
    serializeFactorArgs,
    _decryptArgs,
)
from QuantStudio.Factor.FactorOperation import FactorOperator


# region Schema 定义

_SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT factor_qsid IF NOT EXISTS FOR (f:`因子`) REQUIRE f.QSID IS UNIQUE",
    "CREATE CONSTRAINT operator_qsid IF NOT EXISTS FOR (o:`算子`) REQUIRE o.QSID IS UNIQUE",
    "CREATE CONSTRAINT table_qsid IF NOT EXISTS FOR (t:`因子表`) REQUIRE t.QSID IS UNIQUE",
    "CREATE CONSTRAINT fdb_qsid IF NOT EXISTS FOR (d:`因子库`) REQUIRE d.QSID IS UNIQUE",
    "CREATE CONSTRAINT riskdb_name IF NOT EXISTS FOR (d:`风险库`) REQUIRE d.Name IS UNIQUE",
    "CREATE CONSTRAINT risktable_qsid IF NOT EXISTS FOR (t:`风险表`) REQUIRE t.QSID IS UNIQUE",
    "CREATE CONSTRAINT optimizer_qsid IF NOT EXISTS FOR (o:`组合优化器`) REQUIRE o.QSID IS UNIQUE",
    "CREATE CONSTRAINT tag_name IF NOT EXISTS FOR (t:`标签`) REQUIRE t.Name IS UNIQUE",
    "CREATE CONSTRAINT backtest_qsid IF NOT EXISTS FOR (b:`回测`) REQUIRE b.QSID IS UNIQUE",
    "CREATE CONSTRAINT backtest_result_id IF NOT EXISTS FOR (r:`回测结果`) REQUIRE r.ResultID IS UNIQUE",
    "CREATE CONSTRAINT report_id IF NOT EXISTS FOR (r:`报告`) REQUIRE r.ReportID IS UNIQUE",
    "CREATE CONSTRAINT storer_qsid IF NOT EXISTS FOR (s:`因子存储器`) REQUIRE s.QSID IS UNIQUE",
    "CREATE CONSTRAINT strategy_qsid IF NOT EXISTS FOR (s:`策略`) REQUIRE s.QSID IS UNIQUE",
    "CREATE CONSTRAINT script_qsid IF NOT EXISTS FOR (s:`脚本`) REQUIRE s.QSID IS UNIQUE",
    "CREATE CONSTRAINT bt_resultdb_name IF NOT EXISTS FOR (d:`回测结果库`) REQUIRE d.Name IS UNIQUE",
    "CREATE CONSTRAINT bt_resultset_name IF NOT EXISTS FOR (s:`回测结果集`) REQUIRE s.Name IS UNIQUE",
]

_SCHEMA_INDEXES = [
    "CREATE INDEX factor_name IF NOT EXISTS FOR (f:`因子`) ON (f.Name)",
    "CREATE INDEX factor_class IF NOT EXISTS FOR (f:`因子`) ON (f.FactorClass)",
    "CREATE INDEX factor_op_name IF NOT EXISTS FOR (f:`因子`) ON (f.OperatorName)",
    "CREATE INDEX factor_op_type IF NOT EXISTS FOR (f:`因子`) ON (f.OperatorType)",
    "CREATE INDEX operator_name IF NOT EXISTS FOR (o:`算子`) ON (o.Name)",
    "CREATE INDEX operator_type IF NOT EXISTS FOR (o:`算子`) ON (o.OperatorType)",
    "CREATE INDEX fdb_type IF NOT EXISTS FOR (d:`因子库`) ON (d.DBType)",
    "CREATE INDEX riskdb_type IF NOT EXISTS FOR (d:`风险库`) ON (d.DBType)",
    "CREATE INDEX risktable_name IF NOT EXISTS FOR (t:`风险表`) ON (t.Name)",
    "CREATE INDEX optimizer_type IF NOT EXISTS FOR (o:`组合优化器`) ON (o.OptimizerType)",
    "CREATE INDEX backtest_name IF NOT EXISTS FOR (b:`回测`) ON (b.Name)",
    "CREATE INDEX backtest_category IF NOT EXISTS FOR (b:`回测`) ON (b.BacktestCategory)",
    "CREATE INDEX backtest_class IF NOT EXISTS FOR (b:`回测`) ON (b.ClassName)",
    "CREATE INDEX backtest_result_key IF NOT EXISTS FOR (r:`回测结果`) ON (r.Key)",
    "CREATE INDEX report_name IF NOT EXISTS FOR (r:`报告`) ON (r.Name)",
    "CREATE INDEX report_scenario IF NOT EXISTS FOR (r:`报告`) ON (r.ScenarioName)",
    "CREATE INDEX report_format IF NOT EXISTS FOR (r:`报告`) ON (r.Format)",
    "CREATE INDEX storer_name IF NOT EXISTS FOR (s:`因子存储器`) ON (s.Name)",
    "CREATE INDEX storer_target_table IF NOT EXISTS FOR (s:`因子存储器`) ON (s.TargetTable)",
    "CREATE INDEX strategy_name IF NOT EXISTS FOR (s:`策略`) ON (s.Name)",
    "CREATE INDEX strategy_target_table IF NOT EXISTS FOR (s:`策略`) ON (s.TargetTable)",
    "CREATE INDEX script_name IF NOT EXISTS FOR (s:`脚本`) ON (s.Name)",
    "CREATE INDEX script_module_type IF NOT EXISTS FOR (s:`脚本`) ON (s.ModuleType)",
    "CREATE INDEX script_entry IF NOT EXISTS FOR (s:`脚本`) ON (s.EntryFunction)",
    "CREATE INDEX factor_def_script IF NOT EXISTS FOR (f:`因子`) ON (f.DefScriptQSID)",
    "CREATE INDEX strategy_def_script IF NOT EXISTS FOR (s:`策略`) ON (s.DefScriptQSID)",
    "CREATE INDEX bt_resultdb_class IF NOT EXISTS FOR (d:`回测结果库`) ON (d.ClassName)",
    "CREATE INDEX bt_resultset_group IF NOT EXISTS FOR (s:`回测结果集`) ON (s.GroupName)",
]

# endregion


class QSGraphDB(QSNeo4jObject):
    """基于 Neo4j 的 QuantStudio 计算图注册中心

    QuantStudio 计算图的核心存储引擎，存储因子、回测、风险模型等计算节点的元数据、
    依赖关系图和数据引用，以及算子、因子表、风险库等支撑节点的注册信息。
    支持检索、重建计算、依赖分析和影响范围查询。

    参数通过 ~/QuantStudioConfig/QSGraphDBConfig.json 配置或显式传入。
    """

    class __QS_ArgClass__(QSNeo4jObject.__QS_ArgClass__):
        Name: str = Field(default="QSGraphDB", frozen=True, title="图数据库名称")
        OllamaBaseURL: str = Field(default="http://127.0.0.1:11434", frozen=True, exclude=True, title="Ollama 服务地址")
        OllamaAPIKey: str = Field(default="ollama", frozen=True, exclude=True, repr=False, title="Ollama API Key")
        EmbeddingModel: str = Field(default="", frozen=True, exclude=True, title="嵌入模型名，空字符串表示禁用")
        EmbeddingDim: int = Field(default=0, frozen=True, exclude=True, title="预期嵌入维度，0=自动检测")
        DataDir: Optional[str] = Field(default=None, frozen=False, exclude=True, title="数据因子内联数据存储目录")

    def __init__(self, args: dict = {}, config_file: Optional[str] = None, **kwargs):
        super().__init__(
            args=args,
            config_file=(__QS_ConfigPath__ + os.sep + "QSGraphDBConfig.json" if config_file is None else config_file),
            **kwargs
        )
        self._FactorDBRegistry: Dict[str, FactorDB] = {}
        if self._QSArgs.DataDir is None:
            self._QSArgs.DataDir = os.path.join(tempfile.gettempdir(), "QS_QSGraphDB_Data")
        os.makedirs(self._QSArgs.DataDir, exist_ok=True)

    # region 生命周期

    def connect(self) -> "QSGraphDB":
        """连接到 Neo4j 数据库，首次连接自动创建约束和索引"""
        super().connect()
        self._initSchema()
        self._QS_Logger.info(f"QSGraphDB 已连接到 {self._QSArgs.IPAddr}:{self._QSArgs.Port}")
        return self

    def _initSchema(self):
        """初始化数据库 schema（约束和索引）"""
        with self.session() as session:
            for stmt in _SCHEMA_CONSTRAINTS + _SCHEMA_INDEXES:
                session.run(stmt)
        self._initVectorIndex()

    def _initVectorIndex(self):
        """初始化 Neo4j 向量索引（仅当 EmbeddingModel 已配置时）"""
        if not self._QSArgs.EmbeddingModel or self._QSArgs.EmbeddingDim <= 0:
            return
        try:
            self._runCypher(
                """
                CREATE VECTOR INDEX factor_embedding IF NOT EXISTS
                FOR (f:`因子`) ON (f.Embedding)
                OPTIONS {
                  indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                  }
                }
                """,
                {"dim": self._QSArgs.EmbeddingDim}
            )
            self._QS_Logger.info(f"已创建向量索引 factor_embedding (dim={self._QSArgs.EmbeddingDim})")
            # 策略语义搜索向量索引
            self._runCypher(
                """
                CREATE VECTOR INDEX strategy_embedding IF NOT EXISTS
                FOR (s:`策略`) ON (s.Embedding)
                OPTIONS {
                  indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                  }
                }
                """,
                {"dim": self._QSArgs.EmbeddingDim}
            )
            self._QS_Logger.info(f"已创建向量索引 strategy_embedding (dim={self._QSArgs.EmbeddingDim})")
            # 脚本语义搜索向量索引
            self._runCypher(
                """
                CREATE VECTOR INDEX script_embedding IF NOT EXISTS
                FOR (s:`脚本`) ON (s.Embedding)
                OPTIONS {
                  indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                  }
                }
                """,
                {"dim": self._QSArgs.EmbeddingDim}
            )
            self._QS_Logger.info(f"已创建向量索引 script_embedding (dim={self._QSArgs.EmbeddingDim})")
        except Exception as e:
            self._QS_Logger.warning(f"创建向量索引失败（可能 Neo4j 版本不支持）: {e}")

    def _runCypher(self, query: str, parameters: Optional[Dict] = None) -> list:
        """执行 Cypher 查询并返回结果

        Args:
            query: Cypher 查询语句
            parameters: 查询参数

        Returns:
            记录列表（每条记录转为 dict）
        """
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    # endregion

    # region 嵌入（Embedding）

    def _getFactorEmbeddingText(self, factor: Factor) -> Optional[str]:
        """聚合因子描述文本用于生成嵌入向量

        按优先级合并以下来源:
        1. factor._QSArgs.Name — 因子名称
        2. factor.getMetaData(key="Description") — 因子 Meta 中的 Description
        3. DerivativeFactor 的 Operator Description
        """
        parts = [factor._QSArgs.Name]
        desc = factor.getMetaData(key="Description")
        if desc and isinstance(desc, str) and desc.strip():
            parts.append(desc.strip())
        if isinstance(factor, DerivativeFactor) and factor.Operator:
            op_desc = factor.Operator._QSArgs.Description
            if op_desc and op_desc.strip():
                parts.append(op_desc.strip())
        merged = " ".join(parts).strip()
        return merged if merged else None

    def _generateEmbedding(self, text: str, max_retries: int = 2) -> Optional[List[float]]:
        """调用 Ollama API 生成文本嵌入向量

        Returns:
            嵌入向量列表，失败或未启用时返回 None
        """
        if not self._QSArgs.EmbeddingModel:
            return None
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                url = f"{self._QSArgs.OllamaBaseURL}/api/embeddings"
                payload = {"model": self._QSArgs.EmbeddingModel, "prompt": text}
                headers = {"Authorization": f"Bearer {self._QSArgs.OllamaAPIKey}"}
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                embedding = resp.json()["embedding"]
                if (expected := self._QSArgs.EmbeddingDim) > 0 and len(embedding) != expected:
                    self._QS_Logger.warning(
                        f"嵌入维度不匹配：预期 {expected}，实际 {len(embedding)}"
                    )
                return embedding
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))  # 递增退避
        self._QS_Logger.warning(f"生成嵌入失败（已重试 {max_retries} 次）: {last_error}")
        return None

    # endregion

    # region 存储（Store）

    def registerFactorDB(self, fdb: FactorDB) -> str:
        """注册因子库到图数据库和内存注册表

        以 QSID 为 MERGE 键，节点属性包含 QSID。

        Args:
            fdb: QuantStudio FactorDB 实例

        Returns:
            因子库 QSID
        """
        qsid = fdb._QSArgs.QSID
        props = {
            "QSID": qsid,
            "Name": fdb.Name,
            "DBType": fdb.__class__.__name__,
            "ClassName": fdb.__class__.__name__,
            "ModulePath": fdb.__class__.__module__,
            "ConnectionJSON": self._extractFDBConnection(fdb),
            "UpdatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self._runCypher(
            """
            MERGE (d:`因子库` {QSID: $qsid})
            ON CREATE SET d += $props, d.CreatedAt = $now
            ON MATCH SET d += $props
            """,
            {"qsid": qsid, "props": props, "now": dt.datetime.now(dt.timezone.utc).isoformat()}
        )
        self._FactorDBRegistry[qsid] = fdb
        self._QS_Logger.info(f"已注册因子库: {fdb.Name} (QSID: {qsid})")
        return qsid

    def _extractFDBConnection(self, fdb: FactorDB) -> str:
        """提取因子库的连接信息，使用 ``__QS_Object__.serialize()`` 完整输出

        生成的 ConnectionJSON 包含 ``__type__``、``__class__``、``__module__``、
        加密后的 ``__qsargs__``。重建时由 ``__QS_Object__.__init__`` 自行处理
        ``config_file`` 的默认查找逻辑。
        """
        data = fdb.serialize()
        data["__module__"] = fdb.__class__.__module__
        return json.dumps(_sanitizeForJSON(data), ensure_ascii=False)

    # --- FactorDB CRUD ---

    def listFactorDBs(self) -> List[Dict]:
        """列出所有已注册的因子库节点

        Returns:
            [{QSID, Name, DBType, ClassName, ModulePath, CreatedAt, UpdatedAt}, ...]
        """
        results = self._runCypher(
            "MATCH (d:`因子库`) RETURN d ORDER BY d.Name"
        )
        return [r["d"] for r in results]

    def getFactorDB(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询因子库节点

        Args:
            qsid: 因子库 QSID

        Returns:
            因子库节点属性字典，不存在时返回 None
        """
        results = self._runCypher(
            "MATCH (d:`因子库` {QSID: $qsid}) RETURN d",
            {"qsid": qsid}
        )
        return results[0]["d"] if results else None

    def deleteFactorDB(self, qsid: str) -> int:
        """级联删除因子库及其所有依赖节点

        删除链路：
        (因子)-[:属于因子表]->(因子表)-[:属于因子库]->(因子库)
        包含多跳依赖的因子（通过 [:依赖] 关系）。

        Args:
            qsid: 因子库 QSID

        Returns:
            删除的节点总数
        """
        fdb_node = self.getFactorDB(qsid)
        if not fdb_node:
            return 0

        deleted = 0

        # Step 1: 收集直接因子（通过因子表链路）的所有 QSID
        direct_results = self._runCypher(
            """
            MATCH (d:`因子库` {QSID: $qsid})<-[:`属于因子库`]-(t:`因子表`)<-[:`属于因子表`]-(f:`因子`)
            RETURN DISTINCT f.QSID AS qsid
            """,
            {"qsid": qsid}
        )
        direct_qsids = {r["qsid"] for r in direct_results}

        # Step 2: 递归查找所有间接依赖这些因子的衍生因子
        all_affected_qsids = set(direct_qsids)
        if direct_qsids:
            transitive_results = self._runCypher(
                """
                MATCH (affected:`因子`)-[:`依赖`*1..]->(direct:`因子`)
                WHERE direct.QSID IN $direct_qsids
                RETURN DISTINCT affected.QSID AS qsid
                """,
                {"direct_qsids": list(direct_qsids)}
            )
            all_affected_qsids.update(r["qsid"] for r in transitive_results)

        # Step 3: 解除因子池包含关系
        if all_affected_qsids:
            self._runCypher(
                """
                MATCH (p:`因子池`)-[r:`包含`]->(f:`因子`)
                WHERE f.QSID IN $qsids
                DELETE r
                """,
                {"qsids": list(all_affected_qsids)}
            )

        # Step 4: 删除所有受影响因子节点（DETACH DELETE 自动删除残留关系）
        for fqsid in all_affected_qsids:
            self._runCypher(
                "MATCH (f:`因子` {QSID: $qsid}) DETACH DELETE f",
                {"qsid": fqsid}
            )
            deleted += 1

        # Step 5: 删除因子表节点
        table_results = self._runCypher(
            """
            MATCH (d:`因子库` {QSID: $qsid})<-[:`属于因子库`]-(t:`因子表`)
            DETACH DELETE t
            RETURN count(t) AS cnt
            """,
            {"qsid": qsid}
        )
        deleted += table_results[0]["cnt"] if table_results else 0

        # Step 6: 删除因子库节点
        self._runCypher(
            "MATCH (d:`因子库` {QSID: $qsid}) DETACH DELETE d",
            {"qsid": qsid}
        )
        deleted += 1

        # Step 7: 清理内存注册表
        self._FactorDBRegistry.pop(qsid, None)

        self._QS_Logger.info(f"已级联删除因子库 '{fdb_node.get('Name', qsid)}' 及 {deleted - 1} 个依赖节点")
        return deleted

    def getImpactAnalysis(self, qsid: str) -> Dict:
        """查询删除因子库的影响范围

        Args:
            qsid: 因子库 QSID

        Returns:
            {
                "factor_db": {节点属性},
                "direct_factors": [{QSID, Name, FactorTableName}, ...],
                "indirect_factors": [{QSID, Name}, ...],
                "factor_tables": [{QSID, Name}, ...],
                "total_affected_factors": int,
            }
        """
        fdb_node = self.getFactorDB(qsid)
        if not fdb_node:
            return {"factor_db": None, "direct_factors": [], "indirect_factors": [],
                    "factor_tables": [], "total_affected_factors": 0}

        # 直接因子（通过因子表链路）
        direct_results = self._runCypher(
            """
            MATCH (d:`因子库` {QSID: $qsid})<-[:`属于因子库`]-(t:`因子表`)<-[:`属于因子表`]-(f:`因子`)
            RETURN DISTINCT f.QSID AS QSID, f.Name AS Name, t.Name AS FactorTableName
            """,
            {"qsid": qsid}
        )
        direct_factors = [{"QSID": r["QSID"], "Name": r["Name"], "FactorTableName": r["FactorTableName"]} for r in direct_results]
        direct_qsids = {f["QSID"] for f in direct_factors}

        # 间接因子（多跳依赖）
        indirect_factors = []
        if direct_qsids:
            transitive_results = self._runCypher(
                """
                MATCH (affected:`因子`)-[:`依赖`*1..]->(direct:`因子`)
                WHERE direct.QSID IN $direct_qsids AND NOT affected.QSID IN $direct_qsids
                RETURN DISTINCT affected.QSID AS QSID, affected.Name AS Name
                """,
                {"direct_qsids": list(direct_qsids)}
            )
            indirect_factors = [{"QSID": r["QSID"], "Name": r["Name"]} for r in transitive_results]

        # 因子表
        table_results = self._runCypher(
            """
            MATCH (d:`因子库` {QSID: $qsid})<-[:`属于因子库`]-(t:`因子表`)
            RETURN t.QSID AS QSID, t.Name AS Name
            """,
            {"qsid": qsid}
        )
        factor_tables = [{"QSID": r["QSID"], "Name": r["Name"]} for r in table_results]

        return {
            "factor_db": fdb_node,
            "direct_factors": direct_factors,
            "indirect_factors": indirect_factors,
            "factor_tables": factor_tables,
            "total_affected_factors": len(direct_factors) + len(indirect_factors),
        }

    def reconstructFactorDB(self, qsid: str) -> Optional[FactorDB]:
        """从图元数据重建并连接 FactorDB 实例（getFactorDB + _autoBuildFactorDB + connect 的便捷包装）

        Args:
            qsid: 因子库 QSID

        Returns:
            已连接的 FactorDB 实例，不存在时返回 None
        """
        fdb_node = self.getFactorDB(qsid)
        if not fdb_node:
            return None
        fdb_name = fdb_node.get("Name", qsid)
        if qsid in self._FactorDBRegistry:
            return self._FactorDBRegistry[qsid]
        fdb = self._autoBuildFactorDB(fdb_name, fdb_node)
        self._FactorDBRegistry[qsid] = fdb
        return fdb

    # region 因子池持久化

    def _getFactorDBInfo(self, factor_qsid: str) -> Optional[Dict]:
        """查询因子所属的 FactorDB 信息

        沿 ``(因子)-[:属于因子表]->(因子表)-[:属于因子库]->(因子库)`` 链路查找。

        Returns:
            {fdb_qsid, table_name} 或 None（非 FactorDB 来源时）
        """
        results = self._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[:`属于因子表`]->(t:`因子表`)-[:`属于因子库`]->(d:`因子库`)
            RETURN d.QSID AS fdb_qsid, t.Name AS table_name
            """,
            {"qsid": factor_qsid}
        )
        return results[0] if results else None

    def saveFactorPool(self, name: str, qsids: List[str],
                       user_id: Optional[str] = None) -> None:
        """保存因子池到图数据库

        创建或更新 ``因子池`` 节点，对池中每个因子建立 ``[:包含]`` 关系。

        Args:
            name: 因子池名称
            qsids: 池中因子的 QSID 列表
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if user_id:
            self._runCypher(
                """
                MERGE (p:`因子池` {Name: $name})
                ON CREATE SET p.CreatedAt = $now, p.userId = $user_id
                ON MATCH SET p.UpdatedAt = $now, p.userId = $user_id
                """,
                {"name": name, "now": now, "user_id": user_id}
            )
        else:
            self._runCypher(
                """
                MERGE (p:`因子池` {Name: $name})
                ON CREATE SET p.CreatedAt = $now
                ON MATCH SET p.UpdatedAt = $now
                """,
                {"name": name, "now": now}
            )
        # 先删除旧关系再建立新关系（覆盖保存）
        self._runCypher(
            """
            MATCH (p:`因子池` {Name: $name})-[r:`包含`]->()
            DELETE r
            """,
            {"name": name}
        )
        for qsid in qsids:
            self._runCypher(
                """
                MATCH (p:`因子池` {Name: $name})
                MATCH (f:`因子` {QSID: $qsid})
                MERGE (p)-[:`包含`]->(f)
                """,
                {"name": name, "qsid": qsid}
            )
        self._QS_Logger.info(f"已保存因子池 '{name}'，包含 {len(qsids)} 个因子")

    def loadFactorPool(self, name: str, user_id: Optional[str] = None) -> List[Dict]:
        """从图数据库加载因子池

        Args:
            name: 因子池名称
            user_id: 资源隔离的用户 ID，非空时仅匹配公共资源与该用户的私有资源

        Returns:
            [{QSID, Name, FactorClass, ...}, ...] 池中因子列表
        """
        if user_id is None:
            results = self._runCypher(
                """
                MATCH (p:`因子池` {Name: $name})-[:`包含`]->(f:`因子`)
                RETURN f
                """,
                {"name": name}
            )
        else:
            results = self._runCypher(
                """
                MATCH (p:`因子池` {Name: $name})-[:`包含`]->(f:`因子`)
                WHERE (p.userId IS NULL OR p.userId = $user_id)
                  AND (f.userId IS NULL OR f.userId = $user_id)
                RETURN f
                """,
                {"name": name, "user_id": user_id}
            )
        return [r["f"] for r in results]

    def listFactorPools(self, user_id: Optional[str] = None) -> List[Dict]:
        """列出所有已保存的因子池

        Args:
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            [{Name, CreatedAt, UpdatedAt, FactorCount}, ...]
        """
        if user_id is None:
            results = self._runCypher(
                """
                MATCH (p:`因子池`)
                OPTIONAL MATCH (p)-[:`包含`]->(f:`因子`)
                RETURN p.Name AS Name, p.CreatedAt AS CreatedAt, p.UpdatedAt AS UpdatedAt, count(f) AS FactorCount
                ORDER BY p.Name
                """
            )
        else:
            results = self._runCypher(
                """
                MATCH (p:`因子池`)
                WHERE (p.userId IS NULL OR p.userId = $user_id)
                OPTIONAL MATCH (p)-[:`包含`]->(f:`因子`)
                WHERE (f.userId IS NULL OR f.userId = $user_id)
                RETURN p.Name AS Name, p.CreatedAt AS CreatedAt, p.UpdatedAt AS UpdatedAt, count(f) AS FactorCount
                ORDER BY p.Name
                """,
                {"user_id": user_id}
            )
        return results

    def deleteFactorPool(self, name: str) -> bool:
        """删除已保存的因子池（仅删除池节点，不删除因子）

        Args:
            name: 因子池名称

        Returns:
            是否成功删除
        """
        results = self._runCypher(
            """
            MATCH (p:`因子池` {Name: $name})
            DETACH DELETE p
            RETURN count(p) AS cnt
            """,
            {"name": name}
        )
        deleted = results[0]["cnt"] > 0 if results else False
        if deleted:
            self._QS_Logger.info(f"已删除因子池 '{name}'")
        return deleted

    # endregion

    def storeFactorOperator(self, op: FactorOperator) -> str:
        """存储单个算子节点

        Args:
            op: FactorOperator 实例

        Returns:
            算子 QSID
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        props = self._serializeOperatorNode(op, now)
        self._runCypher(
            """
            MERGE (o:`算子` {QSID: $qsid})
            ON CREATE SET o += $props, o.CreatedAt = $now
            ON MATCH SET o += $props
            """,
            {"qsid": op.QSID, "props": props, "now": now}
        )
        return op.QSID

    def storeFactorTable(self, ft: FactorTable, fdb_name: Optional[str] = None) -> str:
        """存储因子表节点

        Args:
            ft: FactorTable 实例
            fdb_name: 关联的因子库名称

        Returns:
            因子表 QSID
        """
        props = {
            "Name": ft._QSArgs.Name,
            "QSID": ft.QSID,
            "FactorNamesJSON": json.dumps(ft.FactorNames, ensure_ascii=False),
            "MetaDataJSON": json.dumps(_sanitizeForJSON(ft.getMetaData(key=None).to_dict()) if hasattr(ft.getMetaData(key=None), 'to_dict') else {}, ensure_ascii=False),
            "QSArgsJSON": json.dumps(_sanitizeForJSON(ft._QSArgs.serialize()), ensure_ascii=False),
            "UpdatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self._runCypher(
            """
            MERGE (t:`因子表` {QSID: $qsid})
            ON CREATE SET t += $props, t.CreatedAt = $now
            ON MATCH SET t += $props
            """,
            {"qsid": ft.QSID, "props": props, "now": dt.datetime.now(dt.timezone.utc).isoformat()}
        )
        # 建立属于因子库关系
        actual_fdb_name = fdb_name or (ft.FactorDB.Name if ft.FactorDB else None)
        if actual_fdb_name:
            self._runCypher(
                """
                MATCH (t:`因子表` {QSID: $t_qsid})
                MATCH (d:`因子库` {Name: $fdb_name})
                MERGE (t)-[:`属于因子库`]->(d)
                """,
                {"t_qsid": ft.QSID, "fdb_name": actual_fdb_name}
            )
        return ft.QSID

    def storeFactors(self, factors: List[Factor],
                     tags: Optional[Dict[str, List[str]]] = None,
                     user_id: Optional[str] = None) -> List[str]:
        """批量存储多个因子及其完整依赖 DAG

        与逐个调用 storeFactor 相比，此方法将所有因子节点、算子节点和关系
        合并为少量 UNWIND 查询，大幅减少网络往返次数，显著提升大批量写入性能。

        Args:
            factors: 根因子列表
            tags: QSID → 标签列表 的映射（仅对根因子打标签）
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源

        Returns:
            各根因子的 QSID 列表（与输入顺序一致）
        """
        if not factors:
            return []

        # Phase 1: 收集所有 DAG 节点（去重，不立即写入）
        all_factors = []          # 因子列表（发现顺序）
        all_operators = {}        # QSID → Operator
        all_fts = {}              # QSID → (FactorTable, fdb_name_or_None)
        visited_factors = set()
        visited_fts = set()

        for factor in factors:
            self._collectDAGBatch(factor, all_factors, all_operators, all_fts,
                                  visited_factors, visited_fts)

        if not all_factors:
            return [f.QSID for f in factors]

        # Phase 2: 注册 FactorDB 并存储 FactorTable（表数量少，逐条写入即可）
        self._batchStoreFactorTables(all_fts)

        # Phase 3: 拓扑排序因子
        sorted_factors = self._topologicalSort(all_factors)

        # Phase 4: 批量生成嵌入向量
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        embeddings = {}
        if self._QSArgs.EmbeddingModel:
            for factor in sorted_factors:
                text = self._getFactorEmbeddingText(factor)
                if text:
                    emb = self._generateEmbedding(text)
                    if emb is not None:
                        embeddings[factor.QSID] = emb

        # Phase 5: 构建因子节点数据并批量 MERGE（1 条查询替代 N 条）
        factor_nodes = []
        for factor in sorted_factors:
            props = self._serializeFactor(factor)
            if factor.QSID in embeddings:
                props["Embedding"] = embeddings[factor.QSID]
                props["EmbeddingModel"] = self._QSArgs.EmbeddingModel
                props["EmbeddingDim"] = len(embeddings[factor.QSID])
            if user_id:
                props["userId"] = user_id
            factor_nodes.append({"qsid": factor.QSID, "props": props, "now": now})

        if factor_nodes:
            self._runCypher("""
                UNWIND $nodes AS node
                MERGE (f:`因子` {QSID: node.qsid})
                ON CREATE SET f += node.props, f.CreatedAt = node.now
                ON MATCH SET f += node.props
            """, {"nodes": factor_nodes})

        # Phase 6: 批量 MERGE 算子节点（1 条查询替代 N 条）
        op_nodes = []
        for op in all_operators.values():
            op_props = self._serializeOperatorNode(op, now)
            op_nodes.append({"qsid": op.QSID, "props": op_props, "now": now})
        if op_nodes:
            self._runCypher("""
                UNWIND $ops AS op
                MERGE (o:`算子` {QSID: op.qsid})
                ON CREATE SET o += op.props, o.CreatedAt = op.now
                ON MATCH SET o += op.props
            """, {"ops": op_nodes})

        # Phase 7: 批量创建关系（3 条查询替代 Σ(Kᵢ) 条）
        # 7a. (因子)-[:使用算子]->(算子)
        op_rels = [{"f": f.QSID, "o": f.Operator.QSID}
                   for f in sorted_factors
                   if isinstance(f, DerivativeFactor) and f.Operator]
        if op_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (f:`因子` {QSID: rel.f})
                MATCH (o:`算子` {QSID: rel.o})
                MERGE (f)-[:`使用算子`]->(o)
            """, {"rels": op_rels})

        # 7b. (因子)-[:属于因子表]->(因子表)
        ft_rels = [{"f": f.QSID, "t": f.FactorTable.QSID}
                   for f in sorted_factors if f.FactorTable]
        if ft_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (f:`因子` {QSID: rel.f})
                MATCH (t:`因子表` {QSID: rel.t})
                MERGE (f)-[:`属于因子表`]->(t)
            """, {"rels": ft_rels})

        # 7c. (因子)-[:依赖]->(因子)
        dep_rels = []
        for factor in sorted_factors:
            for i, desc in enumerate(factor.Descriptors):
                dep_rels.append({"s": factor.QSID, "t": desc.QSID, "order": i})
        if dep_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (source:`因子` {QSID: rel.s})
                MATCH (target:`因子` {QSID: rel.t})
                MERGE (source)-[r:`依赖`]->(target)
                SET r.order = rel.order
            """, {"rels": dep_rels})

        # Phase 8: 标签（批量 MERGE + MATCH + MERGE）
        if tags:
            tag_rels = []
            for qsid, tag_list in tags.items():
                for tag_name in tag_list:
                    tag_rels.append({"qsid": qsid, "tag": tag_name})
            if tag_rels:
                self._runCypher("""
                    UNWIND $rels AS rel
                    MERGE (t:`标签` {Name: rel.tag})
                    WITH t, rel
                    MATCH (f:`因子` {QSID: rel.qsid})
                    MERGE (f)-[:`打标签`]->(t)
                """, {"rels": tag_rels})

        self._QS_Logger.info(
            f"已批量存储 {len(factors)} 个根因子，"
            f"共 {len(all_factors)} 个因子节点、{len(all_operators)} 个算子节点"
        )
        return [f.QSID for f in factors]

    def _collectDAGBatch(self, factor: Factor, all_factors: list,
                         all_operators: dict, all_fts: dict,
                         visited_factors: set, visited_fts: set):
        """批量模式：收集因子 DAG（不立即写入，统一在 storeFactors 中批量执行）"""
        qsid = factor.QSID
        if qsid in visited_factors:
            return
        visited_factors.add(qsid)
        # 先收集依赖
        if factor.FactorTable:
            self._collectDAGFromTableBatch(factor.FactorTable, all_fts, visited_fts)
        for desc in factor.Descriptors:
            self._collectDAGBatch(desc, all_factors, all_operators, all_fts,
                                  visited_factors, visited_fts)
        all_factors.append(factor)
        if isinstance(factor, DerivativeFactor) and factor.Operator:
            all_operators[factor.Operator.QSID] = factor.Operator

    def _collectDAGFromTableBatch(self, ft: FactorTable, all_fts: dict,
                                   visited_fts: set):
        """批量模式：收集因子表信息（不立即写入）"""
        ft_qsid = ft.QSID
        if ft_qsid in visited_fts:
            return
        visited_fts.add(ft_qsid)
        fdb_name = ft.FactorDB.Name if ft.FactorDB else None
        all_fts[ft_qsid] = (ft, fdb_name)

    def _batchStoreFactorTables(self, all_fts: dict):
        """批量写入因子表并注册关联的因子库"""
        for ft, fdb_name in all_fts.values():
            if ft.FactorDB and ft.FactorDB._QSArgs.QSID not in self._FactorDBRegistry:
                self.registerFactorDB(ft.FactorDB)
            self.storeFactorTable(ft, fdb_name=fdb_name)

    def _serializeOperatorNode(self, op: FactorOperator, now: str) -> dict:
        """序列化算子为节点属性字典（供批量写入复用）"""
        op_data = op.serialize()
        return {
            "Name": op._QSArgs.Name,
            "QSID": op.QSID,
            "OperatorType": op._QSArgs.OperatorType,
            "Arity": op._QSArgs.Arity,
            "DataType": op._QSArgs.DataType,
            "Description": op._QSArgs.Description,
            "OperatorJSON": json.dumps(op_data, ensure_ascii=False),
            "UpdatedAt": now,
        }

    def _topologicalSort(self, dag_nodes: list) -> list:
        """拓扑排序（叶子节点在前）"""
        qsid_to_node = {n.QSID: n for n in dag_nodes}
        in_degree = defaultdict(int)
        adj = defaultdict(list)
        for node in dag_nodes:
            qsid = node.QSID
            in_degree.setdefault(qsid, 0)
            for desc in node.Descriptors:
                if desc.QSID in qsid_to_node:
                    adj[desc.QSID].append(qsid)
                    in_degree[qsid] += 1
        queue = deque(q for q, d in in_degree.items() if d == 0)
        result = []
        while queue:
            q = queue.popleft()
            result.append(qsid_to_node[q])
            for neighbor in adj[q]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return result

    def _serializeFactor(self, factor: Factor) -> dict:
        """序列化因子为 Neo4j 节点属性字典"""
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        props = {
            "Name": factor._QSArgs.Name,
            "QSID": factor.QSID,
            "ClassName": factor.__class__.__name__,
            "ModulePath": factor.__class__.__module__,
            "MetaJSON": json.dumps(_sanitizeForJSON(factor._QSArgs.Meta), ensure_ascii=False),
            "QSArgsJSON": serializeFactorArgs(factor),
            "UpdatedAt": now,
        }
        # 判定因子类别
        if isinstance(factor, DataFactor):
            props["FactorClass"] = "DataFactor"
            props["DataType"] = factor._QSArgs.DataType
            props["DataRef"] = self._serializeDataRef(factor)
        elif isinstance(factor, DerivativeFactor):
            props["FactorClass"] = "DerivativeFactor"
            if factor.Operator:
                props["OperatorName"] = factor.Operator._QSArgs.Name
                props["OperatorType"] = factor.Operator._QSArgs.OperatorType
                props["OperatorQSID"] = factor.Operator.QSID
                props["DataType"] = factor.Operator._QSArgs.DataType
        elif factor.FactorTable:
            props["FactorClass"] = "FactorTableFactor"
            props["FactorTableQSID"] = factor.FactorTable.QSID
            props["NameInFT"] = factor._QSArgs.Name
            # 从因子表获取 DataType
            try:
                meta = factor.getMetaData(key="DataType")
                props["DataType"] = meta if meta else "double"
            except Exception:
                props["DataType"] = "double"
        else:
            props["FactorClass"] = "Factor"
            try:
                meta = factor.getMetaData(key="DataType")
                props["DataType"] = meta if meta else "double"
            except Exception:
                props["DataType"] = "double"
        return props

    def _serializeDataRef(self, factor: DataFactor) -> str:
        """序列化 DataFactor 的数据引用"""
        data = factor._Data
        dtype = factor._QSArgs.DataType
        content = factor._DataContent
        if content == "Value":
            ref = {"type": "scalar", "value": _sanitizeForJSON(data), "dtype": dtype}
        else:
            # 写入 HDF5 文件
            qsid = factor.QSID
            subdir = os.path.join(self._QSArgs.DataDir, qsid[:8])
            os.makedirs(subdir, exist_ok=True)
            filepath = os.path.join(subdir, f"{qsid}.hdf5")
            if h5py is None:
                raise ImportError("h5py 未安装，无法序列化 DataFactor 内联数据")
            with h5py.File(filepath, "w") as f:
                if content == "Factor":
                    f.create_dataset("DateTime", data=[t.timestamp() for t in data.index])
                    f.create_dataset("ID", data=np.array(data.columns.tolist(), dtype="S"))
                    f.create_dataset("Data", data=data.values)
                elif content == "DateTime":
                    f.create_dataset("DateTime", data=[t.timestamp() for t in data.index])
                    f.create_dataset("Data", data=data.values)
                elif content == "ID":
                    f.create_dataset("ID", data=np.array(data.index.tolist(), dtype="S"))
                    f.create_dataset("Data", data=data.values)
            ref = {"type": content.lower(), "file": filepath, "dtype": dtype}
        return json.dumps(ref, ensure_ascii=False)

    # endregion

    # region 因子存储器存储（FactorStorer Store）

    @staticmethod
    def _collectActualFactors(storer: FactorStorer) -> list:
        """从 FactorStorer.Deps 中递归提取所有非 FactorStorer 的 Factor 节点

        处理 split=True 场景：当 FactorStorer 被分割时，其 Deps 是子 FactorStorer，
        需要递归遍历获取实际的 Factor 实例。

        Args:
            storer: FactorStorer 实例

        Returns:
            实际的 Factor 列表
        """
        factors = []
        queue = list(storer.Deps)
        while queue:
            dep = queue.pop(0)
            if isinstance(dep, FactorStorer):
                queue.extend(dep.Deps)
            elif isinstance(dep, Factor):
                factors.append(dep)
        return factors

    def storeFactorStorer(self, storer: FactorStorer, tags: Optional[List[str]] = None,
                          user_id: Optional[str] = None) -> str:
        """存储因子存储器节点

        FactorStorer 是计算图中负责将因子数据写入目标因子库/表的节点。
        入图后建立与依赖因子、目标因子库、目标因子表的关系。

        Args:
            storer: FactorStorer 实例
            tags: 可选的标签列表
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源

        Returns:
            FactorStorer 的 QSID
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        target_fdb = storer._QSArgs.TargetFDB
        target_table = storer._QSArgs.TargetTable
        if target_fdb is None:
            raise __QS_Error__("FactorStorer.TargetFDB 不能为 None，请先连接目标因子库")

        # 序列化 QSArgs（排除不可序列化的 TargetFDB 实例）
        qsargs_dict = storer._QSArgs.model_dump()
        qsargs_serializable = {}
        for k, v in qsargs_dict.items():
            if k == "TargetFDB":
                qsargs_serializable[k] = {
                    "__type__": target_fdb.__class__.__name__,
                    "__module__": target_fdb.__class__.__module__,
                    "Name": getattr(target_fdb, 'Name', str(target_fdb)),
                }
            else:
                qsargs_serializable[k] = _sanitizeForJSON(v)

        fdb_name = getattr(target_fdb, 'Name', str(target_fdb))
        props = {
            "Name": storer._QSArgs.Name,
            "QSID": storer.QSID,
            "ClassName": storer.__class__.__name__,
            "ModulePath": storer.__class__.__module__,
            "TargetFDBName": fdb_name,
            "TargetFDBType": target_fdb.__class__.__name__,
            "TargetTable": target_table,
            "IfExists": storer._QSArgs.IfExists,
            "QSArgsJSON": json.dumps(qsargs_serializable, ensure_ascii=False),
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id
        self._runCypher(
            """
            MERGE (s:`因子存储器` {QSID: $qsid})
            ON CREATE SET s += $props, s.CreatedAt = $now
            ON MATCH SET s += $props
            """,
            {"qsid": storer.QSID, "props": props, "now": now}
        )

        # 建立与依赖因子的关系
        # 处理 split=True 场景：storer.Deps 可能包含子 FactorStorer，
        # 需要递归遍历获取实际的 Factor 节点
        actual_factors = self._collectActualFactors(storer)
        if actual_factors:
            self._runCypher(
                """
                UNWIND $rels AS rel
                MATCH (s:`因子存储器` {QSID: $storer_qsid})
                MATCH (f:`因子` {QSID: rel.factor_qsid})
                MERGE (s)-[:`依赖`]->(f)
                """,
                {"storer_qsid": storer.QSID,
                 "rels": [{"factor_qsid": f.QSID} for f in actual_factors]}
            )

        # 建立与目标因子表的关系
        # 1) 先在图库中查找目标因子表是否已注册
        # 2) 若未注册但目标因子库中存在该表，则自动注册
        # 3) 注册后建立 [写入因子表] 和 [存入因子表] 关系
        if target_table:
            ft_qsid = None
            ft_result = self._runCypher(
                """
                MATCH (t:`因子表`)-[:`属于因子库`]->(d:`因子库` {Name: $fdb_name})
                WHERE t.Name = $table_name
                RETURN t.QSID AS qsid LIMIT 1
                """,
                {"fdb_name": fdb_name, "table_name": target_table}
            )
            if ft_result:
                ft_qsid = ft_result[0]["qsid"]
            elif target_table in target_fdb.TableNames:
                # 目标表在因子库中存在但图库中未注册，自动注册
                ft = target_fdb.getTable(target_table)
                self.storeFactorTable(ft, fdb_name=fdb_name)
                ft_qsid = ft.QSID
                self._QS_Logger.info(
                    f"自动注册目标因子表: {fdb_name}/{target_table} (QSID: {ft_qsid[:16]}...)"
                )
            else:
                self._QS_Logger.warning(
                    f"目标因子表 '{target_table}' 在图库和因子库 '{fdb_name}' 中均不存在，"
                    f"跳过 [写入因子表] 和 [存入因子表] 关系创建。"
                    f"请先运行 run_factor_def.py 将因子数据写入目标库，或手动注册该因子表。"
                )

            if ft_qsid:
                self._runCypher(
                    """
                    MATCH (s:`因子存储器` {QSID: $storer_qsid})
                    MATCH (t:`因子表` {QSID: $ft_qsid})
                    MERGE (s)-[:`写入因子表`]->(t)
                    """,
                    {"storer_qsid": storer.QSID, "ft_qsid": ft_qsid}
                )
                # 建立存储的因子到目标因子表的关系
                if actual_factors:
                    self._runCypher(
                        """
                        UNWIND $rels AS rel
                        MATCH (f:`因子` {QSID: rel.factor_qsid})
                        MATCH (t:`因子表` {QSID: $ft_qsid})
                        MERGE (f)-[:`存入因子表`]->(t)
                        """,
                        {"ft_qsid": ft_qsid,
                         "rels": [{"factor_qsid": f.QSID} for f in actual_factors]}
                    )

        # 标签
        if tags:
            self._runCypher(
                """
                UNWIND $rels AS rel
                MERGE (t:`标签` {Name: rel.tag})
                WITH t, rel
                MATCH (s:`因子存储器` {QSID: rel.qsid})
                MERGE (s)-[:`打标签`]->(t)
                """,
                {"rels": [{"qsid": storer.QSID, "tag": t} for t in tags]}
            )

        self._QS_Logger.info(
            f"已存储因子存储器: {storer._QSArgs.Name} → "
            f"{fdb_name}/{target_table} (QSID: {storer.QSID})"
        )
        return storer.QSID

    def getFactorStorerByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询因子存储器节点"""
        results = self._runCypher(
            "MATCH (s:`因子存储器` {QSID: $qsid}) RETURN s",
            {"qsid": qsid}
        )
        return results[0]["s"] if results else None

    def searchFactorStorers(self, target_table: Optional[str] = None,
                            target_fdb: Optional[str] = None,
                            factor_qsid: Optional[str] = None,
                            limit: int = 100) -> List[Dict]:
        """搜索因子存储器

        Args:
            target_table: 目标因子表名称（模糊匹配）
            target_fdb: 目标因子库名称
            factor_qsid: 依赖的因子 QSID
            limit: 返回数量上限
        """
        conditions = []
        params = {"limit": limit}
        if target_table:
            conditions.append("s.TargetTable CONTAINS $table")
            params["table"] = target_table
        if target_fdb:
            conditions.append("s.TargetFDBName CONTAINS $fdb")
            params["fdb"] = target_fdb
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        if factor_qsid:
            # 按依赖因子检索
            results = self._runCypher(
                f"""
                MATCH (s:`因子存储器`)-[:`依赖`]->(f:`因子` {{QSID: $factor_qsid}})
                {where_clause}
                RETURN s ORDER BY s.Name LIMIT $limit
                """,
                {**params, "factor_qsid": factor_qsid}
            )
        else:
            results = self._runCypher(
                f"""
                MATCH (s:`因子存储器`)
                {where_clause}
                RETURN s ORDER BY s.Name LIMIT $limit
                """,
                params
            )
        return [r["s"] for r in results]

    def deleteFactorStorer(self, qsid: str) -> None:
        """删除因子存储器节点

        Args:
            qsid: FactorStorer 的 QSID
        """
        self._runCypher(
            "MATCH (s:`因子存储器` {QSID: $qsid}) DETACH DELETE s",
            {"qsid": qsid}
        )
        self._QS_Logger.info(f"已删除因子存储器: {qsid}")

    # endregion

    # region 回测结果库存储（BTResultDB / BTResultSet）

    def storeBTResultDB(self, bt_result_db, user_id: Optional[str] = None) -> str:
        """注册回测结果库到图数据库

        对标 registerFactorDB() / registerRiskDB()，存储回测结果库的连接信息。
        节点标签 :`回测结果库`，唯一键为 Name。

        Args:
            bt_result_db: BTResultDB 实例（如 HDF5BTResultDB）
            user_id: 资源归属用户 ID

        Returns:
            回测结果库名称
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()

        # 序列化 QSArgs（排除不可序列化的字段）
        qsargs_dict = bt_result_db._QSArgs.model_dump()
        qsargs_serializable = {}
        for k, v in qsargs_dict.items():
            qsargs_serializable[k] = _sanitizeForJSON(v)

        props = {
            "Name": bt_result_db.Name,
            "ClassName": bt_result_db.__class__.__name__,
            "ModulePath": bt_result_db.__class__.__module__,
            "QSArgsJSON": json.dumps(qsargs_serializable, ensure_ascii=False),
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id

        self._runCypher(
            """
            MERGE (d:`回测结果库` {Name: $name})
            ON CREATE SET d += $props, d.CreatedAt = $now
            ON MATCH SET d += $props
            """,
            {"name": bt_result_db.Name, "props": props, "now": now}
        )
        self._QS_Logger.info(
            f"已注册回测结果库: {bt_result_db.Name} ({bt_result_db.__class__.__name__})"
        )
        return bt_result_db.Name

    def storeBTResultSet(self, group_name: str, bt_result_db_name: str,
                         strategy_qsid: Optional[str] = None,
                         metadata: Optional[dict] = None,
                         tags: Optional[List[str]] = None,
                         user_id: Optional[str] = None) -> str:
        """注册回测结果集节点到图数据库

        回测结果集以 GroupName 为唯一标识，连接策略和回测结果库：
        - (策略)-[:产生结果集]->(回测结果集)
        - (回测结果集)-[:存储于]->(回测结果库)
        - (回测结果集)-[:打标签]->(标签)

        Args:
            group_name: 结果集名称（GroupName，唯一标识）
            bt_result_db_name: 目标回测结果库名称
            strategy_qsid: 关联的策略节点 QSID（建立 产生结果集 关系）
            metadata: 可选的元信息字典
            tags: 可选的标签列表
            user_id: 资源归属用户 ID

        Returns:
            回测结果集名称（即 GroupName）
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()

        props = {
            "Name": group_name,
            "GroupName": group_name,
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id
        if metadata:
            props["MetadataJSON"] = json.dumps(_sanitizeForJSON(metadata), ensure_ascii=False)

        self._runCypher(
            """
            MERGE (s:`回测结果集` {Name: $name})
            ON CREATE SET s += $props, s.CreatedAt = $now
            ON MATCH SET s += $props
            """,
            {"name": group_name, "props": props, "now": now}
        )

        # 建立与目标回测结果库的关系
        self._runCypher(
            """
            MATCH (s:`回测结果集` {Name: $name})
            MATCH (d:`回测结果库` {Name: $db_name})
            MERGE (s)-[:`存储于`]->(d)
            """,
            {"name": group_name, "db_name": bt_result_db_name}
        )

        # 建立与策略的关系
        if strategy_qsid:
            self._runCypher(
                """
                MATCH (st:`策略` {QSID: $strategy_qsid})
                MATCH (s:`回测结果集` {Name: $name})
                MERGE (st)-[:`产生结果集`]->(s)
                """,
                {"strategy_qsid": strategy_qsid, "name": group_name}
            )

        # 标签
        if tags:
            self._runCypher(
                """
                UNWIND $rels AS rel
                MERGE (t:`标签` {Name: rel.tag})
                WITH t, rel
                MATCH (s:`回测结果集` {Name: rel.name})
                MERGE (s)-[:`打标签`]->(t)
                """,
                {"rels": [{"name": group_name, "tag": t} for t in tags]}
            )

        self._QS_Logger.info(
            f"已注册回测结果集: {group_name} → {bt_result_db_name}"
        )
        return group_name

    def getBTResultDBByName(self, name: str) -> Optional[Dict]:
        """按名称查询回测结果库节点"""
        results = self._runCypher(
            "MATCH (d:`回测结果库` {Name: $name}) RETURN d",
            {"name": name}
        )
        return results[0]["d"] if results else None

    def searchBTResultSets(self, strategy_qsid: Optional[str] = None,
                           bt_resultdb_name: Optional[str] = None,
                           group_name: Optional[str] = None,
                           limit: int = 100) -> List[Dict]:
        """搜索回测结果集

        Args:
            strategy_qsid: 关联的策略 QSID
            bt_resultdb_name: 目标回测结果库名称
            group_name: GroupName（模糊匹配）
            limit: 返回数量上限
        """
        conditions = []
        params = {"limit": limit}
        if group_name:
            conditions.append("s.GroupName CONTAINS $group_name")
            params["group_name"] = group_name
        if bt_resultdb_name:
            conditions.append("d.Name = $db_name")
            params["db_name"] = bt_resultdb_name
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        if strategy_qsid:
            results = self._runCypher(
                f"""
                MATCH (st:`策略` {{QSID: $strategy_qsid}})-[:`产生结果集`]->(s:`回测结果集`)
                OPTIONAL MATCH (s)-[:`存储于`]->(d:`回测结果库`)
                {where_clause}
                RETURN s, d.Name AS resultdb_name
                ORDER BY s.GroupName LIMIT $limit
                """,
                {**params, "strategy_qsid": strategy_qsid}
            )
        elif bt_resultdb_name:
            results = self._runCypher(
                f"""
                MATCH (s:`回测结果集`)-[:`存储于`]->(d:`回测结果库` {{Name: $db_name}})
                {where_clause}
                RETURN s, d.Name AS resultdb_name
                ORDER BY s.GroupName LIMIT $limit
                """,
                params
            )
        else:
            results = self._runCypher(
                f"""
                MATCH (s:`回测结果集`)
                OPTIONAL MATCH (s)-[:`存储于`]->(d:`回测结果库`)
                {where_clause}
                RETURN s, d.Name AS resultdb_name
                ORDER BY s.Name LIMIT $limit
                """,
                params
            )
        return [{"result_set": r["s"], "resultdb_name": r.get("resultdb_name")} for r in results]

    def deleteBTResultSet(self, group_name: str) -> None:
        """删除回测结果集节点"""
        self._runCypher(
            "MATCH (s:`回测结果集` {Name: $name}) DETACH DELETE s",
            {"name": group_name}
        )
        self._QS_Logger.info(f"已删除回测结果集: {group_name}")

    # endregion

    # region 回测存储（Backtest Store）

    def _determineBacktestCategory(self, bt_node) -> str:
        """根据 BTNode 的模块路径判定回测类别"""
        module = bt_node.__class__.__module__
        if "SectionFactor" in module:
            return "SectionFactor"
        elif ".Strategy" in module:
            return "Strategy"
        elif "Risk" in module:
            return "Risk"
        elif "TimeSeriesFactor" in module:
            return "TimeSeriesFactor"
        elif "PerformanceAnalysis" in module:
            return "PerformanceAnalysis"
        elif "Event" in module:
            return "Event"
        else:
            return "Other"

    def _collectFactorQSIDs(self, deps: list) -> list:
        """从 BTNode.Deps 中提取所有 Factor 的 QSID（仅一层，不递归）"""
        factor_qsids = []
        for dep in deps:
            if hasattr(dep, "FactorTable"):
                factor_qsids.append(dep.QSID)
        return factor_qsids

    def _collectBTNodeQSIDs(self, deps: list) -> list:
        """从 BTNode.Deps 中提取所有 BTNode 子节点的 QSID（用于 BTReport 场景）"""
        bt_qsids = []
        for dep in deps:
            if hasattr(dep, "genReport") and not hasattr(dep, "FactorTable"):
                bt_qsids.append(dep.QSID)
        return bt_qsids

    def storeBacktest(self, bt_node, tags: Optional[List[str]] = None,
                      dtrange: Optional[tuple] = None,
                      user_id: Optional[str] = None) -> str:
        """存储回测节点及其依赖关系

        Args:
            bt_node: BTNode 实例（IC, QuantilePortfolio, Strategy 等）
            tags: 可选的标签名称列表
            dtrange: 可选的时点范围 (start_dt, end_dt)，用于信息记录
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源

        Returns:
            回测节点 QSID
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        category = self._determineBacktestCategory(bt_node)
        props = {
            "Name": bt_node._QSArgs.Name,
            "QSID": bt_node.QSID,
            "ClassName": bt_node.__class__.__name__,
            "ModulePath": bt_node.__class__.__module__,
            "BacktestCategory": category,
            "QSArgsJSON": json.dumps(_sanitizeForJSON(bt_node._QSArgs.serialize()), ensure_ascii=False),
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id
        if dtrange:
            props["DTRangeJSON"] = json.dumps(
                {"start": dtrange[0].isoformat(), "end": dtrange[1].isoformat()},
                ensure_ascii=False
            )

        self._runCypher(
            """
            MERGE (b:`回测` {QSID: $qsid})
            ON CREATE SET b += $props, b.CreatedAt = $now
            ON MATCH SET b += $props
            """,
            {"qsid": bt_node.QSID, "props": props, "now": now}
        )

        # 建立与 Factor 的依赖关系
        factor_qsids = self._collectFactorQSIDs(bt_node.Deps)
        if factor_qsids:
            self._runCypher(
                """
                UNWIND $factor_qsids AS f_qsid
                MATCH (b:`回测` {QSID: $bt_qsid})
                MATCH (f:`因子` {QSID: f_qsid})
                MERGE (b)-[:`依赖`]->(f)
                """,
                {"bt_qsid": bt_node.QSID, "factor_qsids": factor_qsids}
            )

        # 建立与子 BTNode 的依赖关系（BTReport 场景）
        bt_qsids = self._collectBTNodeQSIDs(bt_node.Deps)
        if bt_qsids:
            self._runCypher(
                """
                UNWIND $bt_qsids AS dep_qsid
                MATCH (b:`回测` {QSID: $bt_qsid})
                MATCH (dep:`回测` {QSID: dep_qsid})
                MERGE (b)-[:`依赖`]->(dep)
                """,
                {"bt_qsid": bt_node.QSID, "bt_qsids": bt_qsids}
            )

        # 标签
        if tags:
            self._runCypher(
                """
                UNWIND $rels AS rel
                MERGE (t:`标签` {Name: rel.tag})
                WITH t, rel
                MATCH (b:`回测` {QSID: rel.qsid})
                MERGE (b)-[:`打标签`]->(t)
                """,
                {"rels": [{"qsid": bt_node.QSID, "tag": t} for t in tags]}
            )

        self._QS_Logger.info(
            f"已存储回测: {bt_node.Name} (QSID: {bt_node.QSID}, "
            f"类别: {category}, 依赖因子: {len(factor_qsids)})"
        )
        return bt_node.QSID

    def storeBacktestResults(self, bt_qsid: str, output: dict,
                             dtrange: tuple) -> List[str]:
        """存储回测结果，将 output dict 中的各项挂载到回测节点上

        Args:
            bt_qsid: 回测节点 QSID
            output: BTNode.backward_compute() 返回的 dict
            dtrange: (start_dt, end_dt) 时点范围

        Returns:
            各 ResultID 列表
        """
        # 确保回测节点存在
        bt_node = self.getBacktestByQSID(bt_qsid)
        if bt_node is None:
            raise __QS_Error__(f"回测节点 {bt_qsid} 不存在，请先调用 storeBacktest")

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        result_ids = []

        for key, value in output.items():
            result_id = self._generateResultID(bt_qsid, key, dtrange)
            result_ids.append(result_id)

            summary = self._generateResultSummary(key, value)
            data_type = summary.get("type", "unknown")

            props = {
                "ResultID": result_id,
                "Key": key,
                "DataType": data_type,
                "SummaryJSON": json.dumps(_sanitizeForJSON(summary), ensure_ascii=False),
                "DTRangeJSON": json.dumps(
                    {"start": dtrange[0].isoformat(), "end": dtrange[1].isoformat()},
                    ensure_ascii=False
                ),
                "UpdatedAt": now,
            }

            # 非标量/空数据存 HDF5，使用框架的 writeNestedDict2HDF5（pickle 序列化）
            needs_file = not isinstance(value, (int, float, np.integer, np.floating, bool))
            if isinstance(value, (pd.DataFrame, pd.Series)):
                needs_file = len(value) > 0
            if needs_file:
                filepath = self._saveResultToHDF5File(result_id, value)
                props["DataRef"] = filepath

            self._runCypher(
                """
                MERGE (r:`回测结果` {ResultID: $result_id})
                ON CREATE SET r += $props, r.CreatedAt = $now
                ON MATCH SET r += $props
                """,
                {"result_id": result_id, "props": props, "now": now}
            )

            # 建立关系
            self._runCypher(
                """
                MATCH (b:`回测` {QSID: $bt_qsid})
                MATCH (r:`回测结果` {ResultID: $result_id})
                MERGE (b)-[:`产生结果`]->(r)
                """,
                {"bt_qsid": bt_qsid, "result_id": result_id}
            )

        self._QS_Logger.info(
            f"已存储回测 {bt_qsid} 的 {len(result_ids)} 个结果项"
        )
        return result_ids

    def _generateResultID(self, bt_qsid: str, key: str, dtrange: tuple) -> str:
        """为回测结果生成确定性唯一 ID"""
        raw = json.dumps(
            [bt_qsid, key, dtrange[0].isoformat(), dtrange[1].isoformat()],
            sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _generateResultSummary(self, key: str, value) -> dict:
        """生成回测结果的轻量摘要"""
        summary = {"key": key}
        if isinstance(value, pd.DataFrame):
            summary.update({
                "type": "DataFrame",
                "shape": list(value.shape),
                "columns": _sanitizeForJSON(list(value.columns)[:50]),
            })
            if len(value.index) > 0:
                summary["index_start"] = str(value.index[0])
                summary["index_end"] = str(value.index[-1])
        elif isinstance(value, pd.Series):
            summary.update({
                "type": "Series",
                "length": len(value),
                "name": str(value.name) if value.name is not None else None,
            })
            if len(value.index) > 0:
                summary["index_start"] = str(value.index[0])
                summary["index_end"] = str(value.index[-1])
        elif isinstance(value, (int, float, np.integer, np.floating)):
            summary.update({"type": "scalar", "value": _sanitizeForJSON(value)})
        elif isinstance(value, str):
            summary.update({"type": "str", "length": len(value)})
        elif isinstance(value, dict):
            summary.update({"type": "dict", "keys": list(value.keys())})
        else:
            summary.update({"type": type(value).__name__, "repr": str(value)[:200]})
        return summary

    def _saveResultToHDF5File(self, result_id: str, value) -> str:
        """将回测结果值写入 HDF5 文件（使用 pickle 序列化，兼容任意类型），返回文件路径

        使用框架 writeNestedDict2HDF5，以 pickle 序列化后存储为 np.uint8 字节数组，
        避免手动处理 dtype 兼容问题（中文列名、Unicode、混合类型等）。
        """
        from QuantStudio.Tools.DataTypeFun import writeNestedDict2HDF5
        subdir = os.path.join(self._QSArgs.DataDir, result_id[:8])
        os.makedirs(subdir, exist_ok=True)
        filepath = os.path.join(subdir, f"{result_id}.hdf5")
        writeNestedDict2HDF5(value, filepath, ref="data", mode="w")
        return filepath

    # endregion

    # region 检索（Retrieve）

    def getFactorByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询因子节点"""
        results = self._runCypher(
            "MATCH (f:`因子` {QSID: $qsid}) RETURN f",
            {"qsid": qsid}
        )
        return results[0]["f"] if results else None

    def searchFactors(self, name: Optional[str] = None, operator_type: Optional[str] = None,
                      operator_name: Optional[str] = None, tag: Optional[str] = None,
                      factor_class: Optional[str] = None, limit: int = 100,
                      user_id: Optional[str] = None) -> List[Dict]:
        """多条件组合搜索因子

        Args:
            name: 因子名称（模糊匹配）
            operator_type: 算子类型（Point/Time/Section/Panel）
            operator_name: 算子名称
            tag: 标签名称
            factor_class: 因子类别（DataFactor/DerivativeFactor/FactorTableFactor）
            limit: 返回数量上限
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源（无 userId）与该用户的私有资源

        Returns:
            因子属性字典列表
        """
        conditions = []
        params = {"limit": limit}
        if name:
            conditions.append("f.Name CONTAINS $name")
            params["name"] = name
        if operator_type:
            conditions.append("f.OperatorType = $op_type")
            params["op_type"] = operator_type
        if operator_name:
            conditions.append("f.OperatorName = $op_name")
            params["op_name"] = operator_name
        if factor_class:
            conditions.append("f.FactorClass = $factor_class")
            params["factor_class"] = factor_class
        if user_id is not None:
            conditions.append("(f.userId IS NULL OR f.userId = $user_id)")
            params["user_id"] = user_id
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        if tag:
            query = f"""
                MATCH (f:`因子`)-[:`打标签`]->(t:`标签` {{Name: $tag}})
                {where_clause}
                RETURN f ORDER BY f.Name LIMIT $limit
            """
            params["tag"] = tag
        else:
            query = f"""
                MATCH (f:`因子`)
                {where_clause}
                RETURN f ORDER BY f.Name LIMIT $limit
            """
        results = self._runCypher(query, params)
        return [r["f"] for r in results]

    def searchFactorsByDescription(self, query_text: str, limit: int = 20,
                                    min_score: Optional[float] = None,
                                    user_id: Optional[str] = None) -> List[Dict]:
        """基于描述文本的向量语义检索

        使用 Ollama 生成查询文本的嵌入向量，通过 Neo4j 向量索引做余弦相似度搜索。

        Args:
            query_text: 自然语言查询文本
            limit: 返回数量上限
            min_score: 最低相似度阈值 (0~1)，None 表示不过滤
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            因子属性字典列表，每项包含 Similarity 分数
        """
        if not self._QSArgs.EmbeddingModel:
            self._QS_Logger.warning("向量检索未启用：EmbeddingModel 为空")
            return []
        query_embedding = self._generateEmbedding(query_text)
        if query_embedding is None:
            return []
        try:
            results = self._runCypher(
                """
                CALL db.index.vector.queryNodes('factor_embedding', $limit, $embedding)
                YIELD node AS f, score
                RETURN f {.Name, .QSID, .FactorClass, .OperatorType,
                          .OperatorName, .DataType, .userId}, score
                ORDER BY score DESC
                """,
                {"limit": limit, "embedding": query_embedding}
            )
        except Exception as e:
            self._QS_Logger.warning(f"向量检索失败（向量索引可能不存在）: {e}")
            return []
        if min_score is not None:
            results = [r for r in results if r["score"] >= min_score]
        if user_id is not None:
            results = [
                r for r in results
                if r["f"].get("userId") in (None, "", user_id)
            ]
        return [{"Similarity": round(r["score"], 6), **r["f"]} for r in results]

    def getDependencyGraph(self, qsid: str, direction: str = "both", max_depth: int = None) -> Dict:
        """获取因子的依赖子图

        Args:
            qsid: 目标因子 QSID
            direction: "down"（输入）/ "up"（下游）/ "both"（双向）
            max_depth: 最大深度限制，None 表示不限制

        Returns:
            {"root": qsid, "nodes": [...], "edges": [...]}
        """
        nodes = {}
        edges = []
        hop_expr = f"*1..{max_depth}" if max_depth is not None else "*"
        if direction in ("down", "both"):
            results = self._runCypher(
                f"""
                MATCH path = (root:`因子` {{QSID: $qsid}})-[:`依赖`{hop_expr}]->(leaf:`因子`)
                UNWIND nodes(path) AS n
                WITH DISTINCT n
                RETURN n
                """,
                {"qsid": qsid}
            )
            for r in results:
                n = r["n"]
                nodes[n["QSID"]] = n
            # 收集边
            edge_results = self._runCypher(
                """
                MATCH (a:`因子`)-[r:`依赖`]->(b:`因子`)
                WHERE a.QSID = $qsid OR b.QSID = $qsid
                   OR a.QSID IN $node_ids OR b.QSID IN $node_ids
                RETURN a.QSID AS source, b.QSID AS target, r.order AS order
                """,
                {"qsid": qsid, "node_ids": list(nodes.keys())}
            )
            edges.extend(edge_results)
        if direction in ("up", "both"):
            results = self._runCypher(
                f"""
                MATCH (dependent:`因子`)-[:`依赖`{hop_expr}]->(target:`因子` {{QSID: $qsid}})
                RETURN DISTINCT dependent
                """,
                {"qsid": qsid}
            )
            for r in results:
                n = r["dependent"]
                nodes[n["QSID"]] = n
            # 补充边
            if nodes:
                edge_results = self._runCypher(
                    """
                    MATCH (a:`因子`)-[r:`依赖`]->(b:`因子`)
                    WHERE a.QSID IN $node_ids AND b.QSID IN $node_ids
                    RETURN a.QSID AS source, b.QSID AS target, r.order AS order
                    """,
                    {"node_ids": list(nodes.keys())}
                )
                existing = {(e["source"], e["target"]) for e in edges}
                for e in edge_results:
                    if (e["source"], e["target"]) not in existing:
                        edges.append(e)
                        existing.add((e["source"], e["target"]))
        # 确保根节点在 nodes 中
        if qsid not in nodes:
            root = self.getFactorByQSID(qsid)
            if root:
                nodes[qsid] = root
        return {"root": qsid, "nodes": list(nodes.values()), "edges": edges}

    def getDescriptors(self, qsid: str) -> List[Dict]:
        """获取因子的直接依赖因子（有序）"""
        results = self._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[r:`依赖`]->(d:`因子`)
            RETURN d, r.order AS order
            ORDER BY r.order
            """,
            {"qsid": qsid}
        )
        return [r["d"] for r in results]

    def getDependents(self, qsid: str, transitive: bool = False) -> List[Dict]:
        """获取依赖该因子的因子

        Args:
            qsid: 目标因子 QSID
            transitive: 是否传递闭包

        Returns:
            因子属性字典列表
        """
        if transitive:
            results = self._runCypher(
                """
                MATCH (dependent:`因子`)-[:`依赖`*]->(target:`因子` {QSID: $qsid})
                RETURN DISTINCT dependent
                """,
                {"qsid": qsid}
            )
        else:
            results = self._runCypher(
                """
                MATCH (dependent:`因子`)-[:`依赖`]->(target:`因子` {QSID: $qsid})
                RETURN dependent
                """,
                {"qsid": qsid}
            )
        return [r["dependent"] for r in results]

    def findOrphanFactors(self) -> List[Dict]:
        """查找无下游依赖且不属于因子表的叶子因子"""
        results = self._runCypher(
            """
            MATCH (f:`因子`)
            WHERE NOT (f)<-[:`依赖`]-()
              AND NOT (f)-[:`属于因子表`]->(:`因子表`)
            RETURN f
            """
        )
        return [r["f"] for r in results]

    # endregion

    # region 回测检索（Backtest Retrieve）

    def getBacktestByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询回测节点"""
        results = self._runCypher(
            "MATCH (b:`回测` {QSID: $qsid}) RETURN b",
            {"qsid": qsid}
        )
        return results[0]["b"] if results else None

    def searchBacktests(self, name: Optional[str] = None,
                        category: Optional[str] = None,
                        factor_qsid: Optional[str] = None,
                        limit: int = 100,
                        user_id: Optional[str] = None) -> List[Dict]:
        """多条件组合搜索回测

        Args:
            name: 回测名称（模糊匹配）
            category: 回测类别（SectionFactor/Strategy/Risk/...）
            factor_qsid: 依赖的因子 QSID（查找使用了该因子的回测）
            limit: 返回数量上限
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            回测属性字典列表
        """
        if factor_qsid:
            query = """
                MATCH (b:`回测`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
            """
            params = {"factor_qsid": factor_qsid, "limit": limit}
            conditions = []
            if name:
                conditions.append("b.Name CONTAINS $name")
                params["name"] = name
            if category:
                conditions.append("b.BacktestCategory = $category")
                params["category"] = category
            if user_id is not None:
                conditions.append("(b.userId IS NULL OR b.userId = $user_id)")
                params["user_id"] = user_id
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query += f"""
                {where_clause}
                RETURN DISTINCT b ORDER BY b.Name LIMIT $limit
            """
        else:
            conditions = []
            params = {"limit": limit}
            if name:
                conditions.append("b.Name CONTAINS $name")
                params["name"] = name
            if category:
                conditions.append("b.BacktestCategory = $category")
                params["category"] = category
            if user_id is not None:
                conditions.append("(b.userId IS NULL OR b.userId = $user_id)")
                params["user_id"] = user_id
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"""
                MATCH (b:`回测`)
                {where_clause}
                RETURN b ORDER BY b.Name LIMIT $limit
            """
        return [r["b"] for r in self._runCypher(query, params)]

    def getBacktestResults(self, bt_qsid: str) -> List[Dict]:
        """获取某个回测的所有结果节点

        Args:
            bt_qsid: 回测节点 QSID

        Returns:
            回测结果属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (b:`回测` {QSID: $bt_qsid})-[:`产生结果`]->(r:`回测结果`)
            RETURN r ORDER BY r.Key
            """,
            {"bt_qsid": bt_qsid}
        )
        return [r["r"] for r in results]

    def getBacktestResult(self, result_id: str) -> Optional[Dict]:
        """按 ResultID 查询单个回测结果节点"""
        results = self._runCypher(
            "MATCH (r:`回测结果` {ResultID: $result_id}) RETURN r",
            {"result_id": result_id}
        )
        return results[0]["r"] if results else None

    def getBacktestDependencyGraph(self, bt_qsid: str,
                                   direction: str = "down") -> Dict:
        """获取回测的依赖子图，包含因子和子回测

        Args:
            bt_qsid: 回测节点 QSID
            direction: "down"（依赖的因子/子回测）/ "up"（谁依赖此回测）

        Returns:
            {"root": bt_qsid, "nodes": [...], "edges": [...]}
        """
        all_nodes = {}
        all_edges = []

        if direction in ("down", "both"):
            # 获取依赖的因子
            factor_results = self._runCypher(
                """
                MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(f:`因子`)
                RETURN f
                """,
                {"qsid": bt_qsid}
            )
            for r in factor_results:
                n = r["f"]
                all_nodes[n["QSID"]] = n
                all_edges.append({"source": bt_qsid, "target": n["QSID"], "type": "依赖"})

            # 获取依赖的子回测
            bt_results = self._runCypher(
                """
                MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(dep:`回测`)
                RETURN dep
                """,
                {"qsid": bt_qsid}
            )
            for r in bt_results:
                n = r["dep"]
                all_nodes[n["QSID"]] = n
                all_edges.append({"source": bt_qsid, "target": n["QSID"], "type": "依赖"})

        if direction in ("up", "both"):
            # 获取哪些回测依赖此回测
            upstream = self._runCypher(
                """
                MATCH (upstream:`回测`)-[:`依赖`]->(b:`回测` {QSID: $qsid})
                RETURN upstream
                """,
                {"qsid": bt_qsid}
            )
            for r in upstream:
                n = r["upstream"]
                all_nodes[n["QSID"]] = n
                all_edges.append({"source": n["QSID"], "target": bt_qsid, "type": "依赖"})

        # 确保根节点在 nodes 中
        if bt_qsid not in all_nodes:
            root = self.getBacktestByQSID(bt_qsid)
            if root:
                all_nodes[bt_qsid] = root

        return {"root": bt_qsid, "nodes": list(all_nodes.values()), "edges": all_edges}

    def getFactorBacktests(self, factor_qsid: str) -> List[Dict]:
        """查询某个因子被哪些回测使用过

        Args:
            factor_qsid: 因子 QSID

        Returns:
            回测属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (b:`回测`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
            RETURN b ORDER BY b.Name
            """,
            {"factor_qsid": factor_qsid}
        )
        return [r["b"] for r in results]

    # endregion

    # region 重建（Reconstruct）

    def reconstructFactor(self, qsid: str, descriptor_map: Optional[Dict[str, Factor]] = None) -> Factor:
        """从图中的元数据重建可计算的 Factor 对象

        Args:
            qsid: 目标因子的 QSID
            descriptor_map: 可选的预构建描述子映射 {QSID: Factor}

        Returns:
            可直接在计算引擎中使用的 Factor 实例
        """
        if descriptor_map is None:
            descriptor_map = {}
        if qsid in descriptor_map:
            if descriptor_map[qsid] is None:
                raise __QS_Error__(f"检测到因子依赖图中存在循环引用: {qsid}")
            return descriptor_map[qsid]
        # 占位标记，检测循环依赖
        descriptor_map[qsid] = None
        factor_data = self.getFactorByQSID(qsid)
        if factor_data is None:
            raise __QS_Error__(f"图中不存在 QSID 为 {qsid} 的因子")
        factor_class = factor_data.get("FactorClass", "Factor")
        if factor_class == "DataFactor":
            factor = self._reconstructDataFactor(factor_data)
        elif factor_class == "DerivativeFactor":
            factor = self._reconstructDerivativeFactor(factor_data, descriptor_map)
        elif factor_class == "FactorTableFactor":
            factor = self._reconstructFactorTableFactor(factor_data)
        else:
            raise __QS_Error__(f"不支持的因子类别: {factor_class}")
        descriptor_map[qsid] = factor
        return factor

    def _reconstructDataFactor(self, factor_data: dict) -> DataFactor:
        """重建 DataFactor"""
        data_ref = json.loads(factor_data.get("DataRef", "{}"))
        args = json.loads(factor_data.get("QSArgsJSON", "{}"))
        args = _desanitizeFromJSON(args)
        args = _decryptArgs(args)
        args["Name"] = factor_data["Name"]
        ref_type = data_ref.get("type", "")
        if ref_type == "scalar":
            data = _desanitizeFromJSON(data_ref["value"])
        elif ref_type in ("factor", "datetime", "id"):
            filepath = data_ref["file"]
            if h5py is None:
                raise ImportError("h5py 未安装，无法重建 DataFactor 内联数据")
            with h5py.File(filepath, "r") as f:
                if ref_type == "factor":
                    dts = [dt.datetime.fromtimestamp(t) for t in f["DateTime"][:]]
                    ids = [s.decode("utf-8") for s in f["ID"][:]]
                    data = pd.DataFrame(f["Data"][:], index=dts, columns=ids)
                elif ref_type == "datetime":
                    dts = [dt.datetime.fromtimestamp(t) for t in f["DateTime"][:]]
                    data = pd.Series(f["Data"][:], index=dts)
                elif ref_type == "id":
                    ids = [s.decode("utf-8") for s in f["ID"][:]]
                    data = pd.Series(f["Data"][:], index=ids)
        else:
            raise __QS_Error__(f"不支持的 DataRef 类型: {ref_type}")
        return DataFactor(data=data, args=args)

    def _reconstructDerivativeFactor(self, factor_data: dict, descriptor_map: dict) -> Factor:
        """重建 DerivativeFactor"""
        # 重建算子
        operator = self._reconstructOperatorFromData(factor_data)
        # 重建描述子
        descriptors_data = self.getDescriptors(factor_data["QSID"])
        descriptors = []
        for desc_data in descriptors_data:
            desc = self.reconstructFactor(desc_data["QSID"], descriptor_map)
            descriptors.append(desc)
        # 解析参数（含解密）
        args = json.loads(factor_data.get("QSArgsJSON", "{}"))
        args = _desanitizeFromJSON(args)
        args = _decryptArgs(args)
        args["Name"] = factor_data["Name"]
        args["Operator"] = operator
        # 调用算子生成因子
        operator_name = factor_data.get("OperatorName", "")
        if operator_name == "rename":
            return operator(*descriptors, factor_name=factor_data["Name"], factor_args=args)
        else:
            return operator(*descriptors, factor_args=args)

    def _reconstructOperatorFromData(self, factor_data: dict) -> FactorOperator:
        """从因子数据重建其算子"""
        op_qsid = factor_data.get("OperatorQSID")
        if not op_qsid:
            raise __QS_Error__(f"因子 {factor_data['Name']} 没有关联的算子")
        return self.reconstructOperator(op_qsid)

    def _autoBuildFactorDB(self, fdb_name: str, fdb_node: dict) -> FactorDB:
        """从图节点元数据自动构建并连接 FactorDB 实例

        支持两种 ConnectionJSON 格式：
        - 新格式（``__QS_Object__.serialize()`` 输出）：包含 ``__type__``、
          ``__qsargs__``、``__module__``
        - 旧格式（手动组装的 dict）：包含 ``ClassName``、``ModulePath``、
          ``ConfigFile``、``QSArgs``

        ``config_file`` 不在 ConnectionJSON 中存储，由 ``__QS_Object__.__init__``
        按默认路径自动查找配置文件。

        Args:
            fdb_name: 因子库名称
            fdb_node: Neo4j 返回的因子库节点（包含 ConnectionJSON 等属性）

        Returns:
            已连接的 FactorDB 实例
        """
        conn_json = json.loads(fdb_node.get("ConnectionJSON", "{}"))
        data = _desanitizeFromJSON(conn_json)

        # 检测格式：新格式包含 __type__ == "__QS_Object__"
        if data.get("__type__") == "__QS_Object__":
            class_path = data.get("__class__", "")
            if "." in class_path:
                module_path, class_name = class_path.rsplit(".", 1)
            else:
                module_path = data.get("__module__")
                class_name = class_path
            qs_args_data = data.get("__qsargs__", {})
        else:
            # 旧格式兼容
            module_path = data.get("ModulePath")
            class_name = data.get("ClassName")
            qs_args_data = data.get("QSArgs", {})

        if not module_path or not class_name:
            raise __QS_Error__(
                f"因子库 '{fdb_name}' 的 ConnectionJSON 缺少 ModulePath 或 ClassName，"
                f"无法自动构建，请先调用 registerFactorDB 显式注册该因子库"
            )

        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise __QS_Error__(
                f"因子库 '{fdb_name}' 自动构建失败: "
                f"无法加载类 {module_path}.{class_name}: {e}"
            )

        # 使用 __QS_ArgClass__.deserialize() 解密 args（兼容明文旧数据）
        qs_args = cls.__QS_ArgClass__.deserialize(qs_args_data).model_dump()
        fdb = cls(args=qs_args)
        fdb.connect()
        self._QS_Logger.info(
            f"已自动构建并连接因子库: '{fdb_name}'"
            + (f" (配置文件: {fdb.ConfigFile})" if fdb.ConfigFile else "")
        )
        return fdb

    def _reconstructFactorTableFactor(self, factor_data: dict) -> Factor:
        """重建 FactorTableFactor"""
        ft_qsid = factor_data.get("FactorTableQSID")
        if not ft_qsid:
            raise __QS_Error__(f"因子 {factor_data['Name']} 没有关联的因子表")
        # 查找因子表关联的因子库
        fdb_results = self._runCypher(
            """
            MATCH (t:`因子表` {QSID: $ft_qsid})-[:`属于因子库`]->(d:`因子库`)
            RETURN d
            """,
            {"ft_qsid": ft_qsid}
        )
        if not fdb_results:
            raise __QS_Error__(f"因子表 {ft_qsid} 没有关联的因子库")
        fdb_node = fdb_results[0]["d"]
        fdb_qsid = fdb_node.get("QSID", "")
        fdb_name = fdb_node["Name"]
        if fdb_qsid in self._FactorDBRegistry:
            fdb = self._FactorDBRegistry[fdb_qsid]
        else:
            fdb = self._autoBuildFactorDB(fdb_name, fdb_node)
            self._FactorDBRegistry[fdb_qsid] = fdb
        # 获取因子表名称
        ft_data = self._runCypher(
            "MATCH (t:`因子表` {QSID: $qsid}) RETURN t",
            {"qsid": ft_qsid}
        )
        ft_node = ft_data[0]["t"] if ft_data else {}
        ft_name = ft_node.get("Name", "")
        # 使用持久化的 QSArgsJSON 重建 FactorTable，绕过 getTable 的 FTArgs/DefaultArgs 合并
        ft_stored_args = _desanitizeFromJSON(json.loads(ft_node.get("QSArgsJSON", "{}")))
        ft_stored_args["Name"] = ft_name
        try:
            TableClass = ft_stored_args.get("TableType") or fdb._TableInfo.loc[ft_name, "TableClass"]
            import sys
            jy_module = sys.modules[fdb.__class__.__module__]
            TableCls = getattr(jy_module, f"_{TableClass}")
            # 移除传入 args 中与 pydantic 默认值相同的字段，避免 pydantic 对传入值做类型强制
            # （默认值不会被 pydantic 验证/强制，但传入值会），导致 model_dump() 差异
            for base_cls in TableCls.__mro__:
                arg_cls = getattr(base_cls, '__QS_ArgClass__', None)
                if arg_cls is None:
                    continue
                if not hasattr(arg_cls, 'model_fields'):
                    continue
                for field_name, field_info in arg_cls.model_fields.items():
                    if field_name not in ft_stored_args:
                        continue
                    try:
                        default_val = field_info.get_default(call_default_factory=False)
                        if ft_stored_args[field_name] == default_val:
                            del ft_stored_args[field_name]
                    except Exception:
                        pass
            ft = TableCls(fdb=fdb, args=ft_stored_args, logger=fdb._QS_Logger)
        except (NameError, AttributeError, KeyError):
            ft = fdb.getTable(ft_name, args=ft_stored_args)
        args = json.loads(factor_data.get("QSArgsJSON", "{}"))
        args = _desanitizeFromJSON(args)
        args = _decryptArgs(args)
        name_in_ft = factor_data.get("NameInFT", "")
        args["Name"] = name_in_ft
        return ft.getFactor(name_in_ft, args=args)

    def reconstructOperator(self, qsid: str) -> FactorOperator:
        """从图中重建算子对象"""
        results = self._runCypher(
            "MATCH (o:`算子` {QSID: $qsid}) RETURN o",
            {"qsid": qsid}
        )
        if not results:
            raise __QS_Error__(f"图中不存在 QSID 为 {qsid} 的算子")
        op_data = results[0]["o"]
        operator_json = op_data.get("OperatorJSON")
        if not operator_json:
            raise __QS_Error__(f"算子 {qsid} 缺少 OperatorJSON 字段")
        return FactorOperator.deserialize(json.loads(operator_json))

    # endregion

    # region 管理（Manage）

    def deleteFactor(self, qsid: str, cascade: bool = False) -> int:
        """删除因子节点及其关系

        Args:
            qsid: 目标因子 QSID
            cascade: 是否级联删除孤立依赖

        Returns:
            删除的节点数
        """
        deleted = 0
        if cascade:
            # 递归删除孤立因子
            to_delete = deque([qsid])
            visited = {qsid}
            while to_delete:
                current = to_delete.popleft()
                # 检查是否有其他因子依赖当前因子
                dependents = self.getDependents(current, transitive=False)
                if len(dependents) == 0 or current == qsid:
                    # 在删除前收集描述子（删除后关系丢失无法查询）
                    descs = self.getDescriptors(current)
                    desc_qsids = [d["QSID"] for d in descs]
                    # 没有其他依赖者，可以删除
                    self._runCypher(
                        "MATCH (f:`因子` {QSID: $qsid}) DETACH DELETE f",
                        {"qsid": current}
                    )
                    deleted += 1
                    # 检查该因子的描述子是否变为孤立
                    for desc_qsid in desc_qsids:
                        if desc_qsid in visited:
                            continue
                        visited.add(desc_qsid)
                        remaining = self.getDependents(desc_qsid, transitive=False)
                        if len(remaining) == 0:
                            to_delete.append(desc_qsid)
        else:
            self._runCypher(
                "MATCH (f:`因子` {QSID: $qsid}) DETACH DELETE f",
                {"qsid": qsid}
            )
            deleted = 1
        return deleted

    def updateFactorMetaData(self, qsid: str, meta: Dict) -> None:
        """更新因子的元信息"""
        existing = self.getFactorByQSID(qsid)
        if not existing:
            raise __QS_Error__(f"因子 {qsid} 不存在")
        old_meta = json.loads(existing.get("MetaJSON", "{}"))
        old_meta = _desanitizeFromJSON(old_meta)
        old_meta.update(meta)
        self._runCypher(
            "MATCH (f:`因子` {QSID: $qsid}) SET f.MetaJSON = $meta",
            {"qsid": qsid, "meta": json.dumps(_sanitizeForJSON(old_meta), ensure_ascii=False)}
        )

    def updateFactorTags(self, qsid: str, add_tags: Optional[List[str]] = None,
                         remove_tags: Optional[List[str]] = None) -> None:
        """增删因子标签"""
        if add_tags:
            for tag_name in add_tags:
                self._runCypher(
                    """
                    MERGE (t:`标签` {Name: $tag_name})
                    WITH t
                    MATCH (f:`因子` {QSID: $qsid})
                    MERGE (f)-[:`打标签`]->(t)
                    """,
                    {"tag_name": tag_name, "qsid": qsid}
                )
        if remove_tags:
            for tag_name in remove_tags:
                self._runCypher(
                    """
                    MATCH (f:`因子` {QSID: $qsid})-[r:`打标签`]->(t:`标签` {Name: $tag_name})
                    DELETE r
                    """,
                    {"qsid": qsid, "tag_name": tag_name}
                )

    def renameFactor(self, qsid: str, new_name: str) -> None:
        """更新因子名称"""
        self._runCypher(
            "MATCH (f:`因子` {QSID: $qsid}) SET f.Name = $name",
            {"qsid": qsid, "name": new_name}
        )

    # endregion

    # region 回测管理（Backtest Manage）

    def deleteBacktest(self, qsid: str, delete_results: bool = True) -> int:
        """删除回测节点及其关系，可选删除关联结果

        Args:
            qsid: 回测 QSID
            delete_results: 是否同时删除关联的回测结果节点

        Returns:
            删除的节点总数
        """
        deleted = 0

        if delete_results:
            # 先获取关联的结果节点，清理 HDF5 文件
            result_nodes = self.getBacktestResults(qsid)
            for r in result_nodes:
                data_ref = r.get("DataRef")
                if data_ref and os.path.exists(data_ref):
                    try:
                        os.remove(data_ref)
                    except OSError:
                        pass
            # 删除结果节点
            self._runCypher(
                """
                MATCH (b:`回测` {QSID: $qsid})-[:`产生结果`]->(r:`回测结果`)
                DETACH DELETE r
                """,
                {"qsid": qsid}
            )
            deleted += len(result_nodes)

        # 删除回测节点本身
        self._runCypher(
            "MATCH (b:`回测` {QSID: $qsid}) DETACH DELETE b",
            {"qsid": qsid}
        )
        deleted += 1

        self._QS_Logger.info(f"已删除回测 {qsid} 及其 {len(result_nodes) if delete_results else 0} 个结果节点")
        return deleted

    # endregion

    # region 报告存储（Report Store）

    def storeReport(self, report_path: str, factor_qsids: List[str],
                    bt_qsid: Optional[str] = None,
                    scenario_name: Optional[str] = None,
                    name: Optional[str] = None,
                    user_id: Optional[str] = None) -> str:
        """将本地报告文件注册到图数据库。

        Args:
            report_path: 报告文件的本地绝对路径
            factor_qsids: 报告涉及的因子 QSID 列表
            bt_qsid: 产生此报告的回测 QSID（可选）
            scenario_name: 场景名称（如 "single_factor"）
            name: 报告名称，默认使用文件名
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源

        Returns:
            ReportID
        """
        if not os.path.exists(report_path):
            raise __QS_Error__(f"报告文件不存在: {report_path}")

        report_path = os.path.abspath(report_path)
        filename = os.path.basename(report_path)
        _, ext = os.path.splitext(filename)
        fmt = ext.lstrip(".").lower()
        if fmt not in ("html", "md", "markdown", "pdf"):
            fmt = "unknown"

        file_size = os.path.getsize(report_path)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        mtime = dt.datetime.fromtimestamp(
            os.path.getmtime(report_path), tz=dt.timezone.utc
        ).isoformat()

        # 生成确定性 ReportID
        raw = json.dumps(
            [report_path, str(file_size), mtime],
            sort_keys=True, ensure_ascii=False
        )
        report_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        props = {
            "ReportID": report_id,
            "Name": name or filename,
            "FilePath": report_path,
            "Format": fmt,
            "FileSize": file_size,
            "ScenarioName": scenario_name or "",
            "FactorNames": json.dumps(factor_qsids, ensure_ascii=False),
            "FileMtime": mtime,
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id

        self._runCypher(
            """
            MERGE (r:`报告` {ReportID: $report_id})
            ON CREATE SET r += $props, r.CreatedAt = $now
            ON MATCH SET r += $props
            """,
            {"report_id": report_id, "props": props, "now": now}
        )

        # 关联因子
        if factor_qsids:
            self._runCypher(
                """
                UNWIND $qsids AS qsid
                MATCH (r:`报告` {ReportID: $report_id})
                MATCH (f:`因子` {QSID: qsid})
                MERGE (f)-[:`有报告`]->(r)
                """,
                {"report_id": report_id, "qsids": factor_qsids}
            )

        # 关联回测
        if bt_qsid:
            bt = self.getBacktestByQSID(bt_qsid)
            if bt:
                self._runCypher(
                    """
                    MATCH (r:`报告` {ReportID: $report_id})
                    MATCH (b:`回测` {QSID: $bt_qsid})
                    MERGE (b)-[:`产生报告`]->(r)
                    """,
                    {"report_id": report_id, "bt_qsid": bt_qsid}
                )

        self._QS_Logger.info(
            f"已注册报告: {props['Name']} (ReportID: {report_id}, "
            f"格式: {fmt}, 大小: {file_size}B, 因子: {len(factor_qsids)}个)"
        )
        return report_id

    def getReport(self, report_id: str) -> Optional[Dict]:
        """按 ReportID 查询报告节点"""
        results = self._runCypher(
            "MATCH (r:`报告` {ReportID: $report_id}) RETURN r",
            {"report_id": report_id}
        )
        return results[0]["r"] if results else None

    def getFactorReports(self, factor_qsid: str) -> List[Dict]:
        """获取某个因子的所有报告

        Args:
            factor_qsid: 因子 QSID

        Returns:
            报告节点属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[:`有报告`]->(r:`报告`)
            RETURN r ORDER BY r.FileMtime DESC
            """,
            {"qsid": factor_qsid}
        )
        return [r["r"] for r in results]

    def getBacktestReports(self, bt_qsid: str) -> List[Dict]:
        """获取某个回测产生的所有报告

        Args:
            bt_qsid: 回测 QSID

        Returns:
            报告节点属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (b:`回测` {QSID: $qsid})-[:`产生报告`]->(r:`报告`)
            RETURN r ORDER BY r.FileMtime DESC
            """,
            {"qsid": bt_qsid}
        )
        return [r["r"] for r in results]

    def searchReports(self, name: Optional[str] = None,
                      scenario_name: Optional[str] = None,
                      factor_qsid: Optional[str] = None,
                      fmt: Optional[str] = None,
                      limit: int = 100,
                      user_id: Optional[str] = None) -> List[Dict]:
        """搜索报告

        Args:
            name: 报告名称（模糊匹配）
            scenario_name: 场景名称
            factor_qsid: 关联的因子 QSID
            fmt: 格式 (html/markdown/pdf)
            limit: 返回数量上限
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            报告节点属性字典列表
        """
        if factor_qsid:
            query = """
                MATCH (f:`因子` {QSID: $factor_qsid})-[:`有报告`]->(r:`报告`)
            """
            params = {"factor_qsid": factor_qsid, "limit": limit}
            conditions = []
            if name:
                conditions.append("r.Name CONTAINS $name")
                params["name"] = name
            if scenario_name:
                conditions.append("r.ScenarioName = $scenario_name")
                params["scenario_name"] = scenario_name
            if fmt:
                conditions.append("r.Format = $fmt")
                params["fmt"] = fmt
            if user_id is not None:
                conditions.append("(r.userId IS NULL OR r.userId = $user_id)")
                params["user_id"] = user_id
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query += f"""
                {where_clause}
                RETURN DISTINCT r ORDER BY r.FileMtime DESC LIMIT $limit
            """
        else:
            conditions = []
            params = {"limit": limit}
            if name:
                conditions.append("r.Name CONTAINS $name")
                params["name"] = name
            if scenario_name:
                conditions.append("r.ScenarioName = $scenario_name")
                params["scenario_name"] = scenario_name
            if fmt:
                conditions.append("r.Format = $fmt")
                params["fmt"] = fmt
            if user_id is not None:
                conditions.append("(r.userId IS NULL OR r.userId = $user_id)")
                params["user_id"] = user_id
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"""
                MATCH (r:`报告`)
                {where_clause}
                RETURN r ORDER BY r.FileMtime DESC LIMIT $limit
            """
        return [r["r"] for r in self._runCypher(query, params)]

    def deleteReport(self, report_id: str, delete_file: bool = False) -> bool:
        """删除报告节点，可选删除本地文件

        Args:
            report_id: ReportID
            delete_file: 是否同时删除本地文件

        Returns:
            是否成功
        """
        report = self.getReport(report_id)
        if not report:
            return False

        # 删除本地文件
        if delete_file:
            filepath = report.get("FilePath")
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError as e:
                    self._QS_Logger.warning(f"删除报告文件失败: {filepath}, {e}")

        # 删除节点
        self._runCypher(
            "MATCH (r:`报告` {ReportID: $report_id}) DETACH DELETE r",
            {"report_id": report_id}
        )

        self._QS_Logger.info(
            f"已删除报告: {report.get('Name', report_id)} "
            f"(ReportID: {report_id}, 删除文件: {delete_file})"
        )
        return True

    # endregion

    # region 风险库存储（RiskDB Store）

    def registerRiskDB(self, risk_db) -> str:
        """注册风险库到图数据库

        Args:
            risk_db: QuantStudio RiskDB 实例

        Returns:
            风险库名称
        """
        connection_data = risk_db.serialize()
        connection_data["__module__"] = risk_db.__class__.__module__
        props = {
            "Name": risk_db.Name,
            "DBType": risk_db.__class__.__name__,
            "ClassName": risk_db.__class__.__name__,
            "ModulePath": risk_db.__class__.__module__,
            "ConnectionJSON": json.dumps(_sanitizeForJSON(connection_data), ensure_ascii=False),
            "UpdatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self._runCypher(
            """
            MERGE (d:`风险库` {Name: $name})
            ON CREATE SET d += $props, d.CreatedAt = $now
            ON MATCH SET d += $props
            """,
            {"name": risk_db.Name, "props": props, "now": dt.datetime.now(dt.timezone.utc).isoformat()}
        )
        self._QS_Logger.info(f"已注册风险库: {risk_db.Name}")
        return risk_db.Name

    def _autoBuildRiskDB(self, rdb_name: str, rdb_node: dict):
        """从图节点元数据自动构建并连接 RiskDB 实例

        与 ``_autoBuildFactorDB`` 使用相同的 ``serialize()`` / ``deserialize()`` 协议。

        Args:
            rdb_name: 风险库名称
            rdb_node: Neo4j 返回的风险库节点（包含 ConnectionJSON 等属性）

        Returns:
            已连接的 RiskDB 实例
        """
        conn_json = json.loads(rdb_node.get("ConnectionJSON", "{}"))
        data = _desanitizeFromJSON(conn_json)

        if data.get("__type__") == "__QS_Object__":
            module_path = data.get("__module__")
            class_name = data.get("__class__")
            qs_args_data = data.get("__qsargs__", {})
        else:
            # 旧格式兼容：{"type": "..."}
            module_path = data.get("ModulePath")
            class_name = data.get("ClassName")
            qs_args_data = data.get("QSArgs", {})

        if not module_path or not class_name:
            self._QS_Logger.warning(
                f"风险库 '{rdb_name}' 的 ConnectionJSON 缺少 ModulePath 或 ClassName，"
                f"无法自动构建，请先调用 registerRiskDB 显式注册该风险库"
            )
            return None

        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise __QS_Error__(
                f"风险库 '{rdb_name}' 自动构建失败: "
                f"无法加载类 {module_path}.{class_name}: {e}"
            )

        qs_args = cls.__QS_ArgClass__.deserialize(qs_args_data).model_dump()
        rdb = cls(args=qs_args)
        rdb.connect()
        self._QS_Logger.info(
            f"已自动构建并连接风险库: '{rdb_name}'"
            + (f" (配置文件: {fdb.ConfigFile})" if fdb.ConfigFile else "")
        )
        return rdb

    def storeRiskTable(self, rt, risk_db_name: Optional[str] = None) -> str:
        """存储风险表节点

        Args:
            rt: RiskTable 实例
            risk_db_name: 关联的风险库名称

        Returns:
            风险表 QSID
        """
        props = {
            "Name": rt._QSArgs.Name,
            "QSID": rt.QSID,
            "ClassName": rt.__class__.__name__,
            "ModulePath": rt.__class__.__module__,
            "MetaDataJSON": json.dumps(_sanitizeForJSON(rt.getMetaData(key=None).to_dict()) if hasattr(rt.getMetaData(key=None), 'to_dict') else {}, ensure_ascii=False),
            "QSArgsJSON": json.dumps(_sanitizeForJSON(rt._QSArgs.serialize()), ensure_ascii=False),
            "UpdatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self._runCypher(
            """
            MERGE (t:`风险表` {QSID: $qsid})
            ON CREATE SET t += $props, t.CreatedAt = $now
            ON MATCH SET t += $props
            """,
            {"qsid": rt.QSID, "props": props, "now": dt.datetime.now(dt.timezone.utc).isoformat()}
        )
        actual_rdb_name = risk_db_name or (rt.RiskDB.Name if hasattr(rt, 'RiskDB') and rt.RiskDB else None)
        if actual_rdb_name:
            self._runCypher(
                """
                MATCH (t:`风险表` {QSID: $t_qsid})
                MATCH (d:`风险库` {Name: $rdb_name})
                MERGE (t)-[:`属于风险库`]->(d)
                """,
                {"t_qsid": rt.QSID, "rdb_name": actual_rdb_name}
            )
        return rt.QSID

    def linkBacktestRiskTable(self, bt_qsid: str, rt_qsid: str) -> None:
        """建立回测节点与风险表的依赖关系

        Args:
            bt_qsid: 回测节点 QSID
            rt_qsid: 风险表 QSID
        """
        self._runCypher(
            """
            MATCH (b:`回测` {QSID: $bt_qsid})
            MATCH (rt:`风险表` {QSID: $rt_qsid})
            MERGE (b)-[:`依赖风险表`]->(rt)
            """,
            {"bt_qsid": bt_qsid, "rt_qsid": rt_qsid}
        )

    def getRiskTableByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询风险表节点"""
        results = self._runCypher(
            "MATCH (rt:`风险表` {QSID: $qsid}) RETURN rt",
            {"qsid": qsid}
        )
        return results[0]["rt"] if results else None

    def searchRiskTables(self, name: Optional[str] = None,
                         limit: int = 100) -> List[Dict]:
        """搜索风险表

        Args:
            name: 风险表名称（模糊匹配）
            limit: 返回数量上限
        """
        if name:
            results = self._runCypher(
                """
                MATCH (rt:`风险表`)
                WHERE rt.Name CONTAINS $name
                RETURN rt ORDER BY rt.Name LIMIT $limit
                """,
                {"name": name, "limit": limit}
            )
        else:
            results = self._runCypher(
                """
                MATCH (rt:`风险表`)
                RETURN rt ORDER BY rt.Name LIMIT $limit
                """,
                {"limit": limit}
            )
        return [r["rt"] for r in results]

    # endregion

    # region 组合优化器存储（Optimizer Store）

    def storeOptimizer(self, pc, tags: Optional[List[str]] = None) -> str:
        """存储组合优化器节点

        Args:
            pc: BasePC 实例（CVXPC、MatlabPC 等）
            tags: 可选的标签列表

        Returns:
            优化器 QSID
        """
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        props = {
            "Name": pc._QSArgs.Name,
            "QSID": pc.QSID,
            "ClassName": pc.__class__.__name__,
            "ModulePath": pc.__class__.__module__,
            "OptimizerType": pc.__class__.__name__,
            "Description": getattr(pc._QSArgs, 'Description', ''),
            "QSArgsJSON": json.dumps(_sanitizeForJSON(pc._QSArgs.serialize()), ensure_ascii=False),
            "UpdatedAt": now,
        }
        self._runCypher(
            """
            MERGE (o:`组合优化器` {QSID: $qsid})
            ON CREATE SET o += $props, o.CreatedAt = $now
            ON MATCH SET o += $props
            """,
            {"qsid": pc.QSID, "props": props, "now": now}
        )
        if tags:
            self._runCypher(
                """
                UNWIND $rels AS rel
                MERGE (t:`标签` {Name: rel.tag})
                WITH t, rel
                MATCH (o:`组合优化器` {QSID: rel.qsid})
                MERGE (o)-[:`打标签`]->(t)
                """,
                {"rels": [{"qsid": pc.QSID, "tag": t} for t in tags]}
            )
        self._QS_Logger.info(f"已存储组合优化器: {pc._QSArgs.Name} (QSID: {pc.QSID})")
        return pc.QSID

    def linkBacktestOptimizer(self, bt_qsid: str, pc_qsid: str) -> None:
        """建立回测（策略）节点与组合优化器的使用关系

        Args:
            bt_qsid: 回测（策略）节点 QSID
            pc_qsid: 组合优化器 QSID
        """
        self._runCypher(
            """
            MATCH (b:`回测` {QSID: $bt_qsid})
            MATCH (o:`组合优化器` {QSID: $pc_qsid})
            MERGE (b)-[:`使用优化器`]->(o)
            """,
            {"bt_qsid": bt_qsid, "pc_qsid": pc_qsid}
        )

    def getOptimizerByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询组合优化器节点"""
        results = self._runCypher(
            "MATCH (o:`组合优化器` {QSID: $qsid}) RETURN o",
            {"qsid": qsid}
        )
        return results[0]["o"] if results else None

    def searchOptimizers(self, name: Optional[str] = None,
                         optimizer_type: Optional[str] = None,
                         limit: int = 100) -> List[Dict]:
        """搜索组合优化器

        Args:
            name: 优化器名称（模糊匹配）
            optimizer_type: 优化器类型（CVXPC / MatlabPC / BasePC）
            limit: 返回数量上限
        """
        conditions = []
        params = {"limit": limit}
        if name:
            conditions.append("o.Name CONTAINS $name")
            params["name"] = name
        if optimizer_type:
            conditions.append("o.OptimizerType = $op_type")
            params["op_type"] = optimizer_type
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        results = self._runCypher(
            f"""
            MATCH (o:`组合优化器`)
            {where_clause}
            RETURN o ORDER BY o.Name LIMIT $limit
            """,
            params
        )
        return [r["o"] for r in results]

    def deleteOptimizer(self, qsid: str) -> None:
        """删除组合优化器节点

        Args:
            qsid: 优化器 QSID
        """
        self._runCypher(
            "MATCH (o:`组合优化器` {QSID: $qsid}) DETACH DELETE o",
            {"qsid": qsid}
        )
        self._QS_Logger.info(f"已删除组合优化器: {qsid}")

    # endregion

    # region 策略存储与检索（Strategy Store & Retrieve）

    def _serializeStrategy(self, def_obj, strategy_instance) -> dict:
        """序列化单个策略实例为 Neo4j 节点属性字典

        Args:
            def_obj: Def 实例（提供 Meta 元信息）
            strategy_instance: 单个策略实例（Factor 对象）

        Returns:
            Neo4j 节点属性字典
        """
        import json as _json
        from QSExt.QSRegistry._serialization import _sanitizeForJSON

        meta = def_obj.Meta
        strategy = strategy_instance
        strategy_cls = type(strategy)
        now = dt.datetime.now(dt.timezone.utc).isoformat()

        props = {
            "Name": strategy._QSArgs.Name,
            "QSID": strategy.QSID,
            "TargetTable": meta.TargetTable,
            "IDType": meta.IDType,
            "OperatorConfigJSON": _json.dumps(
                _sanitizeForJSON(meta.OperatorConfig), ensure_ascii=False
            ),
            "ClassName": strategy_cls.__name__,
            "ModulePath": strategy_cls.__module__,
            "MetaJSON": _json.dumps(_sanitizeForJSON({
                "TargetTable": meta.TargetTable,
                "IDType": meta.IDType,
                "Author": meta.Author,
                "Description": meta.Description,
                "MaxLookBack": meta.MaxLookBack,
                "OperatorConfig": meta.OperatorConfig,
                "Tags": meta.Tags,
                "FactorDeps": meta.FactorDeps,
                "StrategyDeps": meta.StrategyDeps,
                "DBDeps": meta.DBDeps,
                "ModelArgs": meta.ModelArgs,
            }), ensure_ascii=False),
            "DefScriptPath": meta.DefScriptPath,
            "UpdatedAt": now,
        }
        return props

    def storeStrategies(self, strategies: list,
                        tags: Optional[Dict[str, List[str]]] = None,
                        user_id: Optional[str] = None) -> int:
        """批量存储策略到 Neo4j 图数据库

        为每个策略实例（StrategyList 中的每一项）创建 (:策略) 节点，并建立依赖关系：
        - (策略)-[:依赖因子]->(:因子) — FactorDeps 中声明的因子依赖
        - (策略)-[:依赖策略]->(:策略) — StrategyDeps 中声明的策略间依赖
        - (策略)-[:存入因子表]->(:因子表) — 策略信号输出目标表
        - (策略)-[:打标签]->(:标签) — 分类标签

        Args:
            strategies: Def 列表（每个含 StrategyList 可多个策略实例）
            tags: 策略 QSID → 标签列表的映射
            user_id: 资源归属用户 ID，非空时写入 userId 属性标记为私有资源

        Returns:
            成功存储的策略实例数量
        """
        if not strategies:
            return 0

        import json as _json
        from QSExt.QSRegistry._serialization import _sanitizeForJSON

        now = dt.datetime.now(dt.timezone.utc).isoformat()

        # Phase 1: 构建策略节点数据（每个策略实例一个节点）
        strategy_nodes = []
        for sd in strategies:
            for strategy_instance in sd.StrategyList:
                props = self._serializeStrategy(sd, strategy_instance)
                if user_id:
                    props["userId"] = user_id
                # 生成嵌入向量
                if self._QSArgs.EmbeddingModel:
                    text = f"{props['Name']} {sd.Meta.Description} {' '.join(sd.Meta.Tags)}"
                    emb = self._generateEmbedding(text)
                    if emb is not None:
                        props["Embedding"] = emb
                        props["EmbeddingModel"] = self._QSArgs.EmbeddingModel
                        props["EmbeddingDim"] = len(emb)
                strategy_nodes.append({
                    "qsid": props["QSID"],
                    "props": props,
                    "now": now,
                })

        # Phase 2: 批量 MERGE 策略节点
        if strategy_nodes:
            self._runCypher("""
                UNWIND $nodes AS node
                MERGE (s:`策略` {QSID: node.qsid})
                ON CREATE SET s += node.props, s.CreatedAt = node.now
                ON MATCH SET s += node.props
            """, {"nodes": strategy_nodes})

        # Phase 3: 批量创建关系

        # 3a. (策略)-[:依赖因子]->(:因子) — 从 FactorDeps 解析
        factor_dep_rels = []
        for sd in strategies:
            for table_name, entries in sd.Meta.FactorDeps.items():
                for entry in entries:
                    factor_name = entry if isinstance(entry, str) else entry.get("Name", "")
                    if factor_name:
                        for strategy_instance in sd.StrategyList:
                            factor_dep_rels.append({
                                "s_qsid": strategy_instance.QSID,
                                "factor_name": factor_name,
                            })
        if factor_dep_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (s:`策略` {QSID: rel.s_qsid})
                MATCH (f:`因子` {Name: rel.factor_name})
                MERGE (s)-[:`依赖因子`]->(f)
            """, {"rels": factor_dep_rels})

        # 3b. (策略)-[:依赖策略]->(:策略) — 从 StrategyDeps 解析
        strategy_dep_rels = []
        for sd in strategies:
            for dep_module_path in sd.Meta.StrategyDeps:
                # 解析模块路径 → TargetTable
                dep_tt = dep_module_path  # 默认回退：直接把 module_path 当作 TargetTable
                try:
                    dep_mod = importlib.import_module(dep_module_path)
                    dep_meta = getattr(dep_mod, '__STRATEGY_META__', None) or {}
                    dep_tt = dep_meta.get('TargetTable', dep_module_path)
                except ImportError:
                    pass
                for strategy_instance in sd.StrategyList:
                    strategy_dep_rels.append({
                        "s_qsid": strategy_instance.QSID,
                        "target_table": dep_tt,
                    })
        if strategy_dep_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (s:`策略` {QSID: rel.s_qsid})
                MATCH (t:`策略` {TargetTable: rel.target_table})
                MERGE (s)-[:`依赖策略`]->(t)
            """, {"rels": strategy_dep_rels})

        # 3c. (策略)-[:存入因子表]->(:因子表) — TargetTable
        output_rels = []
        for sd in strategies:
            if sd.Meta.TargetTable:
                for strategy_instance in sd.StrategyList:
                    output_rels.append({
                        "s_qsid": strategy_instance.QSID,
                        "target_table": sd.Meta.TargetTable,
                    })
        if output_rels:
            self._runCypher("""
                UNWIND $rels AS rel
                MATCH (s:`策略` {QSID: rel.s_qsid})
                MERGE (t:`因子表` {Name: rel.target_table})
                MERGE (s)-[:`存入因子表`]->(t)
            """, {"rels": output_rels})

        # Phase 4: 标签
        if tags:
            tag_rels = []
            for qsid, tag_list in tags.items():
                for tag_name in tag_list:
                    tag_rels.append({"qsid": qsid, "tag": tag_name})
            if tag_rels:
                self._runCypher("""
                    UNWIND $rels AS rel
                    MERGE (t:`标签` {Name: rel.tag})
                    WITH t, rel
                    MATCH (s:`策略` {QSID: rel.qsid})
                    MERGE (s)-[:`打标签`]->(t)
                """, {"rels": tag_rels})

        total_instances = sum(len(sd.StrategyList) for sd in strategies)
        self._QS_Logger.info(f"已批量存储 {total_instances} 个策略实例 (来自 {len(strategies)} 个 Def)")
        return total_instances

    # --- 脚本节点存储 ---

    def storeScript(self, script_path: str, content: Optional[str] = None,
                    meta: Optional[dict] = None, user_id: Optional[str] = None) -> str:
        """注册脚本节点到图数据库

        Args:
            script_path: 脚本文件路径（用于提取文件名和读取内容）
            content: 脚本内容（为 None 时从 script_path 读取）
            meta: __FACTOR_META__ 或 __STRATEGY_META__ 内容（为 None 时尝试从脚本中提取）
            user_id: 资源归属用户 ID

        Returns:
            脚本节点的 QSID
        """
        import hashlib as _hashlib

        # 1. 读取内容
        if content is None:
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()

        # 2. 计算内容哈希和 QSID
        content_hash = _hashlib.sha256(content.encode("utf-8")).hexdigest()
        qsid = content_hash[:16]  # 前 16 位作为 QSID

        # 3. 提取文件名
        script_name = os.path.basename(script_path)

        # 4. 提取或解析 meta
        if meta is None:
            meta = self._extractMetaFromScript(content)

        # 5. 确定入口函数和模块类型
        entry_function = "defNode" if "defNode" in content else ("defFactor" if "defFactor" in content else "defStrategy")
        module_type = "factor" if "defFactor" in content or "defNode" in content else "strategy"

        # 6. 构建节点属性
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        props = {
            "QSID": qsid,
            "Name": script_name,
            "Path": script_path,
            "Content": content,
            "ContentHash": content_hash,
            "EntryFunction": entry_function,
            "ModuleType": module_type,
            "Author": meta.get("Author", ""),
            "Description": meta.get("Description", ""),
            "Tags": meta.get("Tags", []),
            "MetaJSON": json.dumps(meta, ensure_ascii=False) if meta else "{}",
            "UpdatedAt": now,
        }
        if user_id:
            props["userId"] = user_id

        # 7. 生成嵌入向量
        if self._QSArgs.EmbeddingModel and meta.get("Description"):
            text = f"{script_name} {meta['Description']}"
            emb = self._generateEmbedding(text)
            if emb is not None:
                props["Embedding"] = emb
                props["EmbeddingModel"] = self._QSArgs.EmbeddingModel
                props["EmbeddingDim"] = len(emb)

        # 8. MERGE 脚本节点
        self._runCypher(
            """
            MERGE (s:`脚本` {QSID: $qsid})
            ON CREATE SET s += $props, s.CreatedAt = $now
            ON MATCH SET s += $props
            """,
            {"qsid": qsid, "props": props, "now": now}
        )

        # 9. 建立与依赖脚本的关系
        self._createScriptDeps(qsid, meta)

        # 10. 建立与因子库的关系
        self._createScriptFDBDeps(qsid, meta)

        # 11. 建立标签关系
        if meta.get("Tags"):
            for tag_name in meta["Tags"]:
                self._runCypher(
                    """
                    MERGE (t:`标签` {Name: $tag})
                    WITH t
                    MATCH (s:`脚本` {QSID: $qsid})
                    MERGE (s)-[:`打标签`]->(t)
                    """,
                    {"qsid": qsid, "tag": tag_name}
                )

        self._QS_Logger.info(f"已注册脚本: {script_name} (QSID: {qsid})")
        return qsid

    def _extractMetaFromScript(self, content: str) -> dict:
        """从脚本内容中提取 __FACTOR_META__ 或 __STRATEGY_META__"""
        import re as _re

        # 查找 __FACTOR_META__ 或 __STRATEGY_META__ 的起始位置
        patterns = [r'__FACTOR_META__\s*=\s*\{', r'__STRATEGY_META__\s*=\s*\{']
        for pattern in patterns:
            match = _re.search(pattern, content)
            if match:
                # 从匹配位置开始，找到完整的字典定义
                start = match.end() - 1  # 指向 '{'
                depth = 0
                in_string = False
                string_char = None
                i = start
                while i < len(content):
                    ch = content[i]
                    if in_string:
                        if ch == '\\':
                            i += 1  # 跳过转义字符
                        elif ch == string_char:
                            in_string = False
                    else:
                        if ch in ('"', "'"):
                            in_string = True
                            string_char = ch
                        elif ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                meta_str = content[start:i + 1]
                                try:
                                    return eval(meta_str)
                                except Exception:
                                    pass
                                break
                    i += 1
        return {}

    def _createScriptDeps(self, script_qsid: str, meta: dict):
        """创建脚本间的依赖关系（FactorDeps/StrategyDeps）"""
        factor_deps = meta.get("FactorDeps", {})
        strategy_deps = meta.get("StrategyDeps", {})

        # FactorDeps: {target_table: [factor_name, ...]}
        for target_table, factor_names in factor_deps.items():
            # 查找目标脚本（通过 TargetTable 匹配）
            dep_script = self._findScriptByTargetTable(target_table)
            if dep_script:
                self._runCypher(
                    """
                    MATCH (s:`脚本` {QSID: $source_qsid})
                    MATCH (t:`脚本` {QSID: $target_qsid})
                    MERGE (s)-[r:`依赖脚本`]->(t)
                    SET r.FactorNames = $factor_names
                    """,
                    {
                        "source_qsid": script_qsid,
                        "target_qsid": dep_script["QSID"],
                        "factor_names": factor_names,
                    }
                )

        # StrategyDeps: {target_table: {factor_name: alias, ...}}
        for target_table in strategy_deps:
            dep_script = self._findScriptByTargetTable(target_table)
            if dep_script:
                self._runCypher(
                    """
                    MATCH (s:`脚本` {QSID: $source_qsid})
                    MATCH (t:`脚本` {QSID: $target_qsid})
                    MERGE (s)-[:`依赖脚本`]->(t)
                    """,
                    {
                        "source_qsid": script_qsid,
                        "target_qsid": dep_script["QSID"],
                    }
                )

    def _findScriptByTargetTable(self, target_table: str) -> Optional[Dict]:
        """通过 TargetTable 查找脚本节点"""
        results = self._runCypher(
            """
            MATCH (s:`脚本`)
            WHERE s.MetaJSON CONTAINS $target_table
            RETURN s
            """,
            {"target_table": target_table}
        )
        for r in results:
            meta = json.loads(r["s"].get("MetaJSON", "{}"))
            if meta.get("TargetTable") == target_table:
                return r["s"]
        return None

    def _createScriptFDBDeps(self, script_qsid: str, meta: dict):
        """创建脚本与因子库的依赖关系"""
        db_deps = meta.get("DBDeps", {})
        for fdb_name, purpose in db_deps.items():
            # 查找已注册的因子库
            fdb_results = self._runCypher(
                "MATCH (d:`因子库` {Name: $name}) RETURN d",
                {"name": fdb_name}
            )
            if fdb_results:
                fdb_qsid = fdb_results[0]["d"]["QSID"]
                self._runCypher(
                    """
                    MATCH (s:`脚本` {QSID: $script_qsid})
                    MATCH (d:`因子库` {QSID: $fdb_qsid})
                    MERGE (s)-[r:`使用因子库`]->(d)
                    SET r.Purpose = $purpose
                    """,
                    {
                        "script_qsid": script_qsid,
                        "fdb_qsid": fdb_qsid,
                        "purpose": purpose,
                    }
                )

    def collectScriptFactors(self, factors: list, script_qsid: str) -> list:
        """递归收集脚本定义的因子（排除已定义于其他脚本的因子）

        Args:
            factors: 因子列表（包含 Descriptors 中间因子）
            script_qsid: 当前脚本的 QSID

        Returns:
            应关联到当前脚本的因子列表
        """
        result = []
        visited = set()

        def _collect(factors):
            for factor in factors:
                qsid = factor.QSID
                if qsid in visited:
                    continue
                visited.add(qsid)

                # 检查因子是否已被其他脚本定义
                existing = self._runCypher(
                    """
                    MATCH (f:`因子` {QSID: $qsid})-[:`定义于`]->(s:`脚本`)
                    WHERE s.QSID <> $script_qsid
                    RETURN s.QSID AS script_qsid
                    """,
                    {"qsid": qsid, "script_qsid": script_qsid}
                )

                if existing:
                    self._QS_Logger.debug(
                        f"跳过因子 {factor._QSArgs.Name}（已定义于脚本 {existing[0]['script_qsid']}）"
                    )
                    continue

                result.append(factor)

                # 递归收集 Descriptors（中间因子）
                if hasattr(factor, 'Descriptors') and factor.Descriptors:
                    _collect(factor.Descriptors)

        _collect(factors)
        return result

    def cleanScriptFactors(self, script_qsid: str) -> int:
        """清理脚本关联的所有因子（断开"定义于"关系）

        只删除因子与当前脚本的"定义于"关系，不删除因子节点本身。
        如果因子还被其他脚本定义，因子节点保留。

        Args:
            script_qsid: 脚本节点 QSID

        Returns:
            清理的因子数量
        """
        # 获取脚本关联的所有因子
        results = self._runCypher(
            """
            MATCH (f:`因子`)-[r:`定义于`]->(s:`脚本` {QSID: $qsid})
            DELETE r
            RETURN count(r) AS deleted
            """,
            {"qsid": script_qsid}
        )
        deleted = results[0]["deleted"] if results else 0

        if deleted > 0:
            # 清除因子的 DefScriptQSID 属性（仅对不再被任何脚本定义的因子）
            self._runCypher(
                """
                MATCH (f:`因子`)
                WHERE f.DefScriptQSID = $qsid AND NOT (f)-[:`定义于`]->(:`脚本`)
                REMOVE f.DefScriptQSID
                """,
                {"qsid": script_qsid}
            )
            self._QS_Logger.info(f"已清理脚本 {script_qsid} 的 {deleted} 个因子关系")

        return deleted

    def associateFactorsToScript(self, factors: list, script_qsid: str) -> int:
        """将因子列表关联到脚本（创建"定义于"关系）

        Args:
            factors: 因子对象列表
            script_qsid: 脚本节点 QSID

        Returns:
            成功关联的因子数量
        """
        associated = 0
        for factor in factors:
            self._runCypher(
                """
                MATCH (f:`因子` {QSID: $factor_qsid})
                MATCH (s:`脚本` {QSID: $script_qsid})
                MERGE (f)-[:`定义于`]->(s)
                """,
                {"factor_qsid": factor.QSID, "script_qsid": script_qsid}
            )
            # 更新因子的 DefScriptQSID 属性
            self._runCypher(
                """
                MATCH (f:`因子` {QSID: $factor_qsid})
                SET f.DefScriptQSID = $script_qsid
                """,
                {"factor_qsid": factor.QSID, "script_qsid": script_qsid}
            )
            associated += 1

        if associated > 0:
            self._QS_Logger.info(f"已关联 {associated} 个因子到脚本 {script_qsid}")

        return associated

    def storeDef(self, def_obj, script_path: Optional[str] = None,
                 user_id: Optional[str] = None, clean_old: bool = True) -> dict:
        """存储 Def 及其定义脚本

        一体化存储：脚本节点 + 因子/策略节点 + "定义于"关系。
        默认会清理脚本关联的旧节点关系，再重新关联。

        Args:
            def_obj: Def 实例（含 FactorList、StrategyList 和 Meta）
            script_path: 脚本路径（为 None 时从 meta.DefScriptPath 获取）
            user_id: 用户 ID
            clean_old: 是否清理旧的关系（默认 True）

        Returns:
            {
                "factor_count": int,       # 关联的因子数量
                "script_qsid": "...",      # 脚本节点 QSID
                "dep_script_qsids": [...]   # 依赖脚本 QSID 列表
            }
        """
        # 1. 获取脚本路径
        if script_path is None:
            script_path = def_obj.Meta.DefScriptPath
        if not script_path:
            raise ValueError("无法确定脚本路径：请提供 script_path 或在 meta 中设置 DefScriptPath")

        # 2. 构建脚本元信息
        script_meta = {
            "TargetTable": def_obj.Meta.TargetTable,
            "IDType": def_obj.Meta.IDType,
            "Author": def_obj.Meta.Author,
            "Description": def_obj.Meta.Description,
            "Tags": list(def_obj.Meta.Tags),
            "FactorDeps": def_obj.Meta.FactorDeps,
            "StrategyDeps": def_obj.Meta.StrategyDeps if hasattr(def_obj.Meta, 'StrategyDeps') else {},
            "DBDeps": def_obj.Meta.DBDeps,
            "ModelArgs": def_obj.Meta.ModelArgs,
        }

        # 3. 存储脚本节点
        script_qsid = self.storeScript(script_path, meta=script_meta, user_id=user_id)

        # 4. 存储因子
        self.storeFactors(def_obj.FactorList, user_id=user_id)

        # 5. 清理旧的因子关系
        if clean_old:
            self.cleanScriptFactors(script_qsid)

        # 6. 收集并关联因子（排除已定义于其他脚本的因子）
        own_factors = self.collectScriptFactors(def_obj.FactorList, script_qsid)
        factor_count = self.associateFactorsToScript(own_factors, script_qsid)

        # 7. 获取依赖脚本 QSID
        dep_script_qsids = []
        dep_results = self._runCypher(
            """
            MATCH (s:`脚本` {QSID: $qsid})-[:`依赖脚本`]->(dep:`脚本`)
            RETURN dep.QSID
            """,
            {"qsid": script_qsid}
        )
        dep_script_qsids = [r["dep.QSID"] for r in dep_results]

        # 8. 存储策略（如果有）
        strategy_count = 0
        if def_obj.StrategyList:
            strategy_count = self.storeStrategies([def_obj], user_id=user_id)

        self._QS_Logger.info(
            f"已存储 Def: {factor_count} 个因子, {strategy_count} 个策略, "
            f"脚本 QSID: {script_qsid}, 依赖脚本: {len(dep_script_qsids)} 个"
        )

        return {
            "factor_count": factor_count,
            "strategy_count": strategy_count,
            "script_qsid": script_qsid,
            "dep_script_qsids": dep_script_qsids,
        }

    # 旧名称兼容（调用方可逐步迁移）
    storeFactorDef = storeDef

    def searchStrategies(self, name: Optional[str] = None,
                         tag: Optional[str] = None,
                         factor_qsid: Optional[str] = None,
                         limit: int = 100,
                         user_id: Optional[str] = None) -> List[Dict]:
        """多条件组合搜索策略

        Args:
            name: 策略名称（模糊匹配）
            tag: 标签名称
            factor_qsid: 依赖因子的 QSID，查找所有依赖该因子的策略
            limit: 返回数量上限
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            策略属性字典列表
        """
        conditions = []
        params = {"limit": limit}

        if name:
            conditions.append("s.Name CONTAINS $name")
            params["name"] = name
        if user_id is not None:
            conditions.append("(s.userId IS NULL OR s.userId = $user_id)")
            params["user_id"] = user_id

        if factor_qsid:
            query = f"""
                MATCH (s:`策略`)-[:`依赖因子`]->(f:`因子` {{QSID: $factor_qsid}})
                {'WHERE ' + ' AND '.join(conditions) if conditions else ''}
                RETURN s ORDER BY s.Name LIMIT $limit
            """
            params["factor_qsid"] = factor_qsid
        elif tag:
            query = f"""
                MATCH (s:`策略`)-[:`打标签`]->(t:`标签` {{Name: $tag}})
                {'WHERE ' + ' AND '.join(conditions) if conditions else ''}
                RETURN s ORDER BY s.Name LIMIT $limit
            """
            params["tag"] = tag
        else:
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"""
                MATCH (s:`策略`)
                {where_clause}
                RETURN s ORDER BY s.Name LIMIT $limit
            """

        results = self._runCypher(query, params)
        return [r["s"] for r in results]

    def searchStrategiesByDescription(self, query_text: str, limit: int = 20,
                                       min_score: Optional[float] = None,
                                       user_id: Optional[str] = None) -> List[Dict]:
        """基于描述文本的向量语义检索策略

        Args:
            query_text: 自然语言查询文本
            limit: 返回数量上限
            min_score: 最低相似度阈值 (0~1)
            user_id: 资源隔离的用户 ID，非空时仅返回公共资源与该用户的私有资源

        Returns:
            策略属性字典列表，每项包含 Similarity 分数
        """
        if not self._QSArgs.EmbeddingModel:
            self._QS_Logger.warning("向量检索未启用：EmbeddingModel 为空")
            return []

        query_embedding = self._generateEmbedding(query_text)
        if query_embedding is None:
            return []

        try:
            results = self._runCypher(
                """
                CALL db.index.vector.queryNodes('strategy_embedding', $limit, $embedding)
                YIELD node AS s, score
                RETURN s {.Name, .QSID, .TargetTable, .IDType, .ClassName, .DefScriptPath, .userId}, score
                ORDER BY score DESC
                """,
                {"limit": limit, "embedding": query_embedding}
            )
        except Exception as e:
            self._QS_Logger.warning(f"策略向量检索失败（向量索引可能不存在）: {e}")
            return []

        if min_score is not None:
            results = [r for r in results if r["score"] >= min_score]
        if user_id is not None:
            results = [
                r for r in results
                if r["s"].get("userId") in (None, "", user_id)
            ]
        return [{"Similarity": round(r["score"], 6), **r["s"]} for r in results]

    def getStrategyByQSID(self, qsid: str) -> Optional[Dict]:
        """根据 QSID 查询策略节点

        Args:
            qsid: 策略 QSID

        Returns:
            策略节点属性字典，未找到返回 None
        """
        results = self._runCypher(
            "MATCH (s:`策略` {QSID: $qsid}) RETURN s",
            {"qsid": qsid}
        )
        return results[0]["s"] if results else None

    # --- 脚本节点查询 ---

    def getScriptByQSID(self, qsid: str) -> Optional[Dict]:
        """按 QSID 查询脚本节点

        Args:
            qsid: 脚本节点 QSID

        Returns:
            脚本节点属性字典，未找到返回 None
        """
        results = self._runCypher(
            "MATCH (s:`脚本` {QSID: $qsid}) RETURN s",
            {"qsid": qsid}
        )
        return results[0]["s"] if results else None

    def searchScripts(self, name: Optional[str] = None,
                      module_type: Optional[str] = None,
                      query_text: Optional[str] = None,
                      limit: int = 20,
                      user_id: Optional[str] = None) -> List[Dict]:
        """搜索脚本节点

        Args:
            name: 脚本文件名（模糊匹配）
            module_type: 模块类型（factor / strategy）
            query_text: 语义搜索文本（使用嵌入向量）
            limit: 返回数量上限
            user_id: 资源隔离的用户 ID

        Returns:
            脚本节点属性字典列表
        """
        # 优先使用语义搜索
        if query_text and self._QSArgs.EmbeddingModel:
            return self._searchScriptsByDescription(query_text, limit, user_id=user_id)

        conditions = []
        params = {"limit": limit}
        if name:
            conditions.append("s.Name CONTAINS $name")
            params["name"] = name
        if module_type:
            conditions.append("s.ModuleType = $module_type")
            params["module_type"] = module_type
        if user_id is not None:
            conditions.append("(s.userId IS NULL OR s.userId = $user_id)")
            params["user_id"] = user_id

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
            MATCH (s:`脚本`)
            {where_clause}
            RETURN s ORDER BY s.Name LIMIT $limit
        """
        results = self._runCypher(query, params)
        return [r["s"] for r in results]

    def _searchScriptsByDescription(self, query_text: str, limit: int = 20,
                                     user_id: Optional[str] = None) -> List[Dict]:
        """基于描述文本的向量语义检索脚本"""
        query_embedding = self._generateEmbedding(query_text)
        if query_embedding is None:
            return []
        try:
            results = self._runCypher(
                """
                CALL db.index.vector.queryNodes('script_embedding', $limit, $embedding)
                YIELD node AS s, score
                RETURN s {.Name, .QSID, .ModuleType, .EntryFunction, .Author, .Description, .userId}, score
                ORDER BY score DESC
                """,
                {"limit": limit, "embedding": query_embedding}
            )
        except Exception as e:
            self._QS_Logger.warning(f"脚本向量检索失败: {e}")
            return []
        if user_id is not None:
            results = [
                r for r in results
                if r["s"].get("userId") in (None, "", user_id)
            ]
        return [{"Similarity": round(r["score"], 6), **r["s"]} for r in results]

    def getScriptFactors(self, script_qsid: str) -> List[Dict]:
        """获取脚本定义的所有因子

        Args:
            script_qsid: 脚本节点 QSID

        Returns:
            因子节点属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (f:`因子`)-[:`定义于`]->(s:`脚本` {QSID: $qsid})
            RETURN f
            """,
            {"qsid": script_qsid}
        )
        return [r["f"] for r in results]

    def getScriptStrategies(self, script_qsid: str) -> List[Dict]:
        """获取脚本定义的所有策略

        Args:
            script_qsid: 脚本节点 QSID

        Returns:
            策略节点属性字典列表
        """
        results = self._runCypher(
            """
            MATCH (s:`策略`)-[:`定义于`]->(sc:`脚本` {QSID: $qsid})
            RETURN s
            """,
            {"qsid": script_qsid}
        )
        return [r["s"] for r in results]

    def getScriptDeps(self, script_qsid: str, depth: int = 1) -> Dict:
        """获取脚本的依赖链（递归）

        Args:
            script_qsid: 脚本节点 QSID
            depth: 递归深度

        Returns:
            {
                "script_qsid": "...",
                "dependencies": [
                    {"qsid": "...", "name": "...", "depth": 1, "factor_names": [...]},
                    ...
                ]
            }
        """
        # Neo4j 可变长度关系语法: [:`关系类型`*min..max]
        query = (
            "MATCH path = (s:`脚本` {QSID: $qsid})-[:`依赖脚本`*1.." + str(depth) + "]->(dep:`脚本`)\n"
            "RETURN dep, length(path) AS dep_depth,\n"
            "       [r IN relationships(path) | r.FactorNames] AS factor_names_list\n"
            "ORDER BY dep_depth"
        )
        results = self._runCypher(query, {"qsid": script_qsid})
        dependencies = []
        for r in results:
            dep = r["dep"]
            factor_names = []
            for fn_list in r.get("factor_names_list", []):
                if fn_list:
                    factor_names.extend(fn_list)
            dependencies.append({
                "qsid": dep.get("QSID", ""),
                "name": dep.get("Name", ""),
                "depth": r["dep_depth"],
                "factor_names": factor_names,
            })
        return {
            "script_qsid": script_qsid,
            "dependencies": dependencies,
        }

    def getDefScript(self, qsid: str) -> Optional[Dict]:
        """获取因子或策略的定义脚本（含内容）

        Args:
            qsid: 因子或策略节点 QSID

        Returns:
            脚本节点属性字典，未找到返回 None
        """
        # 先尝试因子
        results = self._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[:`定义于`]->(s:`脚本`)
            RETURN s
            """,
            {"qsid": qsid}
        )
        if results:
            return results[0]["s"]
        # 再尝试策略
        results = self._runCypher(
            """
            MATCH (s:`策略` {QSID: $qsid})-[:`定义于`]->(sc:`脚本`)
            RETURN sc
            """,
            {"qsid": qsid}
        )
        return results[0]["sc"] if results else None

    getFactorDefScript = getDefScript
    getStrategyDefScript = getDefScript

    def getScriptImpact(self, script_qsid: str) -> Dict:
        """分析脚本变更的影响范围

        Args:
            script_qsid: 脚本节点 QSID

        Returns:
            {
                "script_qsid": "...",
                "script_name": "...",
                "direct_factors": [...],    # 直接定义的因子
                "direct_strategies": [...], # 直接定义的策略
                "downstream_scripts": [...], # 依赖该脚本的其他脚本
                "affected_backtests": [...], # 受影响的回测
                "affected_storers": [...],   # 受影响的因子存储器
            }
        """
        # 获取脚本基本信息
        script = self.getScriptByQSID(script_qsid)
        if not script:
            return {"error": f"未找到 QSID 为 {script_qsid} 的脚本"}

        # 1. 直接定义的因子
        direct_factors = self.getScriptFactors(script_qsid)
        direct_factors_info = [
            {"name": f.get("Name", ""), "qsid": f.get("QSID", "")}
            for f in direct_factors
        ]

        # 2. 直接定义的策略
        direct_strategies = self.getScriptStrategies(script_qsid)
        direct_strategies_info = [
            {"name": s.get("Name", ""), "qsid": s.get("QSID", "")}
            for s in direct_strategies
        ]

        # 3. 依赖该脚本的其他脚本（下游脚本）
        downstream_results = self._runCypher(
            """
            MATCH (downstream:`脚本`)-[:`依赖脚本`]->(s:`脚本` {QSID: $qsid})
            RETURN downstream
            """,
            {"qsid": script_qsid}
        )
        downstream_scripts = [
            {
                "qsid": r["downstream"].get("QSID", ""),
                "name": r["downstream"].get("Name", ""),
            }
            for r in downstream_results
        ]

        # 4. 受影响的回测（通过因子关联）
        affected_backtests = []
        for factor in direct_factors:
            bt_results = self._runCypher(
                """
                MATCH (b:`回测`)-[:`使用因子`]->(f:`因子` {QSID: $factor_qsid})
                RETURN b
                """,
                {"factor_qsid": factor.get("QSID", "")}
            )
            for r in bt_results:
                bt = r["b"]
                bt_info = {
                    "qsid": bt.get("QSID", ""),
                    "name": bt.get("Name", ""),
                }
                if bt_info not in affected_backtests:
                    affected_backtests.append(bt_info)

        # 5. 受影响的因子存储器（通过因子关联）
        affected_storers = []
        for factor in direct_factors:
            storer_results = self._runCypher(
                """
                MATCH (st:`因子存储器`)-[:`依赖`]->(f:`因子` {QSID: $factor_qsid})
                RETURN st
                """,
                {"factor_qsid": factor.get("QSID", "")}
            )
            for r in storer_results:
                st = r["st"]
                storer_info = {
                    "qsid": st.get("QSID", ""),
                    "name": st.get("Name", ""),
                    "target_table": st.get("TargetTable", ""),
                }
                if storer_info not in affected_storers:
                    affected_storers.append(storer_info)

        return {
            "script_qsid": script_qsid,
            "script_name": script.get("Name", ""),
            "direct_factors": direct_factors_info,
            "direct_strategies": direct_strategies_info,
            "downstream_scripts": downstream_scripts,
            "affected_backtests": affected_backtests,
            "affected_storers": affected_storers,
        }

    def getStrategyCode(self, qsid: str) -> Optional[str]:
        """根据 QSID 获取策略源代码路径

        Args:
            qsid: 策略 QSID

        Returns:
            DefScriptPath 文件路径，未找到返回 None
        """
        result = self.getStrategyByQSID(qsid)
        if result and result.get("DefScriptPath"):
            path = result["DefScriptPath"]
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    self._QS_Logger.warning(f"读取策略源代码失败 ({path}): {e}")
                    return None
        return None

    def getStrategyDependencyGraph(self, qsid: str, direction: str = "both") -> Dict:
        """获取策略的依赖子图

        Args:
            qsid: 目标策略 QSID
            direction: "down"（上游依赖）/ "up"（下游影响）/ "both"（双向）

        Returns:
            {"root": qsid, "nodes": [...], "edges": [...]}
        """
        nodes = {}
        edges = []

        if direction in ("down", "both"):
            # 上游：策略依赖的因子和子策略
            results = self._runCypher("""
                MATCH (s:`策略` {QSID: $qsid})
                OPTIONAL MATCH (s)-[:`依赖因子`]->(f:`因子`)
                OPTIONAL MATCH (s)-[:`依赖策略`]->(ds:`策略`)
                RETURN s, collect(DISTINCT f) AS factors, collect(DISTINCT ds) AS sub_strategies
            """, {"qsid": qsid})
            for r in results:
                nodes[r["s"]["QSID"]] = r["s"]
                for f in (r.get("factors") or []):
                    nodes[f["QSID"]] = f
                    edges.append({"source": r["s"]["QSID"], "target": f["QSID"], "type": "依赖因子"})
                for ds in (r.get("sub_strategies") or []):
                    nodes[ds["QSID"]] = ds
                    edges.append({"source": r["s"]["QSID"], "target": ds["QSID"], "type": "依赖策略"})

        if direction in ("up", "both"):
            # 下游：哪些策略/回测依赖此策略
            results = self._runCypher("""
                MATCH (s:`策略` {QSID: $qsid})
                OPTIONAL MATCH (ds:`策略`)-[:`依赖策略`]->(s)
                OPTIONAL MATCH (bt:`回测`)-[:`运行策略`]->(s)
                RETURN s, collect(DISTINCT ds) AS dependents, collect(DISTINCT bt) AS backtests
            """, {"qsid": qsid})
            for r in results:
                nodes.setdefault(r["s"]["QSID"], r["s"])
                for ds in (r.get("dependents") or []):
                    nodes[ds["QSID"]] = ds
                    edges.append({"source": ds["QSID"], "target": r["s"]["QSID"], "type": "依赖策略"})
                for bt in (r.get("backtests") or []):
                    nodes[bt["QSID"]] = bt
                    edges.append({"source": bt["QSID"], "target": r["s"]["QSID"], "type": "运行策略"})

        return {
            "root": qsid,
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    def getStrategyDependents(self, qsid: str) -> List[Dict]:
        """查询策略的下游影响：依赖此策略的其他策略和回测

        Args:
            qsid: 策略 QSID

        Returns:
            下游依赖列表，每项含 type（"策略"/"回测"）和节点属性
        """
        results = self._runCypher("""
            MATCH (s:`策略` {QSID: $qsid})
            OPTIONAL MATCH (ds:`策略`)-[:`依赖策略`]->(s)
            OPTIONAL MATCH (bt:`回测`)-[:`运行策略`]->(s)
            RETURN collect(DISTINCT {type: "策略", node: ds}) +
                   collect(DISTINCT {type: "回测", node: bt}) AS dependents
        """, {"qsid": qsid})

        if not results:
            return []
        return [d for d in (results[0].get("dependents") or []) if d["node"] is not None]

    def updateStrategyMeta(self, qsid: str, meta_updates: dict) -> bool:
        """更新策略元信息

        Args:
            qsid: 策略 QSID
            meta_updates: 要更新的键值对

        Returns:
            是否更新成功
        """
        import json as _json
        from QSExt.QSRegistry._serialization import _sanitizeForJSON

        existing = self.getStrategyByQSID(qsid)
        if not existing:
            self._QS_Logger.warning(f"策略 {qsid} 不存在，无法更新")
            return False

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        set_clauses = ["s.UpdatedAt = $now"]
        params = {"qsid": qsid, "now": now}

        for key, val in meta_updates.items():
            param_key = f"val_{key}"
            set_clauses.append(f"s.{key} = ${param_key}")
            params[param_key] = val

        # 如果更新了 MetaJSON 相关字段，同步更新 MetaJSON
        meta_fields = {"Description", "Tags", "Author", "OperatorConfig", "FactorDeps", "StrategyDeps"}
        if meta_fields & set(meta_updates.keys()):
            current_meta = _json.loads(existing.get("MetaJSON", "{}"))
            current_meta.update({k: v for k, v in meta_updates.items() if k in meta_fields})
            set_clauses.append("s.MetaJSON = $meta_json")
            params["meta_json"] = _json.dumps(_sanitizeForJSON(current_meta), ensure_ascii=False)

        query = f"""
            MATCH (s:`策略` {{QSID: $qsid}})
            SET {', '.join(set_clauses)}
        """
        self._runCypher(query, params)
        self._QS_Logger.info(f"已更新策略元信息: {qsid}")
        return True

    def deleteStrategy(self, qsid: str) -> bool:
        """删除策略节点及其所有关系（DETACH DELETE）

        Args:
            qsid: 策略 QSID

        Returns:
            是否删除成功
        """
        existing = self.getStrategyByQSID(qsid)
        if not existing:
            self._QS_Logger.warning(f"策略 {qsid} 不存在，无需删除")
            return False

        self._runCypher(
            "MATCH (s:`策略` {QSID: $qsid}) DETACH DELETE s",
            {"qsid": qsid}
        )
        self._QS_Logger.info(f"已删除策略: {qsid}")
        return True

    # endregion

    # region 分析（Analyze）

    def impactAnalysis(self, qsid: str) -> List[Dict]:
        """影响范围分析，返回所有传递依赖该因子的下游因子"""
        results = self._runCypher(
            """
            MATCH (impacted:`因子`)-[:`依赖`*1..]->(changed:`因子` {QSID: $qsid})
            RETURN impacted,
                   length(shortestPath((impacted)-[:`依赖`*]->(changed))) AS depth
            ORDER BY depth
            """,
            {"qsid": qsid}
        )
        return results

    def findSimilarFactors(self, qsid: str, limit: int = 20) -> List[Dict]:
        """查找使用相同算子的相似因子"""
        results = self._runCypher(
            """
            MATCH (f:`因子` {QSID: $qsid})-[:`使用算子`]->(o:`算子`)
            MATCH (other:`因子`)-[:`使用算子`]->(o2:`算子`)
            WHERE o2.OperatorType = o.OperatorType
              AND o2.Name = o.Name
              AND other.QSID <> $qsid
            RETURN other, o2 LIMIT $limit
            """,
            {"qsid": qsid, "limit": limit}
        )
        return results

    def clearAll(self, confirm: bool = False) -> Dict[str, int]:
        """清空图数据库中所有节点和关系

        Args:
            confirm: 必须为 True 才执行，防止误操作

        Returns:
            删除前的节点统计（便于恢复确认）
        """
        if not confirm:
            raise ValueError("clearAll() 需要 confirm=True 才能执行，防止误操作")
        stats_before = self.getGraphStats()
        self._runCypher("MATCH (n) DETACH DELETE n")
        self._QS_Logger.info(
            f"图库已清空，删除前节点数: {sum(v for k, v in stats_before.items() if not any(c in k for c in ['依赖', '使用', '属于', '打标', '产生', '写入', '存入', '输出', '运行']))}"
        )
        return stats_before

    def getGraphStats(self) -> Dict[str, int]:
        """返回各类节点和关系的计数统计"""
        results = self._runCypher("""
            MATCH (n)
            UNWIND labels(n) AS label
            RETURN label, count(*) AS cnt
        """)
        stats = {}
        for r in results:
            stats[r["label"]] = r["cnt"]
        # 补充未出现的标签为 0
        for label in ["因子", "算子", "因子表", "因子库", "风险库", "风险表", "组合优化器", "标签", "回测", "回测结果", "报告", "因子存储器", "策略", "回测结果库", "回测结果集"]:
            stats.setdefault(label, 0)
        # 关系计数
        rel_results = self._runCypher("""
            MATCH ()-[r]->()
            UNWIND [type(r)] AS rel_type
            RETURN rel_type, count(*) AS cnt
        """)
        for r in rel_results:
            stats[r["rel_type"]] = r["cnt"]
        for rel in ["依赖", "使用算子", "属于因子表", "属于因子库", "属于风险库", "使用优化器", "依赖风险表", "打标签", "产生结果", "产生报告", "有报告", "写入因子表", "存入因子表", "依赖因子", "依赖策略", "运行策略", "产生结果集", "存储于"]:
            stats.setdefault(rel, 0)
        return stats

    def toMermaid(self, qsid: str | list[str], direction: str = "down") -> str:
        """生成因子依赖图的 Mermaid flowchart 源码。

        Args:
            qsid: 目标因子 QSID，或 QSID 列表（多个因子合并显示）
            direction: "down"（该因子依赖谁）、"up"（谁依赖该因子）或 "both"（双向）

        Returns:
            可直接渲染的 Mermaid flowchart 字符串
        """
        qsids = [qsid] if isinstance(qsid, str) else list(qsid)
        if not qsids:
            return "flowchart LR"

        # 合并多个因子的依赖图
        all_nodes: dict[str, dict] = {}
        all_edges: list[dict] = []
        root_ids = set(qsids)

        for q in qsids:
            graph = self.getDependencyGraph(q, direction=direction)
            for n in (graph.get("nodes", []) or []):
                nid = n.get("QSID", "")
                if nid:
                    all_nodes[nid] = n
            for e in (graph.get("edges", []) or []):
                key = (e.get("source"), e.get("target"))
                if key not in {(x.get("source"), x.get("target")) for x in all_edges}:
                    all_edges.append(e)

        if not all_nodes:
            return "flowchart LR"

        # QSID → 短 ID 映射
        qsid_to_short = {nid: nid[:8] for nid in all_nodes}
        lines = ["flowchart LR"]

        # 检测 FactorTableFactor 重名节点，批量查询所属因子表名称
        ftf_nodes = [(nid, n) for nid, n in all_nodes.items() if n.get("FactorClass") == "FactorTableFactor"]
        ft_name_map: dict[str, str] = {}  # FactorTableQSID → FactorTable Name
        if ftf_nodes:
            ft_qsids = list({n["FactorTableQSID"] for _, n in ftf_nodes if n.get("FactorTableQSID")})
            if ft_qsids:
                try:
                    ft_results = self._runCypher(
                        "MATCH (t:`因子表`) WHERE t.QSID IN $qsids RETURN t.QSID, t.Name",
                        {"qsids": ft_qsids}
                    )
                    ft_name_map = {r["t.QSID"]: r["t.Name"] for r in ft_results}
                except Exception:
                    pass

        # 仅对 FactorTableFactor 重名节点附加所属表名
        ftf_name_counts: dict[str, int] = {}
        for _, n in ftf_nodes:
            ftf_name_counts[n.get("Name", "?")] = ftf_name_counts.get(n.get("Name", "?"), 0) + 1

        for nid, n in all_nodes.items():
            sid = qsid_to_short[nid]
            raw_name = n.get("Name", "?")
            label = self._escapeMermaid(raw_name)
            fclass = n.get("FactorClass", "")

            if fclass == "FactorTableFactor" and ftf_name_counts.get(raw_name, 0) > 1:
                ft_name = ft_name_map.get(n.get("FactorTableQSID", ""), "")
                if ft_name:
                    label = f"{label} ({self._escapeMermaid(ft_name)})"

            node_def = f"    {sid}(\"{label}\")"
            lines.append(node_def)
            # 颜色区分类型
            if nid in root_ids:
                lines.append(f"    style {sid} fill:#f9f,stroke:#333,stroke-width:2px")
            elif fclass == "DerivativeFactor":
                lines.append(f"    style {sid} fill:#e1f5fe,stroke:#0288d1")
            elif fclass == "FactorTableFactor":
                lines.append(f"    style {sid} fill:#fff3e0,stroke:#f57c00")

        for e in all_edges:
            src = qsid_to_short.get(e.get("source", ""))
            tgt = qsid_to_short.get(e.get("target", ""))
            if src and tgt:
                lines.append(f"    {src} --> {tgt}")

        return "\n".join(lines)

    @staticmethod
    def _escapeMermaid(name: str) -> str:
        """转义 Mermaid 标签中的特殊字符（引号、括号等）"""
        return (name
                .replace('"', '#quot;')
                .replace('(', '#40;')
                .replace(')', '#41;')
                .replace('[', '#91;')
                .replace(']', '#93;'))

    # endregion

    # region 工具

    def executeCypher(self, query: str, parameters: Optional[Dict] = None) -> List[Dict]:
        """执行原始 Cypher 查询"""
        return self._runCypher(query, parameters)

    def _repr_html_(self) -> str:
        HTML = f"<b>类</b>: QSGraphDB<br/>"
        HTML += f"<b>Neo4j 地址</b>: {html.escape(self._QSArgs.IPAddr)}:{self._QSArgs.Port}<br/>"
        HTML += f"<b>数据库</b>: {html.escape(self._QSArgs.DBName)}<br/>"
        HTML += f"<b>连接状态</b>: {'已连接' if self.isAvailable() else '未连接'}<br/>"
        if self.isAvailable():
            stats = self.getGraphStats()
            HTML += "<b>图统计</b>:<br/>"
            HTML += "<ul>"
            for key, val in stats.items():
                HTML += f"<li>{html.escape(key)}: {val}</li>"
            HTML += "</ul>"
        return HTML

    # endregion

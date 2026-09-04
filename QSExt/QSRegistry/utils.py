# -*- coding: utf-8 -*-
"""QSRegistry 工具函数 — Neo4j 连接配置加载与 QSGraphDB 初始化"""

import os
import json
import re
import logging
from typing import Optional

from dotenv import load_dotenv

from QuantStudio.Core import __QS_Logger__ as Logger
from QSExt import __QS_MainPath__
from .QSGraphDB import QSGraphDB


def load_neo4j_config(config_path: Optional[str] = None) -> dict | None:
    """加载 Neo4j 连接配置，失败返回 None

    返回的字典直接作为 QSGraphDB(args=...) 的参数，
    字段名需与 QSNeo4jObject.__QS_ArgClass__ 一致（IPAddr, Port, User, Pwd, DBName）。

    Args:
        config_path: 配置文件路径，默认 ~/QuantStudioConfig/Neo4jDBConfig.json

    Returns:
        Neo4j 连接参数字典，失败返回 None
    """
    if config_path is None:
        config_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
    else:
        config_path = os.path.expanduser(config_path)

    if not os.path.exists(config_path):
        Logger.warning(f"Neo4j 配置文件不存在: {config_path}")
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        return {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }
    except Exception as e:
        Logger.warning(f"加载 Neo4j 配置失败: {e}")
        return None


def init_graphdb(
    neo4j_config_path: Optional[str] = None,
    skip_embedding: bool = False,
    embedding_model: str = "bge-m3",
    embedding_dim: int = 1024,
) -> Optional[QSGraphDB]:
    """初始化并连接 QSGraphDB

    Args:
        neo4j_config_path: Neo4j 配置文件路径，默认 ~/QuantStudioConfig/Neo4jDBConfig.json
        skip_embedding: 是否跳过向量嵌入配置
        embedding_model: 嵌入模型名称，默认 bge-m3
        embedding_dim: 嵌入向量维度，默认 1024

    Returns:
        已连接的 QSGraphDB 实例，失败返回 None
    """
    neo4j_args = load_neo4j_config(neo4j_config_path)
    if neo4j_args is None:
        return None

    if not skip_embedding:
        load_dotenv(__QS_MainPath__ + "/config/.env")
        neo4j_args["OllamaBaseURL"] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        neo4j_args["OllamaAPIKey"] = os.getenv("OLLAMA_API_KEY", "ollama")
        neo4j_args["EmbeddingModel"] = os.getenv("EMBEDDING_MODEL", embedding_model)
        neo4j_args["EmbeddingDim"] = int(os.getenv("EMBEDDING_DIM", str(embedding_dim)))

    try:
        fgdb = QSGraphDB(args=neo4j_args)
        fgdb.connect()
        Logger.info(f"QSGraphDB 已连接 → {neo4j_args['IPAddr']}:{neo4j_args['Port']}")
        return fgdb
    except Exception as e:
        Logger.warning(f"QSGraphDB 连接失败: {e}")
        return None

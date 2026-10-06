# -*- coding: utf-8 -*-
"""QSRegistry 工具函数 — QSGraphDB 连接配置加载与初始化"""

import os
import json
import re
import logging
from typing import Optional

from QuantStudio.Core import __QS_Logger__ as Logger
from .QSGraphDB import QSGraphDB


def load_qsgraphdb_config(config_path: Optional[str] = None) -> dict | None:
    """加载 QSGraphDB 连接配置，失败返回 None

    返回的字典直接作为 QSGraphDB(args=...) 的参数，字段名需与 QSGraphDB.__QS_ArgClass__
    一致（IPAddr, Port, User, Pwd, DBName, DataDir, EmbeddingModel, EmbeddingDim,
    OllamaBaseURL, OllamaAPIKey 等），未知字段会被 QSGraphDB 拒绝。

    Args:
        config_path: 配置文件路径，默认 ~/QuantStudioConfig/QSGraphDBConfig.json

    Returns:
        QSGraphDB 连接参数字典，失败返回 None
    """
    if config_path is None:
        config_path = os.path.expanduser("~/QuantStudioConfig/QSGraphDBConfig.json")
    else:
        config_path = os.path.expanduser(config_path)

    if not os.path.exists(config_path):
        Logger.warning(f"QSGraphDB 配置文件不存在: {config_path}")
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)
    except Exception as e:
        Logger.warning(f"加载 QSGraphDB 配置失败: {e}")
        return None


def init_graphdb(
    qsgraphdb_config_path: Optional[str] = None,
    skip_embedding: bool = False,
) -> Optional[QSGraphDB]:
    """初始化并连接 QSGraphDB

    Args:
        qsgraphdb_config_path: QSGraphDB 配置文件路径，默认 ~/QuantStudioConfig/QSGraphDBConfig.json
        skip_embedding: 是否跳过向量嵌入配置

    Returns:
        已连接的 QSGraphDB 实例，失败返回 None
    """
    gdb_args = load_qsgraphdb_config(qsgraphdb_config_path)
    if gdb_args is None:
        return None

    if skip_embedding:
        for key in ("EmbeddingModel", "EmbeddingDim", "OllamaBaseURL", "OllamaAPIKey"):
            gdb_args.pop(key, None)

    try:
        fgdb = QSGraphDB(args=gdb_args)
        fgdb.connect()
        Logger.info(f"QSGraphDB 已连接 → {gdb_args.get('IPAddr', '127.0.0.1')}:{gdb_args.get('Port', 7687)}")
        return fgdb
    except Exception as e:
        Logger.warning(f"QSGraphDB 连接失败: {e}")
        return None

# -*- coding: utf-8 -*-
"""QSGraphDB 嵌入生成单元测试。

通过 mock requests.post 验证 `_generateEmbedding` 对 Ollama 与 OpenAI 兼容接口
两类嵌入服务的请求格式与响应解析，无需真实 Neo4j / 嵌入服务。

运行方式：
    pytest tests/test_qsgraphdb_embedding.py -v
"""
from __future__ import annotations

from unittest.mock import patch

from QSExt.QSRegistry.QSGraphDB import QSGraphDB


def _make_gdb(**embedding_args) -> QSGraphDB:
    """构造未连接的 QSGraphDB 实例，仅用于测试 _generateEmbedding

    config_file="" 用于禁用默认配置文件加载，避免用户本机
    ~/QuantStudioConfig/QSGraphDBConfig.json 中的字段混入测试参数。
    """
    return QSGraphDB(args=embedding_args, config_file="")


def test_generate_embedding_openai():
    gdb = _make_gdb(
        EmbeddingProvider="openai",
        EmbeddingBaseURL="https://api.openai.com/v1",
        EmbeddingAPIKey="sk-test",
        EmbeddingModel="text-embedding-3-small",
        EmbeddingDim=3,
    )
    with patch("QSExt.QSRegistry.QSGraphDB.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        vec = gdb._generateEmbedding("hello")
    assert vec == [0.1, 0.2, 0.3]
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/embeddings"
    assert kwargs["json"] == {"model": "text-embedding-3-small", "input": "hello"}
    assert kwargs["headers"] == {"Authorization": "Bearer sk-test"}


def test_generate_embedding_ollama():
    gdb = _make_gdb(
        EmbeddingProvider="ollama",
        EmbeddingBaseURL="http://127.0.0.1:11434",
        EmbeddingModel="bge-m3",
        EmbeddingDim=3,
    )
    with patch("QSExt.QSRegistry.QSGraphDB.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"embedding": [0.4, 0.5, 0.6]}
        vec = gdb._generateEmbedding("hello")
    assert vec == [0.4, 0.5, 0.6]
    args, kwargs = mock_post.call_args
    assert args[0] == "http://127.0.0.1:11434/api/embeddings"
    assert kwargs["json"] == {"model": "bge-m3", "prompt": "hello"}
    assert kwargs["headers"] == {}  # 未配置 APIKey 时不带鉴权头


def test_generate_embedding_disabled():
    gdb = _make_gdb(EmbeddingModel="")
    assert gdb._generateEmbedding("hello") is None

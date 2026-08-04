# -*- coding: utf-8 -*-
"""Embedding 服务 — 基于大语言模型生成文本向量用于语义检索。

默认使用 Ollama 的 bge-m3 模型，1024 维向量。
配置从 config/.env 读取，支持通过参数覆盖。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np
import requests
from dotenv import load_dotenv

from QSExt import __QS_MainPath__

logger = logging.getLogger(__name__)

_ENV_FILE = os.path.join(__QS_MainPath__, "config", ".env")
if os.path.isfile(_ENV_FILE):
    load_dotenv(_ENV_FILE)

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_VECTOR_DIM = 1024


class EmbeddingService:
    """文本向量化服务。

    用法:
        emb = EmbeddingService()
        vec = emb.encode("这是一段因子描述文本")
        result = emb.encode_batch(["文本1", "文本2"])
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
    ):
        self._base_url = (base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self._model = model or DEFAULT_EMBEDDING_MODEL
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return DEFAULT_VECTOR_DIM

    def encode(self, text: str) -> np.ndarray:
        """将单段文本编码为向量。"""
        if not text.strip():
            return np.zeros(self.dim, dtype=np.float32)

        try:
            resp = requests.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            vec = np.array(data["embedding"], dtype=np.float32)
            if len(vec) != self.dim:
                logger.warning("bge-m3 返回向量维度 %d != 预期 %d，用零填充", len(vec), self.dim)
                padded = np.zeros(self.dim, dtype=np.float32)
                padded[: min(len(vec), self.dim)] = vec[: self.dim]
                return padded
            return vec
        except Exception as e:
            logger.error("Ollama embedding 请求失败: %s", e)
            return np.zeros(self.dim, dtype=np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """批量编码文本为向量矩阵。"""
        return np.array([self.encode(t) for t in texts], dtype=np.float32)

    def to_db_format(self, vec: np.ndarray) -> str:
        """将 numpy 向量转为 pgvector 兼容格式。"""
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

# -*- coding: utf-8 -*-
"""LLM 客户端工厂 — 统一创建不同后端的 LangChain ChatModel。

支持的 provider：
  - ollama: 本地 Ollama 模型（默认，使用 ChatOllama）
  - openai: OpenAI 兼容接口（使用 ChatOpenAI，覆盖 OpenAI/DeepSeek/通义千问/智谱等）

配置从 config/.env 读取，也可通过参数覆盖。

用法:
    from QSExt.LLMFactor.mining_log.llm_client import create_llm

    # 使用默认配置（.env 中的 LLM_PROVIDER）
    llm = create_llm()

    # 指定 provider
    llm = create_llm("ollama", model="qwen3")
    llm = create_llm("openai", model="deepseek-chat", base_url="https://api.deepseek.com/v1")
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv

from QSExt import __QS_MainPath__

logger = logging.getLogger(__name__)

_ENV_FILE = os.path.join(__QS_MainPath__, "config", ".env")
if os.path.isfile(_ENV_FILE):
    load_dotenv(_ENV_FILE)


def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    temperature: float = 0.1,
    **kwargs: Any,
):
    """根据 provider 创建 LangChain BaseChatModel 实例。

    Args:
        provider: LLM 提供商，"ollama" 或 "openai"。默认从 LLM_PROVIDER 环境变量读取。
        model: 模型名称。默认根据 provider 从环境变量读取。
        base_url: API 地址。默认根据 provider 从环境变量读取。
        api_key: API 密钥（仅 openai provider 需要）。
        timeout: 请求超时（秒）。
        temperature: 生成温度。
        **kwargs: 传递给 ChatModel 构造函数的额外参数。

    Returns:
        langchain_core.language_models.chat_models.BaseChatModel 实例
    """
    provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower().strip()

    if provider == "ollama":
        return _create_ollama(model=model, base_url=base_url, temperature=temperature, **kwargs)
    elif provider == "openai":
        return _create_openai(
            model=model, base_url=base_url, api_key=api_key,
            timeout=timeout, temperature=temperature, **kwargs,
        )
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}，可选: ollama, openai")


def _create_ollama(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs: Any,
):
    """创建 Ollama ChatModel。"""
    from langchain_ollama import ChatOllama

    model = model or os.getenv("OLLAMA_LLM_MODEL", "qwen3")
    base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        **kwargs,
    )
    logger.info("创建 Ollama LLM: model=%s, base_url=%s", model, base_url)
    return llm


def _create_openai(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    temperature: float = 0.1,
    **kwargs: Any,
):
    """创建 OpenAI 兼容 ChatModel。

    支持所有兼容 OpenAI API 格式的服务：
    - OpenAI: https://api.openai.com/v1
    - DeepSeek: https://api.deepseek.com/v1
    - 通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1
    - 智谱: https://open.bigmodel.cn/api/paas/v4
    - 硅基流动: https://api.siliconflow.cn/v1
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "使用 openai provider 需要安装 langchain-openai: "
            "pip install langchain-openai"
        )

    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = base_url or os.getenv("LLM_BASE_URL")
    api_key = api_key or os.getenv("LLM_API_KEY")
    timeout = timeout or int(os.getenv("LLM_TIMEOUT", "120"))

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        temperature=temperature,
        **kwargs,
    )
    logger.info("创建 OpenAI 兼容 LLM: model=%s, base_url=%s", model, base_url or "(default)")
    return llm

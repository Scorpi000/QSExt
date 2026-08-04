# -*- coding: utf-8 -*-
"""配置文件读写工具。

提供 YAML 配置文件的加载和保存功能，供 Web 配置页面使用。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

__QS_Logger__ = logging.getLogger("QSR.web.config_io")

# 默认配置目录的持久化文件路径
_DEFAULT_DIR_FILE = Path.home() / ".qsresearch" / "default_config_dir"

# 配置文件名列表
CONFIG_FILES = [
    "pipeline.yaml",
    "hypothesis_research.yaml",
    "development.yaml",
    "evaluation.yaml",
]


def find_config_dir() -> Path | None:
    """查找配置文件目录。

    从当前文件位置向上查找 LLMFactor/config/ 目录。

    Returns:
        配置目录路径，未找到返回 None
    """
    # 从 web/utils/ 向上查找到 LLMFactor/config/
    candidates = [
        Path(__file__).parent.parent.parent / "config",
        Path.cwd() / "QSExt" / "LLMFactor" / "config",
    ]
    for p in candidates:
        if p.exists() and (p / "pipeline.yaml").exists():
            return p.resolve()
    return None


def load_yaml(path: Path) -> dict[str, Any]:
    """加载 YAML 文件为 dict。

    Args:
        path: YAML 文件路径

    Returns:
        配置字典，文件不存在返回空字典
    """
    if not path.exists():
        __QS_Logger__.warning("配置文件不存在: %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """将 dict 保存为 YAML 文件。

    Args:
        path: YAML 文件路径
        data: 配置字典
    """
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    __QS_Logger__.info("配置已保存: %s", path)


def load_all_configs(config_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """加载所有配置文件。

    Args:
        config_dir: 配置目录路径，None 则自动查找

    Returns:
        以文件名为 key 的配置字典
    """
    if config_dir is None:
        config_dir = find_config_dir()
    if config_dir is None:
        return {}

    configs = {}
    for name in CONFIG_FILES:
        path = config_dir / name
        configs[name] = load_yaml(path)
    return configs


def save_config(config_dir: Path, filename: str, data: dict[str, Any]) -> None:
    """保存单个配置文件。

    目录不存在时自动创建。

    Args:
        config_dir: 配置目录路径
        filename: 配置文件名
        data: 配置字典
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / filename
    save_yaml(path, data)


def save_default_config_dir(path: str) -> None:
    """将配置目录路径持久化到用户目录。

    Args:
        path: 配置目录路径
    """
    _DEFAULT_DIR_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DEFAULT_DIR_FILE.write_text(path.strip(), encoding="utf-8")
    __QS_Logger__.info("默认配置目录已保存: %s", path)


def load_default_config_dir() -> str | None:
    """读取持久化的默认配置目录。

    Returns:
        配置目录路径，未设置返回 None
    """
    if _DEFAULT_DIR_FILE.exists():
        text = _DEFAULT_DIR_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None

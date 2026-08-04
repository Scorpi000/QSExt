# -*- coding: utf-8 -*-
"""流水线全局配置。

提供 PipelineConfig 和 DataContext，管理因子挖掘流水线的全局设置。
各阶段（hypothesis/development/evaluation）的专属配置由各自的 config 模块管理，
PipelineConfig 只负责全局性设置和各阶段配置文件的加载路径。

使用示例::

    from QSExt.LLMFactor.pipeline_config import PipelineConfig

    # 从 YAML 加载
    config = PipelineConfig.from_yaml("QSExt/LLMFactor/config/pipeline.yaml")

    # 获取项目根目录
    root = config.resolve_project_root()
    # 获取各阶段配置
    hypothesis_config = config.load_hypothesis_config()
    development_config = config.load_development_config()
    evaluation_config = config.load_evaluation_config()

    # 获取 Claude CLI 路径
    cli_path = config.resolve_claude_cli()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

__QS_Logger__ = logging.getLogger("QSR.pipeline_config")


@dataclass
class DataContext:
    """数据上下文 — 构建因子对象和评测参数时使用。

    Attributes:
        trade_day_start: 交易日起始日期
        trade_day_end: 交易日截止日期
        stock_date: 股票截面选取日期
        max_stocks: 最大股票数量
    """
    trade_day_start: str = "2013-01-01"
    trade_day_end: str = "2025-12-31"
    stock_date: str = "2025-06-30"
    max_stocks: int = 1000

    def get_trade_day_start(self) -> datetime:
        """解析为 datetime。"""
        return datetime.strptime(self.trade_day_start, "%Y-%m-%d")

    def get_trade_day_end(self) -> datetime:
        """解析为 datetime。"""
        return datetime.strptime(self.trade_day_end, "%Y-%m-%d")

    def get_stock_date(self) -> datetime:
        """解析为 datetime。"""
        return datetime.strptime(self.stock_date, "%Y-%m-%d")


@dataclass
class PipelineConfig:
    """流水线全局配置。

    Attributes:
        project_root: 项目根目录，"auto" 表示自动查找（查找含 .mcp.json 的目录）
        claude_cli: Claude CLI 路径，"auto" 表示自动查找
        workspace_dir: 产出物输出基础目录，支持绝对路径或相对于项目根目录的路径
        max_turns_hypothesis: 假设生成 Agent 最大轮次
        max_turns_development: 因子开发 Agent 最大轮次
        data: 数据上下文
        config_dir: 配置文件所在目录（用于解析相对路径）
    """
    project_root: str = "auto"
    claude_cli: str = "auto"
    workspace_dir: str = "workspace"
    max_turns_hypothesis: int = 50
    max_turns_development: int = 80
    data: DataContext = field(default_factory=DataContext)
    config_dir: Optional[Path] = None

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        """从 YAML 文件加载配置。

        Args:
            path: YAML 文件路径

        Returns:
            PipelineConfig 实例
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        data_raw = raw.get("data", {})
        data = DataContext(
            trade_day_start=data_raw.get("trade_day_start", "2013-01-01"),
            trade_day_end=data_raw.get("trade_day_end", "2025-12-31"),
            stock_date=data_raw.get("stock_date", "2025-06-30"),
            max_stocks=data_raw.get("max_stocks", 1000),
        )

        return cls(
            project_root=raw.get("project_root", "auto"),
            claude_cli=raw.get("claude_cli", "auto"),
            workspace_dir=raw.get("workspace_dir", "workspace"),
            max_turns_hypothesis=raw.get("max_turns_hypothesis", 50),
            max_turns_development=raw.get("max_turns_development", 80),
            data=data,
            config_dir=path.parent,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineConfig":
        """从 dict 加载配置。"""
        data_raw = d.get("data", {})
        data = DataContext(
            trade_day_start=data_raw.get("trade_day_start", "2013-01-01"),
            trade_day_end=data_raw.get("trade_day_end", "2025-12-31"),
            stock_date=data_raw.get("stock_date", "2025-06-30"),
            max_stocks=data_raw.get("max_stocks", 1000),
        )
        return cls(
            project_root=d.get("project_root", "auto"),
            claude_cli=d.get("claude_cli", "auto"),
            workspace_dir=d.get("workspace_dir", "workspace"),
            max_turns_hypothesis=d.get("max_turns_hypothesis", 50),
            max_turns_development=d.get("max_turns_development", 80),
            data=data,
        )

    def _resolve_phase_config_path(self, filename: str) -> Path:
        """解析阶段配置文件路径。"""
        p = Path(filename)
        if p.is_absolute():
            return p
        # 相对于配置文件所在目录
        if self.config_dir:
            return self.config_dir / p
        return p

    def load_hypothesis_config(self):
        """加载假设生成阶段 ResearchConfig。

        Returns:
            ResearchConfig 实例
        """
        from QSExt.LLMFactor.hypothesis.config import ResearchConfig
        path = self._resolve_phase_config_path("hypothesis_research.yaml")
        if path.exists():
            return ResearchConfig.from_yaml(str(path))
        __QS_Logger__.warning("假设生成配置文件不存在: %s，使用默认值", path)
        return ResearchConfig()

    def load_development_config(self):
        """加载因子开发阶段 DevelopmentConfig。

        Returns:
            DevelopmentConfig 实例
        """
        from QSExt.LLMFactor.development.config import DevelopmentConfig
        path = self._resolve_phase_config_path("development.yaml")
        if path.exists():
            return DevelopmentConfig.from_yaml(str(path))
        __QS_Logger__.warning("因子开发配置文件不存在: %s，使用默认值", path)
        return DevelopmentConfig()

    def load_evaluation_config(self):
        """加载因子评测阶段 EvalConfig。

        Returns:
            EvalConfig 实例
        """
        from QSExt.LLMFactor.evaluation.config import EvalConfig
        path = self._resolve_phase_config_path("evaluation.yaml")
        if path.exists():
            return EvalConfig.from_yaml(str(path))
        __QS_Logger__.warning("因子评测配置文件不存在: %s，使用默认值", path)
        return EvalConfig()

    def resolve_workspace_dir(self) -> Path:
        """解析本次运行的产出物输出目录。

        自动在 workspace_dir 下追加 FM_<时间戳> 子目录。

        Returns:
            完整的工作区目录路径
        """
        base = Path(self.workspace_dir)
        if not base.is_absolute():
            base = self.resolve_project_root() / base
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return base / f"FM_{timestamp}"

    def resolve_project_root(self) -> Path:
        """解析项目根目录。

        Returns:
            项目根目录路径
        """
        if self.project_root != "auto":
            return Path(self.project_root)
        return _find_project_root()

    def resolve_claude_cli(self) -> str:
        """解析 Claude CLI 路径。

        Returns:
            CLI 可执行文件路径
        """
        if self.claude_cli != "auto":
            return self.claude_cli
        return _find_claude_cli()


def _find_project_root() -> Path:
    """自动查找项目根目录（含 .mcp.json 的目录）。"""
    from QSExt import __QS_MainPath__
    parent = Path(__QS_MainPath__).parent
    if (parent / ".mcp.json").exists():
        return parent
    return Path.cwd()


def _find_claude_cli() -> str:
    """从已知路径或 PATH 中查找 Claude CLI。"""
    candidates = [
        Path.home() / ".local" / "bin" / "claude.exe",
        Path.home() / ".local" / "bin" / "claude",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "claude"  # 假设在 PATH 中

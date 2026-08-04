# -*- coding: utf-8 -*-
"""工作目录扫描与解析工具。

扫描 workspace 目录，解析各轮次的挖掘结果。

所有运行模式（单次流水线、持续挖掘循环）统一输出到 FM_* 目录：

    workspace/
    ├── mining_loop.log                 # 循环日志（loop 模式）
    ├── loop_20260713_123456.json       # 循环汇总（loop 模式）
    ├── FM_20260713_123456/             # 轮次产出
    │   ├── metadata.json
    │   ├── factor_def.py
    │   └── evaluation/
    └── FM_20260713_130000/
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

__QS_Logger__ = logging.getLogger("QSR.web.workspace")


@dataclass
class RoundInfo:
    """单轮挖掘结果摘要。"""
    run_id: str
    factor_name: str
    category: str
    status: str
    decision: str
    rankic_mean: float
    rankicir: float
    oos_rankic: float
    composite_score: float
    incremental_ic_t: float
    workspace_path: str
    created_at: str
    timing: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def decision_emoji(self) -> str:
        return {"accepted": "✅", "refining": "🔄", "rejected": "❌"}.get(self.decision, "❓")

    @property
    def status_emoji(self) -> str:
        return {"completed": "✅", "failed": "❌", "evaluating": "⏳"}.get(self.status, "🔄")


def _parse_fm_dir(fm_dir: Path) -> Optional[RoundInfo]:
    """解析单个 FM_ 目录为 RoundInfo。"""
    metadata_file = fm_dir / "metadata.json"
    if not metadata_file.exists():
        return None
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception as e:
        __QS_Logger__.warning(f"解析 {metadata_file} 失败: {e}")
        return None

    eval_data = metadata.get("evaluation", {})
    decision_data = metadata.get("decision", {})

    return RoundInfo(
        run_id=fm_dir.name,
        factor_name=metadata.get("factor_name", fm_dir.name),
        category=metadata.get("category", ""),
        status=metadata.get("status", "unknown"),
        decision=decision_data.get("verdict", ""),
        rankic_mean=eval_data.get("rankic_mean", 0.0),
        rankicir=eval_data.get("rankicir", 0.0),
        oos_rankic=eval_data.get("oos_rankic", 0.0),
        composite_score=eval_data.get("composite_score", 0.0),
        incremental_ic_t=eval_data.get("incremental_ic_t", 0.0),
        workspace_path=str(fm_dir),
        created_at=metadata.get("created_at", ""),
        timing=metadata.get("timing", {}),
        metadata=metadata,
    )


def scan_workspace(workspace_dir: str) -> list[RoundInfo]:
    """扫描工作目录，解析所有 FM_* 轮次结果。

    Args:
        workspace_dir: 工作目录路径

    Returns:
        轮次信息列表，按目录名倒序排列（最新在前）
    """
    workspace_path = Path(workspace_dir)
    if not workspace_path.exists():
        return []

    rounds: list[RoundInfo] = []
    for fm_dir in sorted(workspace_path.glob("FM_*"), key=lambda p: p.name, reverse=True):
        if fm_dir.is_dir():
            info = _parse_fm_dir(fm_dir)
            if info:
                rounds.append(info)

    return rounds


def load_loop_summary(workspace_dir: str) -> Optional[dict]:
    """加载最新的循环汇总（loop_xxx.json）。

    Args:
        workspace_dir: 工作目录路径

    Returns:
        汇总字典，未找到返回 None
    """
    workspace_path = Path(workspace_dir)
    if not workspace_path.exists():
        return None

    loop_files = sorted(workspace_path.glob("loop_*.json"), key=lambda p: p.name, reverse=True)
    if not loop_files:
        return None

    try:
        return json.loads(loop_files[0].read_text(encoding="utf-8"))
    except Exception as e:
        __QS_Logger__.warning(f"解析 {loop_files[0]} 失败: {e}")
        return None


def get_round_detail(workspace_path: str) -> dict[str, Any]:
    """获取单轮挖掘的详细信息。

    Args:
        workspace_path: 轮次工作目录路径（FM_xxx）

    Returns:
        详细信息字典
    """
    path = Path(workspace_path)
    detail: dict[str, Any] = {}

    # metadata.json
    metadata_file = path / "metadata.json"
    if metadata_file.exists():
        try:
            detail["metadata"] = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # evaluation/eval_summary.json（兼容评测阶段的独立输出）
    eval_summary = path / "evaluation" / "eval_summary.json"
    if eval_summary.exists():
        try:
            detail["eval_summary"] = json.loads(eval_summary.read_text(encoding="utf-8"))
        except Exception:
            pass

    # validation 结果
    validation_dir = path / "validation"
    if validation_dir.exists():
        detail["validation"] = {}
        for f in validation_dir.glob("*.json"):
            try:
                detail["validation"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass

    # param_search 结果
    param_dir = path / "param_search"
    if param_dir.exists():
        best_params = param_dir / "best_params.json"
        if best_params.exists():
            try:
                detail["best_params"] = json.loads(best_params.read_text(encoding="utf-8"))
            except Exception:
                pass

    # README
    readme_file = path / "README.md"
    if readme_file.exists():
        detail["readme"] = readme_file.read_text(encoding="utf-8")

    # factor_def.py
    factor_def_file = path / "factor_def.py"
    if factor_def_file.exists():
        detail["factor_code"] = factor_def_file.read_text(encoding="utf-8")

    return detail


def get_log_path(workspace_path: str) -> Optional[str]:
    """获取日志文件路径。

    Args:
        workspace_path: 工作目录路径

    Returns:
        日志文件路径，不存在则返回 None
    """
    path = Path(workspace_path)

    for log_name in ["mining_loop.log", "pipeline.log"]:
        log_file = path / log_name
        if log_file.exists():
            return str(log_file)

    logs_dir = path / "logs"
    if logs_dir.exists():
        log_files = list(logs_dir.glob("*.log"))
        if log_files:
            return str(sorted(log_files, key=lambda p: p.stat().st_mtime)[-1])

    return None

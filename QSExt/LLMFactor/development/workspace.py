# -*- coding: utf-8 -*-
"""因子开发工作区管理。

管理工作区目录结构，负责创建目录、保存代码、报告和搜索结果。

目录结构约定::

    workspace/
    └── FM_{timestamp}/
        ├── {factor_module}.py
        ├── metadata.json
        ├── README.md
        ├── param_search/
        │   ├── search_space.json
        │   ├── best_params.json
        │   └── optimization_history.png
        └── validation/
            ├── syntax_report.json
            ├── execution_report.json
            ├── leak_test_report.json
            ├── unit_check_report.json
            └── semantic_review.md

使用示例::

    from QSExt.LLMFactor.development.workspace import WorkspaceManager

    ws = WorkspaceManager()
    ws_dir = ws.create_workspace("momentum_factor")
    ws.save_factor_code(ws_dir, code, "momentum_factor")
    ws.save_metadata(ws_dir, metadata)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

__QS_Logger__ = logging.getLogger("QSR.development.workspace")


class WorkspaceManager:
    """管理工作区目录结构。

    Attributes:
        base_dir: 工作区根目录，默认 QSExt/LLMFactor/workspace/
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            # 默认使用项目内的 workspace 目录
            self.base_dir = Path(__file__).parent.parent / "workspace"
        else:
            self.base_dir = Path(base_dir)

    def create_workspace(self, factor_name: str) -> Path:
        """创建新的工作区目录。

        Args:
            factor_name: 因子名称，用于日志记录（目录名使用时间戳）

        Returns:
            新创建的工作区目录路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ws_dir = self.base_dir / f"FM_{timestamp}"
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "param_search").mkdir(exist_ok=True)
        (ws_dir / "validation").mkdir(exist_ok=True)
        __QS_Logger__.info(f"创建工作区: {ws_dir} (因子: {factor_name})")
        return ws_dir

    def save_factor_code(self, ws_dir: Path, code: str, module_name: str) -> Path:
        """保存因子定义代码。

        Args:
            ws_dir: 工作区目录
            code: 因子代码内容
            module_name: 模块名（不含 .py）

        Returns:
            保存的文件路径
        """
        file_path = ws_dir / f"{module_name}.py"
        file_path.write_text(code, encoding="utf-8")
        __QS_Logger__.info(f"保存因子代码: {file_path}")
        return file_path

    def save_metadata(self, ws_dir: Path, metadata: dict) -> Path:
        """保存 metadata.json。

        Args:
            ws_dir: 工作区目录
            metadata: 元数据字典

        Returns:
            保存的文件路径
        """
        file_path = ws_dir / "metadata.json"
        file_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_path

    def save_readme(self, ws_dir: Path, content: str) -> Path:
        """保存 README.md。

        Args:
            ws_dir: 工作区目录
            content: README 内容

        Returns:
            保存的文件路径
        """
        file_path = ws_dir / "README.md"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def save_search_space(self, ws_dir: Path, search_space: dict) -> Path:
        """保存搜索空间定义。

        Args:
            ws_dir: 工作区目录
            search_space: 搜索空间定义

        Returns:
            保存的文件路径
        """
        file_path = ws_dir / "param_search" / "search_space.json"
        file_path.write_text(
            json.dumps(search_space, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_path

    def save_validation_report(self, ws_dir: Path, report) -> None:
        """保存验证报告到 validation/ 目录。

        Args:
            ws_dir: 工作区目录
            report: ValidationReport 对象
        """
        val_dir = ws_dir / "validation"

        # 语法检查
        self._save_json(val_dir / "syntax_report.json", asdict(report.syntax))

        # 执行验证
        exec_data = asdict(report.execution)
        # tuple 需要转为 list 才能 JSON 序列化
        if exec_data.get("output_shape"):
            exec_data["output_shape"] = list(exec_data["output_shape"])
        self._save_json(val_dir / "execution_report.json", exec_data)

        # 泄漏检测
        self._save_json(val_dir / "leak_test_report.json", asdict(report.leak_test))

        # 单位检查
        self._save_json(val_dir / "unit_check_report.json", asdict(report.unit_check))

        # 语义审查
        semantic_path = val_dir / "semantic_review.md"
        semantic_path.write_text(report.semantic_review.review_text, encoding="utf-8")

        # 汇总
        self._save_json(val_dir / "validation_summary.json", {
            "all_passed": report.all_passed,
            "auto_fix_count": report.auto_fix_count,
            "fix_history": [asdict(f) for f in report.fix_history],
        })

        __QS_Logger__.info(f"保存验证报告: {val_dir}")

    def save_search_result(self, ws_dir, result) -> None:
        """保存参数搜索结果。

        Args:
            ws_dir: 工作区目录
            result: SearchResult 对象
        """
        ps_dir = ws_dir / "param_search"

        # 最优参数
        self._save_json(ps_dir / "best_params.json", {
            "best_params": result.best_params,
            "best_rankic": result.best_rankic,
        })

        # 优化历史（CSV 格式，便于后续分析）
        if not result.optimization_history.empty:
            history_path = ps_dir / "optimization_history.csv"
            result.optimization_history.to_csv(history_path, index=False)

        # 参数敏感性
        if result.sensitivity:
            self._save_json(ps_dir / "sensitivity.json", result.sensitivity)

        # 优化轨迹图
        if not result.optimization_history.empty:
            self._save_optimization_plot(ps_dir, result.optimization_history)

        __QS_Logger__.info(f"保存搜索结果: {ps_dir}")

    def load_factor_code(self, ws_dir: Path, module_name: str) -> str:
        """加载因子代码。

        Args:
            ws_dir: 工作区目录
            module_name: 模块名

        Returns:
            因子代码内容
        """
        return (ws_dir / f"{module_name}.py").read_text(encoding="utf-8")

    def load_metadata(self, ws_dir: Path) -> dict:
        """加载 metadata.json。"""
        return json.loads((ws_dir / "metadata.json").read_text(encoding="utf-8"))

    def load_search_space(self, ws_dir: Path) -> dict:
        """加载搜索空间定义。"""
        path = ws_dir / "param_search" / "search_space.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def list_workspaces(self) -> list[Path]:
        """列出所有工作区目录，按时间排序。"""
        if not self.base_dir.exists():
            return []
        return sorted(
            [d for d in self.base_dir.iterdir() if d.is_dir() and d.name.startswith("FM_")],
            key=lambda p: p.name,
        )

    # ---- 内部方法 ----

    def _save_json(self, path: Path, data: dict) -> None:
        """保存 JSON 文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _save_optimization_plot(self, ps_dir: Path, history) -> None:
        """保存优化轨迹图。"""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 6))

            # 目标值随试验次数的变化
            if "value" in history.columns:
                ax.plot(history.index, history["value"], alpha=0.3, label="trial value")

                # 累积最优值
                cummax = history["value"].cummax()
                ax.plot(history.index, cummax, color="red", linewidth=2, label="best so far")

            ax.set_xlabel("Trial")
            ax.set_ylabel("Objective Value")
            ax.set_title("Optimization History")
            ax.legend()
            ax.grid(True, alpha=0.3)

            plot_path = ps_dir / "optimization_history.png"
            fig.savefig(plot_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            __QS_Logger__.info(f"保存优化轨迹图: {plot_path}")
        except Exception as e:
            __QS_Logger__.warning(f"保存优化轨迹图失败: {e}")

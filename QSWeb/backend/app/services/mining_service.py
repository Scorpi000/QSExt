"""
因子挖掘服务

管理挖掘框架注册、任务持久化和挖掘执行。
当前仅集成 GPLearner（GPFactor），架构预留未来框架扩展点。
"""

import asyncio
import datetime as dt
import glob as glob_module
import importlib
import json
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import yaml

from app.core.config import settings
from app.models.mining import (
    CreateTaskRequest,
    ContinueRunRequest,
    EvalConfig,
    EvalFactorMetrics,
    EvalMetricsResponse,
    EvalModuleConfig,
    ExportRequest,
    FactorTreeDAG,
    FactorTreeEdge,
    FactorTreeNode,
    FrameworkInfo,
    GPRunConfig,
    HallOfFameEntry,
    LLMFactorRunConfig,
    MiningTask,
    MiningTaskSummary,
    RunLogResponse,
    RunResult,
    RunSummary,
    SubmitRunRequest,
)

logger = logging.getLogger(__name__)


def _kill_proc(proc: subprocess.Popen):
    """停止子进程（Windows: CTRL_BREAK_EVENT → terminate，Unix: terminate → kill）"""
    if proc.poll() is not None:
        return  # 已退出
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


# ─── 回测模块构造器（与 qs_bridge.py 的 _BT_NODE_BUILDERS 一致） ──────

_BT_NODE_BUILDERS = {
    "ic": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.IC",
        "calc_class": "CalcIC",
        "node_module": "QuantStudio.BackTest.SectionFactor.IC",
        "node_class": "IC",
        "requires_price": True,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "node_params_map": {"RollingAvgPeriod": "rolling_avg_period"},
        "default_node_params": {"GenReport": False},
    },
    "ic_decay": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.IC",
        "calc_class": "CalcIC",
        "node_module": "QuantStudio.BackTest.SectionFactor.IC",
        "node_class": "ICDecay",
        "requires_price": True,
        "per_factor": True,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "factor_turnover": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "calc_class": "CalcFactorTurnover",
        "node_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "node_class": "FactorTurnover",
        "requires_price": False,
        "calc_params": ["lookback", "period_lookback", "corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "section_correlation": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "calc_class": "CalcSectionCorrelation",
        "node_module": "QuantStudio.BackTest.SectionFactor.Correlation",
        "node_class": "SectionCorrelation",
        "requires_price": False,
        "calc_params": ["corr_method"],
        "default_node_params": {"GenReport": False},
    },
    "fama_macbeth": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.ReturnDecomposition",
        "calc_class": "CalcFamaMacBethRegression",
        "node_module": "QuantStudio.BackTest.SectionFactor.ReturnDecomposition",
        "node_class": "FamaMacBethRegression",
        "requires_price": True,
        "calc_params": ["lookback", "period_lookback"],
        "node_params_map": {"RollingAvgPeriod": "rolling_avg_period"},
        "default_node_params": {"GenReport": False},
    },
}

def _transform_abs_ic_ir(output: dict, n_factors: int = None) -> "np.ndarray":
    """取 IC 分析的 IC_IR 绝对值（批量模式）。

    output["统计数据"] 是 DataFrame，index=因子名, columns=[IC_IR, ...]，
    每行一个候选因子的统计结果。返回 shape=(n_factors,) 的 fitness 数组。
    """
    import pandas as pd

    stats = output.get("统计数据", output) if isinstance(output, dict) else output
    if isinstance(stats, pd.DataFrame) and "IC_IR" in stats.columns:
        ic_ir = pd.to_numeric(stats["IC_IR"], errors="coerce").fillna(0.0).values
        return np.abs(ic_ir)

    if isinstance(stats, dict):
        val = stats.get("IC_IR", 0.0)
        return np.full(n_factors or 1, float(abs(val)))

    raise ValueError(f"无法从输出中提取 IC_IR，统计数据格式不符合预期: {type(stats)}")

_BUILTIN_TRANSFORMS = {
    "abs_ic_ir": _transform_abs_ic_ir,
}

# 默认可用算子 → QuantStudio 算子对象映射
_DEFAULT_OPERATORS = {
    "add": ("QuantStudio.Factor.BasicOperator", "add"),
    "sub": ("QuantStudio.Factor.BasicOperator", "sub"),
    "mul": ("QuantStudio.Factor.BasicOperator", "mul"),
    "div": ("QuantStudio.Factor.BasicOperator", "div"),
    "qs_abs": ("QuantStudio.Factor.BasicOperator", "qs_abs"),
    "neg": ("QuantStudio.Factor.BasicOperator", "neg"),
}


# ─── 工具函数 ──────────────────────────────────────────────────

def _parse_dt(date_str):
    """解析日期字符串为 datetime"""
    if isinstance(date_str, dt.datetime):
        return date_str
    return dt.datetime.strptime(date_str, "%Y-%m-%d")


# ─── 挖掘框架注册表 ───────────────────────────────────────────────

class MiningService:
    """因子挖掘服务"""

    def __init__(self, factor_service=None):
        self._factor_service = factor_service
        self._tasks_cache: Dict[str, MiningTask] = {}

    # ─── 运行时配置 ────────────────────────────────────────────────

    @property
    def workspace(self) -> str:
        return settings.mining.get("workspace", os.path.expanduser("~/MiningWorkspace"))

    # ─── 框架 ────────────────────────────────────────────────────

    def list_frameworks(self) -> List[FrameworkInfo]:
        frameworks = []
        frameworks.append(FrameworkInfo(
            key="gp",
            name="遗传规划 (GP)",
            description="基于遗传编程的因子表达式自动发现",
            config_schema=self._gp_config_schema(),
        ))
        frameworks.append(FrameworkInfo(
            key="llm_factor",
            name="LLM 因子挖掘",
            description="基于 LLM 驱动的假设生成→因子开发→因子评测循环",
            config_schema=self._llm_factor_config_schema(),
        ))
        return frameworks

    def get_framework_config(self, name: str) -> dict:
        if name == "gp":
            return self._gp_config_schema()
        if name == "llm_factor":
            return self._llm_factor_config_schema()
        cfg = self.frameworks_config.get(name)
        if cfg is None:
            raise ValueError(f"未知的挖掘框架: {name}")
        return cfg

    def _gp_config_schema(self) -> dict:
        from app.models.backtest import BACKTEST_MODULE_REGISTRY

        section_factor_modules = [
            {"key": key, "name": info["name"], "description": info["description"],
             "params": info.get("params", []),
             "requires_price": info.get("requires_price", False),
             "requires_descriptor_ids": info.get("requires_descriptor_ids", True)}
            for key, info in BACKTEST_MODULE_REGISTRY.items()
            if info.get("category") == "SectionFactor"
        ]

        mining_cfg = settings.mining
        frameworks_cfg = mining_cfg.get("frameworks", {})
        gp_cfg = frameworks_cfg.get("gp", {})
        return {
            "operators": list(_DEFAULT_OPERATORS.keys()),
            "default_params": {
                "population_size": gp_cfg.get("population_size", 20),
                "n_generations": gp_cfg.get("n_generations", 20),
                "tournament_size": gp_cfg.get("tournament_size", 20),
                "init_depth": gp_cfg.get("init_depth", [2, 6]),
                "init_method": gp_cfg.get("init_method", "half and half"),
                "const_range": gp_cfg.get("const_range", [-1.0, 1.0]),
                "p_crossover": gp_cfg.get("p_crossover", 0.9),
                "p_subtree_mutation": gp_cfg.get("p_subtree_mutation", 0.01),
                "p_hoist_mutation": gp_cfg.get("p_hoist_mutation", 0.01),
                "p_point_mutation": gp_cfg.get("p_point_mutation", 0.01),
                "p_point_replace": gp_cfg.get("p_point_replace", 0.05),
                "parsimony_coefficient": gp_cfg.get("parsimony_coefficient", 0.0),
            },
            "eval_modules": section_factor_modules,
            "default_eval": gp_cfg.get("default_eval", {
                "modules": [
                    {"module": "ic", "instance_label": "", "params": {}, "section_mode": "auto"}
                ],
                "transform": "abs_ic_ir",
                "sign": "greater",
            }),
        }

    def _llm_factor_config_schema(self) -> dict:
        mining_cfg = settings.mining
        frameworks_cfg = mining_cfg.get("frameworks", {})
        llm_cfg = frameworks_cfg.get("llm_factor", {})
        hyp_cfg = llm_cfg.get("hypothesis", {})
        dev_cfg = llm_cfg.get("development", {})
        eval_cfg = llm_cfg.get("evaluation", {})
        data_cfg = llm_cfg.get("data", {})

        def _dv(section: dict, key: str, default):
            """读取配置值，优先 section 级，其次 llm_cfg 顶级"""
            return section.get(key, llm_cfg.get(key, default))

        return {
            "groups": [
                {
                    "key": "task",
                    "label": "任务配置",
                    "fields": [
                        {"key": "target", "label": "研究方向", "type": "text",
                         "placeholder": "如：动量因子、低波动因子", "required": True},
                        {"key": "market", "label": "目标市场", "type": "select",
                         "options": ["A股", "港股", "美股"],
                         "default": hyp_cfg.get("market", "A股")},
                        {"key": "frequency", "label": "数据频率", "type": "select",
                         "options": ["日频", "周频", "月频"],
                         "default": hyp_cfg.get("frequency", "日频")},
                        {"key": "mode", "label": "运行模式", "type": "select",
                         "options": [
                             {"value": "skill", "label": "Skill — Claude Agent 自主决策"},
                             {"value": "graph", "label": "Graph — Workflow 编排，节点级 LLM 调用"},
                         ],
                         "default": llm_cfg.get("mode", "skill")},
                        {"key": "max_rounds", "label": "最大轮次", "type": "number",
                         "min": 1, "default": llm_cfg.get("max_rounds", 1),
                         "tooltip": "1=单次运行，>1=持续循环"},
                        {"key": "max_hours", "label": "最大时长 (小时)", "type": "number",
                         "min": 0.1, "max": 72.0, "step": 0.5,
                         "default": llm_cfg.get("max_hours", 8.0)},
                        {"key": "stages", "label": "运行阶段", "type": "multi-select",
                         "options": [
                             {"value": "hypothesis", "label": "假设生成"},
                             {"value": "development", "label": "因子开发"},
                             {"value": "evaluation", "label": "因子评测"},
                         ],
                         "default": ["hypothesis", "development", "evaluation"]},
                        {"key": "clear_cache", "label": "清空评测缓存", "type": "switch",
                         "default": True},
                    ],
                },
                {
                    "key": "hypothesis",
                    "label": "假设生成",
                    "fields": [
                        {"key": "max_turns_hypothesis", "label": "Agent 最大轮次", "type": "number",
                         "min": 1, "default": _dv(hyp_cfg, "max_turns_hypothesis", 50)},
                        {"key": "max_directions", "label": "最大方向数", "type": "number",
                         "min": 1, "max": 20, "default": hyp_cfg.get("max_directions", 5)},
                        {"key": "max_wiki_pages_per_direction", "label": "每方向最大 Wiki 页数", "type": "number",
                         "min": 1, "max": 50, "default": hyp_cfg.get("max_wiki_pages_per_direction", 5)},
                        {"key": "max_factor_codes_per_direction", "label": "每方向最大因子代码数", "type": "number",
                         "min": 1, "max": 50, "default": hyp_cfg.get("max_factor_codes_per_direction", 3)},
                        {"key": "freeze_after_n_failures", "label": "连续失败冻结阈值", "type": "number",
                         "min": 1, "max": 20, "default": hyp_cfg.get("freeze_after_n_failures", 3),
                         "tooltip": "某方向连续失败 N 次后冻结"},
                        {"key": "correlation_warning_threshold", "label": "相关性预警阈值", "type": "number",
                         "min": 0.0, "max": 1.0, "step": 0.05,
                         "default": hyp_cfg.get("correlation_warning_threshold", 0.7)},
                        {"key": "min_incremental_ic_t", "label": "最小增量 IC t 值", "type": "number",
                         "min": 0.0, "max": 10.0, "step": 0.1,
                         "default": hyp_cfg.get("min_incremental_ic_t", 2.0)},
                        {"key": "min_turnover_days", "label": "最小换手天数", "type": "number",
                         "min": 1, "max": 60, "default": hyp_cfg.get("min_turnover_days", 5)},
                    ],
                },
                {
                    "key": "development",
                    "label": "因子开发",
                    "fields": [
                        {"key": "max_turns_development", "label": "Agent 最大轮次", "type": "number",
                         "min": 1, "default": _dv(dev_cfg, "max_turns_development", 80)},
                        {"key": "max_auto_fixes", "label": "最大自动修复次数", "type": "number",
                         "min": 0, "max": 20, "default": dev_cfg.get("max_auto_fixes", 3)},
                        {"key": "enable_leak_test", "label": "未来信息泄漏检测", "type": "switch",
                         "default": dev_cfg.get("enable_leak_test", True)},
                        {"key": "enable_unit_check", "label": "单位检查", "type": "switch",
                         "default": dev_cfg.get("enable_unit_check", True)},
                        {"key": "enable_semantic_review", "label": "语义审查 (LLM)", "type": "switch",
                         "default": dev_cfg.get("enable_semantic_review", True)},
                        {"key": "enable_param_search", "label": "参数搜索 (Optuna)", "type": "switch",
                         "default": dev_cfg.get("enable_param_search", True)},
                        {"key": "max_trials", "label": "Optuna 最大试验次数", "type": "number",
                         "min": 10, "max": 1000, "default": dev_cfg.get("max_trials", 200)},
                        {"key": "cv_folds", "label": "交叉验证折数", "type": "number",
                         "min": 1, "max": 10, "default": dev_cfg.get("cv_folds", 3)},
                        {"key": "early_stop_rounds", "label": "早停轮数", "type": "number",
                         "min": 1, "max": 100, "default": dev_cfg.get("early_stop_rounds", 30)},
                        {"key": "optimization_objective", "label": "优化目标", "type": "select",
                         "options": [
                             {"value": "rankic", "label": "RankIC"},
                             {"value": "icir", "label": "ICIR"},
                             {"value": "multi", "label": "多目标加权"},
                         ],
                         "default": dev_cfg.get("optimization_objective", "rankic")},
                    ],
                },
                {
                    "key": "evaluation",
                    "label": "因子评测",
                    "fields": [
                        {"key": "in_sample_start", "label": "样本内起始", "type": "month",
                         "default": eval_cfg.get("in_sample_start", "2015-01")},
                        {"key": "in_sample_end", "label": "样本内结束", "type": "month",
                         "default": eval_cfg.get("in_sample_end", "2022-12")},
                        {"key": "oos_start", "label": "样本外起始", "type": "month",
                         "default": eval_cfg.get("oos_start", "2023-01")},
                        {"key": "oos_end", "label": "样本外结束", "type": "month",
                         "default": eval_cfg.get("oos_end", "2025-12")},
                        {"key": "corr_method", "label": "相关性方法", "type": "select",
                         "options": [
                             {"value": "spearman", "label": "Spearman"},
                             {"value": "pearson", "label": "Pearson"},
                             {"value": "kendall", "label": "Kendall"},
                         ],
                         "default": eval_cfg.get("corr_method", "spearman")},
                        {"key": "ic_lookback", "label": "IC 回溯期数", "type": "number",
                         "min": 1, "max": 252, "default": eval_cfg.get("ic_lookback", 31)},
                        {"key": "period_lookback", "label": "因子回溯期数", "type": "number",
                         "min": 1, "max": 252, "default": eval_cfg.get("period_lookback", 1)},
                        {"key": "group_num", "label": "分组数", "type": "number",
                         "min": 2, "max": 20, "default": eval_cfg.get("group_num", 5)},
                        {"key": "rebalance_freq", "label": "再平衡频率", "type": "select",
                         "options": [
                             {"value": "daily", "label": "日频"},
                             {"value": "weekly", "label": "周频"},
                             {"value": "monthly", "label": "月频"},
                         ],
                         "default": eval_cfg.get("rebalance_freq", "monthly")},
                        {"key": "exclude_st", "label": "剔除 ST", "type": "switch",
                         "default": eval_cfg.get("exclude_st", True)},
                        {"key": "min_listing_days", "label": "最小上市天数", "type": "number",
                         "min": 1, "max": 365, "default": eval_cfg.get("min_listing_days", 60)},
                        {"key": "min_alpha_t", "label": "Alpha t 阈值", "type": "number",
                         "min": 0.0, "max": 10.0, "step": 0.5,
                         "default": eval_cfg.get("min_alpha_t", 3.0)},
                        {"key": "min_composite_score", "label": "综合评分阈值", "type": "number",
                         "min": 0.0, "max": 1.0, "step": 0.05,
                         "default": eval_cfg.get("min_composite_score", 0.60)},
                        {"key": "cache_enabled", "label": "启用数据缓存", "type": "switch",
                         "default": eval_cfg.get("cache_enabled", True)},
                        {"key": "cache_start_mode", "label": "缓存启动模式", "type": "select",
                         "options": [
                             {"value": "continue", "label": "复用已有缓存"},
                             {"value": "new", "label": "每次清空重建"},
                         ],
                         "default": eval_cfg.get("cache_start_mode", "continue")},
                    ],
                },
            ],
            "defaults": {
                "target": "", "market": "A股", "frequency": "日频",
                "mode": "skill", "max_rounds": 1, "max_hours": 8.0,
                "max_turns_hypothesis": llm_cfg.get("max_turns_hypothesis", 50),
                "max_turns_development": llm_cfg.get("max_turns_development", 80),
                "stages": ["hypothesis", "development", "evaluation"],
                "clear_cache": True,
                # 假设生成默认值
                "max_directions": hyp_cfg.get("max_directions", 5),
                "max_wiki_pages_per_direction": hyp_cfg.get("max_wiki_pages_per_direction", 5),
                "max_factor_codes_per_direction": hyp_cfg.get("max_factor_codes_per_direction", 3),
                "freeze_after_n_failures": hyp_cfg.get("freeze_after_n_failures", 3),
                "correlation_warning_threshold": hyp_cfg.get("correlation_warning_threshold", 0.7),
                "min_incremental_ic_t": hyp_cfg.get("min_incremental_ic_t", 2.0),
                "min_turnover_days": hyp_cfg.get("min_turnover_days", 5),
                # 因子开发默认值
                "max_auto_fixes": dev_cfg.get("max_auto_fixes", 3),
                "enable_leak_test": dev_cfg.get("enable_leak_test", True),
                "enable_unit_check": dev_cfg.get("enable_unit_check", True),
                "enable_semantic_review": dev_cfg.get("enable_semantic_review", True),
                "enable_param_search": dev_cfg.get("enable_param_search", True),
                "max_trials": dev_cfg.get("max_trials", 200),
                "cv_folds": dev_cfg.get("cv_folds", 3),
                "early_stop_rounds": dev_cfg.get("early_stop_rounds", 30),
                "optimization_objective": dev_cfg.get("optimization_objective", "rankic"),
                # 因子评测默认值
                "in_sample_start": eval_cfg.get("in_sample_start", "2015-01"),
                "in_sample_end": eval_cfg.get("in_sample_end", "2022-12"),
                "oos_start": eval_cfg.get("oos_start", "2023-01"),
                "oos_end": eval_cfg.get("oos_end", "2025-12"),
                "corr_method": eval_cfg.get("corr_method", "spearman"),
                "ic_lookback": eval_cfg.get("ic_lookback", 31),
                "period_lookback": eval_cfg.get("period_lookback", 1),
                "group_num": eval_cfg.get("group_num", 5),
                "rebalance_freq": eval_cfg.get("rebalance_freq", "monthly"),
                "exclude_st": eval_cfg.get("exclude_st", True),
                "min_listing_days": eval_cfg.get("min_listing_days", 60),
                "min_alpha_t": eval_cfg.get("min_alpha_t", 3.0),
                "min_composite_score": eval_cfg.get("min_composite_score", 0.60),
                "cache_enabled": eval_cfg.get("cache_enabled", True),
                "cache_start_mode": eval_cfg.get("cache_start_mode", "continue"),
            },
        }

    def _resolve_operators(self, operator_names: List[str]) -> List:
        operators = []
        for name in operator_names:
            entry = _DEFAULT_OPERATORS.get(name)
            if entry is None:
                raise ValueError(f"未知的算子: {name}")
            mod = importlib.import_module(entry[0])
            op = getattr(mod, entry[1])
            operators.append(op)
        return operators

    # ─── 任务管理 ────────────────────────────────────────────────

    def _task_dir(self, task_id: str) -> str:
        return os.path.join(self.workspace, "tasks", task_id)

    def _run_dir(self, task_id: str, run_id: str) -> str:
        return os.path.join(self._task_dir(task_id), "runs", run_id)

    def _ensure_dir(self, path: str):
        os.makedirs(path, exist_ok=True)

    def _read_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, data: dict):
        self._ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def create_task(self, req: CreateTaskRequest) -> MiningTask:
        task_id = uuid.uuid4().hex[:12]
        now = dt.datetime.now().isoformat()
        task_dir = self._task_dir(task_id)
        self._ensure_dir(task_dir)
        task_data = {
            "task_id": task_id,
            "name": req.name or f"挖掘任务 {task_id}",
            "framework": req.framework,
            "runs": [],
            "created_at": now,
        }
        self._write_json(os.path.join(task_dir, "task.json"), task_data)
        return MiningTask(**task_data)

    def list_tasks(self) -> List[MiningTaskSummary]:
        tasks_dir = os.path.join(self.workspace, "tasks")
        if not os.path.exists(tasks_dir):
            return []
        summaries = []
        for task_id in sorted(os.listdir(tasks_dir), reverse=True):
            task_json = self._read_json(os.path.join(tasks_dir, task_id, "task.json"))
            if not task_json:
                continue
            runs = task_json.get("runs", [])
            current_status = runs[-1]["status"] if runs else "pending"
            summaries.append(MiningTaskSummary(
                task_id=task_id,
                name=task_json.get("name", ""),
                framework=task_json.get("framework", ""),
                status=current_status,
                current_run=len(runs),
                created_at=task_json.get("created_at", ""),
            ))
        return summaries

    def get_task(self, task_id: str) -> Optional[MiningTask]:
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        if not task_json:
            return None
        # 读取最新 run 的配置，用于前端还原表单
        runs = task_json.get("runs", [])
        config = None
        if runs:
            latest_run_id = runs[-1].get("run_id", "")
            config = self._read_json(os.path.join(self._run_dir(task_id, latest_run_id), "config.json"))
        task_json["config"] = config
        return MiningTask(**task_json)

    def delete_task(self, task_id: str):
        import shutil
        from app.tasks.manager import task_manager
        # 取消正在运行的任务（会触发 on_cancel → proc.kill() 等清理）
        try:
            task_manager.cancel(task_id)
        except Exception:
            pass
        task_dir = self._task_dir(task_id)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)

    # ─── 运行管理 ────────────────────────────────────────────────

    def _next_run_id(self, task_id: str) -> str:
        task_dir = self._task_dir(task_id)
        runs_dir = os.path.join(task_dir, "runs")
        if not os.path.exists(runs_dir):
            return "001"
        existing = sorted(os.listdir(runs_dir))
        if not existing:
            return "001"
        return str(int(existing[-1]) + 1).zfill(3)

    async def submit_run(self, task_id: str, req: SubmitRunRequest) -> str:
        from app.tasks.manager import task_manager
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        # task.json 中的 framework 是权威来源，req 中的 framework 仅作参考
        framework = task_json.get("framework") or req.framework or "gp"
        run_id = self._next_run_id(task_id)

        if framework == "llm_factor":
            return await self._submit_llm_factor_run(task_id, run_id, req.config, framework, task_manager)
        else:
            # GP 框架 — 现有逻辑
            gen_start = 0
            gp_config = GPRunConfig(**req.config) if isinstance(req.config, dict) else req.config

            async def _run():
                return await self._execute_gp_run(task_id, run_id, gp_config, gen_start, task_manager)

            bt_task_id = await task_manager.submit(
                name=f"GP 挖掘 (任务 {task_id}, run {run_id})",
                coro_or_func=_run(),
            )
            await task_manager.update_progress(bt_task_id, 0, "任务已提交")
            return run_id

    async def _submit_llm_factor_run(
        self, task_id: str, run_id: str, config: dict, framework: str, task_manager
    ) -> str:
        """提交 LLMFactor 挖掘运行"""
        # 校验配置
        llm_config = LLMFactorRunConfig(**config)

        async def _run():
            return await self._execute_llm_factor_run(task_id, run_id, llm_config, task_manager)

        bt_task_id = await task_manager.submit(
            name=f"LLMFactor 挖掘 (任务 {task_id}, run {run_id})",
            coro_or_func=_run(),
        )
        await task_manager.update_progress(bt_task_id, 0, "任务已提交")
        return run_id

    async def submit_continue(self, task_id: str, req: ContinueRunRequest) -> str:
        from app.tasks.manager import task_manager
        task_dir = self._task_dir(task_id)
        checkpoint_path = os.path.join(task_dir, "checkpoint.pkl")
        if not os.path.exists(checkpoint_path):
            raise ValueError(f"找不到 checkpoint 文件: {checkpoint_path}")

        task_json = self._read_json(os.path.join(task_dir, "task.json"))
        runs = task_json.get("runs", [])
        if not runs:
            raise ValueError("任务没有已完成的运行，无法接续")

        gen_start = sum(r.get("n_generations", 0) for r in runs)
        last_run_id = runs[-1]["run_id"]
        parent_config = self._read_json(os.path.join(self._run_dir(task_id, last_run_id), "config.json"))
        if not parent_config:
            raise ValueError(f"找不到父 run 的配置: {last_run_id}")

        req.config.operators = parent_config.get("operators", [])
        req.config.terminal_factors = parent_config.get("terminal_factors", [])
        run_id = self._next_run_id(task_id)

        async def _run():
            return await self._execute_gp_run(task_id, run_id, req.config, gen_start, task_manager, checkpoint_path)

        bt_task_id = await task_manager.submit(
            name=f"GP 接续挖掘 (任务 {task_id}, run {run_id})",
            coro_or_func=_run(),
        )
        await task_manager.update_progress(bt_task_id, 0, "任务已提交")
        return run_id

    # ─── GP 挖掘执行 ────────────────────────────────────────────

    async def _execute_gp_run(
        self, task_id, run_id, config: GPRunConfig, gen_start, task_manager,
        checkpoint_path: Optional[str] = None,
    ) -> dict:
        import asyncio
        loop = asyncio.get_running_loop()
        run_dir = self._run_dir(task_id, run_id)
        self._ensure_dir(run_dir)

        config_dict = config.model_dump() if hasattr(config, "model_dump") else config.dict()
        self._write_json(os.path.join(run_dir, "config.json"), config_dict)

        status = {"status": "running", "started_at": dt.datetime.now().isoformat()}
        self._write_json(os.path.join(run_dir, "status.json"), status)
        self._add_run_to_task(task_id, run_id, config.n_generations, "running")

        try:
            result = await loop.run_in_executor(
                None, self._run_gp_sync,
                config, gen_start, task_id, run_id, checkpoint_path,
            )
            status = {"status": "completed", "completed_at": dt.datetime.now().isoformat()}
            self._write_json(os.path.join(run_dir, "status.json"), status)
            self._write_json(os.path.join(run_dir, "result.json"), result)
            self._update_run_in_task(task_id, run_id, "completed")
            self._save_checkpoint(task_id, result)
            self._export_factors(task_id, result, config, result.get("_hof_factors", []))
            return result
        except Exception as e:
            logger.exception(f"GP 挖掘失败: {e}")
            status = {"status": "failed", "error": str(e), "completed_at": dt.datetime.now().isoformat()}
            self._write_json(os.path.join(run_dir, "status.json"), status)
            self._update_run_in_task(task_id, run_id, "failed", str(e))
            raise

    async def _execute_llm_factor_run(
        self, task_id: str, run_id: str, config: LLMFactorRunConfig, task_manager
    ) -> dict:
        """异步执行 LLMFactor 挖掘（子进程模式）。

        使用 subprocess.Popen + run_in_executor 启动子进程（兼容所有平台，无事件循环策略依赖），
        stdout 双路处理（写日志文件 + 解析阶段标记推送进度），
        进程结束后扫描 FM_* 目录提取结果。
        """
        loop = asyncio.get_running_loop()
        run_dir = self._run_dir(task_id, run_id)
        self._ensure_dir(run_dir)

        # 写配置
        config_dict = config.model_dump()
        self._write_json(os.path.join(run_dir, "config.json"), config_dict)
        self._add_run_to_task(task_id, run_id, 0, "running")

        # 生成完整 pipeline config（合并 QSWebConfig.yaml 中 llm_factor 配置 + 运行时参数）
        pipeline_config_path = os.path.join(run_dir, "pipeline_config.yaml")
        llm_cfg = settings.mining.get("frameworks", {}).get("llm_factor", {})
        pipeline_config = {
            "workspace_dir": run_dir,
            "project_root": llm_cfg.get("project_root", "auto"),
            "claude_cli": llm_cfg.get("claude_cli", "auto"),
            "max_turns_hypothesis": config.max_turns_hypothesis,
            "max_turns_development": config.max_turns_development,
            "permission_mode": llm_cfg.get("permission_mode", "bypassPermissions"),
        }
        # 数据上下文
        data_cfg = llm_cfg.get("data", {})
        if data_cfg:
            pipeline_config["data"] = data_cfg
        with open(pipeline_config_path, "w", encoding="utf-8") as f:
            yaml.dump(pipeline_config, f, allow_unicode=True)

        # 生成各阶段配置文件（YAML 默认值 ∪ 表单覆盖值）
        core_fields = {"target", "market", "frequency", "mode", "max_rounds",
                       "max_hours", "max_turns_hypothesis", "max_turns_development",
                       "stages", "clear_cache", "direction"}
        form_overrides = {k: v for k, v in config.model_dump().items()
                          if k not in core_fields and v is not None}
        # 根据 schema groups 路由表单字段到对应阶段
        schema = self._llm_factor_config_schema()
        phase_overrides: dict[str, dict] = {"hypothesis": {}, "development": {}, "evaluation": {}}
        for group in schema["groups"]:
            phase = group["key"]
            if phase == "task":
                continue
            for field in group["fields"]:
                key = field["key"]
                if key in form_overrides:
                    phase_overrides[phase][key] = form_overrides[key]

        self._write_phase_config(
            os.path.join(run_dir, "hypothesis_research.yaml"),
            {**llm_cfg.get("hypothesis", {}), **phase_overrides.get("hypothesis", {})}
        )
        self._write_phase_config(
            os.path.join(run_dir, "development.yaml"),
            {**llm_cfg.get("development", {}), **phase_overrides.get("development", {})}
        )
        self._write_phase_config(
            os.path.join(run_dir, "evaluation.yaml"),
            {**llm_cfg.get("evaluation", {}), **phase_overrides.get("evaluation", {})}
        )

        # 构建命令行
        cmd = [
            sys.executable, "-m", "QSExt.LLMFactor.scripts.run_pipeline",
            "--config", pipeline_config_path,
            "--target", config.target,
            "--market", config.market,
            "--frequency", config.frequency,
            "--mode", config.mode,
            "--max-rounds", str(config.max_rounds),
            "--max-hours", str(config.max_hours),
            "--max-turns-hypothesis", str(config.max_turns_hypothesis),
            "--max-turns-development", str(config.max_turns_development),
            "--stages", ",".join(config.stages),
        ]
        if config.direction:
            cmd += ["--direction", config.direction]
        if not config.clear_cache:
            cmd.append("--no-clear-cache")

        logger.info(f"启动 LLMFactor 子进程: {' '.join(cmd)}")

        # Windows: CREATE_NEW_PROCESS_GROUP 确保 kill 时连带子进程组
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "cwd": os.path.dirname(os.path.dirname(run_dir)),
            "text": False,  # 二进制模式，手动解码
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(cmd, **popen_kwargs)

        # 注册取消回调
        bt_task_id = next(iter(task_manager._running), None)
        if bt_task_id:
            task_manager.set_on_cancel(bt_task_id, lambda: _kill_proc(proc))

        # 写 status.json
        status_data = {
            "status": "running",
            "pid": proc.pid,
            "started_at": dt.datetime.now().isoformat(),
        }
        self._write_json(os.path.join(run_dir, "status.json"), status_data)

        # stdout 处理：线程读取行 → 队列 → 异步消费（写日志 + 解析进度）
        log_path = os.path.join(run_dir, "run.log")
        line_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()

        stage_patterns = [
            (r"(假设生成|hypothesis)", "假设生成中…", 10.0),
            (r"(方向探索|direction)", "方向探索中…", 5.0),
            (r"(深度调研|research)", "深度调研中…", 8.0),
            (r"(因子开发|development|factor.*development)", "因子开发中…", 40.0),
            (r"(因子评测|evaluation|backtest)", "因子评测中…", 70.0),
        ]

        def _reader_thread():
            """在子线程中逐行读取 stdout，写入队列"""
            try:
                with open(log_path, "w", encoding="utf-8") as log_f:
                    for line in iter(proc.stdout.readline, b""):
                        if stop_event.is_set():
                            break
                        text = line.decode("utf-8", errors="replace").rstrip("\n")
                        log_f.write(text + "\n")
                        log_f.flush()
                        line_queue.put(text)
            except Exception:
                pass
            finally:
                line_queue.put(None)  # 结束标记

        reader_future = loop.run_in_executor(None, _reader_thread)

        # 异步消费队列
        try:
            while True:
                text = await loop.run_in_executor(None, line_queue.get)
                if text is None:
                    break
                # 解析阶段标记 → 推送进度
                for pattern, stage_msg, progress in stage_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        if bt_task_id:
                            await task_manager.update_progress(
                                bt_task_id, progress, stage_msg
                            )
                        break
        except Exception as e:
            logger.warning(f"stdout 处理异常: {e}")
        finally:
            stop_event.set()

        # 等待线程和进程结束
        await reader_future
        exit_code = proc.wait()

        # 扫描 FM_* 目录提取结果
        result_data = self._scan_llm_factor_results(run_dir)

        # 更新状态
        if exit_code == 0:
            status_data = {"status": "completed", "exit_code": exit_code,
                           "completed_at": dt.datetime.now().isoformat()}
            self._write_json(os.path.join(run_dir, "status.json"), status_data)
            result = {
                "run_id": run_id,
                "framework": "llm_factor",
                "is_partial": False,
                "data": result_data,
            }
            self._write_json(os.path.join(run_dir, "result.json"), result)
            self._update_run_in_task(task_id, run_id, "completed")
            return result
        else:
            status_data = {"status": "failed", "exit_code": exit_code,
                           "error": f"进程退出码: {exit_code}",
                           "completed_at": dt.datetime.now().isoformat()}
            self._write_json(os.path.join(run_dir, "status.json"), status_data)
            self._update_run_in_task(task_id, run_id, "failed", f"进程退出码: {exit_code}")
            raise RuntimeError(f"LLMFactor 进程异常退出，退出码: {exit_code}")

    @staticmethod
    def _write_phase_config(path: str, config: dict):
        """写入阶段配置文件（仅写入非空配置，子阶段配置按需覆盖默认值）"""
        if not config:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

    def _scan_llm_factor_results(self, run_dir: str) -> dict:
        """扫描 workspace 下的 FM_* 目录，提取评测结果"""
        import glob as _glob
        workspace_root = os.path.dirname(os.path.dirname(run_dir))
        fm_dirs = sorted(_glob.glob(os.path.join(workspace_root, "FM_*")), reverse=True)
        factors = []
        metrics_summary = {}

        for fm_dir in fm_dirs[:10]:  # 最多扫 10 个 FM 目录
            fm_name = os.path.basename(fm_dir)
            eval_dir = os.path.join(fm_dir, "evaluation")
            if not os.path.isdir(eval_dir):
                continue

            # 尝试读取评测结果
            for eval_file in ["report.json", "metrics.json", "ic_result.json"]:
                eval_path = os.path.join(eval_dir, eval_file)
                eval_data = self._read_json(eval_path)
                if eval_data:
                    factors.append({
                        "name": fm_name,
                        "status": "validated",
                        "metrics": {
                            "ic_mean": eval_data.get("ic_mean"),
                            "ic_ir": eval_data.get("ic_ir"),
                            "rank_ic": eval_data.get("rank_ic"),
                            "sharpe": eval_data.get("sharpe"),
                            "max_drawdown": eval_data.get("max_drawdown"),
                        },
                    })
                    break
            else:
                # 无评测结果 —— 仍记录因子
                factors.append({
                    "name": fm_name,
                    "status": "pending_eval",
                    "metrics": {},
                })

        return {
            "stage": "evaluation",
            "factors": factors,
            "metrics_summary": metrics_summary,
            "factor_count": len(factors),
        }

    def _run_gp_sync(
        self, config: GPRunConfig, gen_start, task_id, run_id,
        checkpoint_path: Optional[str] = None,
    ) -> dict:
        from QSExt.GPFactor.GPLearn import GPLearner, GPConfig, toExprStr

        operators = self._resolve_operators(config.operators)
        if not operators:
            raise ValueError("至少需要选择一个算子")

        terminal_factors = self._resolve_terminals_sync(config.terminal_factors)
        terminal_factors = self._resolve_seed_factors_sync(
            getattr(config, "seed_factors", []) or [], terminal_factors
        )
        if not terminal_factors:
            raise ValueError("至少需要一个终端因子（或种子因子）")

        dtruler, dts, section_ids = self._get_eval_context_sync(
            terminal_factors, config
        )
        if not dtruler or not section_ids:
            raise ValueError("无法从终端因子获取时点标尺或截面ID，请检查因子数据")

        gp_config = GPConfig(
            population_size=config.population_size,
            tournament_size=config.tournament_size,
            init_depth=tuple(config.init_depth) if config.init_depth else (2, 6),
            init_method=config.init_method or "half and half",
            const_range=tuple(config.const_range) if config.const_range else None,
            p_crossover=config.p_crossover,
            p_subtree_mutation=config.p_subtree_mutation,
            p_hoist_mutation=config.p_hoist_mutation,
            p_point_mutation=config.p_point_mutation,
            p_point_replace=config.p_point_replace,
            parsimony_coefficient=config.parsimony_coefficient,
        )

        fitness_fun, _eval_sign = self._build_fitness_fun_sync(
            config.eval, dtruler, dts, section_ids,
        )

        learner = GPLearner(
            operator_list=operators,
            terminal_factors=terminal_factors,
            fitness_fun=fitness_fun,
            config=gp_config,
        )

        # 逐代进度回调：实时写入中间结果供前端轮询
        run_dir = self._run_dir(task_id, run_id)

        def _on_generation(gen_idx: int, fitness: list, hof: list):
            gen_best = [float(f.max()) for f in fitness]
            gen_avg = [float(f.mean()) for f in fitness]
            partial_hof = []
            for j, (fit, expr) in enumerate(hof):
                partial_hof.append({
                    "rank": j + 1,
                    "fitness": float(fit) if not (isinstance(fit, float) and np.isnan(fit)) else 0.0,
                    "expression": toExprStr(expr[0]),
                    "pn_structure": _pn_expr_to_structure(expr, config),
                })
            partial = {
                "run_id": run_id,
                "gen_start": gen_start,
                "gen_end": gen_start + gen_idx + 1,
                "is_partial": True,
                "fitness_history": {"gen_best": gen_best, "gen_avg": gen_avg},
                "hall_of_fame": partial_hof,
            }
            self._write_json(os.path.join(run_dir, "result.json"), partial)

        parents = None
        parent_fitness = None
        if checkpoint_path and os.path.exists(checkpoint_path):
            import dill
            with open(checkpoint_path, "rb") as f:
                ckpt = dill.load(f)
            parents = ckpt.get("parents")
            parent_fitness = ckpt.get("parent_fitness")

        evolve_kwargs = dict(
            n_generations=config.n_generations,
            progress_callback=_on_generation,
        )
        if parents is not None and parent_fitness is not None:
            evolve_kwargs["parents"] = parents
            evolve_kwargs["parent_fitness"] = np.array(parent_fitness)

        populations, fitness_history, ancestry = learner.evolve(**evolve_kwargs)

        hall_of_fame = []
        hof_factors = []
        for i, (fit, expr) in enumerate(learner.hall_of_fame):
            pn_structure = _pn_expr_to_structure(expr, config)
            hall_of_fame.append({
                "rank": i + 1,
                "fitness": float(fit) if not (isinstance(fit, float) and np.isnan(fit)) else 0.0,
                "expression": toExprStr(expr[0]),
                "pn_structure": pn_structure,
            })
            hof_factors.append(expr[0])

        gen_best = [float(arr.max()) if not np.all(np.isnan(arr)) else 0.0 for arr in fitness_history]
        gen_avg = [float(arr.mean()) if not np.all(np.isnan(arr)) else 0.0 for arr in fitness_history]
        final_population = populations[-1] if populations else []
        final_fitness = fitness_history[-1] if fitness_history else np.array([])
        final_fitness_list = []
        for v in final_fitness.tolist():
            final_fitness_list.append(float(v) if not (isinstance(v, float) and np.isnan(v)) else 0.0)

        return {
            "run_id": run_id,
            "hall_of_fame": hall_of_fame,
            "fitness_history": {"gen_best": gen_best, "gen_avg": gen_avg},
            "gen_start": gen_start,
            "gen_end": gen_start + len(fitness_history),
            "_final_population": final_population,
            "_final_fitness": final_fitness_list,
            "_hof_factors": hof_factors,
        }

    def _resolve_terminals_sync(self, terminal_refs: List) -> List:
        """同步解析终端因子为 Factor 对象列表，去重"""
        terminals = []
        seen_keys = set()
        for ref in terminal_refs:
            if isinstance(ref, dict):
                conn_id = ref.get("conn_id", "")
                table_name = ref.get("table_name", "")
                factor_name = ref.get("factor_name", "")
            elif hasattr(ref, "conn_id"):
                conn_id = ref.conn_id
                table_name = ref.table_name
                factor_name = ref.factor_name
            else:
                continue
            if not factor_name:
                continue
            key = f"{conn_id}/{table_name}/{factor_name}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if not (conn_id and table_name and factor_name and self._factor_service):
                raise ValueError(f"终端因子参数不完整: {key}")
            try:
                db = self._factor_service._reconstruct_db_sync(conn_id)
                ft = db.getTable(table_name)
                factor = ft.getFactor(factor_name)
                terminals.append(factor)
            except Exception as e:
                raise ValueError(f"获取终端因子失败 {key}: {e}") from e
        return terminals

    def _resolve_seed_factors_sync(self, seed_refs: List, terminals: List) -> List:
        """从种子因子中提取叶节点 DataFactor，合并到终端因子列表

        Args:
            seed_refs: 种子因子引用列表
            terminals: 已有的终端因子列表

        Returns:
            合并后的终端因子列表（原地修改）
        """
        from QuantStudio.Factor.Factor import DataFactor
        from QuantStudio.Factor.FactorOperation import DerivativeFactor
        from QSExt.GPFactor.GPLearn import flattenFactor2PN

        if not seed_refs:
            return terminals

        existing_keys = set()
        for t in terminals:
            ft = getattr(t, "_FactorTable", None)
            if ft:
                conn_id = ft.FactorDB.Name if ft.FactorDB else ""
                table_name = ft.Name
                existing_keys.add(f"{conn_id}/{table_name}/{t.Name}")

        for ref in seed_refs:
            if isinstance(ref, dict):
                conn_id = ref.get("conn_id", "")
                table_name = ref.get("table_name", "")
                factor_name = ref.get("factor_name", "")
            elif hasattr(ref, "conn_id"):
                conn_id = ref.conn_id
                table_name = ref.table_name
                factor_name = ref.factor_name
            else:
                continue

            if not factor_name or not self._factor_service:
                continue

            try:
                db = self._factor_service._reconstruct_db_sync(conn_id)
                ft = db.getTable(table_name)
                seed = ft.getFactor(factor_name)

                # 展开种子因子为 PN，提取所有 DataFactor 叶节点
                pn = flattenFactor2PN(seed)
                for node in pn:
                    if isinstance(node, DerivativeFactor):
                        continue
                    node_ft = getattr(node, "_FactorTable", None)
                    node_conn = node_ft.FactorDB.Name if node_ft and node_ft.FactorDB else ""
                    node_table = node_ft.Name if node_ft else ""
                    key = f"{node_conn}/{node_table}/{node.Name}"
                    if key not in existing_keys:
                        existing_keys.add(key)
                        terminals.append(node)
            except Exception as e:
                logger.warning(f"解析种子因子失败: {e}")

        return terminals

    # ─── 评估上下文 ─────────────────────────────────────────────

    def _get_eval_context_sync(
        self, terminal_factors: List, config: "GPRunConfig"
    ) -> Tuple[List, List, List]:
        """从终端因子获取 DTRuler / DTs / SectionIDs

        参照 qs_bridge._get_dtruler_and_dts 的实现方式：
        - 日期范围优先使用配置中的 start_date/end_date，否则取最近 3 年
        - DTRuler 根据 dtruler_lookback_years 前推起始时间
        - 时点模式 dt_mode 决定使用交易日还是自然日
        """
        bt_cfg = self._load_backtest_config()
        lookback_years = bt_cfg.get("dtruler_lookback_years", 10)

        # 确定评估日期范围
        start_date = getattr(config, "start_date", None) or None
        end_date = getattr(config, "end_date", None) or None
        dt_mode = getattr(config, "dt_mode", None) or "natural"

        for tf in terminal_factors:
            ft = getattr(tf, "_FactorTable", None)
            if ft is None:
                continue
            try:
                all_dts = sorted(ft.getDateTime(ifactor_name=tf.Name))
                if not all_dts:
                    continue

                if start_date and end_date:
                    start_dt = _parse_dt(start_date)
                    end_dt = _parse_dt(end_date)
                else:
                    start_dt = all_dts[-1] - dt.timedelta(days=365 * 3)
                    end_dt = all_dts[-1]

                ruler_start = start_dt - dt.timedelta(days=365 * lookback_years + 1)

                # 交易日模式：尝试从 backtest 配置获取交易日源
                if dt_mode == "trading":
                    tds = bt_cfg.get("trading_day_source")
                    if tds and tds.get("conn_id") and self._factor_service:
                        try:
                            trading_db = self._factor_service._reconstruct_db_sync(tds["conn_id"])
                            method = getattr(trading_db, tds.get("method", "getTradeDay"))
                            method_args = tds.get("method_args", {})
                            dtruler = method(start_date=ruler_start, end_date=end_dt, **method_args)
                            dts = method(start_date=start_dt, end_date=end_dt, **method_args)
                        except Exception as e:
                            logger.warning(f"交易日源获取失败，回退到自然日模式: {e}")
                            dtruler = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=ruler_start, end_dt=end_dt)
                            dts = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=start_dt, end_dt=end_dt)
                    else:
                        dtruler = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=ruler_start, end_dt=end_dt)
                        dts = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=start_dt, end_dt=end_dt)
                else:
                    dtruler = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=ruler_start, end_dt=end_dt)
                    dts = ft.getDateTime(ifactor_name=tf.Name, iid=None, start_dt=start_dt, end_dt=end_dt)

                section_ids = list(ft.getID(ifactor_name=tf.Name))
                if dtruler and section_ids:
                    return dtruler, dts, section_ids
            except Exception as e:
                logger.warning(f"获取评估上下文失败 ({tf.Name}): {e}")
                continue
        return [], [], []


    def _resolve_price_sync(self, price_ref) -> Optional[Any]:
        """解析价格因子引用为 Factor 对象（必须显式配置，无自动回退）"""
        if price_ref is None:
            return None

        conn_id = getattr(price_ref, "conn_id", None) or (price_ref.get("conn_id") if isinstance(price_ref, dict) else None)
        table_name = getattr(price_ref, "table_name", None) or (price_ref.get("table_name") if isinstance(price_ref, dict) else None)
        factor_name = getattr(price_ref, "factor_name", None) or (price_ref.get("factor_name") if isinstance(price_ref, dict) else "close")

        if not (conn_id and table_name and factor_name):
            return None

        if self._factor_service:
            try:
                db = self._factor_service._reconstruct_db_sync(conn_id)
                ft = db.getTable(table_name)
                return ft.getFactor(factor_name)
            except Exception as e:
                logger.warning(f"解析价格因子失败 ({conn_id}/{table_name}/{factor_name}): {e}")

        return None

    @staticmethod
    def _load_backtest_config() -> dict:
        """加载 QSWebConfig.yaml 的回测配置节（复用 dtruler_lookback_years 等参数）"""
        import yaml as _yaml
        cfg_path = settings.QS_CONFIG_PATH
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = _yaml.safe_load(f)
                return cfg.get("backtest", {})
            except Exception:
                pass
        return {}

    # ─── 适应度函数 ─────────────────────────────────────────────

    def _build_fitness_fun_sync(self, eval_config: EvalConfig,
                                  dtruler: List, dts: List, section_ids: List) -> Tuple[Callable, str]:
        """构建适应度函数。

        统一批量评估：所有候选因子一次 Engine.run() 完成。
        使用 FeatherFactorCache 跨代缓存因子数据。
        """
        from app.services.global_config_service import resolve_engine
        from QuantStudio.Core.Node import DTInitData, DTLocalContext
        from QuantStudio.Factor.Factor import FactorContext
        from QuantStudio.Factor.FactorCache import FeatherFactorCache

        transform_fn = self._resolve_transform(eval_config.transform)
        if not eval_config.modules:
            raise ValueError("至少需要一个评估模块")
        mod_cfg = eval_config.modules[0]

        price_factor = self._resolve_price_sync(
            getattr(mod_cfg, "price_ref", None)
        )
        builder = _BT_NODE_BUILDERS.get(mod_cfg.module, {})
        if builder.get("requires_price") and price_factor is None:
            raise ValueError(f"评估模块 '{mod_cfg.module}' 需要价格因子，请在模块配置中指定")

        calc_mod = importlib.import_module(builder["calc_module"])
        calc_cls = getattr(calc_mod, builder["calc_class"])
        node_mod = importlib.import_module(builder["node_module"])
        node_cls = getattr(node_mod, builder["node_class"])

        calc_kwargs = {"descriptor_ids": section_ids}
        for pname in builder.get("calc_params", []):
            if pname in mod_cfg.params:
                calc_kwargs[pname] = mod_cfg.params[pname]
        node_params = dict(builder.get("default_node_params", {}))
        node_params["Name"] = mod_cfg.module
        for node_key, param_key in builder.get("node_params_map", {}).items():
            if param_key in mod_cfg.params:
                node_params[node_key] = mod_cfg.params[param_key]

        # 解析引擎配置
        EngineClass, pid_list, global_cache_dir = resolve_engine()

        cache_dir = os.path.join(global_cache_dir, "eval_cache")
        os.makedirs(cache_dir, exist_ok=True)
        start_dt = dts[0] if dts else dt.datetime(2000, 1, 1)
        end_dt = dts[-1] if dts else dt.datetime.now()

        cache = FeatherFactorCache(args={
            "DTRuler": dtruler,
            "PIDs": pid_list,
            "CacheDir": cache_dir,
            "StartMode": "new",
        })
        cache.start()
        context = FactorContext(
            PID="0", PIDList=pid_list, DTRuler=dtruler,
            SectionIDs=section_ids, DataCache=cache,
        )

        def fitness_fun(factors: List) -> np.ndarray:
            if not factors:
                return np.array([])
            try:
                calc_factor = calc_cls(**calc_kwargs)(*factors, price=price_factor, factor_args={})
                bt_node = node_cls(calc_factor, args=node_params)
                with EngineClass() as exec_engine:
                    output, = exec_engine.run(
                        [bt_node], context,
                        fwd_data_list=[DTLocalContext(DTs=dts)],
                        init_data_list=[DTInitData(DTRange=(start_dt, end_dt))],
                    )
                result = transform_fn(output)
                if len(result) != len(factors):
                    logger.warning(
                        f"适应度数组长度({len(result)})与因子数({len(factors)})不一致，补齐 NaN"
                    )
                    padded = np.full(len(factors), np.nan)
                    padded[:len(result)] = result
                    return padded
                return result
            except Exception as e:
                import traceback
                logger.warning(f"批量评估失败: {e}\n{traceback.format_exc()}")
                return np.full(len(factors), np.nan)

        return fitness_fun, eval_config.sign

    def _resolve_transform(self, transform_spec: str) -> Callable:
        if transform_spec in _BUILTIN_TRANSFORMS:
            return _BUILTIN_TRANSFORMS[transform_spec]
        if transform_spec.startswith("@"):
            script_path = transform_spec[1:]
            script_path = script_path.replace("{workspace}", self.workspace)
            script_path = os.path.expanduser(script_path)
            import importlib.util
            spec = importlib.util.spec_from_file_location("transform", script_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "transform"):
                raise ValueError(f"自定义 transform 脚本缺少 transform 函数: {script_path}")
            return mod.transform
        raise ValueError(f"未知的 transform 配置: {transform_spec}")

    # ─── 持久化 ──────────────────────────────────────────────────

    def _save_checkpoint(self, task_id: str, result: dict):
        import dill
        checkpoint_path = os.path.join(self._task_dir(task_id), "checkpoint.pkl")
        checkpoint = {
            "parents": result.get("_final_population", []),
            "parent_fitness": result.get("_final_fitness", []),
        }
        with open(checkpoint_path, "wb") as f:
            dill.dump(checkpoint, f)

    def _export_factors(self, task_id: str, result: dict, config: GPRunConfig, hof_factors: list):
        """将 Hall of Fame 导出为 FactorDef 脚本"""
        from QSExt.FactorDef.FactorScriptWriter import generate_script

        if not hof_factors:
            return

        hall_of_fame = result.get("hall_of_fame", [])
        factor_names = [f"gp_{i:03d}" for i in range(1, len(hall_of_fame) + 1)]

        script_path = os.path.join(self._task_dir(task_id), "factors.py")

        generate_script(
            factors=hof_factors,
            meta={
                "TargetTable": "stock_cn_factor_mining",
                "IDType": "A股",
                "Author": "MiningStudio (GP)",
                "Description": f"GP 挖掘任务 {task_id} 产出因子",
                "Tags": ["gp", "mining", "auto"],
            },
            output_path=script_path,
            factor_names=factor_names,
        )

    # ─── 任务元数据维护 ──────────────────────────────────────────

    def _add_run_to_task(self, task_id: str, run_id: str, n_generations: int, status: str):
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        runs = task_json.get("runs", [])
        runs.append({
            "run_id": run_id,
            "status": status,
            "n_generations": n_generations,
            "started_at": dt.datetime.now().isoformat(),
            "completed_at": None,
        })
        task_json["runs"] = runs
        self._write_json(os.path.join(self._task_dir(task_id), "task.json"), task_json)

    def _update_run_in_task(self, task_id: str, run_id: str, status: str, error: str = None):
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        for run in task_json.get("runs", []):
            if run["run_id"] == run_id:
                run["status"] = status
                run["completed_at"] = dt.datetime.now().isoformat()
                if error:
                    run["error"] = error
                break
        self._write_json(os.path.join(self._task_dir(task_id), "task.json"), task_json)

    # ─── 结果查询 ────────────────────────────────────────────────

    def get_run_result(self, task_id: str, run_id: str) -> Optional[RunResult]:
        result_json = self._read_json(os.path.join(self._run_dir(task_id, run_id), "result.json"))
        if not result_json:
            return None
        # 后向兼容：GP 结果中 hall_of_fame / fitness_history 从 data 或根字段读取
        if "data" not in result_json and result_json.get("hall_of_fame"):
            result_json["data"] = {
                "hall_of_fame": result_json.get("hall_of_fame", []),
                "fitness_history": result_json.get("fitness_history", {}),
            }
            result_json["framework"] = result_json.get("framework", "gp")
        return RunResult(**result_json)

    def get_run_log(self, task_id: str, run_id: str, offset: int = 0, tail: int = 200) -> RunLogResponse:
        """读取运行日志（增量轮询）"""
        log_path = os.path.join(self._run_dir(task_id, run_id), "run.log")
        if not os.path.exists(log_path):
            return RunLogResponse(lines=[], next_offset=0, eof=True, status="unknown")

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                if offset > 0:
                    f.seek(offset)
                lines = []
                for _ in range(tail):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\n"))
                next_offset = f.tell()
                eof = (next_offset >= os.path.getsize(log_path))
        except Exception:
            return RunLogResponse(lines=[], next_offset=0, eof=True, status="error")

        # 读取运行状态
        status_json = self._read_json(os.path.join(self._run_dir(task_id, run_id), "status.json"))
        run_status = status_json.get("status", "running")

        return RunLogResponse(
            lines=lines,
            next_offset=next_offset,
            eof=eof and run_status != "running",
            status=run_status,
        )

    def get_run_eval_metrics(self, task_id: str, run_id: str) -> EvalMetricsResponse:
        """获取运行评测指标"""
        result_json = self._read_json(os.path.join(self._run_dir(task_id, run_id), "result.json"))
        if not result_json:
            return EvalMetricsResponse(factors=[])

        data = result_json.get("data", result_json)
        factors_raw = data.get("factors", [])
        factors = []
        for f in factors_raw:
            factors.append(EvalFactorMetrics(
                name=f.get("name", "unknown"),
                status=f.get("status", "unknown"),
                metrics=f.get("metrics", {}),
            ))

        status_json = self._read_json(os.path.join(self._run_dir(task_id, run_id), "status.json"))
        updated_at = status_json.get("completed_at") or status_json.get("started_at")

        return EvalMetricsResponse(factors=factors, updated_at=updated_at)

    def get_factor_tree(self, task_id: str, index: int) -> Optional[FactorTreeDAG]:
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        runs = task_json.get("runs", [])
        # 优先已完成，其次运行中（运行中现在也有中间 result.json）
        completed_runs = [r for r in runs if r.get("status") == "completed"]
        running_runs = [r for r in runs if r.get("status") == "running"]
        target_run = (completed_runs[-1] if completed_runs else
                      running_runs[-1] if running_runs else None)
        if target_run is None:
            return None
        result_json = self._read_json(os.path.join(
            self._run_dir(task_id, target_run["run_id"]), "result.json"))
        hall_of_fame = result_json.get("hall_of_fame", [])
        if index < 0 or index >= len(hall_of_fame):
            return None
        entry = hall_of_fame[index]
        pn = entry.get("pn_structure", [])
        if not pn:
            return None
        dag = _pn_to_dag(pn)
        return FactorTreeDAG(
            nodes=[FactorTreeNode(**n) for n in dag["nodes"]],
            edges=[FactorTreeEdge(**e) for e in dag["edges"]],
        )

    # ─── 导出 ────────────────────────────────────────────────────

    def export_factor(self, task_id: str, req: ExportRequest) -> str:
        import shutil
        src = os.path.join(self._task_dir(task_id), "factors.py")
        if not os.path.exists(src):
            raise ValueError(f"因子脚本不存在: {src}")
        target_dir = req.target_dir or settings.factor_def.get("scripts_dir", "")
        if not target_dir:
            raise ValueError("未指定目标目录且配置中无 scripts_dir")
        os.makedirs(target_dir, exist_ok=True)
        dst = os.path.join(target_dir, f"mining_{task_id}.py")
        shutil.copy2(src, dst)
        return dst


# 全局单例
mining_service = MiningService()

# 注入 FactorService 依赖（延迟导入避免循环引用）
from app.services.factor_service import factor_service as _fs  # noqa: E402
mining_service._factor_service = _fs

from QuantStudio.Factor.FactorOperation import DerivativeFactor
from QuantStudio.Factor.Factor import DataFactor, Factor


def _pn_expr_to_structure(pn_expr: list, config) -> list:
    """将 PN 表达式转换为可 JSON 序列化的结构化表示"""
    nodes = []
    for factor in pn_expr:
        if isinstance(factor, DerivativeFactor):
            nodes.append({
                "type": "operator",
                "operator": factor.Operator.serialize(),
                "arity": len(factor.Descriptors),
            })
        elif isinstance(factor, DataFactor):
            if factor._DataContent == "Value":
                nodes.append({
                    "type": "constant",
                    "value": factor._Data if isinstance(factor._Data, (int, float, str)) else str(factor._Data),
                })
            else:
                conn_id = ""
                table_name = ""
                for ref in config.terminal_factors:
                    if isinstance(ref, dict):
                        if ref.get("factor_name") == factor.Name:
                            conn_id = ref.get("conn_id", "")
                            table_name = ref.get("table_name", "")
                            break
                    elif hasattr(ref, "factor_name") and ref.factor_name == factor.Name:
                        conn_id = getattr(ref, "conn_id", "")
                        table_name = getattr(ref, "table_name", "")
                        break
                nodes.append({
                    "type": "terminal",
                    "name": factor.Name,
                    "conn_id": conn_id,
                    "table_name": table_name,
                })
        elif isinstance(factor, Factor):
            # 数据库加载的普通 Factor 实例，作为终端叶子节点
            conn_id = ""
            table_name = ""
            ft = getattr(factor, "_FactorTable", None)
            if ft is not None:
                table_name = ft.Name
                if ft.FactorDB is not None:
                    conn_id = ft.FactorDB.Name
            nodes.append({
                "type": "terminal",
                "name": factor.Name,
                "conn_id": conn_id,
                "table_name": table_name,
            })
    return nodes


def _pn_to_dag(pn: list) -> dict:
    """将 PN 结构化表示转为 React Flow DAG 格式"""
    nodes = []
    edges = []
    arities = [n.get("arity", 0) if n["type"] == "operator" else 0 for n in pn]

    stack = []
    for i, node in enumerate(pn):
        if stack and stack[-1][1] > 0:
            edges.append({"source": str(stack[-1][0]), "target": str(i)})
            stack[-1] = (stack[-1][0], stack[-1][1] - 1)

        if arities[i] > 0:
            stack.append((i, arities[i]))

        while stack and stack[-1][1] == 0:
            stack.pop()

        node_type = node["type"]
        if node_type == "operator":
            name = node["operator"]["__qsargs__"].get("Name", "?")
        elif node_type == "terminal":
            name = node.get("name", "?")
        else:
            name = str(node.get("value", "?"))

        nodes.append({
            "id": str(i),
            "name": name,
            "type": node_type,
        })

    return {"nodes": nodes, "edges": edges}
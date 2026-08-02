"""
因子挖掘服务

管理挖掘框架注册、任务持久化和挖掘执行。
当前仅集成 GPLearner（GPFactor），架构预留未来框架扩展点。
"""

import datetime as dt
import importlib
import json
import logging
import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import yaml

from app.core.config import settings
from app.models.mining import (
    CreateTaskRequest,
    ContinueRunRequest,
    EvalConfig,
    EvalModuleConfig,
    ExportRequest,
    FactorTreeDAG,
    FactorTreeEdge,
    FactorTreeNode,
    FrameworkInfo,
    GPRunConfig,
    HallOfFameEntry,
    MiningTask,
    MiningTaskSummary,
    RunResult,
    RunSummary,
    SubmitRunRequest,
)

logger = logging.getLogger(__name__)


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
    "multi_portfolio": {
        "calc_module": "QuantStudio.BackTest.SectionFactor.QuantilePortfolio",
        "calc_class": "makeQuantilePortfolio",
        "node_module": "QuantStudio.BackTest.SectionFactor.QuantilePortfolio",
        "node_class": "MultiPortfolio",
        "requires_price": False,
        "calc_params": ["group_num", "ascending"],
        "portfolios_mode": True,
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

# 内置 transform 函数
_BUILTIN_TRANSFORMS = {
    "abs": abs,
    "neg": lambda x: -x,
    "square": lambda x: x * x,
    "sqrt": lambda x: x ** 0.5,
    "identity": lambda x: x,
}

# 默认可用算子 → QuantStudio 算子对象映射
_DEFAULT_OPERATORS = {
    "add": ("QuantStudio.Factor.BasicOperator", "add"),
    "sub": ("QuantStudio.Factor.BasicOperator", "sub"),
    "mul": ("QuantStudio.Factor.BasicOperator", "mul"),
    "div": ("QuantStudio.Factor.BasicOperator", "div"),
    "abs": ("QuantStudio.Factor.BasicOperator", "abs"),
    "neg": ("QuantStudio.Factor.BasicOperator", "neg"),
    "sign": ("QuantStudio.Factor.BasicOperator", "sign"),
    "log": ("QuantStudio.Factor.BasicOperator", "log"),
    "power": ("QuantStudio.Factor.BasicOperator", "power"),
    "sqrt": ("QuantStudio.Factor.BasicOperator", "sqrt"),
}


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

    @property
    def frameworks_config(self) -> dict:
        return settings.mining.get("frameworks", {})

    # ─── 框架 ────────────────────────────────────────────────────

    def list_frameworks(self) -> List[FrameworkInfo]:
        frameworks = []
        frameworks.append(FrameworkInfo(
            key="gp",
            name="遗传规划 (GP)",
            description="基于遗传编程的因子表达式自动发现",
            config_schema=self._gp_config_schema(),
        ))
        for key, cfg in self.frameworks_config.items():
            if key != "gp":
                frameworks.append(FrameworkInfo(
                    key=key,
                    name=cfg.get("name", key),
                    description=cfg.get("description", ""),
                    config_schema=cfg,
                ))
        return frameworks

    def get_framework_config(self, name: str) -> dict:
        if name == "gp":
            return self._gp_config_schema()
        cfg = self.frameworks_config.get(name)
        if cfg is None:
            raise ValueError(f"未知的挖掘框架: {name}")
        return cfg

    def _gp_config_schema(self) -> dict:
        return {
            "operators": list(_DEFAULT_OPERATORS.keys()),
            "default_params": {
                "population_size": 1000,
                "n_generations": 20,
                "tournament_size": 20,
                "init_depth": [2, 6],
                "init_method": "half and half",
                "const_range": [-1.0, 1.0],
                "p_crossover": 0.9,
                "p_subtree_mutation": 0.01,
                "p_hoist_mutation": 0.01,
                "p_point_mutation": 0.01,
                "p_point_replace": 0.05,
                "parsimony_coefficient": 0.0,
            },
            "eval_modules": ["ic", "ic_decay", "multi_portfolio", "factor_turnover", "section_correlation", "fama_macbeth"],
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
        return MiningTask(**task_json)

    def delete_task(self, task_id: str):
        import shutil
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
        run_id = self._next_run_id(task_id)
        gen_start = 0

        async def _run():
            return await self._execute_gp_run(task_id, run_id, req.config, gen_start, task_manager)

        bt_task_id = await task_manager.submit(
            name=f"GP 挖掘 (任务 {task_id}, run {run_id})",
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
            self._update_run_in_task(task_id, run_id, "failed")
            raise

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

        fitness_fun, _eval_sign = self._build_fitness_fun_sync(config.eval, config.price_ref)

        learner = GPLearner(
            operator_list=operators,
            terminal_factors=terminal_factors,
            fitness_fun=fitness_fun,
            config=gp_config,
        )

        parents = None
        parent_fitness = None
        if checkpoint_path and os.path.exists(checkpoint_path):
            import dill
            with open(checkpoint_path, "rb") as f:
                ckpt = dill.load(f)
            parents = ckpt.get("parents")
            parent_fitness = ckpt.get("parent_fitness")

        if parents is not None and parent_fitness is not None:
            populations, fitness_history, ancestry = learner.evolve(
                n_generations=config.n_generations,
                parents=parents,
                parent_fitness=np.array(parent_fitness),
            )
        else:
            populations, fitness_history, ancestry = learner.evolve(
                n_generations=config.n_generations,
            )

        hall_of_fame = []
        hof_factors = []
        for i, (fit, expr) in enumerate(learner.hall_of_fame):
            pn_structure = _pn_expr_to_structure(expr, config)
            hall_of_fame.append({
                "rank": i + 1,
                "fitness": float(fit),
                "expression": toExprStr(expr[0]),
                "pn_structure": pn_structure,
            })
            hof_factors.append(expr[0])

        gen_best = [float(arr.max()) for arr in fitness_history]
        gen_avg = [float(arr.mean()) for arr in fitness_history]
        final_population = populations[-1] if populations else []
        final_fitness = fitness_history[-1] if fitness_history else np.array([])

        return {
            "run_id": run_id,
            "hall_of_fame": hall_of_fame,
            "fitness_history": {"gen_best": gen_best, "gen_avg": gen_avg},
            "gen_start": gen_start,
            "gen_end": gen_start + len(fitness_history),
            "_final_population": final_population,
            "_final_fitness": final_fitness.tolist(),
            "_hof_factors": hof_factors,
        }

    def _resolve_terminals_sync(self, terminal_refs: List) -> List:
        """同步解析终端因子为 DataFactor 对象列表，去重"""
        from QuantStudio.Factor.Factor import DataFactor
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
            if conn_id and table_name and factor_name and self._factor_service:
                try:
                    db = self._factor_service._reconstruct_db_sync(conn_id)
                    ft = db.getTable(table_name)
                    factor = ft.getFactor(factor_name)
                    terminals.append(factor)
                except Exception as e:
                    logger.warning(f"获取终端因子失败 {key}: {e}")
                    terminals.append(DataFactor(data=factor_name, args={"Name": factor_name}))
            else:
                terminals.append(DataFactor(data=factor_name, args={"Name": factor_name}))
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

    # ─── 适应度函数 ─────────────────────────────────────────────

    def _build_fitness_fun_sync(self, eval_config: EvalConfig, price_ref=None) -> Tuple[Callable, str]:
        transform_fn = self._resolve_transform(eval_config.transform)

        def fitness_fun(factors: List) -> np.ndarray:
            fitness_values = np.full(len(factors), np.nan)
            for i, factor in enumerate(factors):
                try:
                    outputs = []
                    for mod_cfg in eval_config.modules:
                        output = self._eval_single_factor(factor, mod_cfg, price_ref)
                        outputs.append(output)
                    fitness_values[i] = float(transform_fn(outputs))
                except Exception as e:
                    logger.warning(f"适应度评估失败 (因子 {i}): {e}")
                    fitness_values[i] = np.nan
            return fitness_values

        return fitness_fun, eval_config.sign

    def _resolve_transform(self, transform_spec: str) -> Callable:
        if transform_spec in _BUILTIN_TRANSFORMS:
            fn = _BUILTIN_TRANSFORMS[transform_spec]
            return lambda outputs: fn(outputs[0])
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

    def _eval_single_factor(self, factor, mod_cfg: EvalModuleConfig, price_ref) -> dict:
        from QuantStudio.Core.CalcEngine import Engine
        from QuantStudio.Core.Node import DTInitData, DTLocalContext
        from QuantStudio.Factor.Factor import FactorContext
        from QuantStudio.BackTest.BackTestModel import BTReport

        builder = _BT_NODE_BUILDERS.get(mod_cfg.module)
        if builder is None:
            raise ValueError(f"未知的回测模块: {mod_cfg.module}")
        calc_mod = importlib.import_module(builder["calc_module"])
        calc_cls = getattr(calc_mod, builder["calc_class"])
        node_mod = importlib.import_module(builder["node_module"])
        node_cls = getattr(node_mod, builder["node_class"])
        calc_kwargs = {"descriptor_ids": None}
        for pname in builder.get("calc_params", []):
            if pname in mod_cfg.params:
                calc_kwargs[pname] = mod_cfg.params[pname]
        node_params = dict(builder.get("default_node_params", {}))
        node_params["Name"] = mod_cfg.module
        for node_key, param_key in builder.get("node_params_map", {}).items():
            if param_key in mod_cfg.params:
                node_params[node_key] = mod_cfg.params[param_key]
        calc_factor = calc_cls(**calc_kwargs)(factor, price=price_ref, factor_args={})
        bt_node = node_cls(calc_factor, args=node_params)
        report = BTReport(bt_node_list=[bt_node])
        dtruler = None
        section_ids = []
        context = FactorContext(PID="0", PIDList=["0"], DTRuler=dtruler or [], SectionIDs=section_ids)
        with Engine() as exec_engine:
            output, = exec_engine.run(
                [report], context,
                fwd_data_list=[DTLocalContext(DTs=dtruler or [])],
                init_data_list=[DTInitData(DTRange=(dt.datetime(2000, 1, 1), dt.datetime.now()))],
            )
        return output

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

    def _update_run_in_task(self, task_id: str, run_id: str, status: str):
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        for run in task_json.get("runs", []):
            if run["run_id"] == run_id:
                run["status"] = status
                run["completed_at"] = dt.datetime.now().isoformat()
                break
        self._write_json(os.path.join(self._task_dir(task_id), "task.json"), task_json)

    # ─── 结果查询 ────────────────────────────────────────────────

    def get_run_result(self, task_id: str, run_id: str) -> Optional[RunResult]:
        result_json = self._read_json(os.path.join(self._run_dir(task_id, run_id), "result.json"))
        if not result_json:
            return None
        return RunResult(**result_json)

    def get_factor_tree(self, task_id: str, index: int) -> Optional[FactorTreeDAG]:
        task_json = self._read_json(os.path.join(self._task_dir(task_id), "task.json"))
        runs = task_json.get("runs", [])
        completed_runs = [r for r in runs if r.get("status") == "completed"]
        if not completed_runs:
            return None
        last_run_id = completed_runs[-1]["run_id"]
        result_json = self._read_json(os.path.join(self._run_dir(task_id, last_run_id), "result.json"))
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

from QuantStudio.Factor.FactorOperation import DerivativeFactor
from QuantStudio.Factor.Factor import DataFactor


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
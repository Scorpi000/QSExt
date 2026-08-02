"""
组合优化服务

桥接 QuantStudio CVXPC 优化器和 Web API。
管理优化求解结果的生命周期（内存缓存）。
"""

import asyncio
import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd
import yaml
from ruamel.yaml import YAML

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.models.portfolio import (
    FactorDataRef,
    ObjectiveConfig,
    OptimizeRequest,
    OptimizeResponse,
    SolutionInfo,
)

_ruamel = YAML()
_ruamel.preserve_quotes = True

# ─── 默认优化选项（按求解器类型分别配置）────────────────────

# 各求解器通用默认值
_BASE_OPTIM_OPTIONS: Dict[str, Any] = {
    "verbose": False,
}

# 各求解器的专属默认值（代码级）
# 注意：此处参数直接透传给 CVXPY problem.solve(**options)，
# solver 级别的参数名取决于所选后端（如 OSQP 用 max_iter，ECOS 用 max_iters）
_SOLVER_DEFAULT_OPTIONS: Dict[str, Dict[str, Any]] = {
    "cvxpy": {
        "solver": None,         # None = CVXPY 自动选择
        "verbose": False,
    },
    # "matlab": {},
}

# 合并后的完整默认值缓存
_DEFAULT_OPTIONS_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_optim_options_from_config() -> Dict[str, Any]:
    """从 QSWebConfig.yaml 读取 portfolio.optim_options 节点"""
    cfg_path = settings.QS_CONFIG_PATH
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("portfolio", {}).get("optim_options", {})
        except Exception:
            pass
    return {}


def _load_default_optim_options(solver: str) -> Dict[str, Any]:
    """加载指定求解器的默认优化选项

    优先级（由低到高）：
    1. 代码级通用默认 (_BASE_OPTIM_OPTIONS)
    2. 代码级求解器默认 (_SOLVER_DEFAULT_OPTIONS[solver])
    3. QSWebConfig.json 的 solver_defaults (跨求解器)
    4. QSWebConfig.json 的 <solver> 节点 (求解器专属)
    """
    cache_key = solver

    # 按优先级逐层合并
    config = _load_optim_options_from_config()
    solver_defaults = config.get("solver_defaults", {})
    solver_config = config.get(solver, {})

    merged = {
        **_BASE_OPTIM_OPTIONS,
        **_SOLVER_DEFAULT_OPTIONS.get(solver, {}),
        **solver_defaults,
        **solver_config,
    }
    _DEFAULT_OPTIONS_CACHE[cache_key] = merged
    return merged


class PortfolioService:
    """组合优化服务"""

    def __init__(self):
        self._solutions: Dict[str, Dict[str, Any]] = {}

    # ─── 核心优化逻辑 ─────────────────────────────────────────

    async def optimize(self, req: OptimizeRequest) -> OptimizeResponse:
        """执行组合优化

        根据请求配置构造 QuantStudio CVXPC 优化器并求解。
        """
        solution_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()

        # 构建 mask / 资产 ID
        asset_ids = req.asset_ids
        cov_matrix = req.cov_matrix

        # 如果指定了风险库引用，从 RiskService 获取协方差矩阵
        if req.risk_db_id and req.risk_table_name and req.risk_dt:
            cov_data = await self._get_cov_from_risk(
                req.risk_db_id, req.risk_table_name, req.risk_dt
            )
            if cov_data:
                asset_ids = cov_data[0]
                cov_matrix = cov_data[1]

        if not asset_ids or not cov_matrix:
            raise ValidationException("需要提供 asset_ids + cov_matrix 或有效的风险库引用")

        n = len(asset_ids)
        cov = np.array(cov_matrix, dtype=float)

        # 构建 mask（因子引用优先，否则全选）
        if req.mask_ref:
            mask_values = await self._resolve_factor_to_array(req.mask_ref, asset_ids)
            mask = ~np.isnan(mask_values) & (mask_values != 0)
        else:
            mask = np.ones(n, dtype=bool)

        # 构建预期收益（因子引用优先）
        if req.expected_return_ref:
            expected_return = await self._resolve_factor_to_array(
                req.expected_return_ref, asset_ids
            )
        elif req.expected_return:
            expected_return = np.array(req.expected_return, dtype=float)
        else:
            expected_return = np.zeros(n, dtype=float)

        # 初始持仓
        p0 = np.array(req.initial_weights, dtype=float) if req.initial_weights else None

        # 基准权重（因子引用优先，归一化）
        if req.benchmark_ref:
            bmk_raw = await self._resolve_factor_to_array(req.benchmark_ref, asset_ids)
            total = np.sum(bmk_raw)
            bmk = bmk_raw / total if total > 0 else np.zeros(n)
        elif req.benchmark_weights:
            bmk = np.array(req.benchmark_weights, dtype=float)
        else:
            bmk = None

        # 合并优化选项：代码默认 < QSWebConfig < 请求覆盖
        merged_options = {**_load_default_optim_options(req.solver), **req.optim_options}

        result = await loop.run_in_executor(
            None,
            self._solve_sync,
            solution_id,
            req.solver,
            mask, expected_return, p0, bmk, cov,
            req.objective, req.constraints,
            req.factor_exposures, req.factor_cov, req.specific_risk,
            merged_options,
        )

        # 缓存结果
        self._solutions[solution_id] = {
            "name": req.name,
            "asset_ids": asset_ids,
            "created_at": dt.datetime.now().isoformat(),
            **result,
        }

        # 计算风险分解
        weights = result.get("weights", [])
        risk_decomp = None
        if weights and cov_matrix:
            risk_decomp = self._compute_risk_decomp(weights, cov_matrix, asset_ids)

        return OptimizeResponse(
            solution_id=solution_id,
            name=req.name,
            status=result["status"],
            message=result.get("message", ""),
            solver_name=result.get("solver_name", ""),
            solve_time=result.get("solve_time", 0.0),
            weights=[float(w) if w is not None else 0.0 for w in weights],
            asset_ids=asset_ids,
            risk_decomposition=risk_decomp,
        )

    # ─── 求解器注册表 ─────────────────────────────────────────

    SOLVER_REGISTRY: Dict[str, dict] = {
        "cvxpy": {
            "label": "CVXPY",
            "desc": "基于 CVXPY 的凸优化求解器，支持 MOSEK/ECOS/SCS 等后端",
            "import_path": "QuantStudio.PortfolioConstructor.CVXPC",
            "class_name": "CVXPC",
        },
        # 未来扩展:
        # "matlab": {
        #     "label": "MATLAB",
        #     "desc": "基于 MATLAB Optimization Toolbox 的求解器",
        #     "import_path": "QuantStudio.PortfolioConstructor.MatlabPC",
        #     "class_name": "MatlabPC",
        # },
    }

    @staticmethod
    def get_default_optim_options(solver: str = "cvxpy") -> Dict[str, Any]:
        """返回指定求解器的默认优化选项"""
        return _load_default_optim_options(solver)

    @classmethod
    def list_solvers(cls) -> List[Dict[str, str]]:
        """返回可用求解器列表"""
        return [
            {"key": k, "label": v["label"], "desc": v["desc"]}
            for k, v in cls.SOLVER_REGISTRY.items()
        ]

    # ─── 因子数据解析 ─────────────────────────────────────────

    async def _resolve_factor_to_array(
        self, ref: FactorDataRef, asset_ids: List[str]
    ) -> np.ndarray:
        """从 FactorDB 读取因子截面数据，按 asset_ids 对齐返回 numpy 数组"""
        from app.services.factor_service import factor_service

        db = await factor_service._get_factor_db(ref.conn_id)
        loop = asyncio.get_running_loop()

        def _read():
            ft = db.getTable(ref.table_name)
            factor = ft.getFactor(ref.factor_name)
            # 确定时点
            if ref.dt:
                dts = [dt.datetime.fromisoformat(ref.dt)]
            else:
                all_dts = ft.getDateTime(ifactor_name=ref.factor_name)
                dts = [all_dts[-1]] if all_dts else []
            if not dts:
                return np.zeros(len(asset_ids))
            # 读取截面数据
            df = factor.readData(ids=asset_ids, dts=dts)
            # df: DataFrame(index=[dt], columns=asset_ids)
            if df.shape[0] > 0:
                values = df.iloc[0].values
            else:
                values = np.zeros(len(asset_ids))
            return np.where(pd.notna(values), values, 0.0).astype(float)

        return await loop.run_in_executor(None, _read)

    def _import_solver_class(self, solver: str):
        """根据求解器标识动态导入 PC 类"""
        info = self.SOLVER_REGISTRY.get(solver)
        if info is None:
            raise ValidationException(
                f"不支持的求解器: {solver}，可用: {', '.join(self.SOLVER_REGISTRY.keys())}"
            )
        import importlib
        mod = importlib.import_module(info["import_path"])
        return getattr(mod, info["class_name"])

    def _solve_sync(
        self,
        solution_id: str,
        solver: str,
        mask: np.ndarray,
        expected_return: np.ndarray,
        p0: Optional[np.ndarray],
        bmk: Optional[np.ndarray],
        cov: np.ndarray,
        objective: ObjectiveConfig,
        constraints: List[dict],
        factor_exposures: Optional[List[List[float]]],
        factor_cov: Optional[List[List[float]]],
        specific_risk: Optional[List[float]],
        optim_options: Dict[str, Any],
    ) -> dict:
        """同步执行组合优化（在 executor 中运行）"""
        from QuantStudio.PortfolioConstructor.BasePC import (
            MeanVarianceObjective,
            RiskBudgetObjective,
            MaxDiversificationObjective,
            BudgetConstraint as QSBudgetConstraint,
            WeightConstraint,
            TurnoverConstraint,
            NonZeroNumConstraint,
        )

        PCClass = self._import_solver_class(solver)

        # 构造约束对象
        qs_constraints = []
        for c in constraints:
            ct = c.get("type", "")
            if ct == "budget":
                qs_constraints.append(QSBudgetConstraint(
                    mask=mask, bmk=bmk,
                    args={"UpLimit": c.get("up_limit", 1.0),
                          "DownLimit": c.get("down_limit", 1.0)},
                ))
            elif ct == "box":
                qs_constraints.append(WeightConstraint(
                    mask=mask, bmk=bmk,
                    up_limit=c.get("ubs", 0.1),
                    down_limit=c.get("lbs", 0.0),
                ))
            elif ct == "turnover":
                qs_constraints.append(TurnoverConstraint(
                    mask=mask, p0=p0,
                    args={"UpLimit": c.get("up_limit", 0.5),
                          "ConstraintType": c.get("constraint_type", "总换手限制")},
                ))
            elif ct == "cardinality":
                qs_constraints.append(NonZeroNumConstraint(
                    mask=mask, bmk=bmk,
                    args={"UpLimit": c.get("max_nonzero", 50)},
                ))

        # 构造目标对象
        if objective.type == "mean_variance":
            qs_obj = MeanVarianceObjective(
                mask=mask,
                expected_return=expected_return,
                p0=p0,
                bmk=bmk,
                cov=cov,
                args={
                    "RiskAversionCoef": objective.risk_aversion,
                    "ExpectedReturnCoef": objective.expected_return_coef,
                },
            )
        elif objective.type == "risk_budget":
            budget = None
            if objective.risk_budget:
                budget_arr = np.array(objective.risk_budget, dtype=float)
                budget_arr = budget_arr / np.sum(budget_arr) if np.sum(budget_arr) > 0 else budget_arr
                budget = budget_arr
            qs_obj = RiskBudgetObjective(
                mask=mask,
                budget=budget,
                cov=cov,
            )
        elif objective.type == "max_diversification":
            qs_obj = MaxDiversificationObjective(
                mask=mask,
                cov=cov,
            )
        else:
            return {"status": "error", "message": f"不支持的目标类型: {objective.type}", "weights": []}

        # 构造优化器并求解
        try:
            pc = PCClass(
                mask=mask, objective=qs_obj, constraints=qs_constraints,
                args={"OptimOption": optim_options},
            )
            weights, info = pc.solve()
        except Exception as e:
            return {"status": "error", "message": str(e), "weights": []}

        if weights is None:
            return {
                "status": "infeasible" if "infeasible" in str(info.get("msg", "")).lower() else "error",
                "message": info.get("msg", "求解失败"),
                "weights": [],
                "solver_name": info.get("solver_name", ""),
                "solve_time": info.get("solve_time", 0.0),
            }

        status_map = {1: "optimal", 0: "infeasible"}
        return {
            "status": status_map.get(info.get("status", 0), "error"),
            "message": str(info.get("msg", "")),
            "weights": [float(w) if not np.isnan(w) else 0.0 for w in weights],
            "solver_name": info.get("solver_name", ""),
            "solve_time": info.get("solve_time", 0.0),
        }

    # ─── 风险分解 ─────────────────────────────────────────────

    def _compute_risk_decomp(
        self, weights: List[float], cov_matrix: List[List[float]], asset_ids: List[str]
    ) -> Dict[str, Any]:
        """计算组合风险分解"""
        w = np.array(weights, dtype=float)
        cov = np.array(cov_matrix, dtype=float)
        portfolio_var = float(np.dot(np.dot(w, cov), w))
        portfolio_vol = float(np.sqrt(max(portfolio_var, 0)))

        # 边际风险贡献
        mcr = np.dot(cov, w)  # marginal contribution to risk
        # 风险贡献 = w_i * MCR_i
        rcr = w * mcr
        # 归一化为百分比
        total_risk = np.sum(rcr)
        if total_risk > 1e-15:
            rcr_pct = [float(x / total_risk * 100) for x in rcr]
        else:
            rcr_pct = [0.0] * len(w)

        # Top-N 风险贡献
        contributions = sorted(
            zip(asset_ids, rcr_pct, w),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:20]

        return {
            "portfolio_volatility": round(portfolio_vol, 6),
            "portfolio_variance": round(portfolio_var, 10),
            "risk_contributions": [
                {"asset": aid, "pct": round(pct, 2), "weight": round(float(wt), 6)}
                for aid, pct, wt in contributions
            ],
        }

    # ─── 从风险服务获取协方差 ─────────────────────────────────

    async def _get_cov_from_risk(
        self, db_id: str, table_name: str, dt_str: str
    ) -> Optional[Tuple[List[str], List[List[float]]]]:
        """从 RiskService 获取协方差矩阵"""
        try:
            from app.services.risk_service import risk_service
            cov_data = await risk_service.get_covariance(
                db_id, table_name, dt_str, limit=500
            )
            ids = cov_data.get("ids", [])
            data = cov_data.get("data", [])
            if not ids or not data:
                return None

            # 将 [i, j, val] 三元组转换为稠密矩阵
            n = len(ids)
            mat = np.zeros((n, n), dtype=float)
            for i, j, val in data:
                if i < n and j < n:
                    mat[i, j] = val

            return ids, mat.tolist()
        except Exception:
            return None

    # ─── 结果查询 ─────────────────────────────────────────────

    def get_solution(self, solution_id: str) -> OptimizeResponse:
        """获取求解结果"""
        sol = self._solutions.get(solution_id)
        if sol is None:
            raise NotFoundException("求解结果", solution_id)

        weights = sol.get("weights", [])
        asset_ids = sol.get("asset_ids", [])
        risk_decomp = self._compute_risk_decomp(weights, sol.get("cov", []), asset_ids) if sol.get("cov") else None

        return OptimizeResponse(
            solution_id=solution_id,
            name=sol.get("name", ""),
            status=sol.get("status", "error"),
            message=sol.get("message", ""),
            solver_name=sol.get("solver_name", ""),
            solve_time=sol.get("solve_time", 0.0),
            weights=weights,
            asset_ids=asset_ids,
            risk_decomposition=risk_decomp,
        )

    def get_solution_info(self, solution_id: str) -> SolutionInfo:
        """获取求解结果信息"""
        sol = self._solutions.get(solution_id)
        if sol is None:
            raise NotFoundException("求解结果", solution_id)

        weights = sol.get("weights", [])
        nonzero = sum(1 for w in weights if abs(w) > 1e-8)
        return SolutionInfo(
            solution_id=solution_id,
            name=sol.get("name", ""),
            status=sol.get("status", "error"),
            message=sol.get("message", ""),
            solver_name=sol.get("solver_name", ""),
            solve_time=sol.get("solve_time", 0.0),
            asset_count=len(weights),
            nonzero_count=nonzero,
            created_at=sol.get("created_at", ""),
        )

    def export_weights_csv(self, solution_id: str) -> str:
        """导出权重为 CSV 字符串"""
        sol = self._solutions.get(solution_id)
        if sol is None:
            raise NotFoundException("求解结果", solution_id)

        asset_ids = sol.get("asset_ids", [])
        weights = sol.get("weights", [])
        if not asset_ids or not weights:
            raise ValidationException("该求解结果无权重数据")

        lines = ["资产ID,权重"]
        for aid, w in zip(asset_ids, weights):
            lines.append(f"{aid},{w:.8f}")
        return "\n".join(lines)

    # ─── 任务保存/加载 ─────────────────────────────────────────

    def _load_saved_tasks(self) -> Dict[str, dict]:
        """从 QSWebConfig.yaml 读取已保存的任务"""
        cfg_path = settings.QS_CONFIG_PATH
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                return cfg.get("portfolio", {}).get("saved_tasks", {})
            except Exception:
                pass
        return {}

    def _save_tasks_to_config(self, tasks: Dict[str, dict]):
        """将任务列表持久化到 QSWebConfig.yaml"""
        cfg_path = settings.QS_CONFIG_PATH
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = _ruamel.load(f)
        else:
            cfg = _ruamel.load("{}")
        cfg.setdefault("portfolio", {})["saved_tasks"] = tasks
        Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            _ruamel.dump(cfg, f)

    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有已保存的任务配置"""
        tasks = self._load_saved_tasks()
        result = []
        for tid, t in tasks.items():
            result.append({
                "id": tid,
                "name": t.get("name", ""),
                "created_at": t.get("created_at", ""),
                "updated_at": t.get("updated_at", ""),
            })
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result

    def get_task(self, task_id: str) -> dict:
        """获取单个已保存任务的完整配置"""
        tasks = self._load_saved_tasks()
        t = tasks.get(task_id)
        if t is None:
            raise NotFoundException("保存的任务", task_id)
        return t

    def save_task(self, name: str, config: dict) -> dict:
        """保存优化任务配置（新建或覆盖同名任务）"""
        import uuid as _uuid
        tasks = self._load_saved_tasks()
        now = dt.datetime.now().isoformat()

        # 检查是否已存在同名任务（更新）
        existing_id = None
        for tid, t in tasks.items():
            if t.get("name") == name:
                existing_id = tid
                break

        if existing_id:
            task_id = existing_id
            tasks[task_id] = {
                "name": name,
                "config": config,
                "created_at": tasks[task_id].get("created_at", now),
                "updated_at": now,
            }
        else:
            task_id = _uuid.uuid4().hex[:8]
            tasks[task_id] = {
                "name": name,
                "config": config,
                "created_at": now,
                "updated_at": now,
            }

        self._save_tasks_to_config(tasks)
        return {"id": task_id, "name": name, "message": "保存成功"}

    def delete_task(self, task_id: str):
        """删除已保存的任务"""
        tasks = self._load_saved_tasks()
        if task_id not in tasks:
            raise NotFoundException("保存的任务", task_id)
        del tasks[task_id]
        self._save_tasks_to_config(tasks)


# 全局实例
portfolio_service = PortfolioService()

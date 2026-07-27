"""
回测 API

提供截面因子测试（IC 分析、分位数组合、换手率）和策略回测的 REST 接口。
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Query

from app.models.backtest import (
    ICAnalysisRequest,
    QuantilePortfolioRequest,
    TurnoverRequest,
    StrategyBacktestRequest,
    BacktestRegisterRequest,
)
from app.services.backtest_service import backtest_service
from app.tasks.manager import task_manager
from app.core.exceptions import ValidationException, NotFoundException

router = APIRouter()


# ─── IC 分析 ─────────────────────────────────────────────

@router.post("/ic-analysis")
async def run_ic_analysis(req: ICAnalysisRequest) -> Dict[str, Any]:
    """运行截面因子 IC 分析"""
    try:
        return await backtest_service.run_ic_analysis(req)
    except ValueError as e:
        raise ValidationException(str(e))
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ─── 分位数组合 ──────────────────────────────────────────

@router.post("/quantile-portfolio")
async def run_quantile_portfolio(req: QuantilePortfolioRequest) -> Dict[str, Any]:
    """运行分位数组合分析"""
    try:
        return await backtest_service.run_quantile_portfolio(req)
    except ValueError as e:
        raise ValidationException(str(e))
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ─── 换手率 ──────────────────────────────────────────────

@router.post("/turnover")
async def run_turnover(req: TurnoverRequest) -> Dict[str, Any]:
    """运行因子换手率分析"""
    try:
        return await backtest_service.run_turnover(req)
    except ValueError as e:
        raise ValidationException(str(e))
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ─── 策略回测 ────────────────────────────────────────────

@router.post("/strategy/run")
async def submit_strategy_backtest(req: StrategyBacktestRequest) -> Dict[str, str]:
    """提交策略回测异步任务，返回任务 ID"""
    try:
        task_id = await backtest_service.submit_strategy_backtest(req)
        return {"task_id": task_id, "message": "回测任务已提交"}
    except ValueError as e:
        raise ValidationException(str(e))
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ─── 回测结果 ────────────────────────────────────────────

@router.get("/tasks/{task_id}/result")
async def get_backtest_result(task_id: str) -> Dict[str, Any]:
    """获取异步回测任务的结果"""
    task = task_manager.get_task(task_id)
    if task is None:
        raise NotFoundException("任务", task_id)

    response = task.to_dict()
    if task.status.value == "completed":
        response["result"] = task.result
    elif task.status.value == "failed":
        response["error"] = task.error

    return response


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """获取任务状态"""
    task = task_manager.get_task(task_id)
    if task is None:
        raise NotFoundException("任务", task_id)
    return task.to_dict()


# ─── 回测历史 ────────────────────────────────────────────

@router.get("/history")
async def get_backtest_history(
    factor_name: Optional[str] = Query(None, description="因子名称筛选"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
) -> Dict[str, Any]:
    """获取回测历史列表"""
    results = backtest_service.get_history(factor_name=factor_name, limit=limit)
    return {"total": len(results), "items": results}


# ─── 回测注册 ────────────────────────────────────────────

@router.post("/{task_id}/register")
async def register_backtest(task_id: str, req: BacktestRegisterRequest = BacktestRegisterRequest()) -> Dict[str, Any]:
    """注册回测到 QSRegistry"""
    try:
        return await backtest_service.register_backtest(
            task_id=task_id,
            name=req.name,
            category=req.category,
        )
    except ValueError as e:
        raise ValidationException(str(e))
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")

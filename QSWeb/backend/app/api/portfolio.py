"""
组合优化 API 路由
"""

from typing import Dict, Any

from fastapi import APIRouter, Query, Body
from fastapi.responses import PlainTextResponse

from app.services.portfolio_service import portfolio_service
from app.models.portfolio import OptimizeRequest

router = APIRouter()


@router.get("/optim-options")
async def get_default_optim_options(
    solver: str = Query("cvxpy", description="求解器标识"),
):
    """获取指定求解器的默认优化选项（已合并 QSWebConfig.json 中的设置）"""
    return portfolio_service.get_default_optim_options(solver)


@router.get("/solvers")
async def list_solvers():
    """列出可用的组合优化求解器"""
    return portfolio_service.list_solvers()


@router.post("/optimize")
async def optimize(req: OptimizeRequest):
    """提交组合优化求解

    支持均值方差、风险预算、最大分散化三种目标，
    以及 Box、行业暴露、换手率、基数等多种约束。
    """
    return await portfolio_service.optimize(req)


@router.get("/solutions/{solution_id}")
async def get_solution(solution_id: str):
    """获取求解结果（含权重向量和风险分解）"""
    return portfolio_service.get_solution(solution_id)


@router.get("/solutions/{solution_id}/info")
async def get_solution_info(solution_id: str):
    """获取求解结果摘要信息"""
    return portfolio_service.get_solution_info(solution_id)


@router.get("/solutions/{solution_id}/weights")
async def export_weights(solution_id: str):
    """导出权重为 CSV 格式"""
    csv_content = portfolio_service.export_weights_csv(solution_id)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=weights_{solution_id}.csv"},
    )


# ─── 任务保存/加载 ───────────────────────────────────────────

@router.get("/tasks")
async def list_tasks():
    """列出所有已保存的优化任务配置"""
    return portfolio_service.list_tasks()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取已保存任务的完整配置"""
    return portfolio_service.get_task(task_id)


@router.post("/tasks")
async def save_task(
    name: str = Body(..., description="任务名称"),
    config: Dict[str, Any] = Body(..., description="完整优化配置"),
):
    """保存优化任务配置（同名任务会覆盖）"""
    return portfolio_service.save_task(name, config)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除已保存的任务"""
    portfolio_service.delete_task(task_id)
    return {"message": "删除成功"}

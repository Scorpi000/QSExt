"""
因子挖掘 API 路由
"""

import asyncio
import os

from fastapi import APIRouter, Form, HTTPException

from app.models.mining import (
    ContinueRunRequest,
    CreateTaskRequest,
    ExportRequest,
    RunResult,
    RunSummary,
    SubmitRunRequest,
)
from app.services.mining_service import mining_service

router = APIRouter()


# ─── 框架 ─────────────────────────────────────────────────────

@router.get("/frameworks")
async def list_frameworks():
    """列出可用挖掘框架"""
    return [f.model_dump() for f in mining_service.list_frameworks()]


@router.get("/frameworks/{name}/config")
async def get_framework_config(name: str):
    """获取框架配置模板"""
    try:
        return mining_service.get_framework_config(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/import-factors")
async def import_factors_from_script(
    script_path: str = Form(..., description="因子定义脚本路径 (.py)"),
):
    """从因子定义脚本导入终端因子

    通过全局 FactorDefContext 执行脚本的 defFactor(fdi)，
    展开所有因子提取叶节点 DataFactor，返回去重后的终端因子列表。
    """
    from app.services.factor_def_context import factor_def_context

    if not factor_def_context.is_available:
        raise HTTPException(
            status_code=503,
            detail="FactorDef 上下文不可用，请配置 QSWebConfig.yaml 中 factor_def.settings_path",
        )

    try:
        terminals = await asyncio.to_thread(
            factor_def_context.get_script_terminals, script_path
        )
        return {
            "script": os.path.basename(script_path),
            "terminal_count": len(terminals),
            "terminals": terminals,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 任务 ─────────────────────────────────────────────────────

@router.post("/tasks")
async def create_task(req: CreateTaskRequest):
    """创建挖掘任务"""
    task = mining_service.create_task(req)
    return task.model_dump()


@router.get("/tasks")
async def list_tasks():
    """列出所有挖掘任务"""
    return [t.model_dump() for t in mining_service.list_tasks()]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    task = mining_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task.model_dump()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    task = mining_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    mining_service.delete_task(task_id)
    return {"message": "删除成功"}


# ─── 运行 ─────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/run")
async def submit_run(task_id: str, req: SubmitRunRequest):
    """提交初始挖掘运行"""
    task = mining_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    try:
        run_id = await mining_service.submit_run(task_id, req)
        return {"run_id": run_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tasks/{task_id}/continue")
async def submit_continue(task_id: str, req: ContinueRunRequest):
    """提交接续挖掘运行"""
    task = mining_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    try:
        run_id = await mining_service.submit_continue(task_id, req)
        return {"run_id": run_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 结果 ─────────────────────────────────────────────────────

@router.get("/tasks/{task_id}/runs/{run_id}/result")
async def get_run_result(task_id: str, run_id: str):
    """获取指定运行的结果"""
    result = mining_service.get_run_result(task_id, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在或任务尚未完成")
    return result.model_dump()


@router.get("/tasks/{task_id}/factor-tree/{index}")
async def get_factor_tree(task_id: str, index: int):
    """获取因子树 DAG 数据"""
    dag = mining_service.get_factor_tree(task_id, index)
    if dag is None:
        raise HTTPException(status_code=404, detail="因子树数据不可用")
    return dag.model_dump()


# ─── 导出 ─────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/export")
async def export_factor(task_id: str, req: ExportRequest = None):
    """将挖掘产出的因子导出到目标目录"""
    if req is None:
        req = ExportRequest()
    task = mining_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    try:
        dst = mining_service.export_factor(task_id, req)
        return {"message": "导出成功", "path": dst}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

"""
报告中心 API 路由
"""

from typing import Optional

from fastapi import APIRouter, Query, Body, HTTPException

from app.models.report import (
    ReportGenerateRequest,
    ReportRegisterRequest,
)
from app.services.report_service import report_service

router = APIRouter()


# ─── 报告生成 ─────────────────────────────────────────────────

@router.get("/scenarios")
async def list_scenarios():
    """列出可用的报告场景"""
    return report_service.list_scenarios()


@router.post("/generate")
async def generate_report(req: ReportGenerateRequest):
    """提交报告生成任务（异步执行）

    支持单因子分析场景，可配置 IC、IC 衰减、分位数组合、换手率等模块。
    通过 WebSocket 推送生成进度。
    """
    task_id = await report_service.generate(req)
    return {"task_id": task_id}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取报告生成任务的状态"""
    from app.tasks.manager import task_manager
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task.to_dict()


@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    """获取报告生成任务的结果"""
    from app.tasks.manager import task_manager
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    if task.status.value == "pending":
        raise HTTPException(status_code=202, detail="任务尚未开始")
    elif task.status.value == "running":
        raise HTTPException(status_code=202, detail="任务正在运行中")
    elif task.status.value == "failed":
        raise HTTPException(status_code=500, detail=f"任务执行失败: {task.error}")

    return task.result


# ─── 配置 ─────────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    """获取报告中心配置"""
    from app.services.report_service import get_report_dir
    return {"output_dir": get_report_dir()}


@router.put("/config")
async def update_config(
    output_dir: str = Body(..., embed=True, description="报告输出目录"),
):
    """更新报告中心配置"""
    from app.services.report_service import set_report_dir, get_report_dir
    set_report_dir(output_dir)
    return {"output_dir": get_report_dir(), "message": "保存成功"}


# ─── 报告列表 ─────────────────────────────────────────────────

@router.get("")
async def list_reports(
    scenario: Optional[str] = Query(None, description="场景筛选"),
    factor_name: Optional[str] = Query(None, description="因子名筛选"),
):
    """列出已生成的报告，支持按场景和因子名筛选"""
    return [
        r.model_dump()
        for r in report_service.list_reports(scenario=scenario, factor_name=factor_name)
    ]


@router.get("/{report_id}")
async def get_report(report_id: str):
    """获取报告元信息"""
    info = report_service.get_report(report_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    return info.model_dump()


@router.get("/{report_id}/content")
async def get_report_content(
    report_id: str,
    fmt: str = Query("html", description="报告格式 (html | markdown)"),
):
    """获取报告内容。返回 {factor_name: content, ...}"""
    content = report_service.get_report_content(report_id, fmt)
    if content is None:
        raise HTTPException(status_code=404, detail=f"报告内容不存在: {report_id}")
    return content


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """删除报告"""
    info = report_service.get_report(report_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    report_service.delete_report(report_id)
    return {"message": "删除成功"}


# ─── 报告注册 ─────────────────────────────────────────────────

@router.post("/{report_id}/register")
async def register_report(report_id: str, req: ReportRegisterRequest):
    """将报告注册到 QSRegistry（写入 Neo4j 图数据库）"""
    try:
        result = report_service.register_report(
            report_id,
            factor_qsids=req.factor_qsids,
            bt_qsid=req.bt_qsid,
        )
        return {"message": "注册成功", "report_ids": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

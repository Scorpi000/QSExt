"""
回测工作台 API 路由
"""

from typing import List

from fastapi import APIRouter, HTTPException

from app.models.backtest import (
    ModuleInfo,
    ModuleRunConfig,
    BacktestRunRequest,
    ResultNode,
    BACKTEST_MODULE_REGISTRY,
)
from app.services.factor_service import factor_service
from app.services.qs_bridge import QSBridge, _load_backtest_config
from app.tasks.manager import task_manager

router = APIRouter()

# QSBridge 实例（暂不接入 RegistryService）
qs_bridge = QSBridge(factor_service=factor_service, registry_service=None)


def _module_def_to_info(key: str, mod_def: dict) -> ModuleInfo:
    """将模块注册表条目转换为 ModuleInfo Pydantic 模型"""
    from app.models.backtest import ParamDef
    params = [ParamDef(**p) for p in mod_def.get("params", [])]
    return ModuleInfo(
        key=mod_def["key"],
        name=mod_def["name"],
        category=mod_def["category"],
        description=mod_def.get("description", ""),
        params=params,
        requires_price=mod_def.get("requires_price", False),
        requires_descriptor_ids=mod_def.get("requires_descriptor_ids", True),
    )


# ─── 配置信息 ─────────────────────────────────────────────────

@router.get("/config")
async def get_backtest_config():
    """返回回测相关配置信息（供前端判断功能可用性）"""
    cfg = _load_backtest_config()
    tds = cfg.get("trading_day_source")
    trading_day_available = bool(tds and tds.get("name"))
    section_id_sources = list(cfg.get("section_id_sources", {}).keys())
    return {
        "trading_day_available": trading_day_available,
        "section_id_sources": section_id_sources,
    }


@router.get("/section-id-sources")
async def get_section_id_sources():
    """返回已配置的截面 ID 源列表"""
    cfg = _load_backtest_config()
    sources = cfg.get("section_id_sources", {})
    return [
        {"name": name, "method": info.get("method", "")}
        for name, info in sources.items()
    ]


# ─── 模块列表 ─────────────────────────────────────────────────

@router.get("/modules", response_model=List[ModuleInfo])
async def list_modules():
    """获取所有已注册的回测模块元信息"""
    return [
        _module_def_to_info(key, mod_def)
        for key, mod_def in BACKTEST_MODULE_REGISTRY.items()
    ]


@router.get("/modules/{module_key}", response_model=ModuleInfo)
async def get_module(module_key: str):
    """获取指定模块的详细信息"""
    mod_def = BACKTEST_MODULE_REGISTRY.get(module_key)
    if mod_def is None:
        raise HTTPException(status_code=404, detail=f"未知的回测模块: {module_key}")
    return _module_def_to_info(module_key, mod_def)


# ─── 回测运行 ─────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(request: BacktestRunRequest):
    """提交回测任务（异步执行）"""
    # 验证模块引用
    for cfg in request.module_configs:
        if cfg.module_key not in BACKTEST_MODULE_REGISTRY:
            raise HTTPException(
                status_code=400,
                detail=f"未知的回测模块: {cfg.module_key}",
            )

    async def _run():
        await task_manager.update_progress(task_id, 5, "正在解析因子...")

        result = await qs_bridge.run_backtest(
            module_configs=request.module_configs,
            start_date=request.start_date,
            end_date=request.end_date,
            dt_mode=request.dt_mode,
            rebalance_dts=request.rebalance_dts,
        )

        await task_manager.update_progress(task_id, 90, "正在转换结果...")
        return result.model_dump()

    task_id = await task_manager.submit(
        name=f"回测运行 ({len(request.module_configs)} 个模块)",
        coro_or_func=_run(),
    )

    await task_manager.update_progress(task_id, 0, "任务已提交")
    return {"task_id": task_id}


@router.get("/tasks/{task_id}/result", response_model=ResultNode)
async def get_task_result(task_id: str):
    """获取回测任务的结果"""
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    if task.status.value == "pending":
        raise HTTPException(status_code=202, detail="任务尚未开始")
    elif task.status.value == "running":
        raise HTTPException(status_code=202, detail="任务正在运行中")
    elif task.status.value == "failed":
        raise HTTPException(status_code=500, detail=f"任务执行失败: {task.error}")

    # 从 task.result（dict）重新构造 ResultNode
    return ResultNode(**task.result)

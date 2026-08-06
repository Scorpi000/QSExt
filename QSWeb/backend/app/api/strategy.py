"""
策略工作台 API 路由
"""
import os
import re
import json
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.models.strategy import (
    StrategyMetaModel,
    StrategySearchResult,
    StrategyImportRequest,
    StrategyImportPreviewResponse,
    StrategyBacktestRequest,
    StrategyBacktestResult,
    StrategyDeleteResponse,
    AvailableFactor,
)
from app.services.strategy_service import strategy_service
from app.services.factor_service import factor_service
from app.services.qs_bridge import QSBridge
from app.tasks.manager import task_manager
from app.core.config import settings as app_settings

router = APIRouter()

# QSBridge 实例
qs_bridge = QSBridge(factor_service=factor_service, registry_service=None)


# ─── 导入/预览 ─────────────────────────────────────────────────

@router.post("/import/preview", response_model=StrategyImportPreviewResponse)
async def preview_import(request: StrategyImportRequest):
    """预览策略元信息（仅验证，不保存）"""
    return strategy_service.validate_code(request.code)


@router.post("/import")
async def import_strategy(request: StrategyImportRequest):
    """导入策略：验证 → 保存文件 → 后台注册到 Neo4j"""
    # 1. 验证
    preview = strategy_service.validate_code(request.code)
    if not preview.valid:
        raise HTTPException(status_code=400, detail={"errors": preview.errors})

    # 2. 保存文件
    filepath = strategy_service.save_strategy_file(
        request.code, filename=request.filename
    )

    # 3. 后台注册到 Neo4j（异步）
    strategy_settings_path = app_settings.strategy_def.get("settings_path")
    if not strategy_settings_path:
        raise HTTPException(
            status_code=400,
            detail="未配置 strategy_def.settings_path，请在 QSWebConfig.yaml 中设置",
        )

    async def _register():
        try:
            import sys
            from QSExt.StrategyDef.scripts.register_strategies_to_graphdb import (
                main as register_main,
                _build_profiles_from_modules,
            )

            # 加载已保存的策略模块
            modname = os.path.splitext(os.path.basename(filepath))[0]

            # 将脚本所在目录临时加入 sys.path，使模块可被 importlib 导入
            script_dir = os.path.dirname(os.path.abspath(filepath))
            in_sys_path = script_dir in sys.path
            if not in_sys_path:
                sys.path.insert(0, script_dir)

            try:
                register_main(
                    settings_path=strategy_settings_path,
                    id_profiles=_build_profiles_from_modules(
                        [modname],
                        default_id_type=app_settings.strategy_def.get("default_id_type", "A股"),
                    ),
                    skip_embedding=True,
                )
            finally:
                if not in_sys_path:
                    sys.path.remove(script_dir)
        except Exception as e:
            from QuantStudio.Core import __QS_Logger__ as Logger
            Logger.warning(f"后台 Neo4j 注册失败: {e}")

    task_id = await task_manager.submit(
        name=f"注册策略: {preview.meta.Name if preview.meta else filepath}",
        coro_or_func=_register(),
    )

    return {
        "valid": True,
        "meta": preview.meta.model_dump() if preview.meta else None,
        "filepath": filepath,
        "register_task_id": task_id,
    }


# ─── 搜索 ───────────────────────────────────────────────────────

@router.get("/search", response_model=List[StrategySearchResult])
async def search_strategies(
    q: Optional[str] = Query(default=None, description="搜索关键词"),
    tag: Optional[str] = Query(default=None, description="按标签过滤"),
    factor_qsid: Optional[str] = Query(default=None, description="按依赖因子过滤"),
    limit: int = Query(default=100, description="返回数量上限"),
):
    """搜索策略列表"""
    import asyncio
    loop = asyncio.get_running_loop()

    def _sync():
        neo4j_cfg_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
        if not os.path.exists(neo4j_cfg_path):
            return []

        with open(neo4j_cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        neo4j_args = {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }

        from QSExt.QSRegistry.api import QSGraphDB
        gdb = QSGraphDB(args=neo4j_args)
        try:
            gdb.connect()

            if q and not tag and not factor_qsid:
                # 尝试语义搜索
                semantic = gdb.searchStrategiesByDescription(q, limit=limit)
                if semantic:
                    return [
                        StrategySearchResult(
                            QSID=r.get("QSID", ""),
                            Name=r.get("Name", ""),
                            TargetTable=r.get("TargetTable", ""),
                            IDType=r.get("IDType", ""),
                            Description=r.get("Description", r.get("MetaJSON", "{}")),
                            Tags=r.get("Tags", []),
                            DefScriptPath=r.get("DefScriptPath", ""),
                            UpdatedAt=r.get("UpdatedAt"),
                            Similarity=r.get("Similarity"),
                        )
                        for r in semantic
                    ]

            results = gdb.searchStrategies(
                name=q, tag=tag, factor_qsid=factor_qsid, limit=limit,
            )
            return [
                StrategySearchResult(
                    QSID=r.get("QSID", ""),
                    Name=r.get("Name", ""),
                    TargetTable=r.get("TargetTable", ""),
                    IDType=r.get("IDType", ""),
                    Description=r.get("Description", ""),
                    Tags=r.get("Tags", []),
                    DefScriptPath=r.get("DefScriptPath", ""),
                    UpdatedAt=r.get("UpdatedAt"),
                )
                for r in results
            ]
        finally:
            gdb.disconnect()

    return await loop.run_in_executor(None, _sync)


# ─── 策略模板 ───────────────────────────────────────────────────

@router.get("/template")
async def get_strategy_template():
    """获取新建策略的初始模板"""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "templates", "strategy_template.py",
    )
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="策略模板文件不存在")
    with open(template_path, "r", encoding="utf-8") as f:
        return {"code": f.read()}


# ─── 详情 ───────────────────────────────────────────────────────

@router.get("/{qsid}")
async def get_strategy_detail(qsid: str):
    """获取策略详情"""
    import asyncio
    loop = asyncio.get_running_loop()

    def _sync():
        neo4j_cfg_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
        if not os.path.exists(neo4j_cfg_path):
            return None

        with open(neo4j_cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        neo4j_args = {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }

        from QSExt.QSRegistry.api import QSGraphDB
        gdb = QSGraphDB(args=neo4j_args)
        try:
            gdb.connect()
            return gdb.getStrategyByQSID(qsid)
        finally:
            gdb.disconnect()

    result = await loop.run_in_executor(None, _sync)
    if result is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {qsid}")
    return result


@router.get("/{qsid}/code")
async def get_strategy_code(qsid: str):
    """获取策略源代码"""
    import asyncio
    loop = asyncio.get_running_loop()

    def _sync():
        neo4j_cfg_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
        if not os.path.exists(neo4j_cfg_path):
            return None

        with open(neo4j_cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        neo4j_args = {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }

        from QSExt.QSRegistry.api import QSGraphDB
        gdb = QSGraphDB(args=neo4j_args)
        try:
            gdb.connect()
            return gdb.getStrategyCode(qsid)
        finally:
            gdb.disconnect()

    result = await loop.run_in_executor(None, _sync)
    if result is None:
        raise HTTPException(status_code=404, detail=f"策略代码不存在: {qsid}")
    return {"qsid": qsid, "code": result}


# ─── 删除 ───────────────────────────────────────────────────────

@router.delete("/{qsid}", response_model=StrategyDeleteResponse)
async def delete_strategy(
    qsid: str,
    keep_file: bool = Query(default=True, description="是否保留 .py 文件"),
):
    """删除策略"""
    import asyncio
    loop = asyncio.get_running_loop()

    def _sync():
        neo4j_cfg_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
        if not os.path.exists(neo4j_cfg_path):
            return None

        with open(neo4j_cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r",\s*([}\]])", r"\1", content)
        neo4j_cfg = json.loads(content)
        neo4j_args = {
            "IPAddr": neo4j_cfg["IPAddr"],
            "Port": neo4j_cfg["Port"],
            "User": neo4j_cfg["User"],
            "Pwd": neo4j_cfg["Pwd"],
            "DBName": neo4j_cfg.get("DBName", "neo4j"),
        }

        from QSExt.QSRegistry.api import QSGraphDB
        gdb = QSGraphDB(args=neo4j_args)
        try:
            gdb.connect()
            # 先获取 DefScriptPath
            info = gdb.getStrategyByQSID(qsid)
            file_deleted = False
            if info and info.get("DefScriptPath") and not keep_file:
                script_path = info["DefScriptPath"]
                if os.path.isfile(script_path):
                    os.remove(script_path)
                    file_deleted = True

            deleted = gdb.deleteStrategy(qsid)
            return deleted, file_deleted
        finally:
            gdb.disconnect()

    result = await loop.run_in_executor(None, _sync)
    if result is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {qsid}")

    deleted, file_deleted = result
    return StrategyDeleteResponse(qsid=qsid, deleted=deleted, file_deleted=file_deleted)


# ─── 回测 ───────────────────────────────────────────────────────

@router.post("/backtest", response_model=StrategyBacktestResult)
async def run_strategy_backtest(request: StrategyBacktestRequest):
    """提交策略回测（异步 task）"""
    if not request.code and not request.strategy_qsid:
        raise HTTPException(
            status_code=400, detail="必须提供 code 或 strategy_qsid"
        )

    async def _run():
        await task_manager.update_progress(task_id, 5, "正在加载策略代码...")

        # 加载策略代码
        if request.strategy_qsid:
            code = await strategy_service._load_strategy_from_graph(request.strategy_qsid)
            if code is None:
                raise ValueError(f"找不到策略: {request.strategy_qsid}")
        else:
            code = request.code

        await task_manager.update_progress(task_id, 20, "正在解析因子依赖...")
        await task_manager.update_progress(task_id, 40, "正在执行策略回测...")

        result = await qs_bridge.run_strategy_backtest(
            code=code,
            factor_refs=request.factor_refs,
            model_args=request.model_args,
            operator_config=request.operator_config,
            start_date=request.start_date,
            end_date=request.end_date,
            dt_mode=request.dt_mode,
            descriptor_ids=request.descriptor_ids,
        )

        await task_manager.update_progress(task_id, 90, "正在转换结果...")
        return result.model_dump() if hasattr(result, 'model_dump') else result

    task_id = await task_manager.submit(
        name=f"策略回测",
        coro_or_func=_run(),
    )

    return StrategyBacktestResult(task_id=task_id)


@router.get("/backtest/{task_id}/result")
async def get_backtest_result(task_id: str):
    """获取回测任务结果"""
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


# ─── 可用因子 ───────────────────────────────────────────────────

@router.get("/factors/available", response_model=List[AvailableFactor])
async def get_available_factors():
    """获取可选因子列表（合并 FactorDB + QSRegistry）"""
    factors = []

    # 从 FactorService 获取已连接的因子库中的因子
    try:
        for conn_id, db in factor_service._connections.items():
            try:
                tables = db.TableNames
                for table_name in tables:
                    try:
                        ft = db.getTable(table_name)
                        for factor_name in ft.FactorNames:
                            factors.append(AvailableFactor(
                                name=factor_name,
                                source="db",
                                conn_id=conn_id,
                                table_name=table_name,
                            ))
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    return factors

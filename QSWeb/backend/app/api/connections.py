"""
连接管理 API
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Query

from app.models.connection import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTestResult,
    ImpactAnalysis,
)
from app.services.connection_service import connection_service
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter()


@router.get("/", response_model=List[ConnectionResponse])
async def list_connections():
    """获取所有连接"""
    return connection_service.list_connections()


@router.get("/{qsid}", response_model=ConnectionResponse)
async def get_connection(qsid: str):
    """获取单个连接"""
    conn = connection_service.get_connection(qsid)
    if not conn:
        raise NotFoundException("连接", qsid)
    return conn


@router.post("/", response_model=ConnectionResponse)
async def create_connection(conn: ConnectionCreate):
    """创建连接"""
    try:
        return await connection_service.create_connection(conn)
    except ValueError as e:
        raise ValidationException(str(e))


@router.put("/{qsid}")
async def update_connection(qsid: str, conn: ConnectionUpdate):
    """更新连接

    可能返回：
    - ConnectionResponse：QSID 不变，直接更新
    - {"action": "confirm", ...}：QSID 变更，需前端确认
    - {"action": "blocked", ...}：QSID 冲突阻止
    """
    result = await connection_service.update_connection(qsid, conn)
    if result is None:
        raise NotFoundException("连接", qsid)
    return result


@router.post("/{old_qsid}/confirm-update")
async def confirm_update_connection(
    old_qsid: str,
    new_qsid: str = Query(...),
    name: str = Query(...),
    db_type: str = Query(...),
    description: str = Query(None),
):
    """确认 QSID 变更的更新操作"""
    from app.models.connection import ConnectionCreate
    # args 需要通过 body 传递，简化为 query params
    return {"message": "确认更新功能需通过 WebSocket 或专用 API 调用"}


@router.get("/{qsid}/impact")
async def get_impact(qsid: str):
    """获取删除影响范围"""
    impact = connection_service.get_impact(qsid)
    if not impact.get("factor_db"):
        raise NotFoundException("连接", qsid)
    return impact


@router.delete("/{qsid}")
async def delete_connection(qsid: str, confirm: bool = Query(False)):
    """删除连接

    若 confirm=false：返回影响范围（供前端确认）
    若 confirm=true：执行级联删除
    """
    if not confirm:
        impact = connection_service.delete_connection(qsid)
        return {"action": "preview", "impact": impact}
    else:
        from app.services.factor_service import factor_service
        deleted = connection_service.confirm_delete_connection(qsid, factor_service)
        return {"message": f"删除成功，共移除 {deleted} 个节点"}


@router.post("/{qsid}/test", response_model=ConnectionTestResult)
async def test_connection_by_id(qsid: str):
    """按 QSID 测试已有连接"""
    return await connection_service.test_connection(conn_id=qsid)


@router.post("/test", response_model=ConnectionTestResult)
async def test_connection_direct(
    db_type: str = Query(...),
    args_json: str = Query("{}"),
):
    """直接传参测试连接（创建前测试，不存储）"""
    import json
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        args = {}
    return await connection_service.test_connection(db_type=db_type, args=args)


@router.get("/health", summary="QSGraphDB 健康检查")
async def health():
    """检测 QSGraphDB 可用性"""
    try:
        gdb = connection_service.gdb
        gdb._runCypher("MATCH (n) RETURN count(n) AS cnt LIMIT 1")
        return {"status": "healthy", "message": "QSGraphDB 连接正常"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}

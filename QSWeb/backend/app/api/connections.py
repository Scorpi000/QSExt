"""
连接管理 API
"""

from typing import List
from fastapi import APIRouter, HTTPException

from app.models.connection import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTestResult
)
from app.services.connection_service import connection_service

router = APIRouter()


@router.get("/", response_model=List[ConnectionResponse])
async def list_connections():
    """获取所有连接"""
    return connection_service.list_connections()


@router.get("/{conn_id}", response_model=ConnectionResponse)
async def get_connection(conn_id: str):
    """获取单个连接"""
    conn = connection_service.get_connection(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return conn


@router.post("/", response_model=ConnectionResponse)
async def create_connection(conn: ConnectionCreate):
    """创建连接"""
    return connection_service.create_connection(conn)


@router.put("/{conn_id}", response_model=ConnectionResponse)
async def update_connection(conn_id: str, conn: ConnectionUpdate):
    """更新连接"""
    result = connection_service.update_connection(conn_id, conn)
    if not result:
        raise HTTPException(status_code=404, detail="连接不存在")
    return result


@router.delete("/{conn_id}")
async def delete_connection(conn_id: str):
    """删除连接"""
    if not connection_service.delete_connection(conn_id):
        raise HTTPException(status_code=404, detail="连接不存在")
    return {"message": "删除成功"}


@router.post("/{conn_id}/test", response_model=ConnectionTestResult)
async def test_connection(conn_id: str):
    """测试连接"""
    return await connection_service.test_connection(conn_id)

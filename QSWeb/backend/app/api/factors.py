"""
因子数据 API
"""

from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, HTTPException, Query

from app.models.factor import (
    FactorInfo,
    FactorTableInfo,
    FactorDataRequest,
    FactorDataResponse
)
from app.services.factor_service import factor_service

router = APIRouter()


@router.get("/{conn_id}/tables", response_model=List[FactorTableInfo])
async def list_tables(conn_id: str):
    """获取因子表列表"""
    try:
        return await factor_service.get_tables(conn_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{conn_id}/tables/{table_name}/factors",
    response_model=List[FactorInfo]
)
async def list_factors(conn_id: str, table_name: str):
    """获取因子列表"""
    try:
        return await factor_service.get_factors(conn_id, table_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{conn_id}/tables/{table_name}/factors/{factor_name}/data",
    response_model=FactorDataResponse
)
async def get_factor_data(
    conn_id: str,
    table_name: str,
    factor_name: str,
    start_date: Optional[date] = Query(None, description="起始日期"),
    end_date: Optional[date] = Query(None, description="截止日期"),
    limit: int = Query(100, ge=1, le=10000, description="返回行数限制")
):
    """获取因子数据"""
    try:
        return await factor_service.get_factor_data(
            conn_id=conn_id,
            table_name=table_name,
            factor_names=[factor_name],
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{conn_id}/tables/{table_name}/data",
    response_model=FactorDataResponse
)
async def get_multi_factor_data(
    conn_id: str,
    table_name: str,
    request: FactorDataRequest
):
    """获取多个因子数据"""
    try:
        return await factor_service.get_factor_data(
            conn_id=conn_id,
            table_name=table_name,
            factor_names=request.factor_names,
            start_date=request.start_date,
            end_date=request.end_date,
            ids=request.ids,
            limit=request.limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{conn_id}/tables/{table_name}/factors/{factor_name}/metadata"
)
async def get_factor_metadata(
    conn_id: str,
    table_name: str,
    factor_name: str
) -> Dict[str, Any]:
    """获取因子元数据"""
    try:
        return await factor_service.get_factor_metadata(
            conn_id=conn_id,
            table_name=table_name,
            factor_name=factor_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

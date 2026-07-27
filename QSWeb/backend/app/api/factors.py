"""
因子数据 API
"""

from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, Query

from app.models.factor import (
    FactorInfo,
    FactorTableInfo,
    FactorDataRequest,
    FactorDataResponse,
    RenameRequest,
    MetadataUpdate,
    DeleteTablesRequest,
    DeleteFactorsRequest,
)
from app.services.factor_service import factor_service
from app.core.exceptions import ValidationException

router = APIRouter()


@router.post("/{conn_id}/reconnect")
async def reconnect(conn_id: str):
    """断开并重新连接因子库，清除缓存的数据库实例"""
    try:
        await factor_service.disconnect(conn_id)
        return {"message": "重连成功"}
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/{conn_id}/tables", response_model=List[FactorTableInfo])
async def list_tables(conn_id: str):
    """获取因子表列表"""
    try:
        return await factor_service.get_tables(conn_id)
    except ValueError as e:
        raise ValidationException(str(e))


@router.get(
    "/{conn_id}/tables/{table_name}/factors",
    response_model=List[FactorInfo]
)
async def list_factors(conn_id: str, table_name: str):
    """获取因子列表"""
    try:
        return await factor_service.get_factors(conn_id, table_name)
    except ValueError as e:
        raise ValidationException(str(e))


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
    ids: Optional[str] = Query(None, description="ID 列表，逗号分隔"),
    limit: int = Query(100, ge=1, le=10000, description="返回行数限制")
):
    """获取因子数据"""
    try:
        id_list = [i.strip() for i in ids.split(",") if i.strip()] if ids else None
        return await factor_service.get_factor_data(
            conn_id=conn_id,
            table_name=table_name,
            factor_names=[factor_name],
            start_date=start_date,
            end_date=end_date,
            ids=id_list,
            limit=limit
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


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
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.get(
    "/{conn_id}/tables/{table_name}/factors/{factor_name}/stats"
)
async def get_factor_stats(
    conn_id: str,
    table_name: str,
    factor_name: str
) -> Dict[str, Any]:
    """获取因子统计信息（ID数量、时点数量、起止ID、起止时间）"""
    try:
        return await factor_service.get_factor_stats(
            conn_id=conn_id,
            table_name=table_name,
            factor_name=factor_name
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


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
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.get(
    "/{conn_id}/tables/{table_name}/metadata"
)
async def get_table_metadata(
    conn_id: str,
    table_name: str
) -> Dict[str, Any]:
    """获取因子表元数据"""
    try:
        return await factor_service.get_table_metadata(
            conn_id=conn_id,
            table_name=table_name
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ---------- 表管理 ----------

@router.put("/{conn_id}/tables/{table_name}/rename")
async def rename_table(
    conn_id: str,
    table_name: str,
    request: RenameRequest
):
    """重命名因子表"""
    try:
        return await factor_service.rename_table(
            conn_id=conn_id,
            old_name=table_name,
            new_name=request.new_name
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.delete("/{conn_id}/tables")
async def delete_tables(
    conn_id: str,
    request: DeleteTablesRequest
):
    """批量删除因子表"""
    try:
        return await factor_service.delete_tables(
            conn_id=conn_id,
            table_names=request.table_names
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.put("/{conn_id}/tables/{table_name}/metadata")
async def update_table_metadata(
    conn_id: str,
    table_name: str,
    request: MetadataUpdate
):
    """更新因子表元数据"""
    try:
        return await factor_service.update_table_metadata(
            conn_id=conn_id,
            table_name=table_name,
            metadata=request.metadata
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


# ---------- 因子管理 ----------

@router.put("/{conn_id}/tables/{table_name}/factors/{factor_name}/rename")
async def rename_factor(
    conn_id: str,
    table_name: str,
    factor_name: str,
    request: RenameRequest
):
    """重命名因子"""
    try:
        return await factor_service.rename_factor(
            conn_id=conn_id,
            table_name=table_name,
            old_name=factor_name,
            new_name=request.new_name
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.delete("/{conn_id}/tables/{table_name}/factors")
async def delete_factors(
    conn_id: str,
    table_name: str,
    request: DeleteFactorsRequest
):
    """批量删除因子"""
    try:
        return await factor_service.delete_factors(
            conn_id=conn_id,
            table_name=table_name,
            factor_names=request.factor_names
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")


@router.put("/{conn_id}/tables/{table_name}/factors/{factor_name}/metadata")
async def update_factor_metadata(
    conn_id: str,
    table_name: str,
    factor_name: str,
    request: MetadataUpdate
):
    """更新因子元数据"""
    try:
        return await factor_service.update_factor_metadata(
            conn_id=conn_id,
            table_name=table_name,
            factor_name=factor_name,
            metadata=request.metadata
        )
    except ValidationException:
        raise
    except Exception as e:
        raise ValidationException(f"{type(e).__name__}: {e}")

"""
风险管理 API 路由
"""

from typing import Optional

from fastapi import APIRouter, Query, Body

from app.services.risk_service import risk_service

router = APIRouter()


# ─── 风险库 CRUD ─────────────────────────────────────────────────

@router.get("/databases")
async def list_databases():
    """列出已配置的风险库"""
    return risk_service.list_databases()


@router.get("/databases/{db_id}")
async def get_database(db_id: str):
    """获取单个风险库信息"""
    return risk_service.get_database(db_id)


@router.post("/databases")
async def create_database(
    name: str = Body(..., description="风险库名称"),
    db_type: str = Body("HDF5RDB", description="风险库类型"),
    args: dict = Body(..., description="连接参数（如 HDF5RDB 需要 MainDir）"),
    description: str = Body("", description="备注说明"),
):
    """创建风险库配置"""
    return risk_service.create_database(name, db_type, args, description)


@router.put("/databases/{db_id}")
async def update_database(
    db_id: str,
    name: Optional[str] = Body(None, description="风险库名称"),
    args: Optional[dict] = Body(None, description="连接参数"),
    description: Optional[str] = Body(None, description="备注说明"),
):
    """更新风险库配置"""
    return risk_service.update_database(db_id, name, args, description)


@router.delete("/databases/{db_id}")
async def delete_database(db_id: str):
    """删除风险库配置"""
    risk_service.delete_database(db_id)
    return {"message": "删除成功"}


@router.post("/databases/{db_id}/test")
async def test_database(db_id: str):
    """测试风险库连接"""
    return await risk_service.test_database(db_id)


@router.get("/databases/{db_id}/tables")
async def list_tables(db_id: str):
    """列出风险库下的所有风险表"""
    return await risk_service.list_tables(db_id)


# ─── 风险矩阵 ───────────────────────────────────────────────────

@router.get("/tables/{db_id}/{table_name}/covariance")
async def get_covariance(
    db_id: str,
    table_name: str,
    dt: str = Query(..., description="时点，ISO 格式（如 2024-01-02T00:00:00）"),
    limit: int = Query(100, ge=1, le=5000, description="截取前 N 只证券"),
):
    """获取协方差矩阵"""
    return await risk_service.get_covariance(db_id, table_name, dt, limit)


@router.get("/tables/{db_id}/{table_name}/correlation")
async def get_correlation(
    db_id: str,
    table_name: str,
    dt: str = Query(..., description="时点，ISO 格式（如 2024-01-02T00:00:00）"),
    limit: int = Query(100, ge=1, le=5000, description="截取前 N 只证券"),
):
    """获取相关系数矩阵"""
    return await risk_service.get_correlation(db_id, table_name, dt, limit)


# ─── 因子风险分解 ───────────────────────────────────────────────

@router.get("/tables/{db_id}/{table_name}/factor-decomposition")
async def get_factor_decomposition(
    db_id: str,
    table_name: str,
    dt: str = Query(..., description="时点，ISO 格式（如 2024-01-02T00:00:00）"),
    limit: int = Query(100, ge=1, le=10000, description="截取前 N 只证券的特异性风险"),
):
    """获取因子风险分解"""
    return await risk_service.get_factor_decomposition(db_id, table_name, dt, limit)


@router.get("/tables/{db_id}/{table_name}/dates")
async def get_table_dates(db_id: str, table_name: str):
    """获取风险表的时点列表"""
    import asyncio
    db = await risk_service._get_risk_db(db_id)

    def _get():
        rt = db.getTable(table_name)
        dts = rt.getDateTime()
        return [d.isoformat() for d in dts]

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get)

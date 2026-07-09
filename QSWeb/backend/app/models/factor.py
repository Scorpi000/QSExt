"""
因子相关模型
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import date


class FactorInfo(BaseModel):
    """因子信息"""
    name: str
    table_name: str
    db_name: str
    conn_id: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    last_date: Optional[date] = None
    id_count: Optional[int] = None


class FactorTableInfo(BaseModel):
    """因子表信息"""
    name: str
    db_name: str
    conn_id: str
    factor_count: Optional[int] = None
    description: Optional[str] = None


class FactorDBInfo(BaseModel):
    """因子库信息"""
    name: str
    db_type: str
    table_count: Optional[int] = None
    status: str = "disconnected"


class FactorDataRequest(BaseModel):
    """因子数据请求"""
    factor_names: List[str] = Field(..., description="因子名称列表")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    ids: Optional[List[str]] = Field(None, description="证券 ID 列表")
    limit: int = Field(100, ge=1, le=10000, description="返回行数限制")


class FactorDataResponse(BaseModel):
    """因子数据响应"""
    data: Dict[str, Any] = Field(..., description="数据")
    columns: List[str] = Field(..., description="列名")
    index: List[Any] = Field(..., description="索引")
    total_rows: int = Field(..., description="总行数")
    total_columns: int = Field(..., description="总列数")

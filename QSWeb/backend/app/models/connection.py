"""
因子库连接配置模型
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ConnectionBase(BaseModel):
    """连接配置基础模型"""
    name: str = Field(..., description="连接名称", min_length=1, max_length=100)
    db_type: str = Field(..., description="数据库类型")
    description: Optional[str] = Field(None, description="描述")
    args: Dict[str, Any] = Field(default_factory=dict, description="QuantStudio FactorDB 参数")


class ConnectionCreate(ConnectionBase):
    """创建连接"""
    pass


class ConnectionUpdate(BaseModel):
    """更新连接"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    args: Optional[Dict[str, Any]] = None


class ConnectionResponse(ConnectionBase):
    """连接响应"""
    qsid: str = Field(..., description="连接 QSID（唯一标识）")
    status: str = Field(default="disconnected", description="连接状态")
    source: str = Field(default="neo4j", description="配置来源: settings | neo4j")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class ConnectionTestResult(BaseModel):
    """连接测试结果"""
    success: bool
    message: str
    detail: Optional[Dict[str, Any]] = None


class ImpactFactor(BaseModel):
    """受影响因子"""
    QSID: str
    Name: str
    FactorTableName: Optional[str] = None


class ImpactAnalysis(BaseModel):
    """删除影响分析"""
    factor_db: Optional[Dict[str, Any]] = None
    direct_factors: List[ImpactFactor] = []
    indirect_factors: List[ImpactFactor] = []
    factor_tables: List[Dict[str, str]] = []
    total_affected_factors: int = 0

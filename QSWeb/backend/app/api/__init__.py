"""
API 路由模块
"""

from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.factors import router as factors_router

router = APIRouter()

# 注册子路由
router.include_router(connections_router, prefix="/connections", tags=["连接管理"])
router.include_router(factors_router, prefix="/factors", tags=["因子数据"])

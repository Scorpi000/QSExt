"""
API 路由模块
"""

from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.factors import router as factors_router
from app.api.registry import router as registry_router
from app.api.backtest import router as backtest_router

router = APIRouter()

# 注册子路由
router.include_router(connections_router, prefix="/connections", tags=["连接管理"])
router.include_router(factors_router, prefix="/factors", tags=["因子数据"])
router.include_router(registry_router, prefix="", tags=["QSRegistry"])
router.include_router(backtest_router, prefix="/backtest", tags=["回测"])

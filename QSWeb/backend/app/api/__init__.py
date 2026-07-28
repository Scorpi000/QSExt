"""
API 路由模块
"""

from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.factors import router as factors_router
from app.api.registry import router as registry_router
from app.api.backtest import router as backtest_router
from app.api.risk import router as risk_router
from app.api.portfolio import router as portfolio_router
from app.api.report import router as report_router

router = APIRouter()

# 注册子路由
router.include_router(connections_router, prefix="/connections", tags=["连接管理"])
router.include_router(factors_router, prefix="/factors", tags=["因子数据"])
router.include_router(registry_router, prefix="", tags=["QSRegistry"])
router.include_router(backtest_router, prefix="/backtest", tags=["回测工作台"])
router.include_router(risk_router, prefix="/risk", tags=["风险管理"])
router.include_router(portfolio_router, prefix="/portfolio", tags=["组合优化"])
router.include_router(report_router, prefix="/reports", tags=["报告中心"])

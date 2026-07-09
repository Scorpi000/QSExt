"""
QSWeb 后端应用入口

启动方式:
    cd QSWeb/backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 28000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings

app = FastAPI(
    title="QSWeb API",
    description="QuantStudio Web GUI 后端 API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """健康检查"""
    return {
        "name": "QSWeb API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "healthy"}

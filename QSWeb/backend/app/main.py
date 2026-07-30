"""
QSWeb 后端应用入口

启动方式:
    cd QSWeb/backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 28000
"""

import json
import traceback
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import router as api_router
from app.api.ai import router as ai_router
from app.core.config import settings
from app.core.exceptions import APIException
from app.tasks.manager import task_manager

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
app.include_router(ai_router)


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    """统一 API 异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": exc.detail,
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理 Starlette/FastAPI 标准 HTTP 异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "HTTP_ERROR",
            "message": exc.detail,
            "detail": None,
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理 Pydantic 请求验证异常"""
    errors = []
    for error in exc.errors():
        errors.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数验证失败",
            "detail": errors,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：捕获所有未处理的异常"""
    # 记录完整 traceback 便于排查
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误" if not settings.DEBUG else str(exc),
            "detail": None if not settings.DEBUG else traceback.format_exc(),
        },
    )


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


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查询后台任务状态"""
    task = task_manager.get_task_dict(task_id)
    if task is None:
        return JSONResponse(status_code=404, content={"message": "任务不存在"})
    return task


@app.websocket("/ws/tasks/{task_id}")
async def websocket_task(websocket: WebSocket, task_id: str):
    """WebSocket 端点：推送任务进度更新"""
    await websocket.accept()

    async def on_update(data: dict):
        """任务状态变更时推送"""
        try:
            await websocket.send_text(json.dumps(data, ensure_ascii=False, default=str))
        except Exception:
            pass

    task_manager.subscribe(task_id, on_update)

    # 发送当前状态
    task = task_manager.get_task(task_id)
    if task:
        await websocket.send_text(json.dumps(task.to_dict(), ensure_ascii=False, default=str))

    try:
        while True:
            # 保持连接，等待客户端消息（心跳检测或关闭）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        task_manager.unsubscribe(task_id, on_update)

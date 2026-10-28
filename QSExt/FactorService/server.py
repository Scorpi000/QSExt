"""独立 HTTP 数据源服务，不接收或执行计算图。"""

import asyncio
import datetime as dt
import hmac
import logging
import math
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request as HTTPRequest
from fastapi.responses import Response, JSONResponse
from pydantic import ValidationError

from .codec import dumps_control, loads_control, pack, unpack
from .config import load_settings
from .protocol import PREFIX, PROTOCOL_VERSION, MEDIA_TYPE, Request, BatchRequest, RemoteFactorError
from .registry import Registry

LOGGER = logging.getLogger("QS.FactorService")


def create_app(definitions, config):
    """创建应用并在资源线程内管理数据库生命周期。

    Args:
        definitions: DBDef 列表。
        config: ServiceConfig 或相同结构字典。

    Returns:
        可由 Uvicorn 启动的 FastAPI 应用。
    """
    registry = Registry(definitions, config)
    config = registry.config
    token = os.environ.get(config.Auth.TokenEnv)
    if not token:
        registry.close()
        raise ValueError("服务认证令牌环境变量未设置")

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await asyncio.to_thread(registry.close)

    app = FastAPI(title="QuantStudio 远程因子库", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.registry = registry

    @app.middleware("http")
    async def guard(http, call_next):
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        http.state.request_id = request_id
        try:
            if http.url.path != PREFIX + "/health":
                auth = http.headers.get("authorization", "")
                if not hmac.compare_digest(auth.encode(), ("Bearer " + token).encode()):
                    raise RemoteFactorError("认证失败", code="UNAUTHORIZED", status=401)
            response = await call_next(http)
        except RemoteFactorError as exc:
            response = JSONResponse({"code": exc.code, "message": str(exc), "request_id": request_id, **exc.details}, status_code=exc.status)
        except (ValueError, TypeError, KeyError, ValidationError):
            LOGGER.exception("请求或后端参数错误，request_id=%s", request_id)
            response = JSONResponse({"code": "INVALID_ARGUMENT", "message": "参数或数据类型不受支持", "request_id": request_id}, status_code=422)
        except Exception:
            LOGGER.exception("后端调用失败，request_id=%s", request_id)
            response = JSONResponse({"code": "BACKEND_ERROR", "message": "后端调用失败，请根据请求标识检查服务日志", "request_id": request_id, "effect": "unknown", "operation_id": getattr(http.state, "operation_id", None)}, status_code=500)
        response.headers["X-QS-Request-ID"] = request_id
        LOGGER.info("request_id=%s path=%s status=%s seconds=%.4f", request_id, http.url.path, response.status_code, time.monotonic() - started)
        return response

    async def read_body(http):
        data = bytearray()
        async for chunk in http.stream():
            data.extend(chunk)
            if len(data) > config.Limits.MaxRequestBytes:
                raise RemoteFactorError("请求超过字节限制", code="TOO_LARGE", status=413)
        return bytes(data)

    def control(value):
        data = dumps_control(value)
        if len(data) > config.Limits.MaxResponseBytes:
            raise RemoteFactorError("响应超过字节限制", code="TOO_LARGE", status=413)
        return Response(data, media_type="application/json")

    async def result(future):
        # 断开请求不会取消已经开始的后端操作或释放连接所有权。
        return await asyncio.shield(asyncio.wrap_future(future))

    @app.get(PREFIX + "/health")
    async def health():
        return {"status": "ok"}

    @app.get(PREFIX + "/info")
    async def info():
        return control({"protocol_version": PROTOCOL_VERSION, "service_id": config.ServiceID, "epoch": registry.epoch, "limits": config.Limits.model_dump(), "codecs": [MEDIA_TYPE]})

    @app.get(PREFIX + "/databases")
    async def databases():
        return control(registry.directory())

    @app.get(PREFIX + "/operations/{operation_id}")
    async def operation(operation_id: str):
        return control(registry.operation(operation_id))

    @app.get(PREFIX + "/databases/{database}/capabilities")
    async def capabilities(database: str):
        resource = registry.resource(database)
        return control(await result(resource.executor.submit(resource.capabilities)))

    @app.post(PREFIX + "/databases/{database}/{action}")
    async def dispatch(database: str, action: str, http: HTTPRequest):
        if action not in ("describe", "invoke", "read", "read-batch", "write"):
            raise RemoteFactorError("接口不存在", code="NOT_FOUND", status=404)
        body = await read_body(http)
        if action == "write":
            upload = await asyncio.to_thread(unpack, body, config.Limits.MaxRequestBytes)
            if set(upload) != {"request", "data"}:
                raise ValueError("上传字段错误")
            request = Request.model_validate(upload["request"])
            http.state.operation_id = request.operation_id
            from QuantStudio.Core.QSObject import Panel
            if not isinstance(upload["data"], Panel):
                raise TypeError("写入必须为 Panel")
            if math.prod(upload["data"].shape) > config.Limits.MaxCells:
                raise RemoteFactorError("写入超过单元格限制", code="TOO_LARGE", status=413)
            value = await result(registry.submit(database, request, action, upload["data"]))
        elif action == "read-batch":
            batch = BatchRequest.model_validate(loads_control(body))
            resource = registry.resource(database)
            if any(request.operation != "readData" or request.target.kind == "database" for request in batch.requests):
                raise ValueError("批量接口仅接受原子读取")
            def read_batch():
                values, cells = [], 0
                for request in batch.requests:
                    value = resource.execute(request, "read")
                    cells += math.prod(value.shape)
                    if cells > config.Limits.MaxCells:
                        raise RemoteFactorError("批量读取超过总单元格限制", code="TOO_LARGE", status=413)
                    values.append({"read_spec_id": request.request_id, "data": value})
                return values
            value = await result(resource.executor.submit(read_batch))
        else:
            request = Request.model_validate(loads_control(body))
            http.state.operation_id = request.operation_id
            value = await result(registry.submit(database, request, action))
        if action in ("read", "read-batch"):
            read_at = dt.datetime.now(dt.timezone.utc).isoformat()
            try:
                data = await asyncio.to_thread(pack, value, config.Limits.MaxResponseBytes)
            except ValueError:
                raise RemoteFactorError("结果超过字节限制", code="TOO_LARGE", status=413) from None
            return Response(data, media_type=MEDIA_TYPE, headers={"X-QS-Read-At": read_at})
        return control(value)

    return app


def app_from_settings(path):
    """从 settings.py 创建独立服务。"""
    definitions, config = load_settings(path)
    return create_app(definitions, config)

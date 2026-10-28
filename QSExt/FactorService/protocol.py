"""远程因子库的显式请求、错误和身份协议。"""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from QuantStudio.Core import __QS_Error__

PROTOCOL_VERSION = 1
PREFIX = "/api/factor/v1"
MEDIA_TYPE = "application/vnd.quantstudio.factor+binary"


class RemoteFactorError(__QS_Error__):
    """附带远程操作结果的框架异常。"""

    def __init__(self, message, code="REMOTE_ERROR", status=500, **details):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details
        self.operation_id = details.get("operation_id")
        self.retryable = details.get("retryable", False)


class StrictModel(BaseModel):
    """拒绝未声明的控制字段。"""

    model_config = ConfigDict(extra="forbid")


class Target(StrictModel):
    """可重建的库、表或原子因子描述。"""

    kind: Literal["database", "table", "factor"] = "database"
    table_name: str | None = None
    table_args: dict = Field(default_factory=dict)
    factor_name: str | None = None
    factor_args: dict = Field(default_factory=dict)


class Request(StrictModel):
    """所有数据源调用共用的请求。"""

    request_id: str
    resource_id: str
    config_revision: str
    target: Target = Field(default_factory=Target)
    operation: str = "describe"
    kwargs: dict[str, Any] = Field(default_factory=dict)
    operation_id: str | None = None
    epoch: str | None = None
    expires_at: float | None = None


class BatchRequest(StrictModel):
    """批量原子读取；不包含计算依赖或算子。"""

    requests: list[Request] = Field(min_length=1, max_length=1024)


def digest(value):
    """计算公开描述的确定性摘要。"""
    from .codec import to_control

    def canonical(item):
        if isinstance(item, dict):
            return {key: canonical(part) for key, part in sorted(item.items(), key=lambda pair: repr(pair[0]))}
        if isinstance(item, list):
            return [canonical(part) for part in item]
        if isinstance(item, tuple):
            return tuple(canonical(part) for part in item)
        return item
    raw = json.dumps(to_control(canonical(value)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

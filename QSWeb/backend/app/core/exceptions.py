"""
自定义异常
"""

from typing import Any, Optional


class APIException(Exception):
    """API 异常基类"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Optional[Any] = None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


class NotFoundException(APIException):
    """资源不存在"""

    def __init__(self, resource: str, id: str):
        super().__init__(
            status_code=404,
            code="NOT_FOUND",
            message=f"{resource} 不存在: {id}"
        )


class ConnectionException(APIException):
    """连接异常"""

    def __init__(self, message: str, detail: Optional[Any] = None):
        super().__init__(
            status_code=500,
            code="CONNECTION_ERROR",
            message=message,
            detail=detail
        )


class ValidationException(APIException):
    """验证异常"""

    def __init__(self, message: str, detail: Optional[Any] = None):
        super().__init__(
            status_code=400,
            code="VALIDATION_ERROR",
            message=message,
            detail=detail
        )

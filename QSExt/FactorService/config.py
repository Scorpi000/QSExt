"""加载既有数据库定义及独立的服务导出策略。"""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from QSExt.RuntimeConfig.config import DBDef, RuntimeSettings
from .protocol import StrictModel


class AuthConfig(StrictModel):
    """认证令牌由环境提供。"""

    TokenEnv: str = "QS_FACTOR_SERVICE_TOKEN"


class ExportConfig(StrictModel):
    """公开资源及访问权限。"""

    ResourceID: str = Field(min_length=1)
    Access: Literal["read", "read_write"] = "read"


class LimitsConfig(StrictModel):
    """请求、响应和资源队列限制。"""

    MaxRequestBytes: int = Field(default=8 * 1024 * 1024, gt=0)
    MaxResponseBytes: int = Field(default=256 * 1024 * 1024, gt=0)
    MaxCells: int = Field(default=5_000_000, gt=0)
    MaxQueueSize: int = Field(default=64, gt=0)
    QueueTimeoutSeconds: float = Field(default=30, gt=0)
    OperationTTLSeconds: float = Field(default=300, gt=0)


class ServiceConfig(StrictModel):
    """独立于业务角色的服务配置。"""

    ServiceID: str = Field(min_length=1)
    Host: str = "127.0.0.1"
    Port: int = Field(default=8765, ge=1, le=65535)
    Auth: AuthConfig = Field(default_factory=AuthConfig)
    Databases: dict[str, ExportConfig]
    Limits: LimitsConfig = Field(default_factory=LimitsConfig)

    @model_validator(mode="after")
    def unique_resources(self):
        """首版拒绝多个别名共享可变后端。"""
        ids = [item.ResourceID for item in self.Databases.values()]
        if len(ids) != len(set(ids)):
            raise ValueError("ResourceID 不能重复")
        return self


def validate_definitions(definitions: list[DBDef], config: ServiceConfig):
    """校验名称、导出关系和常见文件后端的重复路径。"""
    names = [item.name for item in definitions]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("因子库逻辑名称必须非空且唯一")
    if set(config.Databases).difference(names):
        raise ValueError("服务导出清单包含未定义的因子库")
    paths = set()
    for definition in definitions:
        if definition.name not in config.Databases:
            continue
        if "." not in definition.resolved_class_name:
            raise ValueError("数据库必须使用已知短名或完整类路径")
        if definition.resolved_class_name.rsplit(".", 1)[-1] not in ("DuckDB", "HDF5DB"):
            continue
        # 未显式配置的路径可能来自后端配置文件，在实例化后还需再次检查。
        for key in ("DBFile", "ParquetDir", "MainDir"):
            value = definition.args.get(key)
            if value and str(value) != ":memory:":
                path = os.path.normcase(str(Path(value).expanduser().resolve()))
                if path in paths:
                    raise ValueError("多个导出因子库使用了同一个后端路径")
                paths.add(path)


def load_settings(path):
    """复用配置继承和环境覆盖，同时保留服务专用字段。

    Args:
        path: settings.py 的文件路径。

    Returns:
        数据库定义列表与服务配置。
    """
    path = str(Path(path).expanduser().resolve())
    values, hooks = RuntimeSettings._load_module_with_inheritance(path)
    for key, value in os.environ.items():
        if key.startswith("QS_"):
            try:
                value = json.loads(value)
            except ValueError:
                pass
            values[key[3:].lower()] = value
    config = ServiceConfig.model_validate(values.get("factor_service", {}))
    settings = RuntimeSettings.from_dict(values, hooks)
    validate_definitions(settings.factor_databases, config)
    return settings.factor_databases, config

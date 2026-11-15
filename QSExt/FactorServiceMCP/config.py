"""FactorService MCP 的进程配置。"""

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_url: str = "http://127.0.0.1:8765"
    service_token_env: str = "QS_FACTOR_SERVICE_TOKEN"
    service_timeout_seconds: float = Field(300, gt=0, le=1800)
    catalog_path: Path = Path("~/.quantstudio/factor-mcp/catalog.sqlite3")
    catalog_ttl_seconds: int = Field(86400, ge=0, le=604800)
    refresh_interval_seconds: int = Field(86400, ge=60, le=604800)
    catalog_databases: list[str] | None = None
    max_cells: int = Field(2000, ge=1, le=100000)
    max_result_bytes: int = Field(65536, ge=4096, le=1048576)
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = Field(28002, ge=1, le=65535)
    mcp_token_env: str = "QS_FACTOR_MCP_TOKEN"

    @field_validator("server_url")
    @classmethod
    def valid_server_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("server_url 必须是不含凭据、查询和片段的 HTTP(S) 地址")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("非本机 FactorService 必须使用 HTTPS")
        return value.rstrip("/")

    @field_validator("catalog_path")
    @classmethod
    def expand_catalog_path(cls, value):
        return value.expanduser().resolve()

    @classmethod
    def from_env(cls, **overrides):
        values = {
            "server_url": os.getenv("QS_FACTOR_MCP_SERVER_URL", cls.model_fields["server_url"].default),
            "service_token_env": os.getenv("QS_FACTOR_MCP_SERVICE_TOKEN_ENV", cls.model_fields["service_token_env"].default),
            "service_timeout_seconds": os.getenv("QS_FACTOR_MCP_SERVICE_TIMEOUT", cls.model_fields["service_timeout_seconds"].default),
            "catalog_path": os.getenv("QS_FACTOR_MCP_CATALOG_PATH", str(cls.model_fields["catalog_path"].default)),
            "catalog_ttl_seconds": os.getenv("QS_FACTOR_MCP_CATALOG_TTL", cls.model_fields["catalog_ttl_seconds"].default),
            "refresh_interval_seconds": os.getenv("QS_FACTOR_MCP_REFRESH_INTERVAL",
                                                    cls.model_fields["refresh_interval_seconds"].default),
            "catalog_databases": ([item.strip() for item in os.environ["QS_FACTOR_MCP_DATABASES"].split(",") if item.strip()]
                                  if os.getenv("QS_FACTOR_MCP_DATABASES") else None),
            "max_cells": os.getenv("QS_FACTOR_MCP_MAX_CELLS", cls.model_fields["max_cells"].default),
            "max_result_bytes": os.getenv("QS_FACTOR_MCP_MAX_RESULT_BYTES", cls.model_fields["max_result_bytes"].default),
            "mcp_token_env": os.getenv("QS_FACTOR_MCP_TOKEN_ENV", cls.model_fields["mcp_token_env"].default),
        }
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls.model_validate(values)

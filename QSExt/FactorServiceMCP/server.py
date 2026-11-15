"""FastMCP 工具层；业务实现保持可独立测试。"""

import hmac
import os

from QSExt.FactorService.client import FactorDBServiceClient
from QSExt.FactorService.protocol import RemoteFactorError

from .catalog import FactorCatalog
from .config import MCPConfig
from .service import FactorDataService
from .refresh import CatalogRefreshManager


def create_service(config):
    def client_factory():
        return FactorDBServiceClient(config.server_url, token_env=config.service_token_env,
                                     timeout_seconds=config.service_timeout_seconds)
    catalog = FactorCatalog(config.catalog_path, client_factory, config.catalog_ttl_seconds,
                            config.catalog_databases)
    return FactorDataService(catalog, client_factory, config.max_cells, config.max_result_bytes)


def create_server(config=None, service=None):
    from fastmcp import FastMCP
    from fastmcp.exceptions import ToolError
    from fastmcp.server.auth import AccessToken, TokenVerifier

    config = config or MCPConfig.from_env()
    service = service or create_service(config)
    refresh_manager = CatalogRefreshManager(service, config.refresh_interval_seconds)

    class SharedTokenVerifier(TokenVerifier):
        def __init__(self, expected):
            super().__init__(required_scopes=["factor:read"])
            self.expected = expected

        async def verify_token(self, token):
            if not hmac.compare_digest(token.encode(), self.expected.encode()):
                return None
            return AccessToken(token=token, client_id="factor-mcp", scopes=["factor:read"])

    auth = None
    if config.transport == "streamable-http":
        token = os.environ.get(config.mcp_token_env)
        if not token:
            raise ValueError(f"HTTP 模式需要设置 MCP 入站令牌环境变量 {config.mcp_token_env}")
        auth = SharedTokenVerifier(token)

    mcp = FastMCP("FactorService", version="0.1.0", auth=auth, mask_error_details=True,
        instructions="发现 FactorService 中的因子及其覆盖范围；小规模读取前先确认因子、ID 和日期。")
    mcp.factor_refresh_manager = refresh_manager

    if config.transport == "streamable-http":
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        def authorized(request: Request):
            value = request.headers.get("Authorization", "")
            scheme, _, supplied = value.partition(" ")
            expected = os.environ.get(config.mcp_token_env, "")
            return scheme.lower() == "bearer" and bool(expected) and hmac.compare_digest(supplied, expected)

        @mcp.custom_route("/admin/catalog", methods=["GET"], include_in_schema=False)
        async def catalog_status(request: Request):
            if not authorized(request):
                return JSONResponse({"message": "Unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
            return JSONResponse(refresh_manager.status())

        @mcp.custom_route("/admin/catalog/refresh", methods=["POST"], include_in_schema=False)
        async def catalog_refresh(request: Request):
            if not authorized(request):
                return JSONResponse({"message": "Unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
            accepted = refresh_manager.request_refresh("manual")
            return JSONResponse({"accepted": accepted, **refresh_manager.status()},
                                status_code=202 if accepted else 200)

    def invoke(method, *args):
        try:
            return getattr(service, method)(*args)
        except ValueError as error:
            raise ToolError(str(error)) from None
        except RemoteFactorError as error:
            raise ToolError(f"{error.code}: {error}") from None

    @mcp.tool(name="factor_list_databases")
    def list_databases() -> dict:
        """列出 FactorService 当前公开的数据库及表、因子数量。"""
        return invoke("list_databases")

    @mcp.tool(name="factor_list_tables")
    def list_tables(database: str | None = None, query: str = "", cursor: str | None = None,
                    page_size: int = 20) -> dict:
        """分页浏览因子表；database 和 query 均可选。"""
        return invoke("list_tables", database, query, cursor, page_size)

    @mcp.tool(name="factor_search_factors")
    def search_factors(query: str = "", database: str | None = None, table: str | None = None,
                       cursor: str | None = None, page_size: int = 20) -> dict:
        """按因子名、表名或描述搜索因子，返回后续工具使用的稳定 factor_id。"""
        return invoke("search_factors", query, database, table, cursor, page_size)

    @mcp.tool(name="factor_get_factor")
    def get_factor(factor_id: str) -> dict:
        """读取一个因子的数据库、因子表、类型、描述和完整元数据。"""
        return invoke("get_factor", factor_id)

    @mcp.tool(name="factor_get_coverage")
    def get_coverage(factor_id: str, id_query: str = "", id_cursor: str | None = None,
                     id_page_size: int = 50, start_date: str | None = None,
                     end_date: str | None = None) -> dict:
        """获取因子的证券 ID 分页、日期范围和覆盖数量；日期使用 ISO 8601。"""
        return invoke("get_coverage", factor_id, id_query, id_cursor, id_page_size, start_date, end_date)

    @mcp.tool(name="factor_read_data")
    def read_data(factor_ids: list[str], ids: list[str], dates: list[str] | None = None,
                  start_date: str | None = None, end_date: str | None = None) -> dict:
        """读取同一因子表中的小规模数据，返回 date/asset_id/factor/value 长表。"""
        return invoke("read_data", factor_ids, ids, dates, start_date, end_date)

    return mcp

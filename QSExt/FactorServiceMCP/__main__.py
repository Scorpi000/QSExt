"""python -m QSExt.FactorServiceMCP。"""

import argparse
import json
import logging

from .config import MCPConfig
from .server import create_server


def main():
    parser = argparse.ArgumentParser(description="独立 FactorService 因子发现与读取 MCP")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=28002)
    parser.add_argument("--server-url")
    parser.add_argument("--catalog-path")
    parser.add_argument("--databases", help="首次同步的数据库白名单，逗号分隔")
    parser.add_argument("--refresh-only", action="store_true", help="刷新目录后退出，不启动 MCP")
    args = parser.parse_args()
    try:
        config = MCPConfig.from_env(transport=args.transport, host=args.host, port=args.port,
                                    server_url=args.server_url, catalog_path=args.catalog_path,
                                    catalog_databases=([x.strip() for x in args.databases.split(",") if x.strip()]
                                                       if args.databases else None))
        if args.refresh_only:
            from .server import create_service
            print(json.dumps(create_service(config).refresh_catalog(), ensure_ascii=False))
            return
        mcp = create_server(config)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    logging.basicConfig(level=logging.WARNING)
    manager = mcp.factor_refresh_manager
    manager.start()
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio", show_banner=False)
        else:
            mcp.run(transport="streamable-http", host=config.host, port=config.port,
                    path="/mcp", stateless=True, show_banner=False)
    finally:
        manager.stop()


if __name__ == "__main__":
    main()

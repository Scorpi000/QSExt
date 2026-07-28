"""
连接管理服务

管理因子库连接的生命周期
配置统一存储在 QSWebConfig.json 中
"""

import uuid
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

from app.models.connection import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTestResult
)
from app.core.config import settings


class ConnectionService:
    """连接管理服务"""

    def __init__(self):
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._config_path = Path(settings.QS_CONFIG_PATH) / "QSWebConfig.json"
        self._config: Dict[str, Any] = {}
        self._load_connections()

    def _load_connections(self):
        """从 QSWebConfig.json 加载连接配置"""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                self._connections = self._config.get("factor_dbs", {})
            except Exception:
                self._config = {"version": "1.0"}
                self._connections = {}
        else:
            self._config = {"version": "1.0"}

    def _save_connections(self):
        """保存连接配置到 QSWebConfig.json，保留其他顶层配置项"""
        self._config["factor_dbs"] = self._connections
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def list_connections(self) -> List[ConnectionResponse]:
        """获取所有连接"""
        result = []
        for conn_id, conn in self._connections.items():
            result.append(ConnectionResponse(
                id=conn_id,
                name=conn["name"],
                db_type=conn["db_type"],
                description=conn.get("description"),
                args=conn.get("args", {}),
                status=conn.get("status", "disconnected")
            ))
        return result

    def get_connection(self, conn_id: str) -> Optional[ConnectionResponse]:
        """获取单个连接"""
        if conn_id not in self._connections:
            return None
        conn = self._connections[conn_id]
        return ConnectionResponse(
            id=conn_id,
            name=conn["name"],
            db_type=conn["db_type"],
            description=conn.get("description"),
            args=conn.get("args", {}),
            status=conn.get("status", "disconnected")
        )

    def create_connection(self, conn: ConnectionCreate) -> ConnectionResponse:
        """创建连接"""
        conn_id = str(uuid.uuid4())[:8]
        self._connections[conn_id] = {
            "name": conn.name,
            "db_type": conn.db_type,
            "description": conn.description,
            "args": conn.args,
            "status": "disconnected"
        }
        self._save_connections()
        return ConnectionResponse(
            id=conn_id,
            name=conn.name,
            db_type=conn.db_type,
            description=conn.description,
            args=conn.args,
            status="disconnected"
        )

    def update_connection(
        self,
        conn_id: str,
        conn: ConnectionUpdate
    ) -> Optional[ConnectionResponse]:
        """更新连接"""
        if conn_id not in self._connections:
            return None

        existing = self._connections[conn_id]
        if conn.name is not None:
            existing["name"] = conn.name
        if conn.description is not None:
            existing["description"] = conn.description
        if conn.args is not None:
            existing["args"] = conn.args

        self._save_connections()
        return ConnectionResponse(
            id=conn_id,
            name=existing["name"],
            db_type=existing["db_type"],
            description=existing.get("description"),
            args=existing.get("args", {}),
            status=existing.get("status", "disconnected")
        )

    def delete_connection(self, conn_id: str) -> bool:
        """删除连接"""
        if conn_id not in self._connections:
            return False
        del self._connections[conn_id]
        self._save_connections()
        return True

    async def test_connection(self, conn_id: str) -> ConnectionTestResult:
        """测试连接"""
        if conn_id not in self._connections:
            return ConnectionTestResult(
                success=False,
                message="连接不存在"
            )

        conn = self._connections[conn_id]
        db_type = conn["db_type"]
        args = conn.get("args", {})

        try:
            # 根据数据库类型测试连接
            if db_type == "HDF5DB":
                return await self._test_hdf5(args)
            elif db_type in ("SQLDB", "JYDB"):
                return await self._test_sql(args)
            elif db_type == "ClickHouseDB":
                return await self._test_clickhouse(args)
            elif db_type == "MongoDB":
                return await self._test_mongodb(args)
            elif db_type == "Neo4jDB":
                return await self._test_neo4j(args)
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"不支持的数据库类型: {db_type}"
                )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"连接测试失败: {str(e)}"
            )

    async def _test_hdf5(self, args: dict) -> ConnectionTestResult:
        """测试 HDF5 连接"""
        import os
        main_dir = args.get("MainDir", "")
        if not main_dir:
            return ConnectionTestResult(
                success=False,
                message="未配置主目录路径"
            )
        if os.path.exists(main_dir):
            return ConnectionTestResult(
                success=True,
                message="HDF5 主目录路径有效"
            )
        else:
            return ConnectionTestResult(
                success=False,
                message=f"路径不存在: {main_dir}"
            )

    async def _test_sql(self, args: dict) -> ConnectionTestResult:
        """测试 SQL 数据库连接"""
        db_type = args.get("DBType", "MySQL")
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 3306)
        user = args.get("User", "root")
        password = args.get("Pwd", "")
        db_name = args.get("DBName", "")

        try:
            if db_type == "MySQL":
                import pymysql
                conn = pymysql.connect(
                    host=host, port=port, user=user,
                    password=password, database=db_name
                )
                conn.close()
            elif db_type == "PostgreSQL":
                import psycopg2
                conn = psycopg2.connect(
                    host=host, port=port, user=user,
                    password=password, dbname=db_name
                )
                conn.close()
            elif db_type == "SQL Server":
                import pyodbc
                conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={db_name};UID={user};PWD={password}"
                conn = pyodbc.connect(conn_str)
                conn.close()
            elif db_type == "Oracle":
                import cx_Oracle
                conn = cx_Oracle.connect(user, password, f"{host}:{port}/{db_name}")
                conn.close()
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"不支持的 SQL 数据库类型: {db_type}"
                )

            return ConnectionTestResult(
                success=True,
                message=f"{db_type} 连接成功"
            )
        except ImportError as e:
            return ConnectionTestResult(
                success=False,
                message=f"缺少数据库驱动: {str(e)}"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"连接失败: {str(e)}"
            )

    async def _test_clickhouse(self, args: dict) -> ConnectionTestResult:
        """测试 ClickHouse 连接"""
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 9000)
        user = args.get("User", "default")
        password = args.get("Pwd", "")
        database = args.get("DBName", "default")

        try:
            import clickhouse_driver
            conn = clickhouse_driver.connect(
                user=user, password=password,
                host=host, port=port, database=database
            )
            conn.close()
            return ConnectionTestResult(
                success=True,
                message="ClickHouse 连接成功"
            )
        except ImportError as e:
            return ConnectionTestResult(
                success=False,
                message=f"缺少 clickhouse-driver: {str(e)}"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"连接失败: {str(e)}"
            )

    async def _test_mongodb(self, args: dict) -> ConnectionTestResult:
        """测试 MongoDB 连接"""
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 27017)
        user = args.get("User", "root")
        password = args.get("Pwd", "")
        database = args.get("DBName", "default")

        try:
            import pymongo
            if user and password:
                uri = f"mongodb://{user}:{password}@{host}:{port}/{database}"
            else:
                uri = f"mongodb://{host}:{port}"
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            client.close()
            return ConnectionTestResult(
                success=True,
                message="MongoDB 连接成功"
            )
        except ImportError as e:
            return ConnectionTestResult(
                success=False,
                message=f"缺少 pymongo: {str(e)}"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"连接失败: {str(e)}"
            )

    async def _test_neo4j(self, args: dict) -> ConnectionTestResult:
        """测试 Neo4j 连接"""
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 7687)
        user = args.get("User", "neo4j")
        password = args.get("Pwd", "")
        database = args.get("DBName", "neo4j")

        try:
            from neo4j import GraphDatabase
            uri = f"bolt://{host}:{port}"
            driver = GraphDatabase.driver(uri, auth=(user, password))
            with driver.session(database=database) as session:
                session.run("RETURN 1")
            driver.close()
            return ConnectionTestResult(
                success=True,
                message="Neo4j 连接成功"
            )
        except ImportError as e:
            return ConnectionTestResult(
                success=False,
                message=f"缺少 neo4j driver: {str(e)}"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"连接失败: {str(e)}"
            )


# 全局连接服务实例
connection_service = ConnectionService()

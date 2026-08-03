"""
连接管理服务 — 以 QSGraphDB 为单一真相源
"""

import asyncio
from typing import Dict, List, Optional, Any

from app.models.connection import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTestResult,
    ImpactAnalysis,
    ImpactFactor,
)


class ConnectionService:
    """连接管理服务 — QSGraphDB 薄封装"""

    def __init__(self, gdb=None):
        """构造函数注入 QSGraphDB 实例

        Args:
            gdb: QSGraphDB 实例。为 None 时延迟初始化（用于模块级单例）。
        """
        self._gdb = gdb

    @property
    def gdb(self):
        """延迟获取 QSGraphDB 实例"""
        if self._gdb is None:
            from QSExt.QSRegistry.QSGraphDB import QSGraphDB
            self._gdb = QSGraphDB()
            self._gdb.connect()
        return self._gdb

    # ─── FactorDB 工厂 ────────────────────────────────────────────

    def _create_fdb_sync(self, db_type: str, args: dict, name: str = ""):
        """根据 db_type + args 创建并连接 FactorDB 实例"""
        # Name 在 __QS_ArgClass__ 中是 frozen 字段，必须在构造时传入
        if name:
            args = {**args, "Name": name}
        if db_type == "HDF5DB":
            from QuantStudio.Factor.HDF5DB import HDF5DB
            db = HDF5DB(args=args)
        elif db_type == "SQLDB":
            from QuantStudio.Factor.SQLDB import SQLDB
            db = SQLDB(args=args)
        elif db_type == "JYDB":
            from QuantStudio.Factor.JYDB import JYDB
            db = JYDB(args=args)
        elif db_type == "ClickHouseDB":
            from QSExt.Factor.ClickHouseDB import ClickHouseDB
            db = ClickHouseDB(args=args)
        elif db_type == "MongoDB":
            from QSExt.Factor.MongoDB import MongoDB
            db = MongoDB(args=args)
        elif db_type == "Neo4jDB":
            from QSExt.Factor.Neo4jDB import Neo4jDB
            db = Neo4jDB(args=args)
        elif db_type == "DuckDB":
            from QSExt.Factor.DuckDB import DuckDB
            db = DuckDB(args=args)
        elif db_type == "SQLite3DB":
            from QSExt.Factor.SQLite3DB import SQLite3DB
            db = SQLite3DB(args=args)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
        db.connect()
        return db

    async def _build_fdb(self, req: ConnectionCreate) -> Any:
        """异步创建并连接 FactorDB 实例"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._create_fdb_sync, req.db_type, req.args, req.name
        )

    # ─── 连接 CRUD ─────────────────────────────────────────────────

    def list_connections(self) -> List[ConnectionResponse]:
        """获取所有连接"""
        fdb_list = self.gdb.listFactorDBs()
        result = []
        for node in fdb_list:
            qsid = node.get("QSID", "")
            if not qsid:
                # 跳过没有 QSID 的旧节点（迁移前创建的）
                continue
            result.append(ConnectionResponse(
                qsid=qsid,
                name=node.get("Name", ""),
                db_type=node.get("DBType", ""),
                description=node.get("Description"),
                args=node.get("Args", {}),
                status="disconnected",
                created_at=node.get("CreatedAt"),
                updated_at=node.get("UpdatedAt"),
            ))
        return result

    def get_connection(self, qsid: str) -> Optional[ConnectionResponse]:
        """获取单个连接"""
        node = self.gdb.getFactorDB(qsid)
        if not node:
            return None
        return ConnectionResponse(
            qsid=node.get("QSID", ""),
            name=node.get("Name", ""),
            db_type=node.get("DBType", ""),
            description=node.get("Description"),
            args={},
            status="disconnected",
            created_at=node.get("CreatedAt"),
            updated_at=node.get("UpdatedAt"),
        )

    async def create_connection(self, req: ConnectionCreate) -> ConnectionResponse:
        """创建连接

        先创建 FactorDB 实例并 connect → 检查 QSID 是否已存在 →
        通过 QSGraphDB 注册 → 返回含 QSID 的响应。
        """
        fdb = await self._build_fdb(req)
        qsid = fdb._QSArgs.QSID

        # 检查 QSID 是否已存在
        existing = self.gdb.getFactorDB(qsid)
        if existing:
            raise ValueError(
                f"已存在相同配置的因子库连接（QSID: {qsid}, Name: {existing.get('Name', '?')}），"
                f"请勿重复创建"
            )

        # 设置 Description（Name 已在构造时传入，为 frozen 字段不可事后赋值）
        if req.description:
            if hasattr(fdb._QSArgs, "Description"):
                fdb._QSArgs.Description = req.description
        self.gdb.registerFactorDB(fdb)

        return ConnectionResponse(
            qsid=qsid,
            name=req.name,
            db_type=req.db_type,
            description=req.description,
            args=req.args,
            status="disconnected",
        )

    async def update_connection(
        self, qsid: str, req: ConnectionUpdate
    ) -> dict:
        """更新连接

        可能返回三种结果：
        - {"action": "direct", "response": ConnectionResponse} — 直接更新成功
        - {"action": "confirm", "impact": dict, "old_qsid": str, "new_qsid": str} — QSID 变更需确认
        - {"action": "blocked", "message": str} — 冲突阻止
        """
        existing = self.gdb.getFactorDB(qsid)
        if not existing:
            return None

        # 合并新旧参数
        new_name = req.name if req.name is not None else existing.get("Name", "")
        new_db_type = existing.get("DBType", "")
        new_description = req.description if req.description is not None else existing.get("Description")

        # 用新参数构造 FactorDB 实例（Name 在构造时传入）
        create_req = ConnectionCreate(
            name=new_name,
            db_type=new_db_type,
            description=new_description,
            args=req.args if req.args is not None else {},
        )
        fdb = await self._build_fdb(create_req)
        new_qsid = fdb._QSArgs.QSID

        if new_qsid == qsid:
            # QSID 不变：直接更新节点属性
            if new_description and hasattr(fdb._QSArgs, "Description"):
                fdb._QSArgs.Description = new_description
            self.gdb.registerFactorDB(fdb)
            return {
                "action": "direct",
                "response": ConnectionResponse(
                    qsid=new_qsid,
                    name=new_name,
                    db_type=new_db_type,
                    description=new_description,
                    args=req.args if req.args is not None else {},
                    status="disconnected",
                )
            }
        else:
            # QSID 变化：先检查冲突
            conflict = self.gdb.getFactorDB(new_qsid)
            if conflict:
                return {
                    "action": "blocked",
                    "message": (
                        f"新参数与已有因子库连接（Name: {conflict.get('Name', '?')}, "
                        f"QSID: {new_qsid}）冲突，请调整参数避免冲突"
                    )
                }

            # 查询影响范围
            impact = self.gdb.getImpactAnalysis(qsid)
            return {
                "action": "confirm",
                "impact": impact,
                "old_qsid": qsid,
                "new_qsid": new_qsid,
            }

    def confirm_update_connection(self, old_qsid: str, new_qsid: str,
                                   name: str, db_type: str,
                                   description: Optional[str],
                                   args: dict) -> ConnectionResponse:
        """确认 QSID 变更的更新操作

        创建新节点 → 迁移因子表关系到新节点 → 删除旧节点。
        """
        # 先构建并注册新 FactorDB
        from app.models.connection import ConnectionCreate
        create_req = ConnectionCreate(
            name=name, db_type=db_type, description=description, args=args
        )
        # 同步创建 FactorDB（Name 在构造时传入）
        fdb = self._create_fdb_sync(db_type, args, name=name)
        if description and hasattr(fdb._QSArgs, "Description"):
            fdb._QSArgs.Description = description
        self.gdb.registerFactorDB(fdb)

        # 迁移因子表关系到新节点
        table_results = self.gdb._runCypher(
            """
            MATCH (d:`因子库` {QSID: $old_qsid})<-[:`属于因子库`]-(t:`因子表`)
            RETURN t.QSID AS QSID
            """,
            {"old_qsid": old_qsid}
        )
        for r in table_results:
            self.gdb._runCypher(
                """
                MATCH (t:`因子表` {QSID: $t_qsid})
                MATCH (d_new:`因子库` {QSID: $new_qsid})
                MATCH (d_old:`因子库` {QSID: $old_qsid})
                MERGE (t)-[:`属于因子库`]->(d_new)
                WITH t, d_old
                MATCH (t)-[r:`属于因子库`]->(d_old)
                DELETE r
                """,
                {"t_qsid": r["QSID"], "new_qsid": new_qsid, "old_qsid": old_qsid}
            )

        # 删除旧因子库节点
        self.gdb._runCypher(
            "MATCH (d:`因子库` {QSID: $old_qsid}) DETACH DELETE d",
            {"old_qsid": old_qsid}
        )

        # 清理旧 QSID 的内存注册表
        self.gdb._FactorDBRegistry.pop(old_qsid, None)

        return ConnectionResponse(
            qsid=new_qsid,
            name=name,
            db_type=db_type,
            description=description,
            args=args,
            status="disconnected",
        )

    def delete_connection(self, qsid: str) -> dict:
        """删除连接前查询影响范围"""
        return self.gdb.getImpactAnalysis(qsid)

    def confirm_delete_connection(self, qsid: str, factor_service=None) -> int:
        """确认删除连接（执行级联删除）

        Args:
            qsid: 因子库 QSID
            factor_service: FactorService 实例，用于断开连接

        Returns:
            删除的节点总数
        """
        # 断开 FactorService 中的连接
        if factor_service and qsid in factor_service._factor_dbs:
            db = factor_service._factor_dbs.pop(qsid, None)
            if db:
                try:
                    db.disconnect()
                except Exception:
                    pass

        return self.gdb.deleteFactorDB(qsid)

    def get_impact(self, qsid: str) -> dict:
        """获取删除影响范围"""
        return self.gdb.getImpactAnalysis(qsid)

    # ─── 连接测试 ──────────────────────────────────────────────────

    async def test_connection(self, conn_id: str = None, *,
                              db_type: str = None,
                              args: dict = None) -> ConnectionTestResult:
        """测试连接（支持按 conn_id 或直接传 db_type + args）

        瞬时连接测试，不写入图数据库。
        """
        if conn_id and not db_type:
            node = self.gdb.getFactorDB(conn_id)
            if not node:
                return ConnectionTestResult(success=False, message="连接不存在")
            db_type = node.get("DBType", "")

        if not db_type:
            return ConnectionTestResult(success=False, message="未指定数据库类型")
        if not args:
            args = {}

        try:
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
            elif db_type in ("DuckDB", "SQLite3DB"):
                return await self._test_file_db(db_type, args)
            else:
                return ConnectionTestResult(
                    success=False, message=f"不支持的数据库类型: {db_type}"
                )
        except Exception as e:
            return ConnectionTestResult(
                success=False, message=f"连接测试失败: {str(e)}"
            )

    async def _test_hdf5(self, args: dict) -> ConnectionTestResult:
        import os
        main_dir = args.get("MainDir", "")
        if not main_dir:
            return ConnectionTestResult(success=False, message="未配置主目录路径")
        if os.path.exists(main_dir):
            return ConnectionTestResult(success=True, message="HDF5 主目录路径有效")
        else:
            return ConnectionTestResult(success=False, message=f"路径不存在: {main_dir}")

    async def _test_sql(self, args: dict) -> ConnectionTestResult:
        db_type = args.get("DBType", "MySQL")
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 3306)
        user = args.get("User", "root")
        password = args.get("Pwd", "")
        db_name = args.get("DBName", "")
        try:
            if db_type == "MySQL":
                import pymysql
                conn = pymysql.connect(host=host, port=port, user=user,
                                       password=password, database=db_name)
                conn.close()
            elif db_type == "PostgreSQL":
                import psycopg2
                conn = psycopg2.connect(host=host, port=port, user=user,
                                        password=password, dbname=db_name)
                conn.close()
            elif db_type == "SQL Server":
                import pyodbc
                conn_str = (f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                            f"SERVER={host},{port};DATABASE={db_name};"
                            f"UID={user};PWD={password}")
                conn = pyodbc.connect(conn_str)
                conn.close()
            elif db_type == "Oracle":
                import cx_Oracle
                conn = cx_Oracle.connect(user, password, f"{host}:{port}/{db_name}")
                conn.close()
            else:
                return ConnectionTestResult(
                    success=False, message=f"不支持的 SQL 数据库类型: {db_type}"
                )
            return ConnectionTestResult(success=True, message=f"{db_type} 连接成功")
        except ImportError as e:
            return ConnectionTestResult(success=False, message=f"缺少数据库驱动: {str(e)}")
        except Exception as e:
            return ConnectionTestResult(success=False, message=f"连接失败: {str(e)}")

    async def _test_clickhouse(self, args: dict) -> ConnectionTestResult:
        host = args.get("IPAddr", "127.0.0.1")
        port = args.get("Port", 9000)
        user = args.get("User", "default")
        password = args.get("Pwd", "")
        database = args.get("DBName", "default")
        try:
            import clickhouse_driver
            conn = clickhouse_driver.connect(
                user=user, password=password, host=host, port=port, database=database
            )
            conn.close()
            return ConnectionTestResult(success=True, message="ClickHouse 连接成功")
        except ImportError as e:
            return ConnectionTestResult(success=False, message=f"缺少 clickhouse-driver: {str(e)}")
        except Exception as e:
            return ConnectionTestResult(success=False, message=f"连接失败: {str(e)}")

    async def _test_mongodb(self, args: dict) -> ConnectionTestResult:
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
            return ConnectionTestResult(success=True, message="MongoDB 连接成功")
        except ImportError as e:
            return ConnectionTestResult(success=False, message=f"缺少 pymongo: {str(e)}")
        except Exception as e:
            return ConnectionTestResult(success=False, message=f"连接失败: {str(e)}")

    async def _test_neo4j(self, args: dict) -> ConnectionTestResult:
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
            return ConnectionTestResult(success=True, message="Neo4j 连接成功")
        except ImportError as e:
            return ConnectionTestResult(success=False, message=f"缺少 neo4j driver: {str(e)}")
        except Exception as e:
            return ConnectionTestResult(success=False, message=f"连接失败: {str(e)}")

    async def _test_file_db(self, db_type: str, args: dict) -> ConnectionTestResult:
        import os
        file_path = args.get("DBFile", args.get("MainDir", ""))
        if file_path:
            parent = os.path.dirname(file_path)
            if not parent or os.path.exists(parent):
                return ConnectionTestResult(success=True, message=f"{db_type} 文件路径有效")
        return ConnectionTestResult(success=False, message=f"文件路径无效: {file_path}")


# 全局连接服务实例（延迟初始化 QSGraphDB）
connection_service = ConnectionService()

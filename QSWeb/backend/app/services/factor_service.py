"""
因子数据服务

桥接 QuantStudio 和 Web API
"""

import os
import sys
from typing import List, Optional, Dict, Any
from datetime import date
from pathlib import Path

from app.models.factor import (
    FactorInfo,
    FactorTableInfo,
    FactorDBInfo,
    FactorDataResponse
)
from app.services.connection_service import connection_service
from app.core.config import settings


class FactorService:
    """因子数据服务"""

    def __init__(self):
        self._factor_dbs: Dict[str, Any] = {}  # 缓存的 FactorDB 实例

    def _get_factor_db(self, conn_id: str):
        """获取 FactorDB 实例"""
        if conn_id in self._factor_dbs:
            return self._factor_dbs[conn_id]

        conn = connection_service.get_connection(conn_id)
        if not conn:
            raise ValueError(f"连接不存在: {conn_id}")

        db_type = conn.db_type
        config = conn.config

        try:
            # 动态导入 QuantStudio 模块并创建实例
            if db_type == "HDF5DB":
                from QuantStudio.Factor.HDF5DB import HDF5DB
                db = HDF5DB(args={"MainDir": config.get("db_path", "")})

            elif db_type == "SQLDB":
                from QuantStudio.Factor.SQLDB import SQLDB
                db = SQLDB(args={
                    "DBType": config.get("db_type", "MySQL"),
                    "DBName": config.get("db_name", ""),
                    "IPAddr": config.get("host", "127.0.0.1"),
                    "Port": config.get("port", 3306),
                    "User": config.get("user", "root"),
                    "Pwd": config.get("password", ""),
                })

            elif db_type == "ClickHouseDB":
                from QSExt.Factor.ClickHouseDB import ClickHouseDB
                db = ClickHouseDB(args={
                    "DBName": config.get("database", "default"),
                    "IPAddr": config.get("host", "127.0.0.1"),
                    "Port": config.get("port", 9000),
                    "User": config.get("user", "default"),
                    "Pwd": config.get("password", ""),
                })

            elif db_type == "MongoDB":
                from QSExt.Factor.MongoDB import MongoDB
                db = MongoDB(args={
                    "DBName": config.get("database", "default"),
                    "IPAddr": config.get("host", "127.0.0.1"),
                    "Port": config.get("port", 27017),
                    "User": config.get("user", "root"),
                    "Pwd": config.get("password", ""),
                })

            elif db_type == "Neo4jDB":
                from QSExt.Factor.Neo4jDB import Neo4jDB
                db = Neo4jDB(args={
                    "DBName": config.get("database", "neo4j"),
                    "IPAddr": config.get("host", "127.0.0.1"),
                    "Port": config.get("port", 7687),
                    "User": config.get("user", "neo4j"),
                    "Pwd": config.get("password", ""),
                })

            else:
                raise ValueError(f"不支持的数据库类型: {db_type}")

            # 连接数据库
            db.connect()
            self._factor_dbs[conn_id] = db
            return db

        except ImportError as e:
            raise ValueError(f"缺少依赖: {str(e)}")
        except Exception as e:
            raise ValueError(f"连接失败: {str(e)}")

    async def get_tables(self, conn_id: str) -> List[FactorTableInfo]:
        """获取因子表列表"""
        db = self._get_factor_db(conn_id)
        conn = connection_service.get_connection(conn_id)
        tables = []

        for table_name in db.TableNames:
            try:
                ft = db.getTable(table_name)
                tables.append(FactorTableInfo(
                    name=table_name,
                    db_name=conn.name,
                    conn_id=conn_id,
                    factor_count=len(ft.FactorNames) if hasattr(ft, 'FactorNames') else None
                ))
            except Exception:
                tables.append(FactorTableInfo(
                    name=table_name,
                    db_name=conn.name,
                    conn_id=conn_id
                ))

        return tables

    async def get_factors(
        self,
        conn_id: str,
        table_name: str
    ) -> List[FactorInfo]:
        """获取因子列表"""
        db = self._get_factor_db(conn_id)
        conn = connection_service.get_connection(conn_id)

        try:
            ft = db.getTable(table_name)
            factors = []

            for factor_name in ft.FactorNames:
                try:
                    # 获取因子元数据
                    meta = ft.getFactorMetaData(factor_names=[factor_name])

                    factors.append(FactorInfo(
                        name=factor_name,
                        table_name=table_name,
                        db_name=conn.name,
                        conn_id=conn_id,
                        description=meta.get("Description", [None])[0] if meta else None,
                        data_type=meta.get("DataType", [None])[0] if meta else None
                    ))
                except Exception:
                    factors.append(FactorInfo(
                        name=factor_name,
                        table_name=table_name,
                        db_name=conn.name,
                        conn_id=conn_id
                    ))

            return factors

        except Exception as e:
            raise ValueError(f"获取因子列表失败: {str(e)}")

    async def get_factor_data(
        self,
        conn_id: str,
        table_name: str,
        factor_names: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        ids: Optional[List[str]] = None,
        limit: int = 100
    ) -> FactorDataResponse:
        """获取因子数据"""
        db = self._get_factor_db(conn_id)

        try:
            ft = db.getTable(table_name)

            # 获取日期范围
            if start_date and end_date:
                dts = ft.getDateTime(
                    ifactor_name=factor_names[0],
                    iid=None,
                    start_dt=start_date,
                    end_dt=end_date
                )
            else:
                dts = ft.getDateTime(
                    ifactor_name=factor_names[0],
                    iid=None
                )

            # 限制返回的数据量
            if len(dts) > limit:
                dts = dts[-limit:]  # 返回最新的数据

            # 获取 ID 列表
            if not ids:
                if dts:
                    ids = ft.getID(
                        ifactor_name=factor_names[0],
                        idt=dts[-1]
                    )
                else:
                    ids = []

            # 限制 ID 数量
            if len(ids) > 100:
                ids = ids[:100]

            # 读取数据
            data = ft.readData(
                factor_names=factor_names,
                ids=ids,
                dts=dts
            )

            # 转换为响应格式
            # Panel 对象需要特殊处理
            if hasattr(data, 'to_frame'):
                # Panel 转 DataFrame
                df = data.to_frame()
                df.index.names = ['datetime', 'code']
            elif hasattr(data, 'to_dict'):
                df = data
            else:
                # 尝试直接使用
                df = data

            # 处理 MultiIndex 情况
            if hasattr(df, 'index') and hasattr(df.index, 'levels'):
                # MultiIndex，重置索引以便前端显示
                df = df.reset_index()

            # 限制返回的行数
            if len(df) > limit:
                df = df.head(limit)

            # 转换 Timestamp 为字符串
            for col in df.columns:
                if hasattr(df[col], 'dt'):
                    df[col] = df[col].astype(str)

            return FactorDataResponse(
                data=df.to_dict() if hasattr(df, 'to_dict') else {},
                columns=list(df.columns) if hasattr(df, 'columns') else [],
                index=[str(dt) for dt in df.index] if hasattr(df, 'index') else [],
                total_rows=len(df) if hasattr(df, '__len__') else 0,
                total_columns=len(df.columns) if hasattr(df, 'columns') else 0
            )

        except Exception as e:
            raise ValueError(f"获取因子数据失败: {str(e)}")

    async def get_factor_metadata(
        self,
        conn_id: str,
        table_name: str,
        factor_name: str
    ) -> Dict[str, Any]:
        """获取因子元数据"""
        db = self._get_factor_db(conn_id)

        try:
            ft = db.getTable(table_name)
            meta = ft.getFactorMetaData(factor_names=[factor_name])
            return meta
        except Exception as e:
            raise ValueError(f"获取因子元数据失败: {str(e)}")

    def disconnect_all(self):
        """断开所有连接"""
        for db in self._factor_dbs.values():
            try:
                db.disconnect()
            except Exception:
                pass
        self._factor_dbs.clear()


# 全局因子服务实例
factor_service = FactorService()

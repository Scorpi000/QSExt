"""
因子数据服务

桥接 QuantStudio 和 Web API
"""

import os
import sys
import datetime
import pandas as pd
from typing import List, Optional, Dict, Any
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
        args = conn.args

        try:
            # 动态导入 QuantStudio 模块并创建实例，args 直接传递原生参数
            if db_type == "HDF5DB":
                from QuantStudio.Factor.HDF5DB import HDF5DB
                db = HDF5DB(args=args)

            elif db_type == "SQLDB":
                from QuantStudio.Factor.SQLDB import SQLDB
                db = SQLDB(args=args)

            elif db_type == "ClickHouseDB":
                from QSExt.Factor.ClickHouseDB import ClickHouseDB
                db = ClickHouseDB(args=args)

            elif db_type == "MongoDB":
                from QSExt.Factor.MongoDB import MongoDB
                db = MongoDB(args=args)

            elif db_type == "Neo4jDB":
                from QSExt.Factor.Neo4jDB import Neo4jDB
                db = Neo4jDB(args=args)

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
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        ids: Optional[List[str]] = None,
        limit: int = 100
    ) -> FactorDataResponse:
        """获取因子数据"""
        db = self._get_factor_db(conn_id)

        try:
            ft = db.getTable(table_name)

            # 获取日期范围（date 转 datetime）
            if start_date and end_date:
                start_dt = datetime.datetime.combine(start_date, datetime.datetime.min.time())
                end_dt = datetime.datetime.combine(end_date, datetime.datetime.min.time())
                dts = ft.getDateTime(
                    ifactor_name=factor_names[0],
                    iid=None,
                    start_dt=start_dt,
                    end_dt=end_dt
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
                ids = ft.getID(ifactor_name=factor_names[0], idt=None)

            # 限制 ID 数量
            if len(ids) > 100:
                ids = ids[:100]

            # 读取数据
            data = ft.readData(
                factor_names=factor_names,
                ids=ids if ids else None,
                dts=dts
            )

            # 转换为响应格式
            # Panel 对象需要特殊处理（自定义 Panel 的 to_frame 有 bug）
            if hasattr(data, 'items') and hasattr(data, 'major_axis'):
                # Panel → 逐因子取 DataFrame 后 stack 成长表
                frames = []
                for factor_name in data.items:
                    factor_df = data[factor_name]  # DataFrame (major_axis × minor_axis)
                    stacked = factor_df.stack(future_stack=True)
                    stacked.name = factor_name
                    frames.append(stacked)
                if frames:
                    df = frames[0].to_frame() if len(frames) == 1 else pd.concat(frames, axis=1)
                    df = df.reset_index()
                    # 统一列名：level_0=datetime, level_1=code
                    col_map = {df.columns[0]: 'datetime', df.columns[1]: 'code'}
                    df = df.rename(columns=col_map)
                else:
                    df = pd.DataFrame()
            elif hasattr(data, 'to_frame'):
                df = data.to_frame()
                df.index.names = ['datetime', 'code']
                df = df.reset_index()
            elif hasattr(data, 'to_dict'):
                df = data
            else:
                df = data

            # 处理 MultiIndex 情况（兜底）
            if hasattr(df, 'index') and hasattr(df.index, 'levels') and len(df.index.levels) > 1:
                df = df.reset_index()

            # 限制返回的行数
            if len(df) > limit:
                df = df.head(limit)

            # 转换不可直接 JSON 序列化的列为字符串，NaN/NaT/None 保留为 None
            for col in df.columns:
                if hasattr(df[col], 'dt'):
                    df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x))
                elif df[col].dtype == object:
                    df[col] = df[col].where(df[col].notna(), None).apply(
                        lambda x: None if x is None else str(x)
                    )

            return FactorDataResponse(
                data=df.to_dict() if hasattr(df, 'to_dict') else {},
                columns=list(df.columns) if hasattr(df, 'columns') else [],
                index=[str(dt) for dt in df.index] if hasattr(df, 'index') else [],
                total_rows=len(df) if hasattr(df, '__len__') else 0,
                total_columns=len(df.columns) if hasattr(df, 'columns') else 0
            )

        except Exception as e:
            raise ValueError(f"获取因子数据失败: {str(e)}")

    async def get_factor_stats(
        self,
        conn_id: str,
        table_name: str,
        factor_name: str
    ) -> Dict[str, Any]:
        """获取因子统计信息（ID数量、时点数量、起止ID、起止时间）"""
        db = self._get_factor_db(conn_id)

        try:
            ft = db.getTable(table_name)

            # 获取全量 ID 和时点
            ids = ft.getID(ifactor_name=factor_name, idt=None)
            dts = ft.getDateTime(ifactor_name=factor_name, iid=None)

            return {
                "id_count": len(ids) if ids else 0,
                "dt_count": len(dts) if dts else 0,
                "first_id": ids[0] if ids else None,
                "last_id": ids[-1] if ids else None,
                "first_dt": str(dts[0]) if dts else None,
                "last_dt": str(dts[-1]) if dts else None,
            }
        except Exception as e:
            raise ValueError(f"获取因子统计信息失败: {str(e)}")

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
            # 转换为可序列化的 dict
            result = {}
            for key, val in meta.items():
                if hasattr(val, 'iloc'):
                    result[key] = str(val.iloc[0]) if len(val) > 0 else None
                else:
                    result[key] = str(val) if val is not None else None
            return result
        except Exception as e:
            raise ValueError(f"获取因子元数据失败: {str(e)}")

    async def get_table_metadata(
        self,
        conn_id: str,
        table_name: str
    ) -> Dict[str, Any]:
        """获取因子表元数据"""
        db = self._get_factor_db(conn_id)

        try:
            ft = db.getTable(table_name)
            meta = ft.getMetaData()
            # 转换为可序列化的 dict
            result = {}
            if hasattr(meta, 'items'):
                for key, val in meta.items():
                    result[key] = str(val) if val is not None else None
            return result
        except Exception as e:
            raise ValueError(f"获取因子表元数据失败: {str(e)}")

    def disconnect(self, conn_id: str):
        """断开指定连接并清除缓存"""
        db = self._factor_dbs.pop(conn_id, None)
        if db is not None:
            try:
                db.disconnect()
            except Exception:
                pass

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

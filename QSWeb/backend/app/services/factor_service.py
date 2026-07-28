"""
因子数据服务

桥接 QuantStudio 和 Web API
"""

import asyncio
import datetime
import pandas as pd
from typing import List, Optional, Dict, Any

from app.models.factor import (
    FactorInfo,
    FactorTableInfo,
    FactorDBInfo,
    FactorDataResponse
)
from app.services.connection_service import connection_service


class FactorService:
    """因子数据服务"""

    def __init__(self):
        self._factor_dbs: Dict[str, Any] = {}  # 缓存的 FactorDB 实例

    def _create_db_sync(self, db_type: str, args: dict):
        """同步创建并连接 FactorDB 实例（在 executor 中运行）"""
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
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
        db.connect()
        return db

    async def _get_factor_db(self, conn_id: str):
        """获取 FactorDB 实例（connect 阶段在 executor 中运行）"""
        if conn_id in self._factor_dbs:
            return self._factor_dbs[conn_id]

        conn = connection_service.get_connection(conn_id)
        if not conn:
            raise ValueError(f"连接不存在: {conn_id}")

        loop = asyncio.get_running_loop()
        try:
            db = await loop.run_in_executor(
                None,
                self._create_db_sync,
                conn.db_type,
                conn.args
            )
            self._factor_dbs[conn_id] = db
            return db
        except ImportError as e:
            raise ValueError(f"缺少依赖: {str(e)}")
        except Exception as e:
            raise ValueError(f"连接失败: {str(e)}")

    async def get_tables(self, conn_id: str) -> List[FactorTableInfo]:
        """获取因子表列表"""
        db = await self._get_factor_db(conn_id)
        conn = connection_service.get_connection(conn_id)

        def _sync():
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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_factors(
        self,
        conn_id: str,
        table_name: str
    ) -> List[FactorInfo]:
        """获取因子列表"""
        db = await self._get_factor_db(conn_id)
        conn = connection_service.get_connection(conn_id)

        def _sync():
            try:
                ft = db.getTable(table_name)
                factors = []
                for factor_name in ft.FactorNames:
                    try:
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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

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
        db = await self._get_factor_db(conn_id)

        def _sync():
            try:
                ft = db.getTable(table_name)

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

                if len(dts) > limit:
                    dts = dts[-limit:]

                _ids = ids
                if not _ids:
                    _ids = ft.getID(ifactor_name=factor_names[0], idt=None)

                if len(_ids) > 100:
                    _ids = _ids[:100]

                data = ft.readData(
                    factor_names=factor_names,
                    ids=_ids if _ids else None,
                    dts=dts
                )

                # 转换为响应格式
                if hasattr(data, 'items') and hasattr(data, 'major_axis'):
                    frames = []
                    for fname in data.items:
                        factor_df = data[fname]
                        stacked = factor_df.stack(future_stack=True)
                        stacked.name = fname
                        frames.append(stacked)
                    if frames:
                        df = frames[0].to_frame() if len(frames) == 1 else pd.concat(frames, axis=1)
                        df = df.reset_index()
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

                if hasattr(df, 'index') and hasattr(df.index, 'levels') and len(df.index.levels) > 1:
                    df = df.reset_index()

                if len(df) > limit:
                    df = df.head(limit)

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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_factor_stats(
        self,
        conn_id: str,
        table_name: str,
        factor_name: str
    ) -> Dict[str, Any]:
        """获取因子统计信息（ID数量、时点数量、起止ID、起止时间）"""
        db = await self._get_factor_db(conn_id)

        def _sync():
            try:
                ft = db.getTable(table_name)
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

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_factor_metadata(
        self,
        conn_id: str,
        table_name: str,
        factor_name: str
    ) -> Dict[str, Any]:
        """获取因子元数据"""
        db = await self._get_factor_db(conn_id)

        def _sync():
            try:
                ft = db.getTable(table_name)
                meta = ft.getFactorMetaData(factor_names=[factor_name])
                result = {}
                for key, val in meta.items():
                    if hasattr(val, 'iloc'):
                        result[key] = str(val.iloc[0]) if len(val) > 0 else None
                    else:
                        result[key] = str(val) if val is not None else None
                return result
            except Exception as e:
                raise ValueError(f"获取因子元数据失败: {str(e)}")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_table_metadata(
        self,
        conn_id: str,
        table_name: str
    ) -> Dict[str, Any]:
        """获取因子表元数据"""
        db = await self._get_factor_db(conn_id)

        def _sync():
            try:
                ft = db.getTable(table_name)
                meta = ft.getMetaData()
                result = {}
                if hasattr(meta, 'items'):
                    for key, val in meta.items():
                        result[key] = str(val) if val is not None else None
                return result
            except Exception as e:
                raise ValueError(f"获取因子表元数据失败: {str(e)}")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def disconnect(self, conn_id: str):
        """断开指定连接并清除缓存"""
        db = self._factor_dbs.pop(conn_id, None)
        if db is not None:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, db.disconnect)
            except Exception:
                pass

    async def rename_table(self, conn_id: str, old_name: str, new_name: str) -> Dict[str, Any]:
        """重命名因子表"""
        db = await self._get_factor_db(conn_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.renameTable(old_name, new_name))
        return {"message": f"表 '{old_name}' 已重命名为 '{new_name}'"}

    async def delete_tables(self, conn_id: str, table_names: List[str]) -> Dict[str, Any]:
        """批量删除因子表"""
        db = await self._get_factor_db(conn_id)

        def _sync():
            for name in table_names:
                db.deleteTable(name)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync)
        return {"message": f"已删除 {len(table_names)} 个表"}

    async def update_table_metadata(self, conn_id: str, table_name: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """更新因子表元数据"""
        db = await self._get_factor_db(conn_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.setTableMetaData(table_name, meta_data=metadata))
        return {"message": f"表 '{table_name}' 元数据已更新"}

    async def rename_factor(self, conn_id: str, table_name: str, old_name: str, new_name: str) -> Dict[str, Any]:
        """重命名因子"""
        db = await self._get_factor_db(conn_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.renameFactor(table_name, old_name, new_name))
        return {"message": f"因子 '{old_name}' 已重命名为 '{new_name}'"}

    async def delete_factors(self, conn_id: str, table_name: str, factor_names: List[str]) -> Dict[str, Any]:
        """批量删除因子"""
        db = await self._get_factor_db(conn_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.deleteFactor(table_name, factor_names))
        return {"message": f"已从表 '{table_name}' 删除 {len(factor_names)} 个因子"}

    async def update_factor_metadata(self, conn_id: str, table_name: str, factor_name: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """更新因子元数据"""
        db = await self._get_factor_db(conn_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.setFactorMetaData(table_name, factor_name, meta_data=metadata))
        return {"message": f"因子 '{factor_name}' 元数据已更新"}

    async def disconnect_all(self):
        """断开所有连接"""
        loop = asyncio.get_running_loop()
        for db in self._factor_dbs.values():
            try:
                await loop.run_in_executor(None, db.disconnect)
            except Exception:
                pass
        self._factor_dbs.clear()


# 全局因子服务实例
factor_service = FactorService()

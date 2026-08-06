"""
风险管理服务

桥接 QuantStudio RiskDB 和 Web API，管理风险库连接的生命周期。
初始定义从统一 RuntimeSettings.risk_databases 读取，运行时增删改写 Neo4j。
"""

import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.exceptions import NotFoundException, ConnectionException, ValidationException


class RiskService:
    """风险管理服务"""

    def __init__(self):
        self._risk_dbs: Dict[str, Any] = {}  # 缓存的 RiskDB 实例
        self._db_configs: Dict[str, Dict[str, Any]] = {}
        self._load_config()

    def _load_config(self):
        """从统一 RuntimeSettings 加载风险库初始配置。

        RISK_DATABASES 格式与 FACTOR_DATABASES 对齐：
        [{name, class, args, description}, ...]
        内部转为 {name: {...}} 字典便于按名查找。
        _settings_names 集合标记 settings.py 来源。
        """
        self._settings_names = set()
        try:
            rs = settings.runtime_settings
            entries = rs.risk_databases or []
            self._db_configs = {}
            for entry in entries:
                name = entry["name"]
                self._db_configs[name] = entry
                self._settings_names.add(name)
        except Exception:
            self._db_configs = {}

    def list_databases(self) -> List[Dict[str, Any]]:
        """列出已配置的风险库"""
        result = []
        for db_id, cfg in self._db_configs.items():
            source = "settings" if db_id in getattr(self, "_settings_names", set()) else "neo4j"
            result.append({
                "id": db_id,
                "name": cfg.get("name", db_id),
                "db_type": cfg.get("class", cfg.get("db_type", "HDF5RDB")),
                "description": cfg.get("description", ""),
                "connected": db_id in self._risk_dbs,
                "source": source,
            })
        return result

    def get_database(self, db_id: str) -> Dict[str, Any]:
        """获取单个风险库信息"""
        cfg = self._db_configs.get(db_id)
        if cfg is None:
            raise NotFoundException("风险库", db_id)
        return {
            "id": db_id,
            "name": cfg.get("name", db_id),
            "db_type": cfg.get("db_type", "HDF5RDB"),
            "description": cfg.get("description", ""),
            "connected": db_id in self._risk_dbs,
        }

    def create_database(self, name: str, db_type: str, args: dict, description: str = "") -> Dict[str, Any]:
        """创建风险库配置"""
        db_id = uuid.uuid4().hex[:8]
        if db_type not in ("HDF5RDB", "HDF5FRDB"):
            raise ValidationException(f"不支持的风险库类型: {db_type}")
        self._db_configs[db_id] = {
            "name": name,
            "db_type": db_type,
            "description": description,
            "args": args,
        }
        return {
            "id": db_id,
            "name": name,
            "db_type": db_type,
            "description": description,
            "connected": False,
        }

    def _is_settings_source(self, db_id: str) -> bool:
        """检查风险库是否来自 settings.py。"""
        return db_id in getattr(self, "_settings_names", set())

    def update_database(self, db_id: str, name: str = None, args: dict = None, description: str = None) -> Dict[str, Any]:
        """更新风险库配置。settings 来源的不允许通过 Web UI 修改。"""
        if self._is_settings_source(db_id):
            raise ValidationException("此风险库来自 settings.py 配置文件，请在配置文件中修改后重启服务")
        cfg = self._db_configs.get(db_id)
        if cfg is None:
            raise NotFoundException("风险库", db_id)
        if name is not None:
            cfg["name"] = name
        if args is not None:
            cfg["args"] = args
        if description is not None:
            cfg["description"] = description
        self._risk_dbs.pop(db_id, None)
        return {
            "id": db_id,
            "name": cfg.get("name", db_id),
            "db_type": cfg.get("class", cfg.get("db_type", "HDF5RDB")),
            "description": cfg.get("description", ""),
            "connected": False,
        }

    def delete_database(self, db_id: str) -> bool:
        """删除风险库配置。settings 来源的不允许删除。"""
        if self._is_settings_source(db_id):
            raise ValidationException("此风险库来自 settings.py 配置文件，请在配置文件中删除后重启服务")
        if db_id not in self._db_configs:
            raise NotFoundException("风险库", db_id)
        del self._db_configs[db_id]
        self._risk_dbs.pop(db_id, None)
        return True

    async def test_database(self, db_id: str) -> Dict[str, Any]:
        """测试风险库连接"""
        cfg = self._db_configs.get(db_id)
        if cfg is None:
            raise NotFoundException("风险库", db_id)
        db_type = cfg.get("db_type", "HDF5RDB")
        args = cfg.get("args", {})
        loop = asyncio.get_running_loop()
        try:
            db = await loop.run_in_executor(None, self._create_db_sync, db_type, args)
            table_count = len(db.TableNames)
            return {"success": True, "message": f"连接成功，共 {table_count} 张风险表"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    def _create_db_sync(self, db_type: str, args: dict):
        """同步创建并连接 RiskDB 实例"""
        if db_type == "HDF5RDB":
            from QuantStudio.Risk.HDF5RDB import HDF5RDB
            db = HDF5RDB(args=args)
        elif db_type == "HDF5FRDB":
            from QuantStudio.Risk.HDF5RDB import HDF5FRDB
            db = HDF5FRDB(args=args)
        else:
            raise ValueError(f"不支持的风险库类型: {db_type}")
        db.connect()
        return db

    async def _get_risk_db(self, db_id: str):
        """获取 RiskDB 实例（connect 阶段在 executor 中运行）"""
        if db_id in self._risk_dbs:
            return self._risk_dbs[db_id]

        cfg = self._db_configs.get(db_id)
        if cfg is None:
            raise NotFoundException("风险库", db_id)

        db_type = cfg.get("db_type", "HDF5RDB")
        args = cfg.get("args", {})

        loop = asyncio.get_running_loop()
        try:
            db = await loop.run_in_executor(
                None, self._create_db_sync, db_type, args
            )
        except Exception as e:
            raise ConnectionException(f"连接风险库失败: {str(e)}")

        self._risk_dbs[db_id] = db
        return db

    async def list_tables(self, db_id: str) -> List[Dict[str, Any]]:
        """列出风险库下的所有风险表"""
        db = await self._get_risk_db(db_id)
        loop = asyncio.get_running_loop()

        def _list():
            tables = []
            for name in db.TableNames:
                rt = db.getTable(name)
                dts = rt.getDateTime()
                from QuantStudio.Risk.RiskTable import FactorRT
                is_factor = isinstance(rt, FactorRT)
                factor_count = len(rt.FactorNames) if is_factor else 0
                tables.append({
                    "name": name,
                    "is_factor_rt": is_factor,
                    "factor_count": factor_count,
                    "dt_count": len(dts),
                    "first_dt": dts[0].isoformat() if dts else None,
                    "last_dt": dts[-1].isoformat() if dts else None,
                })
            return tables

        return await loop.run_in_executor(None, _list)

    async def get_covariance(
        self, db_id: str, table_name: str, dt_str: str, limit: int = 100
    ) -> Dict[str, Any]:
        """获取协方差矩阵，默认截取前 limit 只证券"""
        import datetime as dt_mod
        db = await self._get_risk_db(db_id)
        dt_val = dt_mod.datetime.fromisoformat(dt_str)

        def _read():
            rt = db.getTable(table_name)
            panel = rt.readCov(dts=[dt_val])
            if panel.shape[0] == 0:
                return {"dt": dt_str, "ids": [], "data": [], "total": 0}
            cov_df = panel.iloc[0]
            all_ids = cov_df.index.tolist()
            total = len(all_ids)
            # 截取前 N 只
            ids = all_ids[:limit]
            sub = cov_df.iloc[:limit, :limit]
            data = []
            for i in range(len(ids)):
                for j in range(len(ids)):
                    val = sub.iloc[i, j]
                    if pd.notna(val):
                        data.append([i, j, float(val)])
            return {
                "dt": dt_str,
                "ids": [str(x) for x in ids],
                "data": data,
                "total": total,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read)

    async def get_correlation(
        self, db_id: str, table_name: str, dt_str: str, limit: int = 100
    ) -> Dict[str, Any]:
        """获取相关系数矩阵（从协方差矩阵转换），默认截取前 limit 只证券"""
        import datetime as dt_mod
        db = await self._get_risk_db(db_id)
        dt_val = dt_mod.datetime.fromisoformat(dt_str)

        def _read():
            rt = db.getTable(table_name)
            panel = rt.readCov(dts=[dt_val])
            if panel.shape[0] == 0:
                return {"dt": dt_str, "ids": [], "data": [], "total": 0}
            cov_df = panel.iloc[0]
            all_ids = cov_df.index.tolist()
            total = len(all_ids)
            # 截取前 N 只
            ids = all_ids[:limit]
            sub = cov_df.iloc[:limit, :limit]
            # 计算相关系数矩阵
            std = np.sqrt(np.diag(sub.values))
            std[std == 0] = np.nan
            corr = sub.values / np.outer(std, std)
            data = []
            for i in range(len(ids)):
                for j in range(len(ids)):
                    val = corr[i, j]
                    if pd.notna(val):
                        data.append([i, j, float(val)])
            return {
                "dt": dt_str,
                "ids": [str(x) for x in ids],
                "data": data,
                "total": total,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read)

    async def get_factor_decomposition(
        self, db_id: str, table_name: str, dt_str: str, limit: int = 100
    ) -> Dict[str, Any]:
        """获取因子风险分解，特异性风险默认截取前 limit 只证券"""
        import datetime as dt_mod
        db = await self._get_risk_db(db_id)
        dt_val = dt_mod.datetime.fromisoformat(dt_str)

        def _read():
            from QuantStudio.Risk.RiskTable import FactorRT
            rt = db.getTable(table_name)
            if not isinstance(rt, FactorRT):
                return {"error": "该风险表不是多因子风险表，无法进行因子风险分解"}

            factor_cov = rt.readFactorCov(dts=[dt_val])
            specific_risk = rt.readSpecificRisk(dts=[dt_val])
            factor_names = rt.FactorNames

            if factor_cov.shape[0] == 0:
                return {
                    "dt": dt_str,
                    "factors": [],
                    "factor_cov": {"ids": [], "data": []},
                    "specific_risk": {"ids": [], "values": [], "total": 0},
                }

            fc_df = factor_cov.iloc[0]
            f_ids = fc_df.index.tolist()

            # 因子协方差（因子数量通常少，不截断）
            factor_cov_data = []
            for i in range(len(f_ids)):
                for j in range(len(f_ids)):
                    val = fc_df.iloc[i, j]
                    if pd.notna(val):
                        factor_cov_data.append([i, j, float(val)])

            # 特异性风险，截取前 N 只
            sr = specific_risk.loc[dt_val] if dt_val in specific_risk.index else pd.Series(dtype=float)
            all_ids = sr.index.tolist()
            total = len(all_ids)
            sr_ids = all_ids[:limit]
            sr_values = [float(sr[i]) if pd.notna(sr[i]) else None for i in sr_ids]

            return {
                "dt": dt_str,
                "factors": factor_names,
                "factor_count": len(factor_names),
                "factor_cov": {
                    "ids": [str(x) for x in f_ids],
                    "data": factor_cov_data,
                },
                "specific_risk": {
                    "ids": [str(x) for x in sr_ids],
                    "values": sr_values,
                    "total": total,
                },
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read)


# 全局实例
risk_service = RiskService()

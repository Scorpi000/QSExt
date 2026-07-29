"""
全局因子池服务

支持双源因子解析（FactorDB + QSRegistry）、持久化到 QSGraphDB、
懒加载统计信息。
"""

import asyncio
from typing import Dict, List, Optional, Any

from app.models.connection import ConnectionResponse


class PoolItem:
    """池中因子项"""
    __slots__ = ("id", "qsid", "source", "label", "ref", "stats")

    def __init__(self, *, id: str, qsid: str, source: str, label: str,
                 ref: dict, stats: Optional[dict] = None):
        self.id = id
        self.qsid = qsid
        self.source = source  # "db" or "registry"
        self.label = label
        self.ref = ref  # {conn_id?, table_name?, factor_name?}
        self.stats = stats

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "qsid": self.qsid,
            "source": self.source,
            "label": self.label,
            "ref": self.ref,
            "stats": self.stats,
        }


class FactorPoolService:
    """全局因子池服务"""

    def __init__(self, gdb=None, factor_service=None):
        self._gdb = gdb
        self._factor_service = factor_service
        self._cache: Dict[str, Any] = {}  # qsid -> Factor 对象缓存

    @property
    def gdb(self):
        if self._gdb is None:
            from QSExt.QSRegistry.QSGraphDB import QSGraphDB
            self._gdb = QSGraphDB()
            self._gdb.connect()
        return self._gdb

    # ─── 因子解析 ─────────────────────────────────────────────────

    async def resolve(self, items: List[dict]) -> Dict[str, Any]:
        """双源解析因子对象

        Args:
            items: PoolItem 字典列表

        Returns:
            {pool_item_id: Factor 对象}
        """
        result = {}
        for item in items:
            pool_id = item["id"]
            qsid = item.get("qsid", "")
            source = item.get("source", "db")
            ref = item.get("ref", {})

            # registry 因子用 QSID 做缓存键，FactorDB 因子用完整路径做缓存键
            if source == "registry":
                cache_key = f"registry:{qsid}"
            else:
                cache_key = f"db:{ref.get('conn_id','')}:{ref.get('table_name','')}:{ref.get('factor_name','')}"

            if cache_key in self._cache:
                result[pool_id] = self._cache[cache_key]
                continue

            if source == "registry":
                factor = await self._resolve_from_registry(qsid)
            else:
                factor = await self._resolve_from_db(ref)
            self._cache[cache_key] = factor
            result[pool_id] = factor
        return result

    async def _resolve_from_registry(self, qsid: str):
        """从 QSRegistry 解析因子"""
        loop = asyncio.get_running_loop()

        def _sync():
            return self.gdb.reconstructFactor(qsid)

        return await loop.run_in_executor(None, _sync)

    async def _resolve_from_db(self, ref: dict):
        """从 FactorDB 解析因子"""
        if not self._factor_service:
            raise ValueError("FactorPoolService 未配置 FactorService")

        conn_id = ref.get("conn_id", "")
        table_name = ref.get("table_name", "")
        factor_name = ref.get("factor_name", "")

        db = await self._factor_service._get_factor_db(conn_id)

        loop = asyncio.get_running_loop()

        def _sync():
            ft = db.getTable(table_name)
            return ft.getFactor(factor_name)

        return await loop.run_in_executor(None, _sync)

    # ─── 统计信息（懒加载）─────────────────────────────────────────

    async def get_stats(self, item: dict) -> dict:
        """获取因子统计信息"""
        source = item.get("source", "db")
        ref = item.get("ref", {})

        if source == "db" and self._factor_service:
            conn_id = ref.get("conn_id", "")
            table_name = ref.get("table_name", "")
            factor_name = ref.get("factor_name", "")
            if conn_id and table_name and factor_name:
                stats = await self._factor_service.get_factor_stats(
                    conn_id, table_name, factor_name
                )
                return stats
        return {}

    # ─── 池持久化 ─────────────────────────────────────────────────

    async def save_pool(self, name: str, items: List[dict]) -> None:
        """保存因子池到图数据库

        1. 解析所有因子为 Factor 对象
        2. 调用 ``gdb.storeFactors`` 写入正式因子节点（含完整 DAG、算子、因子表）
        3. 创建 ``因子池`` 节点和 ``[:包含]`` 关系
        """
        resolved = await self.resolve(items)
        factors = list(resolved.values())
        if not factors:
            return
        qsids = await asyncio.get_running_loop().run_in_executor(
            None, self.gdb.storeFactors, factors
        )
        # storeFactors 返回 QSID 列表，顺序与输入一致
        self.gdb.saveFactorPool(name, list(qsids))

    def load_pool(self, name: str) -> List[dict]:
        """从图数据库加载因子池"""
        factors = self.gdb.loadFactorPool(name)
        result = []
        for f in factors:
            qsid = f.get("QSID", "")
            name_in_ft = f.get("NameInFT") or f.get("Name", "")

            # 通过关系链查找 FactorDB 来源信息
            ref = {}
            source = "registry"
            db_info = self.gdb._getFactorDBInfo(qsid)
            if db_info:
                source = "db"
                ref = {
                    "conn_id": db_info.get("fdb_qsid", ""),
                    "table_name": db_info.get("table_name", ""),
                    "factor_name": name_in_ft,
                }

            result.append({
                "id": f"{source}:{qsid}",
                "qsid": qsid,
                "source": source,
                "label": f.get("Name", qsid),
                "ref": ref,
            })
        return result

    def list_pools(self) -> List[dict]:
        """列出已保存的池子"""
        return self.gdb.listFactorPools()

    def delete_pool(self, name: str) -> bool:
        """删除已保存的池子"""
        return self.gdb.deleteFactorPool(name)

    # ─── 清理 ─────────────────────────────────────────────────────

    def cleanup_by_conn_id(self, conn_id: str, pool_items: List[dict]) -> List[dict]:
        """根据 conn_id 清理池中来自被删因子库的因子（source="db" 且未在图库中）

        Args:
            conn_id: 被删除的因子库 QSID
            pool_items: 当前池中的所有因子项

        Returns:
            清理后的因子项列表
        """
        return [
            item for item in pool_items
            if not (item.get("source") == "db" and item.get("ref", {}).get("conn_id") == conn_id)
        ]

    def cleanup_by_qsids(self, affected_qsids: set, pool_items: List[dict]) -> List[dict]:
        """根据 QSID 列表清理池中因子（source="registry" 且 QSID 在图数据库中被级联删除）

        Args:
            affected_qsids: 被级联删除的因子 QSID 集合
            pool_items: 当前池中的所有因子项

        Returns:
            清理后的因子项列表
        """
        return [
            item for item in pool_items
            if not (item.get("qsid", "") in affected_qsids)
        ]


# 全局因子池服务实例
factor_pool_service = FactorPoolService()

# 注入 FactorService 依赖（延迟导入避免循环引用）
from app.services.factor_service import factor_service as _fs
factor_pool_service._factor_service = _fs

"""
全局因子池 API
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, Body

from app.services.factor_pool_service import factor_pool_service
from app.core.exceptions import ValidationException, NotFoundException

router = APIRouter()


@router.post("/factors")
async def add_factors_to_pool(items: List[dict] = Body(..., description="要添加的因子引用列表")):
    """添加因子到池（resolve + 缓存）

    请求体示例：
    [{"id": "db:conn1:table1:factor1", "qsid": "", "source": "db",
      "label": "动量因子", "ref": {"conn_id": "qsid123", "table_name": "表1", "factor_name": "因子1"}}]
    """
    try:
        resolved = await factor_pool_service.resolve(items)
        result = []
        for item in items:
            pool_id = item["id"]
            factor = resolved.get(pool_id)
            result.append({
                "item": item,
                "resolved": factor is not None,
            })
        return {"items": result}
    except Exception as e:
        raise ValidationException(str(e))


@router.delete("/factors/{item_id}")
async def remove_factor(item_id: str):
    """从池中移除因子（仅清理缓存，不删除图数据）"""
    # 清理缓存
    keys_to_remove = [k for k in factor_pool_service._cache if item_id in k]
    for k in keys_to_remove:
        factor_pool_service._cache.pop(k, None)
    return {"message": f"已从池中移除因子: {item_id}"}


@router.post("/save")
async def save_pool(
    name: str = Query(..., description="池子名称"),
    items: List[dict] = Body(..., description="池中因子列表"),
):
    """保存因子池到图数据库"""
    try:
        await factor_pool_service.save_pool(name, items)
        return {"message": f"因子池 '{name}' 已保存"}
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/load/{name}")
async def load_pool(name: str):
    """从图数据库加载因子池"""
    items = factor_pool_service.load_pool(name)
    if not items:
        raise NotFoundException("因子池", name)
    return {"name": name, "items": items}


@router.get("/list")
async def list_pools():
    """列出已保存的因子池"""
    return factor_pool_service.list_pools()


@router.delete("/{name}")
async def delete_pool(name: str):
    """删除已保存的因子池"""
    if not factor_pool_service.delete_pool(name):
        raise NotFoundException("因子池", name)
    return {"message": f"因子池 '{name}' 已删除"}


@router.post("/factors/stats")
async def get_factor_stats(
    item: dict = Body(..., description="因子项信息"),
):
    """获取因子统计信息（懒加载）"""
    try:
        stats = await factor_pool_service.get_stats(item)
        return stats
    except Exception as e:
        raise ValidationException(str(e))


@router.post("/cleanup")
async def cleanup_pool(
    conn_id: Optional[str] = Query(None, description="被删除的因子库 QSID"),
    affected_qsids: Optional[List[str]] = Body(None, description="被级联删除的因子 QSID 列表"),
    pool_items: List[dict] = Body(..., description="当前池中因子列表"),
):
    """删除因子库后清理池子"""
    items = pool_items
    if conn_id:
        items = factor_pool_service.cleanup_by_conn_id(conn_id, items)
    if affected_qsids:
        items = factor_pool_service.cleanup_by_qsids(set(affected_qsids), items)
    return {"items": items}

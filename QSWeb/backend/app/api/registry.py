"""
QSRegistry API

因子搜索、DAG 可视化、算子列表等。
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query

from app.services.registry_service import registry_service, _get_args_schema_sync
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter()


@router.get("/factors/search")
async def search_factors(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
):
    """关键词搜索因子"""
    try:
        return await registry_service.search_factors(q, limit)
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/factors/search/semantic")
async def semantic_search(
    q: str = Query(..., description="自然语言描述"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
):
    """语义搜索因子（Ollama 嵌入向量检索）"""
    try:
        return await registry_service.semantic_search(q, limit)
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/factors/{qsid}")
async def get_factor_detail(qsid: str):
    """获取因子详情（元信息 + 依赖 + 统计）"""
    try:
        result = await registry_service.get_factor_detail(qsid)
        if result is None:
            raise NotFoundException("因子", qsid)
        return result
    except NotFoundException:
        raise
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/factors/{qsid}/dag")
async def get_factor_dag(qsid: str):
    """获取因子依赖 DAG 数据（从 Neo4j 获取依赖关系，已计算布局）"""
    try:
        return await registry_service.get_factor_dag(qsid)
    except ValueError as e:
        raise NotFoundException("因子", qsid)
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/operators")
async def list_operators(
    operator_type: Optional[str] = Query(None, description="算子类型筛选：Point/Time/Section/Panel"),
):
    """获取已注册算子列表"""
    try:
        return await registry_service.list_operators(operator_type)
    except Exception as e:
        raise ValidationException(str(e))


@router.get("/args/{class_name:path}/schema")
async def get_args_schema(class_name: str):
    """
    获取 QSArgs JSON Schema（基于 Pydantic model_json_schema()）

    class_name 格式: module.path.ClassName 或 module.path:ClassName
    例如: QuantStudio.Factor.Operator.TimeOperator.TimeDifference
    """
    try:
        return await registry_service.get_args_schema(class_name)
    except ValueError as e:
        raise NotFoundException("类", f"{class_name}（{e}）")
    except Exception as e:
        raise ValidationException(str(e))

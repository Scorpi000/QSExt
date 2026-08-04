"""
全局配置 API 路由
"""

from fastapi import APIRouter, Body

from app.services.global_config_service import get_global_config, set_global_config

router = APIRouter()


@router.get("")
async def get_config():
    """获取全局配置"""
    return get_global_config()


@router.put("")
async def update_config(body: dict = Body(..., description="完整全局配置对象")):
    """
    更新全局配置。
    Body 示例:
    {
        "cache_dir": "D:/Data/QSCache",
        "engine": {
            "type": "ParallelEngine",
            "params": {"n_workers": 4}
        }
    }
    """
    set_global_config(body)
    return {"message": "保存成功", "config": get_global_config()}

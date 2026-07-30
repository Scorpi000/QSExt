"""
因子脚本导入 API

支持上传 .py 文件或粘贴代码，导入模块验证后存储到配置目录。
注册到图数据库请使用 register_factors_to_graphdb.py。
"""

import os
from typing import Optional
from fastapi import APIRouter, Form, File, UploadFile

from app.services.import_service import import_service, ImportResult
from app.core.config import settings
from app.core.exceptions import ValidationException

router = APIRouter()


@router.post("/factors/import")
async def import_factor(
    code: Optional[str] = Form(None, description="粘贴的代码内容"),
    filename: str = Form("factor.py", description="文件名"),
    file: Optional[UploadFile] = File(None, description="上传的 .py 文件"),
):
    """导入因子定义脚本

    支持两种方式（二选一）：
    1. 上传 .py 文件（file 参数）
    2. 粘贴代码（code + filename 参数）

    流程: importlib 加载模块 → 读取 __FACTOR_META__ → 验证 defFactor → 存储
    """
    if file is not None:
        if not file.filename.endswith(".py"):
            raise ValidationException("仅支持 .py 文件")
        filename = file.filename
        code = (await file.read()).decode("utf-8")
    elif code is not None:
        code = code.strip()
        if not code:
            raise ValidationException("代码内容不能为空")
    else:
        raise ValidationException("请上传 .py 文件或粘贴代码")

    result: ImportResult = import_service.validate_import(code, filename)

    if result.errors:
        raise ValidationException(
            f"脚本验证失败: {'; '.join(result.errors)}"
        )

    saved_path, was_renamed, original_filename = import_service.save_script(code, filename)
    result.filename = os.path.basename(saved_path)
    result.was_renamed = was_renamed
    result.original_filename = original_filename
    if was_renamed:
        result.warnings.append(
            f"文件名 '{original_filename}' 已存在，自动更名为 '{result.filename}'"
        )

    # 后台任务：注册到图数据库
    task_id = None
    settings_path = settings.factor_def.get("settings_path")
    if settings_path:
        import uuid
        from app.tasks.manager import task_manager
        task_id = uuid.uuid4().hex[:12]
        await task_manager.submit(
            name=f"注册因子: {result.filename}",
            coro_or_func=lambda: import_service.register_to_graph(
                saved_path, settings_path
            ),
            task_id=task_id,
        )
        register_hint = None  # 已在后台执行，不需要提示命令
    else:
        register_hint = (
            "未配置 factor_def.settings_path，"
            "请在 QSWebConfig.json 中设置后自动注册到图数据库"
        )

    return {
        "success": result.success,
        "filename": result.filename,
        "saved_path": saved_path,
        "meta": result.meta,
        "warnings": result.warnings,
        "has_def_factor": result.has_def_factor,
        "has_meta": result.has_meta,
        "was_renamed": result.was_renamed,
        "original_filename": result.original_filename,
        "task_id": task_id,
        "register_hint": register_hint,
    }


@router.post("/factors/import/preview")
async def preview_import(
    code: Optional[str] = Form(None, description="粘贴的代码内容"),
    filename: str = Form("factor.py", description="文件名"),
    file: Optional[UploadFile] = File(None, description="上传的 .py 文件"),
):
    """仅预览因子脚本的元信息，不执行存储"""
    if file is not None:
        if not file.filename.endswith(".py"):
            raise ValidationException("仅支持 .py 文件")
        code = (await file.read()).decode("utf-8")
        filename = file.filename
    elif code is not None:
        code = code.strip()
        if not code:
            raise ValidationException("代码内容不能为空")
    else:
        raise ValidationException("请上传 .py 文件或粘贴代码")

    result: ImportResult = import_service.validate_import(code, filename)

    if result.errors:
        raise ValidationException(
            f"脚本验证失败: {'; '.join(result.errors)}"
        )

    return {
        "success": result.success,
        "meta": result.meta,
        "warnings": result.warnings,
        "has_def_factor": result.has_def_factor,
        "has_meta": result.has_meta,
    }

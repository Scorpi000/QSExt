"""
策略服务层 —— 策略代码验证、文件存储、Neo4j 注册、回测执行
"""
import os
import sys
import json
import re
import importlib
import importlib.util
import tempfile
import datetime as dt
from typing import Optional, List, Dict, Tuple

from app.models.strategy import (
    StrategyMetaModel, OperatorConfigModel,
    StrategyImportPreviewResponse, StrategySearchResult,
)


class StrategyService:
    """策略管理服务"""

    def __init__(self, scripts_dir: str = None):
        self._scripts_dir = scripts_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "strategies",
        )

    @property
    def scripts_dir(self) -> str:
        return self._scripts_dir

    # ─── 代码验证 ─────────────────────────────────────────────

    def validate_code(self, code: str) -> StrategyImportPreviewResponse:
        """验证策略代码，提取元信息

        Args:
            code: 策略 Python 代码字符串

        Returns:
            StrategyImportPreviewResponse
        """
        errors = []
        warnings = []
        meta = None
        valid = True

        # 1. 语法检查
        try:
            compile(code, "<strategy>", "exec")
        except SyntaxError as e:
            errors.append(f"语法错误 (行 {e.lineno}): {e.msg}")
            return StrategyImportPreviewResponse(valid=False, errors=errors)

        # 2. 动态加载并检查约定
        try:
            module = self._load_module_from_code(code, "_strategy_preview")
        except Exception as e:
            errors.append(f"模块加载失败: {str(e)}")
            return StrategyImportPreviewResponse(valid=False, errors=errors)

        # 3. 检查 __STRATEGY_META__
        raw_meta = getattr(module, "__STRATEGY_META__", None)
        if raw_meta is None:
            errors.append("缺少 __STRATEGY_META__ 字典")
            valid = False
        elif not isinstance(raw_meta, dict):
            errors.append("__STRATEGY_META__ 必须是 dict 类型")
            valid = False
        else:
            # 检查必填字段
            if not raw_meta.get("TargetTable"):
                errors.append("__STRATEGY_META__ 缺少必填字段: TargetTable")
                valid = False
            if not raw_meta.get("IDType"):
                errors.append("__STRATEGY_META__ 缺少必填字段: IDType")
                valid = False

            # 构造元信息模型
            try:
                op_config = raw_meta.get("OperatorConfig", {})
                meta = StrategyMetaModel(
                    Name=raw_meta.get("TargetTable", ""),
                    TargetTable=raw_meta.get("TargetTable", ""),
                    IDType=raw_meta.get("IDType", "A股"),
                    OperatorConfig=OperatorConfigModel(
                        SignalType=op_config.get("SignalType", "目标权重"),
                        InitCash=op_config.get("InitCash", 1e6),
                        ShortAllowed=op_config.get("ShortAllowed", False),
                    ),
                    FactorDeps=raw_meta.get("FactorDeps", {}),
                    StrategyDeps=raw_meta.get("StrategyDeps", {}),
                    DBDeps=raw_meta.get("DBDeps", {}),
                    ModelArgs=raw_meta.get("ModelArgs", {}),
                    Author=raw_meta.get("Author", "Anonymous"),
                    Description=raw_meta.get("Description", ""),
                    Tags=raw_meta.get("Tags", []),
                    MaxLookBack=raw_meta.get("MaxLookBack", 365),
                    DefScriptPath=raw_meta.get("DefScriptPath", ""),
                )
            except Exception as e:
                warnings.append(f"元信息解析警告: {str(e)}")

        # 4. 检查 defStrategy
        if not hasattr(module, "defStrategy") or not callable(module.defStrategy):
            errors.append("缺少 defStrategy(sdi) 函数")
            valid = False

        # 清理
        sys.modules.pop("_strategy_preview", None)

        return StrategyImportPreviewResponse(
            valid=valid,
            meta=meta,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _load_module_from_code(code: str, module_name: str):
        """从代码字符串动态加载模块"""
        spec = importlib.util.spec_from_file_location(
            module_name,
            os.path.join(tempfile.gettempdir(), f"{module_name}.py"),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        exec(compile(code, f"<{module_name}>", "exec"), module.__dict__)
        return module

    # ─── 文件存储 ─────────────────────────────────────────────

    def save_strategy_file(self, code: str, filename: str = None) -> str:
        """保存策略代码到文件

        Args:
            code: 策略代码
            filename: 文件名（不含扩展名），None 时自动生成

        Returns:
            保存的文件路径
        """
        os.makedirs(self._scripts_dir, exist_ok=True)

        if filename is None:
            filename = f"strategy_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 确保文件名唯一
        base_name = filename.rsplit(".", 1)[0]
        filepath = os.path.join(self._scripts_dir, f"{base_name}.py")
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(self._scripts_dir, f"{base_name}_{counter}.py")
            counter += 1

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        return filepath

    # ─── 回测执行 ─────────────────────────────────────────────

    async def run_backtest(
        self,
        request,
        qs_bridge,
        task_manager,
        task_id: str,
    ):
        """执行策略回测（异步任务）

        Args:
            request: StrategyBacktestRequest
            qs_bridge: QSBridge 实例
            task_manager: TaskManager 实例
            task_id: 任务 ID
        """
        await task_manager.update_progress(task_id, 5, "正在加载策略代码...")

        # 加载策略模块
        if request.strategy_qsid:
            from QSExt.QSRegistry.api import QSGraphDB
            # 从 Neo4j 获取策略信息
            code = await self._load_strategy_from_graph(request.strategy_qsid)
            if code is None:
                raise ValueError(f"找不到策略: {request.strategy_qsid}")
        elif request.code:
            code = request.code
        else:
            raise ValueError("必须提供 code 或 strategy_qsid")

        await task_manager.update_progress(task_id, 20, "正在解析因子依赖...")

        # 委托给 QSBridge
        result = await qs_bridge.run_strategy_backtest(
            code=code,
            factor_refs=request.factor_refs,
            model_args=request.model_args,
            operator_config=request.operator_config,
            start_date=request.start_date,
            end_date=request.end_date,
            dt_mode=request.dt_mode,
            descriptor_ids=request.descriptor_ids,
        )

        await task_manager.update_progress(task_id, 90, "正在转换结果...")
        return result.model_dump() if hasattr(result, 'model_dump') else result

    async def _load_strategy_from_graph(self, qsid: str) -> Optional[str]:
        """从 Neo4j 加载策略代码"""
        import asyncio
        loop = asyncio.get_running_loop()

        def _sync():
            from QSExt.QSRegistry.api import QSGraphDB
            import json as _json

            neo4j_cfg_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
            if not os.path.exists(neo4j_cfg_path):
                return None

            with open(neo4j_cfg_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r",\s*([}\]])", r"\1", content)
            neo4j_cfg = _json.loads(content)

            neo4j_args = {
                "IPAddr": neo4j_cfg["IPAddr"],
                "Port": neo4j_cfg["Port"],
                "User": neo4j_cfg["User"],
                "Pwd": neo4j_cfg["Pwd"],
                "DBName": neo4j_cfg.get("DBName", "neo4j"),
            }

            gdb = QSGraphDB(args=neo4j_args)
            try:
                gdb.connect()
                return gdb.getStrategyCode(qsid)
            finally:
                gdb.disconnect()

        return await loop.run_in_executor(None, _sync)


# 单例（优先使用 QSWebConfig.yaml 中 strategy_def.scripts_dir）
def _default_strategy_scripts_dir() -> str:
    try:
        from app.core.config import settings
        return settings.strategy_def["scripts_dir"]
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "strategies",
        )

strategy_service = StrategyService(scripts_dir=_default_strategy_scripts_dir())

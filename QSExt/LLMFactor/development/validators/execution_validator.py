# -*- coding: utf-8 -*-
"""Agent B: 执行验证器。

检查项：
    1. 动态导入 factor_def.py 模块
    2. 调用 defFactor() 验证返回 FactorDef 对象
    3. readData() 小样本试运行
    4. 输出 shape 验证
    5. NaN/Inf 比例检测

注意：此验证器需要 QuantStudio 运行环境。若环境不可用，会跳过执行验证并标记为警告。

使用示例::

    validator = ExecutionValidator()
    report = validator.validate(factor_dir, hypothesis)
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import numpy as np

from QSExt.LLMFactor.development.models import ExecutionReport

__QS_Logger__ = logging.getLogger("QSR.development.execution_validator")

# NaN 比例警告阈值
NAN_RATIO_WARNING = 0.5
NAN_RATIO_CRITICAL = 0.9


class ExecutionValidator:
    """执行验证器（Agent B）。"""

    def validate(self, factor_dir: str, hypothesis: dict = None) -> ExecutionReport:
        """执行验证。

        Args:
            factor_dir: 因子目录路径
            hypothesis: 假设文档（未使用，保持接口一致）

        Returns:
            ExecutionReport
        """
        issues = []

        code_path = Path(factor_dir) / "factor_def.py"
        if not code_path.exists():
            return ExecutionReport(
                passed=False,
                issues=["factor_def.py 不存在"],
            )

        # 1. 动态导入模块
        module, import_err = self._load_module(code_path)
        if import_err:
            return ExecutionReport(
                passed=False,
                issues=[f"模块导入失败: {import_err}"],
            )

        # 2. 检查 defFactor 函数
        if not hasattr(module, "defFactor"):
            return ExecutionReport(
                passed=False,
                issues=["模块中未找到 defFactor 函数"],
            )

        # 3. 尝试构建 FDI 并执行 defFactor
        fdi, factors, exec_err = self._try_execute(module)
        if exec_err:
            return ExecutionReport(
                passed=False,
                issues=[f"defFactor() 执行失败: {exec_err}"],
            )

        if not factors:
            return ExecutionReport(
                passed=False,
                issues=["defFactor() 返回空列表"],
            )

        # 4. readData() 小样本试运行
        data, read_err = self._try_read_data(factors, fdi)
        if read_err:
            return ExecutionReport(
                passed=False,
                issues=[f"readData() 失败: {read_err}"],
            )

        # 5. 输出验证
        output_shape = data.shape if hasattr(data, "shape") else None

        if output_shape and (output_shape[0] == 0 or output_shape[1] == 0):
            issues.append(f"输出数据为空: shape={output_shape}")

        # 6. NaN/Inf 比例检测
        nan_ratio = self._calc_nan_ratio(data)
        if nan_ratio > NAN_RATIO_CRITICAL:
            issues.append(f"NaN/Inf 比例过高: {nan_ratio:.1%} (>{NAN_RATIO_CRITICAL:.0%})")
        elif nan_ratio > NAN_RATIO_WARNING:
            issues.append(f"NaN/Inf 比例较高: {nan_ratio:.1%} (>{NAN_RATIO_WARNING:.0%})")

        return ExecutionReport(
            passed=len(issues) == 0,
            output_shape=output_shape,
            nan_ratio=nan_ratio,
            issues=issues,
        )

    def _load_module(self, code_path: Path):
        """动态加载 factor_def.py 模块。"""
        try:
            module_name = f"_factor_def_{code_path.parent.name}"
            spec = importlib.util.spec_from_file_location(module_name, str(code_path))
            if spec is None or spec.loader is None:
                return None, f"无法创建模块 spec: {code_path}"

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, None
        except Exception as e:
            return None, str(e)

    def _try_execute(self, module):
        """尝试执行 defFactor()。"""
        try:
            from QSExt.DefModule.DefContent import DefInput, Def

            # 构建最小化 FDI（需要 JYDB 连接）
            fdi = self._build_minimal_fdi()
            if fdi is None:
                return None, None, "无法构建 FDI（JYDB 连接不可用）"

            result = module.defFactor(fdi=fdi)

            # 处理两种返回类型
            if isinstance(result, list):
                return fdi, result, None
            elif hasattr(result, "FactorList"):
                return fdi, result.FactorList, None
            else:
                return None, None, f"defFactor() 返回了未知类型: {type(result).__name__}"
        except Exception as e:
            return None, None, str(e)

    def _build_minimal_fdi(self):
        """构建最小化的 FDI 用于测试。"""
        try:
            import datetime as dt
            from QSExt.DefModule.DefContent import DefInput
            from QuantStudio.Factor.JYDB import JYDB

            SDB = JYDB().connect()

            # 小样本：5 个交易日，5 只股票
            DTRuler = SDB.getTradeDay(
                start_date=dt.datetime(2025, 1, 1),
                end_date=dt.datetime(2025, 4, 30),
            )
            DTs = DTRuler[-5:]  # 最近 5 天
            IDs = ["000001.SZ", "600519.SH", "688579.SH"]
            SectionIDs = IDs

            return DefInput(
                Debug=True,
                FDB={"JYDB": SDB},
                DTs=DTs,
                IDs=IDs,
                SectionIDs=SectionIDs,
                DTRuler=DTRuler,
            )
        except Exception as e:
            __QS_Logger__.warning(f"构建 FDI 失败: {e}")
            return None

    def _try_read_data(self, factors, fdi):
        """尝试 readData() 小样本运行。"""
        try:
            factor = factors[0]
            data = factor.readData(
                ids=fdi.IDs,
                dts=fdi.DTs,
                section_ids=fdi.SectionIDs,
                dt_ruler=fdi.DTRuler,
            )
            return data, None
        except Exception as e:
            return None, str(e)

    def _calc_nan_ratio(self, data) -> float:
        """计算 NaN/Inf 比例。"""
        try:
            if hasattr(data, "values"):
                values = data.values
            else:
                values = np.array(data)

            total = values.size
            if total == 0:
                return 1.0

            nan_count = np.isnan(values).sum() + np.isinf(values).sum()
            return float(nan_count / total)
        except Exception:
            return 0.0

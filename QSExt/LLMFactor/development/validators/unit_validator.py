# -*- coding: utf-8 -*-
"""Agent D: 单位检查验证器。

检查项：
    1. 解析代码中使用的表名
    2. 检测主板/科创板单位差异
    3. 验证单位换算逻辑是否正确

使用示例::

    validator = UnitValidator()
    report = validator.validate(factor_dir, hypothesis)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from QSExt.LLMFactor.development.models import UnitCheckReport

__QS_Logger__ = logging.getLogger("QSR.development.unit_validator")

# 已知的单位差异表对（主板/科创板）
# 格式: (主板表, 科创板表, 主板单位, 科创板单位)
KNOWN_UNIT_DIFFERENCES = [
    ("股票行情表现", "科创板行情表现", "万元", "元"),
    ("公司衍生报表数据_新会计准则(新)", "科创板衍生报表数据", "一致", "一致"),
]

# 万元/元 相关的字段关键词
MONEY_UNIT_KEYWORDS = ["总市值", "流通市值", "成交额"]


class UnitValidator:
    """单位检查验证器（Agent D）。"""

    def validate(self, factor_dir: str, hypothesis: dict = None) -> UnitCheckReport:
        """执行单位检查。

        Args:
            factor_dir: 因子目录路径
            hypothesis: 假设文档（未使用，保持接口一致）

        Returns:
            UnitCheckReport
        """
        code_path = Path(factor_dir) / "factor_def.py"
        if not code_path.exists():
            return UnitCheckReport(
                passed=False,
                issues=["factor_def.py 不存在"],
            )

        code = code_path.read_text(encoding="utf-8")
        issues = []
        conversions = {}

        # 1. 提取代码中使用的表名
        tables = self._extract_table_names(code)

        # 2. 检查是否有双板合并
        has_star_board = any("科创板" in t for t in tables)
        has_main_board = any(
            t for t in tables
            if "科创板" not in t and t not in ("",)
        )

        if not (has_star_board and has_main_board):
            # 非双板因子，跳过单位检查
            return UnitCheckReport(
                passed=True,
                conversions={},
                issues=[],
            )

        # 3. 检查单位换算逻辑
        for main_table, star_table, main_unit, star_unit in KNOWN_UNIT_DIFFERENCES:
            if main_table in code and star_table in code:
                conversions[f"{main_table}/{star_table}"] = {
                    "主板单位": main_unit,
                    "科创板单位": star_unit,
                }

                if main_unit != star_unit:
                    # 检查是否有换算逻辑
                    has_conversion = self._check_unit_conversion(
                        code, main_table, star_table, main_unit, star_unit
                    )
                    if not has_conversion:
                        issues.append(
                            f"检测到单位差异但未找到换算逻辑: "
                            f"{main_table}({main_unit}) vs {star_table}({star_unit})"
                        )
                    else:
                        conversions[f"{main_table}/{star_table}"]["换算"] = "已检测到"

        return UnitCheckReport(
            passed=len(issues) == 0,
            conversions=conversions,
            issues=issues,
        )

    def _extract_table_names(self, code: str) -> list[str]:
        """从代码中提取 JYDB 表名。"""
        # 匹配 getTable("表名") 模式
        pattern = r'getTable\(\s*["\']([^"\']+)["\']'
        return re.findall(pattern, code)

    def _check_unit_conversion(
        self, code: str,
        main_table: str, star_table: str,
        main_unit: str, star_unit: str,
    ) -> bool:
        """检查代码中是否有单位换算逻辑。

        启发式检查：
        - 是否有 /10000 或 *10000 的操作
        - 是否有 "万元" 或 "元" 的注释说明
        """
        # 检查 /10000 或 *10000
        if re.search(r"[/\*]\s*10000", code):
            return True

        # 检查 "元→万元" 或类似注释
        conversion_comments = [
            "元→万元", "万元→元", "元转万元", "万元转元",
            "统一单位", "单位换算", "单位转换",
        ]
        for comment in conversion_comments:
            if comment in code:
                return True

        return False

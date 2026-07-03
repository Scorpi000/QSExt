# -*- coding: utf-8 -*-
"""回测报告生成系统核心

提供：
- Scenario: 报告场景（从回测结果 dict 生成结构化报告）
- DataContext: 组件数据上下文（解耦组件和数据来源）
- ScenarioResult: 渲染结果容器
- 结果拆分工具函数
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


# ============================================================
# DataContext
# ============================================================

class DataContext:
    """组件数据上下文。

    内部是两级映射 {source_name: {key: value}}，组件通过 `source.key` 获取数据。

    source == "meta" 时为元数据通道，可存储因子名称、日期范围等非回测产出数据。
    """

    def __init__(self, output: dict, factor_names: List[str],
                 config: dict):
        """
        Args:
            output: BTReport.backward_compute() 产出的 dict
            factor_names: 当前上下文对应的因子名列表
            config: 场景配置 dict
        """
        self._data: Dict[str, Dict[str, Any]] = {}
        for module_key, module_dict in output.items():
            if module_key == "Report":
                continue
            if isinstance(module_dict, dict):
                self._data[module_key] = module_dict
            else:
                self._data[module_key] = {"_value": module_dict}

        self._meta = {
            "factor_names": factor_names,
            "factor_count": len(factor_names),
            "config": config,
            "dt_start": None,
            "dt_end": None,
        }
        # 尝试从 output 中推断日期范围
        self._infer_date_range(output)

    def _infer_date_range(self, output: dict):
        """从 output 中各 DataFrame 的 index 推断日期范围"""
        for module_dict in output.values():
            if not isinstance(module_dict, dict):
                continue
            for val in module_dict.values():
                if isinstance(val, pd.DataFrame) and not val.empty:
                    idx = val.index
                    if isinstance(idx, pd.DatetimeIndex) and len(idx) > 0:
                        if self._meta["dt_start"] is None:
                            self._meta["dt_start"] = str(idx[0])
                        self._meta["dt_end"] = str(idx[-1])
                        return
                elif isinstance(val, pd.Series) and not val.empty:
                    idx = val.index
                    if isinstance(idx, pd.DatetimeIndex) and len(idx) > 0:
                        if self._meta["dt_start"] is None:
                            self._meta["dt_start"] = str(idx[0])
                        self._meta["dt_end"] = str(idx[-1])

    def get(self, source: str, key: Optional[str] = None) -> Any:
        """获取指定 source 下的数据。

        Args:
            source: 数据来源，如 "0-Rank IC 分析"，特殊值 "meta" 为元数据
            key: 数据键名，如 "IC"、"统计数据"。None 返回整个 source dict
        """
        if source == "meta":
            return self._meta.get(key) if key else self._meta
        source_data = self._data.get(source, {})
        if key is None:
            return source_data
        return source_data.get(key)

    def set(self, source: str, key: str, value: Any):
        """设置自定义数据（场景 prepare_data_context 中使用）"""
        if source == "meta":
            self._meta[key] = value
        else:
            if source not in self._data:
                self._data[source] = {}
            self._data[source][key] = value

    def keys(self) -> List[str]:
        """列出所有 source 名"""
        return list(self._data.keys())


# ============================================================
# 结果拆分
# ============================================================

def split_output_for_factor(output: dict, factor_name: str) -> dict:
    """从合并的 output dict 中提取单个因子的结果。

    各模块产出的 DataFrame 通常 columns 对应因子名。
    拆分时提取对应列，返回独立 dict 供单因子报告渲染。

    Args:
        output: 完整的 BTReport output dict
        factor_name: 要提取的因子名称

    Returns:
        仅包含该因子列的新 dict（DataFrame 为 view 引用，非 copy）
    """
    factor_output = {}
    for module_key, module_dict in output.items():
        if module_key == "Report":
            continue
        if not isinstance(module_dict, dict):
            factor_output[module_key] = module_dict
            continue

        factor_module = {}
        for data_key, df in module_dict.items():
            if isinstance(df, pd.DataFrame):
                if factor_name in df.columns:
                    factor_module[data_key] = df[[factor_name]]
                elif factor_name in df.index:
                    # 转置结构：index=因子名, columns=统计量名（如 IC 统计数据）
                    factor_module[data_key] = df.loc[[factor_name]]
                elif any(c.startswith(f"{factor_name}::") for c in df.columns):
                    # 合并的多因子数据（列名含 "因子名::" 前缀）
                    prefix = f"{factor_name}::"
                    cols = [c for c in df.columns if c.startswith(prefix)]
                    sub = df[cols].rename(columns=lambda c: c[len(prefix):])
                    factor_module[data_key] = sub
                else:
                    # 共享数据（如截面宽度），直接保留
                    factor_module[data_key] = df
            elif isinstance(df, pd.Series):
                if factor_name in df.index:
                    factor_module[data_key] = df[[factor_name]]
                else:
                    factor_module[data_key] = df
            elif isinstance(df, dict):
                # 嵌套 dict
                if factor_name in df:
                    # 如分位数组合的 "投资组合": {"因子名": {...}}
                    factor_module[data_key] = {factor_name: df[factor_name]}
                elif data_key == factor_name:
                    # ICDecay 格式：{factor_name: {"IC": df, "统计数据": df, ...}}
                    # 展平到顶层并重命名 "IC" → "IC衰减"
                    inner = dict(df)
                    if "IC" in inner:
                        inner["IC衰减"] = inner.pop("IC")
                    factor_module.update(inner)
                else:
                    factor_module[data_key] = df
            else:
                factor_module[data_key] = df

        # 规范化模块键名：去除因子名后缀，使 config 中的 source 引用能匹配
        # "2-分位数组合(动量因子_1M)" → "2-分位数组合"
        normalized_key = _normalize_module_key(module_key, factor_name)
        factor_output[normalized_key] = factor_module

    return factor_output


def _normalize_module_key(module_key: str, factor_name: str) -> str:
    """规范化 BTReport 模块键名，去除其中的因子名后缀。

    例如 "2-分位数组合(动量因子_1M)" → "2-分位数组合"
    如果去除后缀后发生冲突，保留原始键名。
    """
    suffix = f"({factor_name})"
    if module_key.endswith(suffix):
        return module_key[: -len(suffix)]
    return module_key


# ============================================================
# ScenarioResult
# ============================================================

@dataclass
class ScenarioResult:
    """一次 render() 的返回结果"""
    output: dict = field(default_factory=dict)
    reports: Dict[str, Dict[str, str]] = field(default_factory=dict)


def register_reports_to_db(
    result: "ScenarioResult",
    factor_qsids: List[str],
    output_dir: str,
    bt_qsid: Optional[str] = None,
    scenario_name: Optional[str] = None,
) -> Dict[str, str]:
    """将 ScenarioResult 中的报告写入文件并注册到图数据库。

    Args:
        result: Scenario.render() 返回的 ScenarioResult
        factor_qsids: 各因子的 QSID 列表（顺序与 factors 一致）
        output_dir: 报告输出目录
        bt_qsid: 关联的回测 QSID
        scenario_name: 场景名称

    Returns:
        {factor_name_fmt: report_id, ...}
    """
    from QSExt.QSRegistry.QSGraphDB import QSGraphDB

    os.makedirs(output_dir, exist_ok=True)

    # 尝试连接图数据库（可能因配置缺失或 Neo4j 不可用而失败）
    gdb = None
    try:
        gdb = QSGraphDB()
        gdb.connect()
    except Exception as e:
        import logging
        _logger = logging.getLogger("QS.ReportGenerator")
        _logger.warning(f"无法连接图数据库，跳过报告注册: {e}")

    report_ids = {}

    # 按因子名建立 QSID 映射（result.reports 保持插入顺序，与 factor_names 一致）
    if isinstance(factor_qsids, list):
        _factor_qsid_map = {}
        for i, factor_name in enumerate(result.reports.keys()):
            if i < len(factor_qsids):
                _factor_qsid_map[factor_name] = factor_qsids[i]
    else:
        _factor_qsid_map = {}

    for factor_name, reports in result.reports.items():
        for fmt, content in reports.items():
            filename = f"{factor_name}_{scenario_name or 'report'}.{fmt}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            # 注册到图数据库
            if gdb is not None:
                try:
                    fqsid = _factor_qsid_map.get(factor_name)
                    fqsids = [fqsid] if fqsid else []
                    rid = gdb.storeReport(
                        report_path=filepath,
                        factor_qsids=fqsids,
                        bt_qsid=bt_qsid,
                        scenario_name=scenario_name,
                        name=f"{factor_name} - {fmt.upper()} 报告",
                    )
                    report_ids[f"{factor_name}_{fmt}"] = rid
                except Exception as e:
                    _logger.warning(f"注册报告 {filename} 到图数据库失败: {e}")

    return report_ids


# ---- 注册内置组件（在导入时自动完成） ----

def _register_builtin_components():
    """注册所有内置组件到 ComponentRegistry"""
    from QSExt.ReportGenerator.components.registry import ComponentRegistry
    from QSExt.ReportGenerator.components.chart import Chart
    from QSExt.ReportGenerator.components.data_table import DataTable
    from QSExt.ReportGenerator.components.stat_grid import StatGrid
    from QSExt.ReportGenerator.components.factor_summary import FactorSummary
    from QSExt.ReportGenerator.components.section import Section

    ComponentRegistry.register("chart", Chart)
    ComponentRegistry.register("data_table", DataTable)
    ComponentRegistry.register("stat_grid", StatGrid)
    ComponentRegistry.register("factor_summary", FactorSummary)
    ComponentRegistry.register("section", Section)


_register_builtin_components()

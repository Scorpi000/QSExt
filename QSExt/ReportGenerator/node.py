# -*- coding: utf-8 -*-
"""ReportGeneratorNode — 将报告渲染封装为 QuantStudio 计算图 DAG 节点

直接依赖 BTNodes，在 backward_compute 中聚合子节点输出并渲染报告。
数据源映射和标准化规则由 config.yaml 的 ``data_sources`` 段驱动，
不依赖具体场景，新增场景只需修改配置文件。

DAG 拓扑: BTNodes → ReportGeneratorNode

使用方式::

    from QSExt.ReportGenerator.node import ReportGeneratorNode
    from QuantStudio.Core.CalcEngine import Engine

    rg_node = ReportGeneratorNode(
        bt_nodes=nodes,
        factor_names=["动量因子", "价值因子"],
        report_config=config["report"],
        args={"OutputFormats": ["html", "markdown"]}
    )
    result = Engine().run([rg_node], context)[0]
    # result["_reports"]["动量因子"]["html"] → 完整 HTML 报告

config.yaml 中 ``data_sources`` 格式::

    data_sources:
      - node_pattern: "Rank IC"       # 匹配 BTNode.Name 的模式
        source_key: "0-Rank IC 分析"   # 映射到的 source key
      - node_pattern: "分位数组合"
        source_key: "2-分位数组合"
        merge: true                    # 多个同名节点合并到一个 key
        merge_by_factor: true          # 合并时列名加因子名前缀
      - node_pattern: "IC 衰减"
        source_key: "1-IC 衰减分析"
        normalize:
          flatten_factor_nested: true  # 展平 {factor: {sub: df}} → {sub: df}
          rename: {"IC": "IC衰减"}     # 重命名子 key
      - node_pattern: "换手率"
        source_key: "3-因子换手率"
        normalize:
          rename_keys: {"因子换手率": "换手率"}
"""

from typing import Any, List, Optional

import pandas as pd
from pydantic import Field
from QuantStudio.Core.Node import Node, Context, DTLocalContext, DTInitData


class ReportGeneratorNode(Node):
    """报告生成节点（配置驱动，不绑定具体场景）。"""

    class __QS_ArgClass__(Node.__QS_ArgClass__):
        Name: str = Field(default="ReportGenerator", frozen=True,
                          title="名称")
        FactorNames: list = Field(default=[], title="因子名列表")
        ReportConfig: dict = Field(default={}, title="报告配置")
        OutputFormats: list = Field(default=["html"], title="输出格式")
        ThemeName: str = Field(default="default", title="主题名称")

    def __init__(self, bt_nodes, factor_names=None, report_config=None,
                 args=None, config_file=None, factor_metas=None, **kwargs):
        if args is None:
            args = {}
        if factor_names is not None:
            args.setdefault("FactorNames", list(factor_names))
        if report_config is not None:
            args.setdefault("ReportConfig", dict(report_config))

        super().__init__(deps=list(bt_nodes), args=args,
                         config_file=config_file, **kwargs)
        self._factor_names = factor_names or args.get("FactorNames", [])
        self._report_config = report_config or args.get("ReportConfig", {})
        self._factor_metas = factor_metas or {}

    # ---- DAG 接口 ----

    def init_compute(self, path: List[str], init_data: DTInitData,
                     context: Context) -> List[DTInitData]:
        NodeState = context.NodeState.setdefault(self.QSID, {})
        DTRange = NodeState.get("dt_range", None)
        if DTRange is None:
            NodeState["dt_range"] = init_data.DTRange
        else:
            NodeState["dt_range"] = (
                min(DTRange[0], init_data.DTRange[0]),
                max(DTRange[1], init_data.DTRange[1])
            )
        if self.QSID in path[:-1]:
            return []
        return [DTInitData(DTRange=NodeState["dt_range"])] * len(self.Deps)

    def forward_compute(self, path: List[str], fwd_data: DTLocalContext,
                        context: Context):
        return (
            [DTLocalContext(DTs=fwd_data.DTs)] * len(self.Deps),
            DTLocalContext(DTs=fwd_data.DTs)
        )

    # ---- 数据聚合（配置驱动）----

    @staticmethod
    def _match_source(node_name: str, ds_cfg: dict) -> bool:
        """检查 BTNode 名称是否匹配 data_source 的 node_pattern。"""
        pattern = ds_cfg.get("node_pattern", "")
        return pattern and pattern in node_name

    @staticmethod
    def _apply_normalize(module_dict: dict, ds_cfg: dict) -> dict:
        """按 data_source 的 normalize 规则处理模块数据。"""
        norm = ds_cfg.get("normalize", {})
        if not norm:
            return module_dict

        result = dict(module_dict)

        # rename_keys: {"旧名": "新名"}
        for old, new in norm.get("rename_keys", {}).items():
            if old in result:
                result[new] = result.pop(old)

        # rename: {"旧子key": "新子key"}（用于展平后的嵌套 dict）
        rename_map = norm.get("rename", {})
        if rename_map:
            for key in list(result.keys()):
                if isinstance(result[key], dict):
                    inner = dict(result[key])
                    for old, new in rename_map.items():
                        if old in inner:
                            inner[new] = inner.pop(old)
                    result[key] = inner

        return result

    def _build_output(self, bwd_data_list: List[dict]) -> dict:
        """按 config 的 data_sources 聚合 BTNode 输出为 source dict。

        若未定义 data_sources，直接用 BTNode 名称作为 key（兜底）。
        """
        ds_list = self._report_config.get("data_sources", [])
        if not ds_list:
            # 无配置：直接用节点名
            return {
                self.Deps[i].Name: i_output
                for i, i_output in enumerate(bwd_data_list)
            }

        output = {}
        merge_buffers = {}

        for i, i_output in enumerate(bwd_data_list):
            node_name = self.Deps[i].Name
            matched = False
            for ds_cfg in ds_list:
                if not self._match_source(node_name, ds_cfg):
                    continue
                matched = True
                source_key = ds_cfg.get("source_key", node_name)
                if ds_cfg.get("merge"):
                    merge_buffers.setdefault(source_key, []).append(
                        (node_name, i_output)
                    )
                elif source_key not in output:
                    output[source_key] = self._apply_normalize(
                        i_output, ds_cfg
                    )
                break

            if not matched:
                if node_name not in output:
                    output[node_name] = i_output

        # 处理合并节点
        for source_key, entries in merge_buffers.items():
            ds_cfg = next(
                (d for d in ds_list if d.get("source_key") == source_key),
                {}
            )
            merged = self._merge_entries(entries, ds_cfg)
            output[source_key] = self._apply_normalize(merged, ds_cfg)

        return output

    @staticmethod
    def _merge_entries(entries: list, ds_cfg: dict) -> dict:
        """合并多个 BTNode 输出为一个模块 dict。

        若 merge_by_factor 为 True，从节点名提取因子名作为列名前缀。
        """
        merged = {}
        for node_name, module_dict in entries:
            fname = ""
            if ds_cfg.get("merge_by_factor") and "(" in node_name:
                fname = node_name.split("(", 1)[-1].rstrip(")")

            for data_key, data_val in module_dict.items():
                if isinstance(data_val, pd.DataFrame) and fname:
                    data_val = data_val.rename(
                        columns=lambda c: f"{fname}::{c}"
                        if not c.startswith(f"{fname}::") else c
                    )
                if data_key not in merged:
                    merged[data_key] = data_val
                elif isinstance(data_val, pd.DataFrame):
                    merged[data_key] = pd.concat(
                        [merged[data_key], data_val], axis=1
                    )
                elif isinstance(data_val, dict):
                    merged[data_key].update(data_val)
        return merged

    # ---- 渲染 ----

    def _inject_factor_info(self, ctx: "DataContext",  # noqa: F821
                            factor_names: list) -> None:
        dt_start = ctx.get("meta", "dt_start") or "未指定"
        dt_end = ctx.get("meta", "dt_end") or "未指定"
        factor_info = {
            "name": (
                factor_names[0]
                if len(factor_names) == 1
                else ", ".join(factor_names)
            ),
            "count": len(factor_names),
            "dt_start": dt_start,
            "dt_end": dt_end,
        }
        if len(factor_names) == 1:
            desc = self._factor_metas.get(
                factor_names[0], {}
            ).get("description", "")
            if desc:
                factor_info["description"] = desc
        ctx.set("meta", "factor_info", factor_info)

    def backward_compute(self, path: List[str], bwd_data_list: List[dict],
                         context: Context,
                         local_context: Optional[DTLocalContext] = None) -> dict:
        from QSExt.ReportGenerator.core import DataContext, split_output_for_factor
        from QSExt.ReportGenerator.layout import LayoutRenderer
        from QSExt.ReportGenerator.themes.base import Theme

        # 1. 配置驱动：聚合 BTNode 输出
        output = self._build_output(bwd_data_list)

        # 2. 渲染参数
        theme = Theme()
        layout_renderer = LayoutRenderer()
        report_config = self._report_config or self._QSArgs.ReportConfig
        factor_names = self._factor_names or self._QSArgs.FactorNames
        formats = self._QSArgs.OutputFormats

        # 3. 逐因子渲染
        reports = {}
        if factor_names:
            for fname in factor_names:
                single_output = split_output_for_factor(output, fname)
                ctx = DataContext(single_output, [fname], report_config)
                self._inject_factor_info(ctx, [fname])
                reports[fname] = {}
                for fmt in formats:
                    reports[fname][fmt] = layout_renderer.render(
                        report_config, ctx, theme, fmt
                    )

        result = dict(output)
        result["_reports"] = reports
        return result

    def merge_result(self, result_list: List[dict],
                     context: Context) -> dict:
        return result_list[0]

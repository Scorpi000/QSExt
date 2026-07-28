"""
报告中心 Pydantic 模型
"""

from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field


# ─── 报告场景 ─────────────────────────────────────────────────

class ReportScenario(BaseModel):
    """可用的报告场景元信息"""
    key: str = Field(..., description="场景唯一标识")
    name: str = Field(..., description="场景中文名")
    description: str = Field(default="", description="场景描述")
    output_formats: List[str] = Field(default=["html", "markdown"], description="支持的输出格式")
    module_options: List[str] = Field(default_factory=list, description="可选模块列表")


# 已注册的场景
REPORT_SCENARIO_REGISTRY: Dict[str, dict] = {
    "single_factor": {
        "key": "single_factor",
        "name": "单因子分析",
        "description": "生成单因子测试报告，包含 IC 分析、IC 衰减、分位数组合和换手率分析",
        "output_formats": ["html", "markdown"],
        "module_options": ["ic", "ic_decay", "quantile_portfolio", "factor_turnover"],
    },
}


# ─── 因子引用（与回测共用模式） ─────────────────────────────

class FactorRef(BaseModel):
    """因子引用 — 从 FactorDB 加载"""
    conn_id: str = Field(..., description="FactorDB 连接 ID")
    table_name: str = Field(..., description="因子表名")
    factor_name: str = Field(..., description="因子名称")


class PriceRef(BaseModel):
    """价格因子引用"""
    conn_id: str = Field(..., description="价格因子所在的 FactorDB 连接 ID")
    table_name: str = Field(..., description="价格因子所在的表名")
    factor_name: str = Field(default="close", description="价格因子名称")


# ─── 报告生成请求 ────────────────────────────────────────────

class ReportModuleConfig(BaseModel):
    """单个报告模块的配置（对应 config.yaml 中 modules 段）"""
    ic: Optional[Any] = Field(None, description="IC 模块配置，false=禁用，dict=参数覆盖")
    ic_decay: Optional[Any] = Field(None, description="IC 衰减模块配置")
    quantile_portfolio: Optional[Any] = Field(None, description="分位数组合模块配置")
    factor_turnover: Optional[Any] = Field(None, description="因子换手率模块配置")


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""
    scenario: str = Field(default="single_factor", description="报告场景标识")
    name: str = Field(default="", description="报告名称（用于显示）")
    factor_refs: List[FactorRef] = Field(..., min_length=1, description="因子引用列表")
    price_ref: Optional[PriceRef] = Field(None, description="价格因子引用（用于计算收益率）")
    mask_ref: Optional[FactorRef] = Field(None, description="Mask 因子引用（可选，过滤无效样本）")
    cat_data_ref: Optional[FactorRef] = Field(None, description="分类因子引用（可选，行业分组等）")
    weight_ref: Optional[FactorRef] = Field(None, description="权重因子引用（可选）")
    start_date: str = Field(..., description="起始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="结束日期 (YYYY-MM-DD)")
    output_formats: List[str] = Field(default=["html"], description="输出格式")
    modules: ReportModuleConfig = Field(default_factory=ReportModuleConfig, description="模块启用/配置")
    descriptor_ids: Optional[List[str]] = Field(None, description="截面 ID 列表，None=使用因子表中全部 ID")
    rebalance_dts: Optional[List[str]] = Field(None, description="调仓时点列表 (YYYY-MM-DD)")


# ─── 报告元信息 ─────────────────────────────────────────────

class ReportInfo(BaseModel):
    """报告元信息（用于列表展示）"""
    id: str = Field(..., description="报告 ID")
    name: str = Field(..., description="报告名称")
    scenario: str = Field(..., description="场景标识")
    factor_names: List[str] = Field(default_factory=list, description="因子名称列表")
    formats: List[str] = Field(default_factory=list, description="已生成的格式")
    registered: bool = Field(default=False, description="是否已注册到 QSRegistry")
    created_at: str = Field(..., description="创建时间 (ISO)")
    start_date: str = Field(default="", description="数据起始日期")
    end_date: str = Field(default="", description="数据结束日期")


# ─── 报告注册请求 ──────────────────────────────────────────

class ReportRegisterRequest(BaseModel):
    """报告注册请求"""
    factor_qsids: Optional[List[str]] = Field(None, description="关联的因子 QSID 列表")
    bt_qsid: Optional[str] = Field(None, description="关联的回测 QSID")

"""
回测相关 Pydantic 模型
"""

from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field


# ─── 因子引用 ─────────────────────────────────────────────────

class FactorRef(BaseModel):
    """因子引用（双源）"""
    source: Literal["db", "registry"] = Field(default="db", description="因子来源")
    name: str = Field(..., description="因子名称或 QSID")
    conn_id: Optional[str] = Field(None, description="FactorDB 连接 ID（source=db 时必填）")
    table_name: Optional[str] = Field(None, description="因子表名（source=db 时必填）")


class PriceRef(BaseModel):
    """价格因子引用"""
    conn_id: str = Field(..., description="价格因子所在的 FactorDB 连接 ID")
    table_name: str = Field(..., description="价格因子所在的表名")
    factor_name: str = Field(default="close", description="价格因子名称")


# ─── 模块注册表 ───────────────────────────────────────────────

class ParamDef(BaseModel):
    """模块参数定义"""
    name: str = Field(..., description="参数名")
    type: Literal["int", "float", "str", "bool", "select", "multiselect_ids", "multiselect_factor"] = Field(..., description="参数类型")
    label: str = Field(..., description="参数中文标签")
    default: Optional[Any] = Field(None, description="默认值")
    options: Optional[List[str]] = Field(None, description="可选项（type=select/multiselect 时使用）")
    required: bool = Field(default=False, description="是否必填")
    description: Optional[str] = Field(None, description="参数说明")


class ModuleInfo(BaseModel):
    """回测模块元信息"""
    key: str = Field(..., description="模块唯一标识")
    name: str = Field(..., description="模块中文名")
    category: Literal["SectionFactor", "Portfolio", "Correlation", "ReturnDecomposition", "Risk", "Strategy"] = Field(..., description="模块类别")
    description: str = Field(default="", description="模块描述")
    params: List[ParamDef] = Field(default_factory=list, description="模块参数定义列表")
    requires_price: bool = Field(default=False, description="是否需要价格因子")
    requires_descriptor_ids: bool = Field(default=True, description="是否需要截面 ID")


# ─── 运行配置 ─────────────────────────────────────────────────

class ModuleRunConfig(BaseModel):
    """单个回测模块的运行配置"""
    module_key: str = Field(..., description="模块标识")
    instance_label: str = Field(default="", description="用户自定义标签（区分同一模块的多次运行）")
    factor_refs: List[FactorRef] = Field(..., min_length=1, description="分配给该模块的因子引用列表（从全局因子池中选择）")
    params: Dict[str, Any] = Field(default_factory=dict, description="模块参数值")
    price_ref: Optional[PriceRef] = Field(None, description="本模块的价格因子引用（需要价格时必填，从全局价格因子池中选择）")
    descriptor_source: Optional[str] = Field(None, description="截面 ID 源名称（对应 QSWebConfig 中配置的 section_id_sources key），为 None 则使用 descriptor_ids")
    descriptor_ids: Optional[List[str]] = Field(None, description="自定义截面 ID 列表（descriptor_source 为 None 时生效）")


class BacktestRunRequest(BaseModel):
    """回测运行请求"""
    module_configs: List[ModuleRunConfig] = Field(..., min_length=1, description="待运行的模块配置列表")
    start_date: str = Field(..., description="起始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="结束日期 (YYYY-MM-DD)")
    dt_mode: Literal["natural", "trading"] = Field(default="trading", description="时点模式：natural=自然日, trading=交易日")
    rebalance_dts: Optional[List[str]] = Field(None, description="再平衡时点列表（YYYY-MM-DD）")


# ─── 结果树 ───────────────────────────────────────────────────

class ResultNode(BaseModel):
    """结果树节点"""
    key: str = Field(..., description="节点名")
    label: str = Field(..., description="节点显示名")
    type: Literal["branch", "series", "dataframe", "scalar"] = Field(..., description="节点数据类型")
    children: Optional[List["ResultNode"]] = Field(None, description="子节点（type=branch 时有值）")
    data: Optional[Any] = Field(None, description="叶子节点数据")
    # series: {"index": [...], "values": [...]}
    # dataframe: {"columns": [...], "index": [...], "data": [[...]]}
    # scalar: any JSON-serializable value


# ─── 模块注册表 ───────────────────────────────────────────────

BACKTEST_MODULE_REGISTRY: Dict[str, dict] = {
    "ic": {
        "key": "ic",
        "name": "IC 分析",
        "category": "SectionFactor",
        "description": "计算因子值与下一期收益率的截面秩相关性（Rank IC），包括 IC 序列、移动平均、截面宽度和统计摘要",
        "params": [
            {
                "name": "corr_method",
                "type": "select",
                "label": "相关性方法",
                "default": "spearman",
                "options": ["spearman", "pearson", "kendall"],
                "required": False,
                "description": "计算 IC 时使用的相关系数方法"
            },
            {
                "name": "lookback",
                "type": "int",
                "label": "数据回溯期数",
                "default": 31,
                "required": False,
                "description": "在时间标尺上的回溯期数，即回溯多久的数据来完成计算"
            },
            {
                "name": "period_lookback",
                "type": "int",
                "label": "计算回溯期数",
                "default": 1,
                "required": False,
                "description": "在计算标尺上的回溯期数，如月度 IC 填 1"
            },
            {
                "name": "rolling_avg_period",
                "type": "int",
                "label": "移动平均期数",
                "default": 12,
                "required": False,
                "description": "IC 移动平均的窗口期数"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点，格式 <数字><单位>：1m=月末, 2w=双周, 3m=季末, 1y=年末。空=使用全部时点"
            },
        ],
        "requires_price": True,
        "requires_descriptor_ids": True,
    },
    "ic_decay": {
        "key": "ic_decay",
        "name": "IC 衰减",
        "category": "SectionFactor",
        "description": "分析因子 IC 随日期间隔的衰减情况，每个因子产生一条 IC 衰减曲线",
        "params": [
            {
                "name": "corr_method",
                "type": "select",
                "label": "相关性方法",
                "default": "spearman",
                "options": ["spearman", "pearson", "kendall"],
                "required": False,
                "description": "计算 IC 时使用的相关系数方法"
            },
            {
                "name": "lookback",
                "type": "int",
                "label": "数据回溯期数",
                "default": 31,
                "required": False,
                "description": "在时间标尺上的回溯期数，即回溯多久的数据来完成计算"
            },
            {
                "name": "period_lookback",
                "type": "int",
                "label": "计算回溯期数",
                "default": 1,
                "required": False,
                "description": "在计算标尺上的回溯期数"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点，格式 <数字><单位>：1m=月末, 2w=双周, 3m=季末, 1y=年末。空=使用全部时点"
            },
        ],
        "requires_price": True,
        "requires_descriptor_ids": True,
    },
    "multi_portfolio": {
        "key": "multi_portfolio",
        "name": "分位数组合",
        "category": "Portfolio",
        "description": "按因子值排序分组构建分位数组合，对比各组净值、收益和风险指标",
        "params": [
            {
                "name": "group_num",
                "type": "int",
                "label": "分位数分组数",
                "default": 5,
                "required": False,
                "description": "将截面 ID 按因子值排序后分组，如 5 表示五分位数组合"
            },
            {
                "name": "ascending",
                "type": "bool",
                "label": "升序排列",
                "default": False,
                "required": False,
                "description": "因子值升序排列后分组，True=因子值小的在第一组"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点"
            },
        ],
        "requires_price": True,
        "requires_descriptor_ids": True,
    },
    "factor_turnover": {
        "key": "factor_turnover",
        "name": "因子换手率",
        "category": "SectionFactor",
        "description": "计算前后两期因子值的截面秩相关性，衡量因子值的稳定性",
        "params": [
            {
                "name": "corr_method",
                "type": "select",
                "label": "相关性方法",
                "default": "spearman",
                "options": ["spearman", "pearson", "kendall"],
                "required": False,
                "description": "计算换手率时使用的相关系数方法"
            },
            {
                "name": "lookback",
                "type": "int",
                "label": "数据回溯期数",
                "default": 31,
                "required": False,
                "description": "在时间标尺上的回溯期数"
            },
            {
                "name": "period_lookback",
                "type": "int",
                "label": "计算回溯期数",
                "default": 1,
                "required": False,
                "description": "在计算标尺上的回溯期数，如月度换手率填 1"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点"
            },
        ],
        "requires_price": False,
        "requires_descriptor_ids": True,
    },
    "section_correlation": {
        "key": "section_correlation",
        "name": "截面相关性",
        "category": "SectionFactor",
        "description": "计算多个因子两两之间的截面相关性，评估因子共线性",
        "params": [
            {
                "name": "corr_method",
                "type": "select",
                "label": "相关性方法",
                "default": "spearman",
                "options": ["spearman", "pearson", "kendall"],
                "required": False,
                "description": "计算截面相关性时使用的相关系数方法"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点"
            },
        ],
        "requires_price": False,
        "requires_descriptor_ids": True,
    },
    "fama_macbeth": {
        "key": "fama_macbeth",
        "name": "Fama-MacBeth 回归",
        "category": "SectionFactor",
        "description": "两步 Fama-MacBeth 回归分析，评估因子对收益率的解释力和风险溢价",
        "params": [
            {
                "name": "lookback",
                "type": "int",
                "label": "数据回溯期数",
                "default": 31,
                "required": False,
                "description": "在时间标尺上的回溯期数"
            },
            {
                "name": "period_lookback",
                "type": "int",
                "label": "计算回溯期数",
                "default": 1,
                "required": False,
                "description": "在计算标尺上的回溯期数"
            },
            {
                "name": "rolling_avg_period",
                "type": "int",
                "label": "移动平均期数",
                "default": 12,
                "required": False,
                "description": "回归统计量的移动平均窗口期数"
            },
            {
                "name": "calc_dt_rule",
                "type": "str",
                "label": "计算时点规则",
                "default": "",
                "required": False,
                "description": "将 DTs 按频率采样为计算时点"
            },
        ],
        "requires_price": True,
        "requires_descriptor_ids": True,
    },
}

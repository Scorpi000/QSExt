"""
组合优化相关 Pydantic 模型
"""

from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field


# ─── 优化目标 ─────────────────────────────────────────────────

class ObjectiveConfig(BaseModel):
    """优化目标配置"""
    type: Literal["mean_variance", "risk_budget", "max_diversification"] = Field(
        ..., description="优化目标类型"
    )
    # 均值方差参数
    risk_aversion: float = Field(default=1.0, ge=0, description="风险厌恶系数 (mean_variance)")
    expected_return_coef: float = Field(default=0.0, description="收益项系数 (mean_variance)")
    # 风险预算参数
    risk_budget: Optional[List[float]] = Field(None, description="风险预算向量 (risk_budget)，None 表示等风险平价")


# ─── 约束条件 ─────────────────────────────────────────────────

class BoxConstraint(BaseModel):
    """Box 约束：lbs <= w_i <= ubs"""
    type: Literal["box"] = "box"
    lbs: float = Field(default=0.0, description="权重下限")
    ubs: float = Field(default=0.1, description="权重上限")


class IndustryExposureConstraint(BaseModel):
    """行业暴露约束"""
    type: Literal["industry_exposure"] = "industry_exposure"
    industry_data_ref: Optional[str] = Field(None, description="行业因子数据引用")
    up_limit: float = Field(default=0.3, description="行业暴露上限")
    down_limit: float = Field(default=-0.3, description="行业暴露下限")


class TurnoverConstraint(BaseModel):
    """换手率约束"""
    type: Literal["turnover"] = "turnover"
    up_limit: float = Field(default=0.5, ge=0, description="换手率上限")
    constraint_type: Literal["总换手限制", "总买入限制", "总卖出限制"] = Field(
        default="总换手限制", description="换手约束类型"
    )


class CardinalityConstraint(BaseModel):
    """基数约束：非零权重个数"""
    type: Literal["cardinality"] = "cardinality"
    max_nonzero: int = Field(default=50, ge=1, description="最大非零权重个数")


class BudgetConstraint(BaseModel):
    """预算约束：总权重限制"""
    type: Literal["budget"] = "budget"
    up_limit: float = Field(default=1.0, description="权重上限")
    down_limit: float = Field(default=1.0, description="权重下限")


# 约束联合类型
ConstraintConfig = (
    BoxConstraint | IndustryExposureConstraint |
    TurnoverConstraint | CardinalityConstraint | BudgetConstraint
)


# ─── 优化请求/响应 ───────────────────────────────────────────

class FactorDataRef(BaseModel):
    """因子数据引用 — 从 FactorDB 读取某个因子在某时点的截面数据"""
    conn_id: str = Field(..., description="FactorDB 连接 ID")
    table_name: str = Field(..., description="因子表名")
    factor_name: str = Field(..., description="因子名称")
    dt: Optional[str] = Field(None, description="时点 (ISO 格式)，None 表示最新时点")


class OptimizeRequest(BaseModel):
    """组合优化请求"""
    name: str = Field(default="未命名优化", description="优化任务名称")
    solver: str = Field(default="cvxpy", description="求解器标识（cvxpy / matlab / ...）")
    objective: ObjectiveConfig = Field(..., description="优化目标配置")
    constraints: List[Dict[str, Any]] = Field(default_factory=list, description="约束条件列表")
    optim_options: Dict[str, Any] = Field(default_factory=dict, description="优化选项（求解器参数，如 solver/verbose/max_iters 等）")
    # 风险数据引用（从风险服务获取）
    risk_db_id: Optional[str] = Field(None, description="风险库 ID")
    risk_table_name: Optional[str] = Field(None, description="风险表名")
    risk_dt: Optional[str] = Field(None, description="风随时点 (ISO 格式)")
    # 可选：直接传入协方差矩阵
    cov_matrix: Optional[List[List[float]]] = Field(None, description="协方差矩阵（直接传入）")
    asset_ids: Optional[List[str]] = Field(None, description="资产 ID 列表（与 cov_matrix 配对使用）")
    # 可选：预期收益（与 expected_return_ref 互斥，ref 优先）
    expected_return: Optional[List[float]] = Field(None, description="预期收益向量")
    expected_return_ref: Optional[FactorDataRef] = Field(None, description="预期收益因子引用（从 FactorDB 读取）")
    # 可选：初始持仓、基准
    initial_weights: Optional[List[float]] = Field(None, description="初始持仓权重")
    benchmark_weights: Optional[List[float]] = Field(None, description="基准权重")
    benchmark_ref: Optional[FactorDataRef] = Field(None, description="基准权重因子引用（从 FactorDB 读取，归一化后使用）")
    # 可选：Mask（与 mask 全 True 互斥，ref 优先）
    mask_ref: Optional[FactorDataRef] = Field(None, description="Mask 因子引用 — 因子值非 NaN 的 ID 为可选资产")
    # 可选：因子暴露数据
    factor_exposures: Optional[List[List[float]]] = Field(None, description="因子暴露矩阵 (n_assets × k_factors)")
    factor_names: Optional[List[str]] = Field(None, description="因子名称列表")
    # 可选：因子协方差 + 特异性风险（用于因子模型协方差）
    factor_cov: Optional[List[List[float]]] = Field(None, description="因子协方差矩阵")
    specific_risk: Optional[List[float]] = Field(None, description="特异性风险向量")


class OptimizeResponse(BaseModel):
    """优化求解结果"""
    solution_id: str = Field(..., description="求解结果 ID")
    name: str = Field(..., description="优化任务名称")
    status: Literal["optimal", "infeasible", "unbounded", "error"] = Field(..., description="求解状态")
    message: str = Field(default="", description="求解信息")
    solver_name: str = Field(default="", description="求解器名称")
    solve_time: float = Field(default=0.0, description="求解耗时（秒）")
    weights: List[float] = Field(default_factory=list, description="最优权重")
    asset_ids: List[str] = Field(default_factory=list, description="资产 ID 列表")
    # 风险分解（如可用）
    risk_decomposition: Optional[Dict[str, Any]] = Field(None, description="风险分解")


class SolutionInfo(BaseModel):
    """求解结果信息"""
    solution_id: str = Field(..., description="求解结果 ID")
    name: str = Field(..., description="优化任务名称")
    status: str = Field(..., description="求解状态")
    message: str = Field(default="", description="求解信息")
    solver_name: str = Field(default="", description="求解器名称")
    solve_time: float = Field(default=0.0, description="求解耗时（秒）")
    asset_count: int = Field(default=0, description="资产数量")
    nonzero_count: int = Field(default=0, description="非零权重数量")
    created_at: str = Field(default="", description="创建时间")


# ─── 保存的任务 ──────────────────────────────────────────────

class SavedTask(BaseModel):
    """已保存的优化任务配置"""
    id: str = Field(..., description="任务 ID")
    name: str = Field(..., description="任务名称")
    config: OptimizeRequest = Field(..., description="完整优化配置")
    created_at: str = Field(default="", description="创建时间")
    updated_at: str = Field(default="", description="更新时间")

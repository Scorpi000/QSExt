"""
因子挖掘相关 Pydantic 模型
"""

from datetime import datetime
from typing import Optional, List, Any, Dict, Literal

from pydantic import BaseModel, Field


# ─── 因子引用 ─────────────────────────────────────────────────

class TerminalFactorRef(BaseModel):
    """终端因子引用"""
    conn_id: str = Field(..., description="FactorDB 连接 ID")
    table_name: str = Field(..., description="因子表名")
    factor_name: str = Field(..., description="因子名称")


class PriceRef(BaseModel):
    """价格因子引用（用于适应度评估）"""
    conn_id: str = Field(..., description="价格因子所在的 FactorDB 连接 ID")
    table_name: str = Field(..., description="价格因子所在的表名")
    factor_name: str = Field(default="close", description="价格因子名称")


# ─── 评估配置 ─────────────────────────────────────────────────

class EvalModuleConfig(BaseModel):
    """单个评估模块配置"""
    module: str = Field(..., description="回测模块标识，如 ic、multi_portfolio")
    params: Dict[str, Any] = Field(default_factory=dict, description="模块参数")


class EvalConfig(BaseModel):
    """适应度评估配置"""
    modules: List[EvalModuleConfig] = Field(..., min_length=1, description="评估模块列表")
    transform: str = Field(default="identity", description="transform 函数：内置函数名 或 @path/to/script.py")
    sign: Literal["greater", "less"] = Field(default="greater", description="greater=越大越好, less=越小越好")

    @classmethod
    def from_simplified(cls, module: str, metric: str, transform: str = "abs", sign: str = "greater", params: dict = None) -> "EvalConfig":
        """从简化格式构造完整 EvalConfig"""
        return cls(
            modules=[EvalModuleConfig(module=module, params=params or {})],
            transform=transform,
            sign=sign,
        )


# ─── 挖掘配置 ─────────────────────────────────────────────────

class GPRunConfig(BaseModel):
    """GP 挖掘运行配置（一次 run 的参数）"""
    # 算子与终端
    operators: List[str] = Field(default_factory=list, description="算子名称列表，如 ['add', 'sub', 'mul']")
    terminal_factors: List[TerminalFactorRef] = Field(..., min_length=0, description="终端因子列表")
    seed_factors: List[TerminalFactorRef] = Field(default_factory=list, description="种子因子列表，其叶节点自动并入终端因子")

    # GP 参数
    population_size: int = Field(default=1000, ge=10, le=100000, description="种群大小")
    n_generations: int = Field(default=20, ge=1, le=1000, description="进化代数")
    tournament_size: int = Field(default=20, ge=2, description="锦标赛选择参赛者数量")
    init_depth: tuple = Field(default=(2, 6), description="初始树深度范围")
    init_method: Literal["grow", "full", "half and half"] = Field(default="half and half", description="初始化方法")
    const_range: Optional[tuple] = Field(default=(-1.0, 1.0), description="常数范围，null 表示不使用常数")
    p_crossover: float = Field(default=0.9, ge=0.0, le=1.0, description="交叉概率")
    p_subtree_mutation: float = Field(default=0.01, ge=0.0, le=1.0, description="子树变异概率")
    p_hoist_mutation: float = Field(default=0.01, ge=0.0, le=1.0, description="提升变异概率")
    p_point_mutation: float = Field(default=0.01, ge=0.0, le=1.0, description="点变异概率")
    p_point_replace: float = Field(default=0.05, ge=0.0, le=1.0, description="点变异中每个节点被替换的概率")
    parsimony_coefficient: float = Field(default=0.0, ge=0.0, description="复杂度惩罚系数")

    # 运行时
    price_ref: Optional[PriceRef] = Field(None, description="价格因子引用（评估模块需要价格时必填）")
    section_id_source: Optional[str] = Field(None, description="截面 ID 源名称")
    descriptor_ids: Optional[List[str]] = Field(None, description="自定义截面 ID 列表")

    eval: EvalConfig = Field(..., description="适应度评估配置")


# ─── 任务与运行 ──────────────────────────────────────────────

class RunStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunSummary(BaseModel):
    """一次运行的摘要信息"""
    run_id: str = Field(..., description="运行 ID，如 '001'")
    status: str = Field(default="pending", description="运行状态")
    n_generations: int = Field(default=0, description="进化代数")
    started_at: Optional[str] = Field(None, description="开始时间")
    completed_at: Optional[str] = Field(None, description="完成时间")


class MiningTaskSummary(BaseModel):
    """任务摘要（用于列表展示）"""
    task_id: str = Field(..., description="任务 ID")
    name: str = Field(default="", description="任务名称")
    framework: str = Field(..., description="挖掘框架标识")
    status: str = Field(default="pending", description="当前状态")
    current_run: int = Field(default=0, description="已完成运行数")
    created_at: str = Field(default="", description="创建时间")


class MiningTask(BaseModel):
    """任务详情"""
    task_id: str = Field(..., description="任务 ID")
    name: str = Field(default="", description="任务名称")
    framework: str = Field(..., description="挖掘框架标识")
    runs: List[RunSummary] = Field(default_factory=list, description="运行历史")
    created_at: str = Field(default="", description="创建时间")


# ─── 结果模型 ────────────────────────────────────────────────

class HallOfFameEntry(BaseModel):
    """Hall of Fame 单个条目"""
    rank: int = Field(..., description="排名")
    fitness: float = Field(..., description="适应度值")
    expression: str = Field(..., description="因子表达式字符串")
    pn_structure: List[Dict[str, Any]] = Field(default_factory=list, description="PN 结构化表示（内部使用，API 不暴露）", exclude=True)


class RunResult(BaseModel):
    """一次运行的结果"""
    run_id: str = Field(..., description="运行 ID")
    hall_of_fame: List[HallOfFameEntry] = Field(default_factory=list, description="Hall of Fame")
    fitness_history: Dict[str, List[float]] = Field(default_factory=dict, description="适应度历史: {gen_best: [...], gen_avg: [...]}")
    gen_start: int = Field(default=0, description="本次运行的起始代数（接续时 > 0）")
    gen_end: int = Field(default=0, description="本次运行的结束代数")


# ─── DAG 模型 ────────────────────────────────────────────────

class FactorTreeNode(BaseModel):
    """因子树节点"""
    id: str = Field(..., description="节点 ID")
    name: str = Field(..., description="节点显示名（算子名或因子名）")
    type: Literal["operator", "terminal"] = Field(..., description="节点类型")


class FactorTreeEdge(BaseModel):
    """因子树边"""
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")


class FactorTreeDAG(BaseModel):
    """因子树 DAG 数据（React Flow 兼容）"""
    nodes: List[FactorTreeNode] = Field(default_factory=list, description="节点列表")
    edges: List[FactorTreeEdge] = Field(default_factory=list, description="边列表")


# ─── API 请求 ────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str = Field(default="", description="任务名称")
    framework: str = Field(..., description="挖掘框架标识")


class SubmitRunRequest(BaseModel):
    """提交运行请求"""
    config: GPRunConfig = Field(..., description="运行配置")


class ContinueRunRequest(BaseModel):
    """接续运行请求"""
    config: GPRunConfig = Field(..., description="运行配置（算子和终端因子被忽略，使用父 run 的配置）")


class ExportRequest(BaseModel):
    """导出请求"""
    target_dir: Optional[str] = Field(None, description="目标目录，默认写入 config.factor_def.scripts_dir")


# ─── 框架模型 ────────────────────────────────────────────────

class FrameworkInfo(BaseModel):
    """挖掘框架信息"""
    key: str = Field(..., description="框架唯一标识")
    name: str = Field(..., description="框架名称")
    description: str = Field(default="", description="框架描述")
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="配置模板（前端据此渲染表单）")

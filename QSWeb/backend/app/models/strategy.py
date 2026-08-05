"""
策略工作台 Pydantic 模型
"""
from typing import Optional, List, Dict
from datetime import datetime

from pydantic import BaseModel, Field


# ─── 策略元信息 ─────────────────────────────────────────────────

class OperatorConfigModel(BaseModel):
    """策略算子配置模型"""
    SignalType: str = Field(default="目标权重", title="信号类型")
    InitCash: float = Field(default=1e6, title="初始资金")
    ShortAllowed: bool = Field(default=False, title="是否允许卖空")


class StrategyMetaModel(BaseModel):
    """策略元信息模型 —— 对应 __STRATEGY_META__"""
    Name: str = Field(default="", title="策略名称")
    QSID: Optional[str] = Field(default=None, title="策略 QSID")
    TargetTable: str = Field(default="", title="输出因子表名")
    IDType: str = Field(default="A股", title="证券类型")
    OperatorConfig: OperatorConfigModel = Field(
        default_factory=OperatorConfigModel, title="算子配置"
    )
    FactorDeps: Dict[str, List] = Field(default={}, title="依赖因子")
    StrategyDeps: Dict[str, Dict[str, str]] = Field(default={}, title="依赖策略")
    DBDeps: Dict[str, str] = Field(default={}, title="因子库依赖")
    ModelArgs: Dict[str, str] = Field(default={}, title="模型参数")
    Author: str = Field(default="Anonymous", title="作者")
    Description: str = Field(default="", title="描述")
    Tags: List[str] = Field(default=[], title="标签")
    MaxLookBack: int = Field(default=365, title="最大回溯天数")
    DefScriptPath: str = Field(default="", title="定义脚本路径")


# ─── 搜索 ───────────────────────────────────────────────────────

class StrategySearchResult(BaseModel):
    """策略搜索结果"""
    QSID: str = Field(title="策略 QSID")
    Name: str = Field(title="策略名称")
    TargetTable: str = Field(default="", title="输出表名")
    IDType: str = Field(default="", title="证券类型")
    Author: str = Field(default="", title="作者")
    Description: str = Field(default="", title="描述")
    Tags: List[str] = Field(default=[], title="标签")
    DefScriptPath: str = Field(default="", title="脚本路径")
    UpdatedAt: Optional[str] = Field(default=None, title="更新时间")
    Similarity: Optional[float] = Field(default=None, title="语义相似度")


# ─── 导入/预览 ──────────────────────────────────────────────────

class StrategyImportRequest(BaseModel):
    """策略导入请求"""
    code: str = Field(title="策略 Python 代码")
    filename: Optional[str] = Field(default=None, title="文件名（可选，用于保存）")


class StrategyImportPreviewResponse(BaseModel):
    """策略导入预览响应"""
    valid: bool = Field(title="是否有效")
    meta: Optional[StrategyMetaModel] = Field(default=None, title="解析出的元信息")
    errors: List[str] = Field(default=[], title="验证错误列表")
    warnings: List[str] = Field(default=[], title="验证警告列表")


# ─── 回测请求/响应 ──────────────────────────────────────────────

class FactorRefModel(BaseModel):
    """因子引用模型"""
    name: str = Field(title="因子名")
    source: str = Field(default="db", title="来源: db / registry")
    conn_id: Optional[str] = Field(default=None, title="连接 ID（source=db 时）")
    table_name: Optional[str] = Field(default=None, title="因子表名（source=db 时）")


class StrategyBacktestRequest(BaseModel):
    """策略回测请求"""
    # 策略标识（二选一）
    code: Optional[str] = Field(default=None, title="策略 Python 代码字符串")
    strategy_qsid: Optional[str] = Field(default=None, title="已注册策略的 QSID")

    # 因子依赖映射
    factor_refs: List[FactorRefModel] = Field(default=[], title="依赖因子映射")

    # 参数覆盖
    model_args: Dict = Field(default={}, title="ModelArgs 覆盖值")
    operator_config: Optional[OperatorConfigModel] = Field(
        default=None, title="OperatorConfig 覆盖"
    )

    # 日期范围
    start_date: str = Field(title="起始日期 (YYYY-MM-DD)")
    end_date: str = Field(title="截止日期 (YYYY-MM-DD)")
    dt_mode: str = Field(default="natural", title="时点模式: natural / trading")

    # 截面
    descriptor_ids: Optional[List[str]] = Field(default=None, title="截面证券列表")


class StrategyBacktestResult(BaseModel):
    """策略回测结果"""
    task_id: str = Field(title="异步任务 ID")


# ─── 可用因子 ───────────────────────────────────────────────────

class AvailableFactor(BaseModel):
    """可用因子项"""
    name: str = Field(title="因子名")
    source: str = Field(title="来源: db / registry")
    conn_id: Optional[str] = Field(default=None, title="连接 ID")
    table_name: Optional[str] = Field(default=None, title="因子表名")
    qsid: Optional[str] = Field(default=None, title="QSID（registry 来源）")
    description: Optional[str] = Field(default=None, title="因子描述")


# ─── 策略删除 ───────────────────────────────────────────────────

class StrategyDeleteResponse(BaseModel):
    """策略删除响应"""
    qsid: str = Field(title="策略 QSID")
    deleted: bool = Field(title="是否已删除")
    file_deleted: bool = Field(default=False, title="是否删除了文件")

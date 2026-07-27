"""
回测数据模型
"""

from typing import Optional, List, Any, Dict
from datetime import date
from pydantic import BaseModel, Field


# ─── IC 分析 ─────────────────────────────────────────────

class ICAnalysisRequest(BaseModel):
    """IC 分析请求"""
    conn_id: str = Field(..., description="因子库连接 ID")
    table_name: str = Field(..., description="因子表名称")
    factor_name: str = Field(..., description="因子名称")
    price_table_name: str = Field("", description="价格表名称（同一因子库中,默认与因子表相同）")
    price_field: str = Field("复权收盘价", description="价格字段名")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    corr_method: str = Field("spearman", description="IC 计算方法: spearman / pearson")
    lookback: int = Field(1, ge=1, description="前视期数")


class ICAnalysisResponse(BaseModel):
    """IC 分析响应"""
    ic_series: List[Dict[str, Any]] = Field(default_factory=list, description="IC 时间序列")
    ic_decay: List[Dict[str, Any]] = Field(default_factory=list, description="IC 衰减")
    summary: Dict[str, Any] = Field(default_factory=dict, description="统计摘要")
    factor_name: str = ""
    corr_method: str = "spearman"


# ─── 分位数组合 ──────────────────────────────────────────

class QuantilePortfolioRequest(BaseModel):
    """分位数组合请求"""
    conn_id: str = Field(..., description="因子库连接 ID")
    table_name: str = Field(..., description="因子表名称")
    factor_name: str = Field(..., description="因子名称")
    price_table_name: str = Field("", description="价格表名称")
    price_field: str = Field("复权收盘价", description="价格字段名")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    n_groups: int = Field(5, ge=2, le=20, description="分组数量")
    rebalance_freq: str = Field("monthly", description="再平衡频率: daily / weekly / monthly")


class QuantilePortfolioResponse(BaseModel):
    """分位数组合响应"""
    nav_series: List[Dict[str, Any]] = Field(default_factory=list, description="各分组净值曲线")
    long_short_nav: List[Dict[str, Any]] = Field(default_factory=list, description="多空净值曲线")
    summary: Dict[str, Any] = Field(default_factory=dict, description="分组统计")
    factor_name: str = ""
    n_groups: int = 5


# ─── 换手率 ──────────────────────────────────────────────

class TurnoverRequest(BaseModel):
    """换手率分析请求"""
    conn_id: str = Field(..., description="因子库连接 ID")
    table_name: str = Field(..., description="因子表名称")
    factor_name: str = Field(..., description="因子名称")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    top_pct: float = Field(0.2, ge=0.01, le=0.5, description="头部选股比例")
    rebalance_freq: str = Field("monthly", description="再平衡频率: daily / weekly / monthly")


class TurnoverResponse(BaseModel):
    """换手率响应"""
    turnover_series: List[Dict[str, Any]] = Field(default_factory=list, description="换手率时间序列")
    avg_turnover: float = 0.0
    factor_name: str = ""


# ─── 策略回测 ────────────────────────────────────────────

class StrategyBacktestRequest(BaseModel):
    """策略回测请求"""
    conn_id: str = Field(..., description="因子库连接 ID")
    table_name: str = Field(..., description="因子表名称")
    factor_name: str = Field(..., description="因子/信号名称")
    price_table_name: str = Field("", description="价格表名称")
    price_field: str = Field("复权收盘价", description="价格字段名")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    initial_capital: float = Field(1000000.0, ge=0, description="初始资金")
    commission_rate: float = Field(0.0003, ge=0, le=0.01, description="佣金费率")
    slippage: float = Field(0.001, ge=0, le=0.02, description="滑点比例")
    rebalance_freq: str = Field("monthly", description="再平衡频率: daily / weekly / monthly")
    signal_direction: str = Field("long", description="信号方向: long / short / long_short")
    top_n: int = Field(20, ge=1, le=200, description="选股数量")


class BacktestResult(BaseModel):
    """回测结果"""
    task_id: str = ""
    nav_series: List[Dict[str, Any]] = Field(default_factory=list, description="净值曲线")
    daily_returns: List[Dict[str, Any]] = Field(default_factory=list, description="日收益率")
    trades: List[Dict[str, Any]] = Field(default_factory=list, description="交易记录")
    summary: Dict[str, Any] = Field(default_factory=dict, description="统计指标")
    params: Dict[str, Any] = Field(default_factory=dict, description="回测参数")


# ─── 回测历史 ────────────────────────────────────────────

class BacktestHistoryQuery(BaseModel):
    """回测历史查询"""
    factor_name: Optional[str] = Field(None, description="因子名称筛选")
    start_date: Optional[date] = Field(None, description="起始日期")
    end_date: Optional[date] = Field(None, description="截止日期")
    limit: int = Field(20, ge=1, le=100, description="返回数量上限")


class BacktestRegisterRequest(BaseModel):
    """回测注册请求"""
    name: Optional[str] = Field(None, description="回测名称")
    category: Optional[str] = Field(None, description="回测类别: SectionFactor / Strategy")


# ─── 任务状态 ────────────────────────────────────────────

class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str = ""
    name: str = ""
    status: str = ""
    progress: float = 0.0
    progress_message: str = ""
    error: Optional[str] = None
    result: Optional[Any] = None

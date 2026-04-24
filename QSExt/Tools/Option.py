from enum import Enum
import traceback
from typing import List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from scipy.stats import norm
from scipy.optimize import brentq
from pydantic import BaseModel, Field


class OptionType(str, Enum):
    """期权类型枚举"""
    CALL = "call"
    PUT = "put"

class MarketParams(BaseModel):
    """市场参数模型"""
    spot_price: float = Field(gt=0, description="标的资产当前价格")
    risk_free_rate: float = Field(description="无风险利率 (例如 0.05)")
    volatility: Optional[float] = Field(default=None, gt=0, description="历史波动率或基准波动率")

class EuropeanBlackSholesModel:
    """欧式期权的 Black-Sholes 模型"""

    @classmethod
    def calcIntrinsicValue(cls, s: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, -1))

        if option_type == OptionType.CALL:
            intrinsic_value = np.maximum(s - k, 0)
        else:# PUT
            intrinsic_value = np.maximum(k - s, 0)
        return np.squeeze(intrinsic_value)

    @classmethod
    def calcExpiryPayoff(cls, s: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, -1))

        if option_type == OptionType.CALL:
            payoff = np.maximum(s - k, 0)
        else:
            payoff = np.maximum(k - s, 0)
        return np.squeeze(payoff)

    @classmethod
    def calcPrice(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的理论价格。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            option_type: 期权类型, CALL 或者 PUT
        
        Returns:
            期权理论价格
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))

        # 内在价值
        if option_type == OptionType.CALL:
            intrinsic_value = np.maximum(s - k, 0)
        else:# PUT
            intrinsic_value = np.maximum(k - s, 0)
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        d2 = d1 - sigma * np.sqrt(tau)
        if option_type == OptionType.CALL:
            price = s * norm.cdf(d1) - k * np.exp(-r * tau) * norm.cdf(d2)
        else:# PUT
            price = k * np.exp(-r * tau) * norm.cdf(-d2) - s * norm.cdf(-d1)
        price = np.where(tau <= 0, intrinsic_value, price)
        return np.squeeze(price)

    @classmethod
    def calcDelta(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的希腊字母 Delta。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            option_type: 期权类型, CALL 或者 PUT
        
        Returns:
            希腊字母 Delta
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        if option_type == OptionType.CALL:
            greek = norm.cdf(d1)
        else:
            greek = norm.cdf(d1) - 1
        greek = np.where(tau <= 0, 0, greek)
        return np.squeeze(greek)

    @classmethod
    def calcGamma(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的希腊字母 Gamma。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
        
        Returns:
            希腊字母 Gamma
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        greek = norm.pdf(d1) / (s * sigma * np.sqrt(tau))
        greek = np.where(tau <= 0, 0, greek)
        return np.squeeze(greek)

    @classmethod
    def calcTheta(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的希腊字母 Theta。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            option_type: 期权类型, CALL 或者 PUT
        
        Returns:
            希腊字母 Theta
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        d2 = d1 - sigma * np.sqrt(tau)
        term1 = - (s * norm.pdf(d1) * sigma) / (2 * np.sqrt(tau))
        if option_type == OptionType.CALL:
            term2 = -r * k * np.exp(-r * tau) * norm.cdf(d2)
        else:
            term2 = r * k * np.exp(-r * tau) * norm.cdf(-d2)
        greek = (term1 + term2)
        greek = np.where(tau <= 0, 0, greek)
        return np.squeeze(greek)
    
    @classmethod
    def calcRho(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的希腊字母 Rho。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            option_type: 期权类型, CALL 或者 PUT
        
        Returns:
            希腊字母 Rho
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        d2 = d1 - sigma * np.sqrt(tau)
        if option_type == OptionType.CALL:
            greek = k * tau * np.exp(-r * tau) * norm.cdf(d2)
        else:
            greek = -k * tau * np.exp(-r * tau) * norm.cdf(-d2)
        greek = np.where(tau <= 0, 0, greek)
        return np.squeeze(greek)
    
    @classmethod
    def calcVega(cls, s: float | np.ndarray, tau: float | np.ndarray, r: float | np.ndarray, sigma: float | np.ndarray, k: float | np.ndarray, option_type: OptionType=OptionType.CALL) -> float | np.ndarray:
        """
        基于 Black-Sholes 公式计算期权的希腊字母 Vega。每个入参可以是标量或者是一维向量，返回的结果是高维数组，如果某个入参是向量，则对应的返回结果增加一维，维度和入参位置一一对应

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            option_type: 期权类型, CALL 或者 PUT
        
        Returns:
            希腊字母 Vega
        """
        if isinstance(s, np.ndarray): s = s.reshape((-1, 1, 1, 1, 1))
        if isinstance(tau, np.ndarray): tau = tau.reshape((1, -1, 1, 1, 1))
        if isinstance(r, np.ndarray): r = r.reshape((1, 1, -1, 1, 1))
        if isinstance(sigma, np.ndarray): sigma = sigma.reshape((1, 1, 1, -1, 1))
        if isinstance(k, np.ndarray): k = k.reshape((1, 1, 1, 1, -1))
        
        d1 = (np.log(s / k) + (r + 0.5 * sigma ** 2) * tau) / (sigma * np.sqrt(tau))
        greek = s * norm.pdf(d1) * np.sqrt(tau)
        greek = np.where(tau <= 0, 0, greek)
        return np.squeeze(greek)

    @classmethod
    def calcImpliedVolatility(cls, p: float, s: float, tau: float, r: float, k: float, option_type: OptionType=OptionType.CALL) -> Optional[float]:
        """
        计算期权的隐含波动率。

        Args:
            p: 期权价格
            s: 标的资产价格
            r: 无风险利率

        Returns:
            Optional[float]: 隐含波动率，如果无法计算则返回 None
        """
        def objective(sigma):
            theoretical_price = cls.calcPrice(s=s, tau=tau, r=r, sigma=sigma, k=k, option_type=option_type)
            return theoretical_price - p

        intrinsic_val = max(s - k, 0) if option_type == OptionType.CALL else max(k - s, 0)
        if p < intrinsic_val:
            raise Exception(f"隐含波动率求解失败: 条件不合理 option_price={p}, spot_price={s}, strike={k}, option_type={option_type}")
        
        try:
            iv = brentq(objective, 0.001, 5.0, maxiter=100)
            return iv
        except ValueError:
            raise Exception(f"隐含波动率求解失败: {traceback.format_exc()}")


class Option(BaseModel):
    """
    代表单个的期权
    """
    kind: str = Field(default="European", description="期权种类")
    option_type: OptionType = Field(description="期权类型 (CALL/PUT)")
    strike: float = Field(gt=0, description="期权行权价")
    maturity: float = Field(ge=0, description="期权剩余到期时间 (年)")
    market_price: Optional[float] = Field(None, ge=0, description="市场价格 (可选)")
    quantity: int = Field(default=1, description="期权数量 (正数表示买入，负数表示卖出)")

class EuropeanOptionPortfolio:
    """代表一个由多个欧式期权组成的组合。主要职责是聚合单个期权的计算结果并提供整体视图。"""

    def __init__(self, market_params: MarketParams, options: List[Option]):
        """
        初始化期权组合。

        Args:
            market_params: 市场参数对象
            options: 期权列表
        """
        self.market_params = market_params
        self.options = options

    def get_net_premium(self) -> float:
        """
        计算构建组合的初始净权利金成本 (正数为支出，负数为收入)。

        Returns:
            净权利金成本
        """
        premium = 0.0
        for opt in self.options:
            # 如果有市场价格，优先使用市场价格计算成本，否则使用理论价格
            if opt.market_price is not None:
                price = opt.market_price
            else:
                price = EuropeanBlackSholesModel.calcPrice(s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, sigma=self.market_params.volatility, k=opt.strike, option_type=opt.option_type)
            premium += opt.quantity * price
        return premium

    def get_payoff_at_expiry(self, s: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarry]=None, include_premium: bool=False) -> float | np.ndarray:
        """
        计算组合到期时的总盈亏

        Args:
            s: 标的资产价格
            include_premium: 是否包含初始成本

        Returns:
            np.ndarray: 对应的到期盈亏数组
        """
        if s is None: s = self.market_params.spot_price

        total_payoff = 0
        for opt in self.options:
            total_payoff += EuropeanBlackSholesModel.calcExpiryPayoff(s=s, k=(opt.strike if k is None else k), option_type=opt.option_type) * opt.quantity
        if include_premium: total_payoff = total_payoff - self.get_net_premium()
        return total_payoff
    
    def get_individual_payoff_at_expiry(self, s: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarry]=None, include_premium: bool=False) -> np.ndarray:
        """
        计算组合到期时的总盈亏

        Args:
            s: 标的资产价格
            include_premium: 是否包含初始成本

        Returns:
            np.ndarray: 对应的到期盈亏数组
        """
        if s is None: s = self.market_params.spot_price

        payoff_list = []
        for opt in self.options:
            payoff = EuropeanBlackSholesModel.calcExpiryPayoff(s=s, k=(opt.strike if k is None else k), option_type=opt.option_type) * opt.quantity
            if include_premium:
                # 如果有市场价格，优先使用市场价格计算成本，否则使用理论价格
                if opt.market_price is not None:
                    premium = opt.market_price
                else:
                    premium = EuropeanBlackSholesModel.calcPrice(s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, sigma=self.market_params.volatility, k=opt.strike, option_type=opt.option_type)
                payoff = payoff - premium * opt.quantity
            payoff_list.append(payoff)
        return np.array(payoff_list)

    def get_current_theoretical_value(self, s: Optional[float | np.ndarray]=None, tau: Optional[float | np.ndarray]=None, r: Optional[float | np.ndarray]=None, sigma: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarray]=None, include_premium: bool=False) -> float | np.ndarray:
        """
        计算当前时刻在给定标的价格范围下的理论价值

        Args:
            spot_price_range: 标的资产价格数组
            include_premium: 是否包含权利金

        Returns:
            np.ndarray: 对应的当前理论盈亏数组
        """
        current_values = np.zeros_like(spot_price_range, dtype=float)
        for opt in self.options:
            price = opt.get_theoretical_price(spot_price_range, self.market_params.risk_free_rate, volatility=self.market_params.volatility, spot_price=self.market_params.spot_price)
            current_values += opt.quantity * price
        if include_premium: current_values = current_values - self.get_net_premium()
        return current_values

    def get_greeks(self, spot_price_range: np.ndarray) -> pd.DataFrame:
        """
        计算当前组合的总希腊字母。

        Args:
            spot_price_range: 标的资产价格数组

        Returns:
            组合的总希腊字母
        """
        total_greeks = pd.DataFrame(0, index=spot_price_range, columns=["delta", "gamma", "theta", "vega", "rho"])

        for opt in self.options:
            greeks = opt.get_greeks(spot_price_range, self.market_params.risk_free_rate, volatility=self.market_params.volatility, spot_price=self.market_params.spot_price)
            total_greeks += opt.quantity * greeks

        return total_greeks

# ==========================================
# 绘图功能
# ==========================================

def plot_portfolio_pnl(portfolio: EuropeanOptionPortfolio, portfolio_pnl: pd.Series, individual_pnl: Optional[pd.DataFrame]=None, ax=None):
    """
    绘制期权组合的盈亏分布
    
    Args:
        portfolio : 期权组合
        portfolio_pnl: 期权组合盈亏
        individual_pnl: 单个期权盈亏
        ax : 绘图的坐标轴
    """
    if ax is None:
        fig = Figure(figsize=(12, 7))
        ax = fig.add_subplot(1, 1, 1)
    else:
        fig = None
    colors = plt.cm.tab10(np.linspace(0, 1, len(portfolio.options)))
    # 绘制单个期权盈亏
    if individual_pnl is not None:
        for i, opt in enumerate(portfolio.options):
            label = (f"{'买入' if opt.quantity > 0 else '卖出'}"
                    f"{opt.quantity}手"
                    f"{'看涨' if opt.option_type == OptionType.CALL else '看跌'}"
                    f"(K={opt.strike}, P={opt.market_price})")
            ax.plot(individual_pnl.index, individual_pnl.iloc[:, i].values, '--', alpha=0.6, color=colors[i], label=label)
    
    # 绘制组合总盈亏
    ax.plot(portfolio_pnl.index, portfolio_pnl.values, 'k-', linewidth=2.5, label='组合总盈亏')
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    
    # 标注关键行权价
    for opt in portfolio.options:
        strike = opt.strike
        ax.axvline(x=strike, color='red', linestyle=':', alpha=0.4)
        ax.annotate(f'K={strike}', xy=(strike, ax.get_ylim()[0]), xytext=(strike, ax.get_ylim()[0]*0.9), fontsize=8, color='red', ha='center')
    
    # 标注盈亏平衡点
    zero_crossings = portfolio_pnl.index[:-1][np.diff(np.sign(portfolio_pnl.values)) != 0]
    for bp in zero_crossings[:3]:# 最多标注3个平衡点
        ax.plot(bp, 0, color='steelblue', marker='o', markersize=8)
        ax.annotate(f'盈亏平衡\n{bp:.2f}', xy=(bp, 0), xytext=(bp, max(portfolio_pnl.values)*0.1), fontsize=9, ha='center')
    
    # 最大盈利/亏损标注
    S_max, S_min = portfolio_pnl.index[0], portfolio_pnl.index[-1]
    max_profit = portfolio_pnl.max()
    max_loss = portfolio_pnl.min()
    ax.annotate(f'最大盈利: {max_profit:.2f}',  xy=(portfolio_pnl.idxmax(), max_profit), xytext=(portfolio_pnl.idxmax() + (S_max-S_min)*0.05, max_profit*0.9), fontsize=10, color='red', arrowprops=dict(arrowstyle='->', color='red'))
    ax.annotate(f'最大亏损: {max_loss:.2f}', xy=(portfolio_pnl.idxmin(), max_loss), xytext=(portfolio_pnl.idxmin() + (S_max-S_min)*0.05, max_loss*1.1), fontsize=10, color='green', arrowprops=dict(arrowstyle='->', color='green'))
    
    # ax.set_xlabel('标的资产到期价格 $S_T$', fontsize=12)
    # ax.set_ylabel('到期盈亏', fontsize=12)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    return fig, ax

def plot_greek(greek: pd.DataFrame, S_0:Optional[float]=None, ax = None):
    """
    计算并绘制期权组合的希腊字母分布
    
    Args:
        greek : 希腊字母, 
        S_0: 当前价格
    """
    if ax is None:
        fig = Figure(figsize=(12, 7))
        ax = fig.add_subplot(1, 1, 1)
    else:
        fig = None

    colors = plt.cm.tab10(np.linspace(0, 1, len(greek.columns)))

    for i, igreek in enumerate(greek.columns):
        ax.plot(greek.index, greek[igreek].values, label=igreek, color=colors[i], alpha=0.9)
        ax.axhline(0, color='black', linewidth=1)
        if S_0 is not None: ax.axvline(S_0, color='red', linestyle=':')
        ax.set_xlabel('标的资产价格')
        ax.legend()
        ax.grid(True, alpha=0.3)
    return fig, ax

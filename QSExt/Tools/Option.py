from enum import Enum
import traceback
from typing import List, Optional, Dict

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

    def get_payoff_at_expiry(self, s: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarray]=None, include_premium: bool=False) -> float | np.ndarray:
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
    
    def get_individual_payoff_at_expiry(self, s: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarray]=None, include_premium: bool=False) -> np.ndarray:
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
        计算当前组合的理论价值

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            include_premium: 是否包含权利金

        Returns:
            组合当前理论价值
        """
        if s is None: s = self.market_params.spot_price
        if r is None: r = self.market_params.risk_free_rate
        if sigma is None: sigma = self.market_params.volatility

        current_value = 0
        for i, opt in enumerate(self.options):
            opt_tau = (opt.maturity if tau is None else tau)
            opt_k = (opt.strike if k is None else k)
            if (sigma is None) and (opt.market_price is None):
                raise Exception(f"没有传入波动率，市场参数中没有波动率，并且第 {i} 个期权的市场价格为 None 无法估计隐含波动率")
            elif sigma is None:
                opt_sigma = EuropeanBlackSholesModel.calcImpliedVolatility(p=opt.market_price, s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, k=opt.strike, option_type=opt.option_type)
            else:
                opt_sigma = sigma
            price = EuropeanBlackSholesModel.calcPrice(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type)
            current_value += opt.quantity * price
        if include_premium: current_value = current_value - self.get_net_premium()
        return current_value

    def get_individual_current_theoretical_value(self, s: Optional[float | np.ndarray]=None, tau: Optional[float | np.ndarray]=None, r: Optional[float | np.ndarray]=None, sigma: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarray]=None, include_premium: bool=False) -> float | np.ndarray:
        """
        计算当前组合的理论价值

        Args:
            s: 标的资产价格
            tau: 到期时间(单位：年)
            r: 无风险利率
            sigma: 波动率
            k: 执行价
            include_premium: 是否包含权利金

        Returns:
            组合当前理论价值
        """
        if s is None: s = self.market_params.spot_price
        if r is None: r = self.market_params.risk_free_rate
        if sigma is None: sigma = self.market_params.volatility

        current_value_list = []
        for i, opt in enumerate(self.options):
            opt_tau = (opt.maturity if tau is None else tau)
            opt_k = (opt.strike if k is None else k)
            if (sigma is None) and (opt.market_price is None):
                raise Exception(f"没有传入波动率，市场参数中没有波动率，并且第 {i} 个期权的市场价格为 None 无法估计隐含波动率")
            elif sigma is None:
                opt_sigma = EuropeanBlackSholesModel.calcImpliedVolatility(p=opt.market_price, s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, k=opt.strike, option_type=opt.option_type)
            else:
                opt_sigma = sigma
            value = EuropeanBlackSholesModel.calcPrice(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity
            if include_premium:
                # 如果有市场价格，优先使用市场价格计算成本，否则使用理论价格
                if opt.market_price is not None:
                    premium = opt.market_price
                else:
                    premium = EuropeanBlackSholesModel.calcPrice(s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, sigma=self.market_params.volatility, k=opt.strike, option_type=opt.option_type)
                value = value - premium * opt.quantity
            current_value_list.append(value)
        return np.array(current_value_list)

    def get_greeks(self, s: Optional[float | np.ndarray]=None, tau: Optional[float | np.ndarray]=None, r: Optional[float | np.ndarray]=None, sigma: Optional[float | np.ndarray]=None, k: Optional[float | np.ndarray]=None) -> Dict[str, np.ndarray]:
        """
        计算当前组合的总希腊字母。

        Args:
            spot_price_range: 标的资产价格数组

        Returns:
            组合的总希腊字母
        """
        if s is None: s = self.market_params.spot_price
        if r is None: r = self.market_params.risk_free_rate
        if sigma is None: sigma = self.market_params.volatility

        greeks = {"Delta": 0, "Gamma": 0, "Theta": 0, "Vega": 0, "Rho": 0}
        for i, opt in enumerate(self.options):
            opt_tau = (opt.maturity if tau is None else tau)
            opt_k = (opt.strike if k is None else k)
            if (sigma is None) and (opt.market_price is None):
                raise Exception(f"没有传入波动率，市场参数中没有波动率，并且第 {i} 个期权的市场价格为 None 无法估计隐含波动率")
            elif sigma is None:
                opt_sigma = EuropeanBlackSholesModel.calcImpliedVolatility(p=opt.market_price, s=self.market_params.spot_price, tau=opt.maturity, r=self.market_params.risk_free_rate, k=opt.strike, option_type=opt.option_type)
            else:
                opt_sigma = sigma
            greeks = {
                "Delta": EuropeanBlackSholesModel.calcDelta(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity + greeks["Delta"],
                "Gamma": EuropeanBlackSholesModel.calcGamma(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity + greeks["Gamma"],
                "Theta": EuropeanBlackSholesModel.calcTheta(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity + greeks["Theta"],
                "Vega": EuropeanBlackSholesModel.calcVega(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity + greeks["Vega"],
                "Rho": EuropeanBlackSholesModel.calcRho(s=s, tau=opt_tau, r=r, sigma=opt_sigma, k=opt_k, option_type=opt.option_type) * opt.quantity + greeks["Rho"]
            }
        return greeks

def plot_portfolio_value_relative_to_s(portfolio: EuropeanOptionPortfolio, portfolio_value: pd.Series, individual_value: Optional[pd.DataFrame]=None, ax=None):
    """
    绘制期权组合价值相对于标的资产价格的分布
    
    Args:
        portfolio : 期权组合
        portfolio_value: 期权组合价值
        individual_value: 单个期权价值
        ax : 绘图的坐标轴
    """
    if ax is None:
        fig = Figure(figsize=(12, 7))
        ax = fig.add_subplot(1, 1, 1)
    else:
        fig = None
    colors = plt.cm.tab10(np.linspace(0, 1, len(portfolio.options)))
    # 绘制单个期权盈亏
    if individual_value is not None:
        for i, opt in enumerate(portfolio.options):
            label = (f"{'买入' if opt.quantity > 0 else '卖出'}"
                    f"{opt.quantity}手"
                    f"{'看涨' if opt.option_type == OptionType.CALL else '看跌'}"
                    f"(K={opt.strike}, P={opt.market_price})")
            ax.plot(individual_value.index, individual_value.iloc[:, i].values, '--', alpha=0.6, color=colors[i], label=label)
    
    # 绘制组合总盈亏
    ax.plot(portfolio_value.index, portfolio_value.values, 'k-', linewidth=2.5, label='组合总盈亏')
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    
    # 标注关键行权价
    for opt in portfolio.options:
        strike = opt.strike
        ax.axvline(x=strike, color='red', linestyle=':', alpha=0.4)
        ax.annotate(f'K={strike}', xy=(strike, ax.get_ylim()[0]), xytext=(strike, ax.get_ylim()[0]*0.9), fontsize=8, color='red', ha='center')
    
    # 标注盈亏平衡点
    zero_crossings = portfolio_value.index[:-1][np.diff(np.sign(portfolio_value.values)) != 0]
    for bp in zero_crossings[:3]:# 最多标注3个平衡点
        ax.plot(bp, 0, color='steelblue', marker='o', markersize=8)
        ax.annotate(f'盈亏平衡\n{bp:.2f}', xy=(bp, 0), xytext=(bp, max(portfolio_value.values)*0.1), fontsize=9, ha='center')
    
    # 最大盈利/亏损标注
    S_max, S_min = portfolio_value.index[0], portfolio_value.index[-1]
    max_profit = portfolio_value.max()
    max_loss = portfolio_value.min()
    ax.annotate(f'最大盈利: {max_profit:.2f}',  xy=(portfolio_value.idxmax(), max_profit), xytext=(portfolio_value.idxmax() + (S_max-S_min)*0.05, max_profit*0.9), fontsize=10, color='red', arrowprops=dict(arrowstyle='->', color='red'))
    ax.annotate(f'最大亏损: {max_loss:.2f}', xy=(portfolio_value.idxmin(), max_loss), xytext=(portfolio_value.idxmin() + (S_max-S_min)*0.05, max_loss*1.1), fontsize=10, color='green', arrowprops=dict(arrowstyle='->', color='green'))
    
    # ax.set_xlabel('标的资产到期价格 $S_T$', fontsize=12)
    # ax.set_ylabel('到期盈亏', fontsize=12)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    return fig, ax

def plot_portfolio_value(portfolio: EuropeanOptionPortfolio, portfolio_value: pd.Series, individual_value: Optional[pd.DataFrame]=None, ax=None):
    """
    绘制期权组合的价值分布
    
    Args:
        portfolio : 期权组合
        portfolio_value: 期权组合价值
        individual_value: 单个期权价值
        ax : 绘图的坐标轴
    """
    if ax is None:
        fig = Figure(figsize=(12, 7))
        ax = fig.add_subplot(1, 1, 1)
    else:
        fig = None
    colors = plt.cm.tab10(np.linspace(0, 1, len(portfolio.options)))
    # 绘制单个期权价值
    if individual_value is not None:
        for i, opt in enumerate(portfolio.options):
            label = (f"{'买入' if opt.quantity > 0 else '卖出'}"
                    f"{opt.quantity}手"
                    f"{'看涨' if opt.option_type == OptionType.CALL else '看跌'}"
                    f"(K={opt.strike}, P={opt.market_price})")
            ax.plot(individual_value.index, individual_value.iloc[:, i].values, '--', alpha=0.6, color=colors[i], label=label)
    
    # 绘制组合价值
    ax.plot(portfolio_value.index, portfolio_value.values, 'k-', linewidth=2.5, label='组合')
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    
    # 最大价值/最小价值标注
    S_max, S_min = portfolio_value.index[0], portfolio_value.index[-1]
    max_profit = portfolio_value.max()
    max_loss = portfolio_value.min()
    ax.annotate(f'最大价值: {max_profit:.2f}',  xy=(portfolio_value.idxmax(), max_profit), xytext=(portfolio_value.idxmax() + (S_max-S_min)*0.05, max_profit*0.9), fontsize=10, color='red', arrowprops=dict(arrowstyle='->', color='red'))
    ax.annotate(f'最小价值: {max_loss:.2f}', xy=(portfolio_value.idxmin(), max_loss), xytext=(portfolio_value.idxmin() + (S_max-S_min)*0.05, max_loss*1.1), fontsize=10, color='green', arrowprops=dict(arrowstyle='->', color='green'))
    
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    return fig, ax

def plot_greek(greek: pd.DataFrame, current_idx:Optional[float]=None, ax = None):
    """
    计算并绘制期权组合的希腊字母分布
    
    Args:
        greek : 希腊字母, 
        current_idx: 当前位置
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
        if current_idx is not None: ax.axvline(current_idx, color='red', linestyle=':')
        ax.set_xlabel('标的资产价格')
        ax.legend()
        ax.grid(True, alpha=0.3)
    return fig, ax

def calc_single_maturity_variance(T: float, opts: pd.DataFrame, R: float) -> float:
    """
    计算单个到期月份的隐含方差

    Args:
        T: 剩余到期时间（年）
        opts: 该月份所有期权，索引为代码（可忽略），包含列：type, strike, price
        R: 无风险利率（连续复利，年化）

    Returns: 年化方差，若无法计算则返回 nan
    """
    if opts.empty:
        return np.nan

    # 1. 寻找平值执行价：对同一执行价，看涨与看跌价格差的绝对值最小
    min_diff = np.inf
    K_atm = None
    call_atm = put_atm = None
    for strike, group in opts.groupby("strike"):
        if len(group) == 2:
            c = group[group["type"] == "call"]
            p = group[group["type"] == "put"]
            if len(c) == 1 and len(p) == 1:
                diff = abs(c["price"].iloc[0] - p["price"].iloc[0])
                if diff < min_diff:
                    min_diff = diff
                    K_atm = strike
                    call_atm = c["price"].iloc[0]
                    put_atm = p["price"].iloc[0]
    if K_atm is None:
        return np.nan

    # 2. 远期价格 F
    F = K_atm + np.exp(R * T) * (call_atm - put_atm)

    # 3. 确定 K0：小于等于 F 的最大可用执行价
    all_strikes = sorted(opts["strike"].unique())
    K0_candidates = [k for k in all_strikes if k <= F]
    if not K0_candidates:
        return np.nan
    K0 = max(K0_candidates)

    # 4. 筛选虚值期权并定价
    #    用字典便于后面按执行价取价
    price_dict = {}
    for k in all_strikes:
        if k < K0:
            # 虚值看跌
            put = opts[(opts["type"] == "put") & (opts["strike"] == k)]
            if not put.empty:
                price_dict[k] = put["price"].iloc[0]
        elif k > K0:
            # 虚值看涨
            call = opts[(opts["type"] == "call") & (opts["strike"] == k)]
            if not call.empty:
                price_dict[k] = call["price"].iloc[0]
        else:  # k == K0
            call = opts[(opts["type"] == "call") & (opts["strike"] == K0)]
            put = opts[(opts["type"] == "put") & (opts["strike"] == K0)]
            if not call.empty and not put.empty:
                price_dict[K0] = (call["price"].iloc[0] + put["price"].iloc[0]) / 2.0
            elif not call.empty:
                price_dict[K0] = call["price"].iloc[0]
            elif not put.empty:
                price_dict[K0] = put["price"].iloc[0]

    if not price_dict:
        return np.nan

    # 5. 分左右方向截断连续零报价
    #    左边（执行价 <= K0）：从 K0 向下遍历，遇到连续两个零停止
    left_strikes = sorted([k for k in price_dict if k <= K0], reverse=True)  # 降序
    left_final = []
    consec_zeros = 0
    for k in left_strikes:
        p = price_dict[k]
        if p <= 1e-12 or np.isnan(p):
            consec_zeros += 1
            if consec_zeros >= 2:
                break  # 连续两个零，停止选取，且不添加当前零
            else:
                left_final.append((k, 0.0))  # 保留第一个零
        else:
            consec_zeros = 0
            left_final.append((k, p))

    # 右边（执行价 > K0）：从 K0 向上遍历
    right_strikes = sorted([k for k in price_dict if k >= K0])
    right_final = []
    consec_zeros = 0
    for k in right_strikes:
        p = price_dict[k]
        if p <= 1e-12 or np.isnan(p):
            consec_zeros += 1
            if consec_zeros >= 2:
                break
            else:
                right_final.append((k, 0.0))
        else:
            consec_zeros = 0
            right_final.append((k, p))

    # 合并并去重（K0 可能重复）
    final_pairs = left_final.copy()
    for k, p in right_final:
        if k == K0:
            continue
        final_pairs.append((k, p))
    final_pairs.sort(key=lambda x: x[0])

    strikes = np.array([x[0] for x in final_pairs])
    prices = np.array([x[1] for x in final_pairs])

    if len(strikes) == 0:
        return np.nan

    # 6. 计算 ΔK
    n = len(strikes)
    delta_K = np.zeros(n)
    if n == 1:
        delta_K[0] = 1.0  # 单点情况，理论上不会发生
    else:
        delta_K[0] = strikes[1] - strikes[0]
        delta_K[-1] = strikes[-1] - strikes[-2]
        if n > 2:
            for i in range(1, n - 1):
                delta_K[i] = (strikes[i + 1] - strikes[i - 1]) / 2.0

    # 7. 求和项
    contrib = np.sum(delta_K / (strikes**2) * np.exp(R * T) * prices)

    # 8. 方差公式
    variance = (2.0 / T) * contrib - (1.0 / T) * ((F / K0) - 1) ** 2
    return max(variance, 0.0)

def calc_variance_swap_iv(spot_price: pd.Series, risk_free_rate: pd.Series, option_info: pd.DataFrame, option_price: pd.DataFrame, option_maturity: pd.DataFrame) -> pd.Series:
    """基于方差互换原理估计隐含波动率（无模型隐含波动率，类似CBOE VIX方法）

    Args:
        spot_price: 标的资产价格序列, index 是时间序列
        risk_free_rate: 年化无风险利率（连续复利）, index 是时间序列
        option_info: 期权基本信息, index 是期权证券代码, columns=["type", "strike"], 其中 type 表示期权类型，可选值有 "call"(看涨期权), "put"(看跌期权), strike 表示期权的执行价
        option_price: 期权价格序列, index 是时间序列, columns 是期权证券代码
        option_maturity: 期权到期时间, 单位是年, index 是时间序列, columns 是期权证券代码，若值为NaN表示该时点该期权未上市。
    
    Returns:
        隐含波动率估计值（年化）, index 是时间序列
    """
    # 用于年化与分钟数转换常数
    MINUTES_PER_YEAR = 365 * 24 * 60  # 525600
    MINUTES_PER_30_DAYS = 30 * 24 * 60  # 43200
    NEAR_TERM_THRESHOLD_DAYS = 7 / 365  # 7天转换为年

    result = pd.Series(index=spot_price.index, dtype=float)

    # 主循环：每个时点
    for t in spot_price.index:
        try:
            # 当前时点在市的期权
            avail_opts = option_maturity.loc[t].dropna().index
            if len(avail_opts) == 0:
                result[t] = np.nan
                continue

            # 构建该时点所有上市期权的 DataFrame
            info = option_info.loc[avail_opts]  # type, strike
            prices = option_price.loc[t, avail_opts]
            maturities = option_maturity.loc[t, avail_opts]
            opts_df = pd.DataFrame({
                "type": info["type"],
                "strike": info["strike"],
                "price": prices.values,
                "maturity": maturities.values,
            }, index=avail_opts)

            # 按到期时间分组，选取两个最短的到期日（注意可能有微小不一致，这里直接用唯一值）
            unique_maturities = sorted(opts_df["maturity"].unique())
            if len(unique_maturities) < 2:
                result[t] = np.nan
                continue

            T_near = unique_maturities[0]
            T_next = unique_maturities[1]

            # 近月到期时间不足7天则切换至次近月，并取再下一个月份作为次近月
            if T_near < NEAR_TERM_THRESHOLD_DAYS:
                if len(unique_maturities) >= 3:
                    T_near = unique_maturities[1]
                    T_next = unique_maturities[2]
                else:
                    # 只有两个月且近月即将到期，无法可靠计算
                    result[t] = np.nan
                    continue

            # 获取近月与次近月期权子集
            near_opts = opts_df[opts_df["maturity"] == T_near].copy()
            next_opts = opts_df[opts_df["maturity"] == T_next].copy()

            if near_opts.empty or next_opts.empty:
                result[t] = np.nan
                continue

            R = risk_free_rate.loc[t]

            var_near = calc_single_maturity_variance(T_near, near_opts, R)
            var_next = calc_single_maturity_variance(T_next, next_opts, R)

            if np.isnan(var_near) or np.isnan(var_next):
                result[t] = np.nan
                continue

            # 时间加权插值到30天
            N_T1 = T_near * MINUTES_PER_YEAR
            N_T2 = T_next * MINUTES_PER_YEAR
            N_30 = MINUTES_PER_30_DAYS

            # 权重
            w_near = (N_T2 - N_30) / (N_T2 - N_T1)
            w_next = (N_30 - N_T1) / (N_T2 - N_T1)

            # 加权总方差（再乘以365/30转换为30天年化方差，开方得标准差）
            weighted_var = T_near * var_near * w_near + T_next * var_next * w_next
            implied_vol = np.sqrt((365.0 / 30.0) * max(weighted_var, 0.0))

            result[t] = implied_vol
        except Exception:
            result[t] = np.nan

    return result
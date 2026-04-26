import pandas as pd
import numpy as np

from QSExt.Tools.Option import EuropeanBlackSholesModel, calc_variance_swap_iv


# ---------- 构造模拟数据 ----------
np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=3, freq='B')
spot = pd.Series([100, 101, 99], index=dates)# 标的价格
r = pd.Series(0.03, index=dates)# 年化无风险利率

# 期权代码
codes = [
    'C_95_N', 'P_95_N', 'C_97.5_N', 'P_97.5_N',
    'C_100_N', 'P_100_N', 'C_102.5_N', 'P_102.5_N',
    'C_105_N', 'P_105_N',
    'C_95_X', 'P_95_X', 'C_97.5_X', 'P_97.5_X',
    'C_100_X', 'P_100_X', 'C_102.5_X', 'P_102.5_X',
    'C_105_X', 'P_105_X'
]
# 注：N 结尾为近月合约，X 结尾为次近月合约
near_T = 0.12   # 近月约 44 天
next_T = 0.25   # 次近月约 91 天
strikes = [95, 97.5, 100, 102.5, 105]
sigma_true = 0.20  # 真实波动率

# option_info
info_data = {'type': [], 'strike': []}
for code in codes:
    opt_type = 'call' if code.startswith('C') else 'put'
    strike = float(code.split('_')[1])
    info_data['type'].append(opt_type)
    info_data['strike'].append(strike)
option_info = pd.DataFrame(info_data, index=codes)

# option_price 和 option_maturity
price_data = []
maturity_data = []
for date in dates:
    s = spot[date]
    row_price = {}
    row_mat = {}
    for code in codes:
        opt_type = 'call' if code.startswith('C') else 'put'
        strike = float(code.split('_')[1])
        T = near_T if code.endswith('N') else next_T
        price = EuropeanBlackSholesModel.calcPrice(s, T, r[date], sigma_true, strike, opt_type)
        # 添加微小噪声，模拟买卖价差
        price *= (1 + np.random.normal(0, 0.002))
        row_price[code] = max(price, 0.001)  # 避免零价
        row_mat[code] = T
    price_data.append(row_price)
    maturity_data.append(row_mat)

option_price = pd.DataFrame(price_data, index=dates)
option_maturity = pd.DataFrame(maturity_data, index=dates)

# ---------- 调用函数 ----------
# 注意：之前定义的函数名是 calc_variance_swap_iv
iv_series = calc_variance_swap_iv(spot, r, option_info, option_price, option_maturity)

print("估计的隐含波动率（年化小数）:")
print(iv_series)
print(f"\n真实波动率: {sigma_true}")
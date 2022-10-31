# coding=utf-8
from sre_constants import IN
from typing import Optional, Union
import datetime as dt

import numpy as np
import pandas as pd

__MinCash__ = 1e-4
__MinNum__ = 1e-4

# 根据交易记录模拟交易
# idt: 交易发生的时点
# itransaction: 此时点的交易记录, DataFrame(index=["产品代码"], columns=["方向", "数量", "价格", "费用"]), 方向可选: 1: 买入, -1: 卖出
# iposition: 交易前持仓, DataFrame(index=["产品代码"], columns=["数量", "成本价", "最新价"])
# icash: 交易前现金, Series(index=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
# iproduct_price: 产品此时点的价格, Series(index=["产品代码"])
# icash_price: 现金此时点的价格, float
# 返回: iposition: 交易后持仓, DataFrame(index=["产品代码"], columns=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
# 返回: icash: 交易后现金, Series(index=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
def tradeTransaction(idt: dt.datetime, itransaction: pd.DataFrame, iposition: Optional[pd.DataFrame], icash: pd.Series, iproduct_price: pd.DataFrame, icash_price: float):
    # 没有交易, 更新账户信息
    if itransaction is None:
        iPrice = iproduct_price.loc[iposition.index]
        iposition["当日盈亏"] = (iPrice - iposition["最新价"]) * iposition["数量"]
        iposition["当日实现盈亏"] = 0
        iposition["最新价"] = iPrice
        iposition["市值"] = iPrice * iposition["数量"]
        iposition["权重"] = iposition["市值"] / (iposition["市值"].sum() + icash["数量"] * icash_price)
        icash = pd.Series([icash["数量"], icash["成本价"], icash_price, icash_price*icash["数量"], max(1-iposition["权重"].sum(), 0), 0, (icash_price - icash["最新价"]) * icash["数量"]], index=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
        return iposition, icash
    iCash = icash["数量"] * icash_price
    # 先卖出
    iSell = itransaction[itransaction["方向"] < 0]
    iIDs = iSell.index.difference(iposition.index)
    if iIDs.shape[0] > 0:
        raise Exception(f"{idt}: 卖出的产品{iIDs.tolist()}不在当前持仓中")
    iSell = iSell.reindex(iposition.index).fillna(0)
    iposition["数量"] = iposition["数量"] - iSell["数量"]
    if (iposition["数量"] < -__MinNum__).any():
        raise Exception(f"{idt}: 产品{iposition[iposition['数量'] < -__MinNum__].index.tolist()}卖出数量超过当前持仓!")
    iCash += (iSell["数量"] * iSell["价格"] - iSell["费用"]).sum()
    if iCash < -__MinCash__:
        raise Exception(f"{idt}: 当前现金 {iCash + (iSell['数量'] * iSell['价格'] - iSell['费用']).sum()} 不足以支付卖出费用!")
    iposition["当日实现盈亏"] = iSell["数量"] * (iSell["价格"] - iposition["成本价"]) - iSell["费用"]
    iposition["当日盈亏"] = (iproduct_price.loc[iposition.index] - iposition["最新价"]) * iposition["数量"]
    iposition["当日盈亏"] += iSell["数量"] * (iSell["价格"] - iposition["最新价"]) - iSell["费用"]
    # 再买入
    iBuy = itransaction[itransaction["方向"] > 0]
    iCash -= (iBuy["数量"] * iBuy["价格"] + iBuy["费用"]).sum()
    if iCash < -__MinCash__:
        raise Exception(f"{idt}: 当前现金 {iCash + (iBuy['数量'] * iBuy['价格'] + iBuy['费用']).sum()} 不足以支付买入金额和费用!")
    iIDs = iBuy.index.union(iposition.index)
    iposition, iBuy = iposition.reindex(iIDs).fillna(0), iBuy.reindex(iIDs).fillna(0)
    iNum = iposition["数量"] + iBuy["数量"]
    iposition["成本价"] = iposition["成本价"].where(iNum==0, (iposition["数量"] * iposition["成本价"] + iBuy["数量"] * iBuy["价格"] + iBuy["费用"]) / iNum)
    iposition["数量"] = iNum
    iposition["当日实现盈亏"] -= iBuy["费用"]
    iposition["当日盈亏"] += (iproduct_price.loc[iIDs] - iBuy["价格"]) * iBuy["数量"] - iBuy["费用"]
    iposition["最新价"] = iproduct_price.loc[iposition.index]
    iposition["市值"] = iposition["最新价"] * iposition["数量"]
    iposition["权重"] = iposition["市值"] / (iposition["市值"].sum() + iCash)
    iNum = iCash / icash_price
    icash = pd.Series([iNum, 
        (icash["成本价"] if iNum <= icash["数量"] else (icash["数量"] * icash["成本价"] + (iNum - icash["数量"]) * icash_price) / iNum), 
        icash_price, icash_price*iNum, max(1-iposition["权重"].sum(), 0), 
        max(0, icash["数量"]-iNum) * (icash_price - icash["成本价"]), 
        (icash_price - icash["最新价"]) * icash["数量"]], 
        index=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
    return iposition, icash


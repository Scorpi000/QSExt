# coding=utf-8
from itertools import product
from sre_constants import IN
from turtle import position
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

# 根据交易记录进行回测
# cash_price: 现金产品净值, Series(index=["时点"]), 按照时点升序
# product_price: 产品净值, DataFrame(index=["时点"], columns=["产品代码"]), 按照时点排序
# cashflow: 现金流, Series(index=["时点"]), 现金流为正表示流入, 为负表示流出, 假设现金流入流出发生在每个时点之前, 即计入当期收益率的计算
# transaction: 交易记录, DataFrame(index=["时点"], columns=["产品代码", "方向", "数量", "价格", "费用"]), 方向可选: 1: 买入, -1: 卖出
# init_position: 期初持仓信息, DataFrame(index=["产品代码"], columns=["数量", "成本价", "最新价"])
# init_cash: 期初现金信息, Series(index=["数量", "成本价", "最新价"])
# 返回: Position: 持仓信息, DataFrame(index=["产品代码", "时点"], columns=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏", "浮动盈亏", "浮动盈亏率"])
# 返回: Cash: 持仓现金, DataFrame(index=["时点"], columns=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏", "浮动盈亏", "浮动盈亏率"])
# 返回: Account: 账户信息, DataFrame(index=["时点"], columns=["市值", "持仓成本", "权重", "当日实现盈亏", "当日盈亏", "浮动盈亏", "总资产", "当日初始总资产", "现金流发生前总资产", "当日收益率"])
def backtestTransaction(cash_price, product_price, cashflow, transaction, 
    init_cash=pd.Series([10000, 1, 1], index=["数量", "成本价", "最新价"]),
    init_position=pd.DataFrame(columns=["数量", "成本价", "最新价"])):
    nDT = cash_price.shape[0]
    TransactionDTs = set(transaction.index)
    transaction = transaction.set_index(["产品代码"], append=True)
    Position, Cash, PreVal = [], np.zeros((nDT, 7)), np.zeros((nDT,))
    iPosition, iCash = init_position, pd.Series(np.r_[init_cash.values, np.zeros((4,))], index=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
    for i, iDT in enumerate(cash_price.index):
        iNum = cashflow.get(iDT, 0) / iCash["最新价"]
        if iNum!=0:
            iCash["成本价"] = (iNum * iCash["最新价"] + iCash["数量"] * iCash["成本价"]) / (iCash["数量"] + iNum)
            iCash["数量"] += iNum
            if iCash["数量"] < -__MinNum__:
                raise Exception(f"{iDT}: 当前现金 {iCash['数量'] * iCash['最新价']} 不足以提取 {cashflow[iDT]}!")
        PreVal[i] = (iPosition["数量"] * iPosition["最新价"]).sum() + iCash["数量"] * iCash["最新价"]
        iPosition = iPosition[iPosition["数量"].abs() >= __MinNum__].copy()
        if iDT not in TransactionDTs:
            iPosition, iCash = tradeTransaction(iDT, None, iPosition, iCash, product_price.iloc[i], cash_price.iloc[i])
        else:
            iPosition, iCash = tradeTransaction(iDT, transaction.loc[iDT], iPosition, iCash, product_price.iloc[i], cash_price.iloc[i])
        iPosition["日期"] = iDT
        Position.append(iPosition)
        Cash[i] = iCash.values
    if Position:
        Position = pd.concat(Position, axis=0, ignore_index=False).set_index(["日期"], append=True).swaplevel(axis=0)
    else:
        Position = pd.DataFrame(columns=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
    Position["浮动盈亏"] = (Position["最新价"] - Position["成本价"]) * Position["数量"]
    Position["浮动盈亏率"] = Position["最新价"] / Position["成本价"] - 1
    Cash = pd.DataFrame(Cash, index=cash_price.index, columns=["数量", "成本价", "最新价", "市值", "权重", "当日实现盈亏", "当日盈亏"])
    Cash["浮动盈亏"] = (Cash["最新价"] - Cash["成本价"]) * Cash["数量"]
    Cash["浮动盈亏率"] = Cash["最新价"] / Cash["成本价"] - 1

    # 计算账户指标
    if Position.shape[0]>0:
        Account = Position.groupby(axis=0, level=0)[["市值", "权重", "当日实现盈亏", "当日盈亏", "浮动盈亏"]].sum().reindex(index=cash_price.index).fillna(0)
    else:
        Account = pd.DataFrame(0, columns=["市值", "权重", "当日实现盈亏", "当日盈亏", "浮动盈亏"], index=cash_price.index)
    Account["当日实现盈亏"] += Cash["当日实现盈亏"]
    Account["当日盈亏"] += Cash["当日盈亏"]
    Account["浮动盈亏"] += Cash["浮动盈亏"]
    Account["总资产"] = Account["市值"] + Cash["市值"]
    Account["当日初始总资产"] = PreVal
    Account["现金流发生前总资产"] = Account["总资产"] - cashflow.reindex(cash_price.index).fillna(0)
    Account["持仓成本"] = (Position["成本价"] * Position["数量"]).groupby(axis=0, level=0).sum().reindex(index=cash_price.index).fillna(0)
    Account["持仓成本"] += Cash["成本价"] * Cash["数量"]
    Account["当日收益率"] = Account["当日盈亏"] / Account["当日初始总资产"]
    return Position, Cash, Account

if __name__=="__main__":
    import time

    np.random.seed(0)
    DTs = [dt.datetime(2022, 1, 1) + dt.timedelta(i) for i in range(730)]
    ProductPrice = (1 + pd.DataFrame(-0.05 + np.random.rand(len(DTs), 2)*0.1, index=DTs, columns=["A", "B"])).cumprod()
    CashPrice = (1 + pd.Series(-0.005 + np.random.rand(len(DTs))*0.01, index=DTs)).cumprod()
    InitPosition = pd.DataFrame(columns=["数量", "成本价", "最新价"])
    InitCash = pd.Series([10000, 1, 1], index=["数量", "成本价", "最新价"])
    Cashflow = pd.Series(dtype=float)

    Transaction = pd.DataFrame([
        ("A", 1, 5000, ProductPrice.loc[dt.datetime(2022, 1, 1), "A"], 0),
        ("B", 1, 1000, ProductPrice.loc[dt.datetime(2022, 1, 10), "B"], 0),
        ("A", -1, 5000, ProductPrice.loc[dt.datetime(2022, 1, 10), "A"], 1000),
        ("B", 1, 1000, ProductPrice.loc[dt.datetime(2022, 1, 15), "B"], 0),
    ], index=[dt.datetime(2022, 1, 1), dt.datetime(2022, 1, 10), dt.datetime(2022, 1, 10), dt.datetime(2022, 1, 15)], 
    columns=["产品代码", "方向", "数量", "价格", "费用"])

    StartT = time.perf_counter()
    Position, Cash, Account = backtestTransaction(CashPrice, ProductPrice, Cashflow, Transaction, InitCash, InitPosition)
    print("回测时间: ", time.perf_counter() - StartT)

    print("===")
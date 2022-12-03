# -*- coding: utf-8 -*-
"""投资组合管理工具"""

import datetime as dt

import numpy as np
import pandas as pd

# 获取代码
def _get_code(conn, code, portfolio_detail, info_table, detail_table, if_exist):
    SQLStr = f"SELECT DISTINCT code FROM {detail_table} ORDER BY code"
    Codes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
    if code in Codes:
        if if_exist=="error":
            raise Exception(f"组合 ID '{code}' 已存在!")
        elif if_exist=="inc_code":
            while code in Codes:
                code = str(int(code)+1).zfill(6)
        elif if_exist=="replace":
            Cursor = conn.cursor()
            SQLStr = f"DELETE FROM {detail_table} WHERE code='{code}'"
            Cursor.execute(SQLStr)
            SQLStr = f"DELETE FROM {info_table} WHERE code='{code}'"
            Cursor.execute(SQLStr)
            conn.commit()
            Cursor.close()
        elif if_exist=="append":
            SQLStr = f"SELECT MAX(datetime) FROM {detail_table} WHERE code='{code}'"
            Cursor = conn.cursor()
            Cursor.execute(SQLStr)
            MaxDT = Cursor.fetchall()
            Cursor.close()
            if len(MaxDT)>0:
                MaxDT = MaxDT[0][0]
                portfolio_detail = portfolio_detail[portfolio_detail["datetime"]>MaxDT]
        elif if_exist=="update":
            SQLStr = f"""
                DELETE FROM {detail_table} 
                WHERE code='{code}'
                AND datetime>='{portfolio_detail['datetime'].min().strftime('%Y-%m-%d %H:%M:%S.%f')}'
                AND datetime<='{portfolio_detail['datetime'].max().strftime('%Y-%m-%d %H:%M:%S.%f')}'
            """
            Cursor = conn.cursor()
            Cursor.execute(SQLStr)
            conn.commit()
            Cursor.close()
        else:
            raise Exception(f"不支持的写入方式(if_exist): '{if_exist}'")
    return (code, portfolio_detail)

# 将资产配置写入数据库
# portfolio_detail: Series(index=(datetime, index_code), values=weight)
# if_exist:
# error: 抛出异常
# replace: 删除旧组合, 写入新组合
# update: 覆盖方式更新已有的组合
# append: 追加方式更新已有的组合
# inc_code: 在给定 ID 基础上增加 ID 值以添加组合
def write_asset_allocation_to_sql(conn, portfolio_info, portfolio_detail, 
    info_table="asset_allocation_info", detail_table="asset_allocation_detail", asset_info_table="asset_cn_info", 
    code="990000", if_exist="error", min_max_range=0.05, preview=False):
    Portfolio = portfolio_detail.reset_index()
    Portfolio.columns = ["datetime", "index_code", "weight"]
    # 替换大类资产代码
    SQLStr = f"SELECT code, type, index_code FROM {asset_info_table} WHERE type<>'Ohters'"
    AssetInfo = pd.read_sql_query(SQLStr, conn, index_col=["code"])
    Portfolio["asset_code"] = Portfolio["index_code"].apply(lambda x: AssetInfo[AssetInfo["index_code"]==x].index[0])
    # 编码
    code, Portfolio = _get_code(conn, code, Portfolio, info_table, detail_table, if_exist)
    Portfolio["code"] = code
    # 补充字段
    Portfolio["weight_min"] = (Portfolio["weight"] - min_max_range).clip(lower=0)
    Portfolio["weight_max"] = (Portfolio["weight"] + min_max_range).clip(upper=1)
    Portfolio = Portfolio.loc[:, ["datetime", "code", "asset_code", "weight", "weight_min", "weight_max"]]
    portfolio_info["code"] = code
    # 组合信号写入数据库
    if not preview:
        Cursor = conn.cursor()
        if Portfolio.shape[0]>0:
            SQLStr = f"REPLACE INTO {detail_table} ({','.join(Portfolio.columns)}) VALUES ({','.join(['%s']*Portfolio.shape[1])})"
            DTs = Portfolio["datetime"]
            Portfolio["datetime"] = [iDT.strftime("%Y-%m-%d %H:%M:%S.%f") for iDT in DTs]
            NewData = Portfolio.astype("O").where(pd.notnull(Portfolio), None)
            Cursor.executemany(SQLStr, NewData.values.tolist())
            Portfolio["datetime"] = DTs
        SQLStr = f"REPLACE INTO {info_table} ({','.join(portfolio_info.index)}) VALUES ({','.join(['%s']*portfolio_info.shape[0])})"
        NewData = portfolio_info.astype("O").where(pd.notnull(portfolio_info), None)
        Cursor.executemany(SQLStr, [NewData.tolist()])
        conn.commit()
        Cursor.close()
    return portfolio_detail, Portfolio

# 给定资产配置组合 ID 读取组合的历史特性
def read_asset_allocation_from_sql(conn, code, info_table="asset_allocation_info", detail_table="asset_allocation_detail", asset_info_table="asset_cn_info", start_dt=None, end_dt=None):
    # 读取模型信息
    SQLStr = f"SELECT * FROM {info_table} WHERE code='{code}'"
    PortfolioInfo = pd.read_sql_query(SQLStr, conn)
    if PortfolioInfo.shape[0]==0:
        raise Exception(f"不存在 ID 为 '{code}' 的资产配置组合!")
    PortfolioInfo = PortfolioInfo.iloc[0]
    # 读取模型历史持仓
    SQLStr = f"""
        SELECT t.code, t.datetime, t.asset_code, t1.type AS asset_type, t1.name AS asset_name, t1.index_code, t.weight, t.weight_min, t.weight_max
        FROM {detail_table} t INNER JOIN {asset_info_table} t1 ON (t.asset_code=t1.asset_code)
        {f"AND t.datetime>='{start_dt.strftime('%Y-%m-%d %H:%M:%S.%f')}'" if start_dt is not None else ""}
        {f"AND t.datetime<='{end_dt.strftime('%Y-%m-%d %H:%M:%S.%f')}'" if end_dt is not None else ""}
        ORDER BY t.datetime, t.asset_code
    """
    PortfolioDetail = pd.read_sql_query(SQLStr, conn)
    return PortfolioInfo, PortfolioDetail

# 检查资产配置数据的完整性
def check_asset_allocation_integrity(conn, info_table="asset_allocation_info", detail_table="asset_allocation_detail", asset_info_table="asset_cn_info", auto_fix=False):
    Integrity = True
    # 检查 info 表和 detail 表的 code 是否匹配
    SQLStr = f"SELECT DISTINCT code FROM {info_table}"
    InfoCodes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
    SQLStr = f"SELECT DISTINCT code FROM {detail_table}"
    DetailCodes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
    InfoDifDetailCodes = set(InfoCodes).difference(DetailCodes)
    if InfoDifDetailCodes:
        print(f"表 '{info_table}' 比表 '{detail_table}' 多出的组合 code: {sorted(InfoDifDetailCodes)}")
        Integrity = False
    DetailDifInfoCodes = set(DetailCodes).difference(InfoCodes)
    if DetailDifInfoCodes:
        print(f"表 '{detail_table}' 比表 '{info_table}' 多出的组合 code: {sorted(DetailDifInfoCodes)}")
        Integrity = False
    # 检查 detail 表中的大类资产 code 是否在 asset_info 表中
    SQLStr = f"SELECT DISTINCT code FROM {asset_info_table}"
    AllAssetCodes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
    SQLStr = f"SELECT DISTINCT asset_code FROM {detail_table}"
    DetailAssetCodes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
    DetailDifAllAssetCodes = set(DetailAssetCodes).difference(AllAssetCodes)
    if DetailDifAllAssetCodes:
        print(f"表 '{detail_table}' 比表 '{asset_info_table}' 多出的大类资产 code: {sorted(DetailDifAllAssetCodes)}")
        Integrity = False
    # 修复数据
    if (not Integrity) and auto_fix:
        Cursor = conn.cursor()
        if InfoDifDetailCodes:
            SQLStr = f"""DELETE FROM {info_table} WHERE code IN ('{"','".join(InfoDifDetailCodes)}')"""
            Cursor.execute(SQLStr)
            print(f"删除表 '{info_table}' 中 code 为 {sorted(InfoDifDetailCodes)} 的组合")
        if DetailDifInfoCodes:
            SQLStr = f"""DELETE FROM {detail_table} WHERE code IN ('{"','".join(DetailDifInfoCodes)}')"""
            Cursor.execute(SQLStr)
            print(f"删除表 '{detail_table}' 中 code 为 {sorted(DetailDifInfoCodes)} 的组合")
        if DetailDifAllAssetCodes:
            SQLStr = f"""SELECT DISTINCT code FROM {detail_table} WHERE asset_code IN ({",".join([str(iCode) for iCode in DetailDifAllAssetCodes])})"""
            DetailDifAssetInfoCodes = pd.read_sql_query(SQLStr, conn).iloc[:, 0].tolist()
            SQLStr = f"""DELETE FROM {detail_table} WHERE code IN ('{"','".join(DetailDifAssetInfoCodes)}')"""
            Cursor.execute(SQLStr)
            print(f"删除表 '{detail_table}' 中 code 为 {sorted(DetailDifAssetInfoCodes)} 的组合")
            SQLStr = f"""DELETE FROM {info_table} WHERE code IN ('{"','".join(DetailDifAssetInfoCodes)}')"""
            Cursor.execute(SQLStr)
            print(f"删除表 '{info_table}' 中 code 为 {sorted(DetailDifAssetInfoCodes)} 的组合")
        conn.commit()
        Cursor.close()
    return Integrity

# 将投资组合写入数据库
# portfolio_detail: Series(index=(datetime, index_code), values=weight)
# if_exist:
# error: 抛出异常
# replace: 删除旧组合, 写入新组合
# update: 覆盖方式更新已有的组合
# append: 追加方式更新已有的组合
# inc_code: 在给定 ID 基础上增加 ID 值以添加组合
def write_portfolio_to_sql(conn, portfolio_info, portfolio_detail, 
    info_table="portfolio_info", detail_table="portfolio_detail", product_info_table="product_cn_info", 
    code="990000", if_exist="error",preview=False):
    pass
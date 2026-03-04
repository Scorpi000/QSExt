# -*- coding: utf-8 -*-
"""更新因子数据"""
import os
import importlib
import argparse
import datetime as dt
from typing import Dict

from dateutil.parser import parse
import dateparser
import click

from QuantStudio.Core import __QS_Error__
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Factor.FactorDB import FactorDB
from QuantStudio.Factor.JYDB import JYDB
from QuantStudio.Factor.HDF5DB import HDF5DB
from QuantStudio.Core.CalcEngine import Engine, ParallelEngine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.FactorStorer import FactorStorer
from QSExt.FactorDef.FactorDefContent import FactorDefInput
from QuantStudio.Tools.DateTimeFun import getDateTimeSeries, getMonthLastDateTime, getYearLastDateTime


def loadFDB() -> Dict[str, FactorDB]:
    return {
        "JYDB": JYDB().connect(),
        "HDB": HDF5DB().connect()
    }

def loadModule(module_name, file_path):
    ModuleSpec = importlib.util.spec_from_file_location(module_name, file_path)
    Module = importlib.util.module_from_spec(ModuleSpec)
    ModuleSpec.loader.exec_module(Module)
    return Module

# 解析日期时间
def parseDateTime(dt_str):
    if not isinstance(dt_str, str): return None
    # 时点格式, 是否去掉空格
    __DTFmt__ = [
        ("%Y年%m月%d日%H:%M:%S", True),
        ("%Y年%m月%d日%H:%M", True),
        ("%Y年%m月%d日%H时", True),
        ("%Y年%m月%d日", True),
        ("%m月%d日%H:%M", True),
    ]
    dt_str = dt_str.strip()
    for iFmt, iDropWhiteSpace in __DTFmt__:
        try:
            if iDropWhiteSpace:
                iDT = dt.datetime.strptime(dt_str.replace(" ", ""), iFmt)
            else:
                iDT = dt.datetime.strptime(dt_str, iFmt)
            if iDT.year==1900:
                iDT = dt.datetime(dt.date.today().year, iDT.month, iDT.day, iDT.hour, iDT.minute, iDT.second, iDT.microsecond)
            return iDT
        except:
            pass
    try:
        return parse(dt_str, ignoretz=True)
    except:
        pass
    iDT = dateparser.parse(dt_str.replace(" ", ""))
    if iDT is None:
        iDT = dateparser.parse(dt_str)
    return iDT

def getFactorUpdateArgs(tdb):
    Parser = argparse.ArgumentParser(description="解析因子脚本更新参数")
    Parser.add_argument("-d", "--debug", type=str, default="y", help="debug 模式, [y]es or [n]o")
    Parser.add_argument("-tbl", "--table_name", type=str, default=None, help="数据写入的目标因子表")
    Parser.add_argument("-sdt", "--start_dt", type=str, default=None, help="起始时点, 格式: %Y-%m-%d 或者 %Y%m%d")
    Parser.add_argument("-edt", "--end_dt", type=str, default=None, help="结束时点, 格式: %Y-%m-%d 或者 %Y%m%d")
    Parser.add_argument("-slb", "--start_look_back", type=int, default=0, help="起始时点的回溯天数")
    Parser.add_argument("-elb", "--end_look_back", type=int, default=0, help="结束时点的回溯天数")
    Parser.add_argument("-ids", "--ids", type=str, default=None, help="证券代码列表, 以逗号分隔, 比如: 000001.SZ,000002.SZ")
    Parser.add_argument("-idtp", "--id_type", type=str, default=None, help="证券类型, 比如: stock, mf, pf_sl, pf_ia")
    Parser.add_argument("-um", "--update_method", type=str, default="update", help="更新方式")
    Parser.add_argument("-pn", "--process_num", type=int, default=0, help="子进程数量, 0 表示串行计算")
    Parser.add_argument("-darg", "--def_args", type=str, default=None, help="因子定义参数, 字典字面量, 格式: {'key': 'value'}")
    Parser.add_argument("-ll", "--log_level", type=str, default="INFO", help="log level")
    Parser.add_argument("-ld", "--log_dir", type=str, default="", help="日志输出的文件目录")

    InputArgs = Parser.parse_args()
    Args = {
        "debug": (InputArgs.debug.lower() in ("y", "yes")),
        "table_name": InputArgs.table_name,
        "ids": (InputArgs.ids.split(",") if InputArgs.ids else None),
        "id_type": InputArgs.id_type,
        "end_dt": parseDateTime(InputArgs.end_dt) if InputArgs.end_dt else None,
        "update_method": InputArgs.update_method,
        "process_num": InputArgs.process_num,
        "def_args": eval(InputArgs.def_args) if InputArgs.def_args else {},
        "log_level": InputArgs.log_level,
        "log_dir": InputArgs.log_dir
    }
    if InputArgs.start_dt=="max_dt":
        if tdb is None:
            raise __QS_Error__("当 start_dt 为 'max_dt' 时必须传入目标因子库对象")
        FT = tdb.getTable(Args["table_name"])
        Args["start_dt"] = FT.getDateTime()[-1] + dt.timedelta(1)
    elif InputArgs.start_dt:
        Args["start_dt"] = parseDateTime(InputArgs.start_dt)
    else:
        Args["start_dt"] = None
    Today = dt.datetime.combine(dt.date.today(), dt.time(0))
    if (Args["start_dt"] is None) and (Args["end_dt"] is None):
        if Args["debug"]:
            Args["start_dt"] = dt.datetime(Today.year - 1, 12, 1)
            Args["end_dt"] = dt.datetime(Today.year - 1, 12, 31)
        else:
            Args["start_dt"] = dt.datetime(Today.year - 3, 1, 1)
            Args["end_dt"] = Today
    elif Args["start_dt"] is None:
        if Args["debug"]:
            Args["start_dt"] = Args["end_dt"] - dt.timedelta(30)
        else:
            Args["start_dt"] = dt.datetime(Args["end_dt"].year - 3, 1, 1)
    elif Args["end_dt"] is None:
        if Args["debug"]:
            Args["end_dt"] = Args["start_dt"] + dt.timedelta(30)
        else:
            Args["end_dt"] = Today
    Args["start_dt"] -= dt.timedelta(InputArgs.start_look_back)
    Args["end_dt"] -= dt.timedelta(InputArgs.end_look_back)
    return Args

@click.command()
@click.argument("def_file")
@click.option("-tdb", "--target_db", type=str, help="目标因子库")
@click.option("-tbl", "--table_name", type=str, default=None, help="目标因子表")
@click.option("-sdt", "--start_dt", type=str, default=None, help="起始时点, 格式: %Y-%m-%d")
@click.option("-edt", "--end_dt", type=str, default=None, help="结束时点, 格式: %Y-%m-%d")
@click.option("-slb", "--start_look_back", type=int, default=0, help="起始时点的回溯天数")
@click.option("-elb", "--end_look_back", type=int, default=0, help="结束时点的回溯天数")
@click.option("-dtt", "--dt_type", type=str, default="交易日", help="时点类型, 可选: t(交易日), n(自然日)")
@click.option("-dtf", "--dt_freq", type=str, default="d", help="时点频率, 可选: d(日), m(月), y(年)")
@click.option("-mlk", "--max_lookback", type=int, default=3650, help="最长回溯期")
@click.option("-dtdb", "--dt_db", type=str, default=None, help="用于提取时点序列的因子库名称或者因子表名称, 比如 WDB 或者 LDB:stock_cn_day_bar")
@click.option("-ids", "--ids", type=str, default="", help="证券代码列表, 以逗号分隔, 比如: 000001.SZ,000002.SZ")
@click.option("-idt", "--id_type", type=str, default="stock", help="证券类型, 可选: stock(A股), mf(公募基金)")
@click.option("-iddb", "--id_db", type=str, default=None, help="用于提取 ID 序列的因子库名称或者因子表名称, 比如 WDB 或者 LDB:stock_cn_day_bar")
@click.option("-um", "--update_method", type=str, default="update", help="更新方式")
@click.option("-ion", "--io_num", type=int, default=4, help="IO 并发数量")
@click.option("-pn", "--process_num", type=int, default=0, help="子进程数量, 0 表示串行计算")
@click.option("-darg", "--def_args", type=str, default=None, help="因子定义参数, 字典字面量, 格式: {'key': 'value'}")
@click.option("-proxy", "--proxy", type=str, default="no", help="是否使用因子本地代理，可选：yes, no")
def updateFactorData(
    def_file, target_db, table_name=None,
    start_dt=None, end_dt=None, start_look_back=0, end_look_back=0, dt_type="t", dt_freq="d", max_lookback=3650, dt_db=None, 
    ids=None, id_type="stock", id_db=None, 
    update_method="update", io_num=4, process_num=0, def_args=None, proxy="no"
):
    Logger.info("=================================================")
    
    # 导入因子定义
    DefFileName = ".".join(os.path.split(def_file)[-1].split(".")[:-1])
    DefModule = loadModule(DefFileName, def_file)
    Logger.info(f"导入因子定义: {def_file}")

    # 因子库对象
    FDBs = loadFDB()
    TDB = FDBs[target_db]
    
    # 更新的起止时间
    if start_dt is None:
        if (table_name is not None) and (table_name in TDB.TableNames):
            FT = TDB.getTable(table_name)
            start_dt = FT.getDateTime()[-1] + dt.timedelta(1)
            Logger.info(f"未指定起始时点, 使用了目标因子表 {table_name} 中数据结束时点的下一个自然日作为起始时点: {start_dt}")
        else:
            start_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
            Logger.error(f"未指定起始时点, 设置为当天: {start_dt}")
            return -1
    else:
        start_dt = dt.datetime.strptime(start_dt, "%Y-%m-%d")
        Logger.info(f"指定了起始时点: {start_dt}")
    if start_look_back>0:
        start_dt -= dt.timedelta(start_look_back)
        Logger.info(f"最终起始时点: {start_dt}, 在初始起始时点基础上回溯 {start_look_back} 天得到")
    else:
        Logger.info(f"最终起始时点: {start_dt}, 等于初始起始时点")
    if end_dt is None:
        end_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
        Logger.info(f"未指定结束时点, 设置为当天: {end_dt}, ")
    else:
        end_dt = dt.datetime.strptime(end_dt, "%Y-%m-%d")
        Logger.info(f"指定了结束时点: {end_dt}")
    if end_look_back > 0:
        end_dt -= dt.timedelta(end_look_back)
        Logger.info(f"最终结束时点: {end_dt}, 在初始结束时点基础上回溯 {end_look_back} 天得到")
    else:
        Logger.info(f"最终结束时点: {end_dt}, 等于初始结束时点")
    
    # 设置时点序列
    if dt_type=="t":# 交易日
        dt_db = dt_db.split(":")
        if dt_db[0] not in FDBs:
            Logger.error(f"提取时点序列的因子库对象({dt_db})不存在")
            return -1
        if len(dt_db)==1:
            DTs = FDBs[dt_db[0]].getTradeDay(start_date=start_dt.date(), end_date=end_dt.date(), output_type="datetime")
            DTRuler = FDBs[dt_db[0]].getTradeDay(start_date=start_dt.date() - dt.timedelta(max_lookback), end_date=end_dt.date(), output_type="datetime")
        else:
            iFactorName = (dt_db[2] if len(dt_db)>2 else None)
            FT = FDBs[dt_db[0]].getTable(dt_db[1])
            DTs = FT.getDateTime(ifactor_name=iFactorName, start_dt=start_dt, end_dt=end_dt)
            DTRuler = FT.getDateTime(ifactor_name=iFactorName, start_dt=start_dt - dt.timedelta(max_lookback), end_dt=end_dt)
    elif dt_type=="n":# 自然日
        DTs = getDateTimeSeries(start_dt=start_dt, end_dt=end_dt, timedelta=dt.timedelta(1))
        DTRuler = getDateTimeSeries(start_dt=start_dt - dt.timedelta(max_lookback), end_dt=end_dt, timedelta=dt.timedelta(1))
    else:
        Logger.error(f"无法识别的时点类型: {dt_type}")
        return -1
    # 调整时点频率
    if dt_freq in ("m", ):
        DTs = getMonthLastDateTime(DTs)
        DTRuler = getMonthLastDateTime(DTRuler)
    elif dt_freq in ("y", ):
        DTs = getYearLastDateTime(DTs)
        DTRuler = getYearLastDateTime(DTRuler)
    elif dt_freq!="d":
        Logger.error(f"无法识别的时点频率: {dt_freq}")
        return -1
    if DTs:
        Logger.info(f"时点序列: {DTs[0]} ~ {DTs[-1]}, 共 {len(DTs)} 天, 类型 '{dt_type}', 频率 '{dt_freq}'")
        Logger.info(f"时点标尺序列: {DTRuler[0]} ~ {DTRuler[-1]}, 共 {len(DTRuler)} 天, 类型 '{dt_type}', 频率 '{dt_freq}'")
    else:
        Logger.warning("没有需要更新的时点")
        return 0
    
    # 设置 ID 序列
    if isinstance(ids, str) and (ids!=""):
        IDs = sorted(ids.split(","))
        id_type = "外部指定"
    elif id_type:
        id_db = id_db.split(":")
        if id_db[0] not in FDBs:
            Logger.info(f"提取 ID 序列的因子库对象({id_db})不存在")
            return -1           
        if len(id_db)==1:
            if id_type=="stock":
                IDs = FDBs[id_db[0]].getStockID(is_current=False)
            elif id_type=="bond":
                IDs = FDBs[id_db[0]].getBondID(is_current=False)
            elif id_type=="mf":
                IDs = FDBs[id_db[0]].getMutualFundID(is_current=False)
            else:
                Logger.error(f"不支持指定的 ID 类型: {id_type}")
                return -1
        else:
            iFactorName = (id_db[2] if len(id_db) > 2 else None)
            FT = FDBs[id_db[0]].getTable(id_db[1])
            IDs = FT.getID(ifactor_name=iFactorName)
    else:
        Logger.error("没有指定 ID 序列")
        return -1
    SectionIDs = IDs
    if IDs:
        Logger.info(f"ID 序列: {IDs[0]} ~ {IDs[-1]}, 共 {len(IDs)} 个, 类型 '{id_type}'")
    else:
        Logger.warning("没有需要更新的ID")
        return 0

    if def_args: def_args = eval(def_args)
    else: def_args = {}
    Logger.info(f"定义参数: {def_args}")
    
    if proxy.lower()=="no":
        FDI = FactorDefInput(FDB=FDBs, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler, ModelArgs=def_args)
    elif proxy.lower()=="yes":
        FDI = FactorDefInput(FDB=FDBs, DTs=DTs, IDs=IDs, SectionIDs=SectionIDs, DTRuler=DTRuler, ModelArgs=def_args, ProxyDB=TDB)
    else:
        Logger.error(f"不支持的入参 proxy={proxy}")
        return -1
    FactorDef = DefModule.defFactor(fdi=FDI)
    if FactorDef.MaxLookBack > max_lookback:
        Logger.error(f"因子定义中的回溯期 {FactorDef.MaxLookBack} 超过了指定的最长回溯期 {max_lookback}")
        return -1
    # 目标因子表
    if table_name is None:
        table_name = FactorDef.TargetTable
        if table_name:
            Logger.info(f"目标因子表: {table_name}, 未指定目标因子表, 使用了因子定义文件中设置的因子表")
        else:
            table_name = DefFileName
            Logger.info(f"目标因子表: {table_name}, 未指定目标因子表, 并且因子定义文件中也未设置目标因子表, 使用了文件名作为目标因子表")
    else:
        Logger.info(f"目标因子表: {table_name}")

    Storer = FactorStorer(deps=FactorDef.FactorList, args={"TargetFDB": TDB, "TargetTable": table_name, "IfExists": update_method, "UpdateMeta": False})

    # ExecEngine = Engine()
    # PIDList = ["0"]
    ExecEngine = ParallelEngine(args={"IOConcurrentNum": io_num})
    PIDList = [f"0-{i}" for i in range(process_num)]

    Cache = FeatherFactorCache(args={"DTRuler": DTRuler, "MinDTUnit": dt.timedelta(1), "PIDs": PIDList})
    Cache.start()

    Context = FactorContext(
        PID="0",
        PIDList=PIDList,
        DTRuler=DTRuler,
        DefaultSectionIDs=SectionIDs,
        SplitType="连续切分",
        FactorDataCache=Cache
    )
    LocalContext = FactorLocalContext(DTs=DTs, IDs=IDs)
    ExecEngine.run([Storer], Context, fwd_data_list=[LocalContext], init_data_list=[FactorInitData(DTRange=(DTs[0], DTs[-1]), SectionIDs=SectionIDs)])
    
    Cache.end(clear=False)

    # 关闭因子库连接
    for iFDB in FDBs.values():
        iFDB.disconnect()
    return 0

if __name__=="__main__":
    # updateFactorData(r".\stock_cn_factor_momentum.py", start_dt="2019-04-15", end_dt="2019-04-30", dt_db="JYDB", id_db="JYDB")

    # from click.testing import CliRunner
    # Runner = CliRunner()
    # Result = Runner.invoke(updateFactorData, "./stock_cn_factor_momentum.py -sdt 2019-04-15 -edt 2019-04-30 -sdb LDB:HDF5DB -scfg ./QSConfig/HDF5DBConfig.json -tdb TDB:HDF5DB -tcfg ./QSConfig/HDF5DBConfig.json -dtdb LDB:stock_cn_day_bar_nafilled -iddb LDB:stock_cn_day_bar_nafilled -ll INFO")
    # print(Result)

    updateFactorData()
    
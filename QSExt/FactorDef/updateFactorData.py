# -*- coding: utf-8 -*-
"""更新因子数据"""
import os
import importlib
import logging
logging.root.setLevel(logging.NOTSET)
import datetime as dt

import click

import QuantStudio.api as QS
from QuantStudio.FactorDataBase.FactorDB import FactorDB

def getLogger(log_dir, log_level):
    Fmt = "QSFactor - %(asctime)s - %(levelname)s : %(message)s"
    Logger = logging.getLogger()
    if isinstance(log_dir, str) and os.path.isdir(log_dir):
        LogFile = os.path.join(log_dir, "QSFactor_"+dt.date.today().strftime("%Y%m%d")+".log")
        LogHandler = logging.FileHandler(LogFile, mode="a")
        LogHandler.setLevel(log_level)
        LogHandler.setFormatter(logging.Formatter(Fmt))
        Logger.addHandler(LogHandler)
    else:
        # LogHandler = logging.StreamHandler()
        # LogHandler.setLevel(log_level)
        # LogHandler.setFormatter(logging.Formatter(Fmt))
        # Logger.addHandler(LogHandler)
        logging.basicConfig(level=log_level, format=Fmt)
        Logger.setLevel(log_level)
    return Logger

def loadModule(module_name, file_path):
    ModuleSpec = importlib.util.spec_from_file_location(module_name, file_path)
    Module = importlib.util.module_from_spec(ModuleSpec)
    ModuleSpec.loader.exec_module(Module)
    return Module

@click.command()
@click.argument("def_file")
@click.option("-tbl", "--table_name", type=str, default=None, help="目标因子表")
@click.option("-sdt", "--start_dt", type=str, default=None, help="起始时点, 格式: %Y-%m-%d")
@click.option("-edt", "--end_dt", type=str, default=None, help="结束时点, 格式: %Y-%m-%d")
@click.option("-slb", "--start_look_back", type=int, default=0, help="起始时点的回溯天数")
@click.option("-elb", "--end_look_back", type=int, default=0, help="结束时点的回溯天数")
@click.option("-ids", "--ids", type=str, default="", help="证券代码列表, 以逗号分隔, 比如: 000001.SZ,000002.SZ")
@click.option("-um", "--update_method", type=click.Choice(["update", "append", "update_notnull"]), default="update", help="更新方式")
@click.option("-pn", "--process_num", type=int, default=0, help="子进程数量, 0 表示串行计算")
@click.option("-darg", "--def_args", type=str, default=None, help="因子定义参数, 字典字面量, 格式: {'key': 'value'}")
@click.option("-sdb", "--sdb", type=str, default="LDB:HDF5DB", help="需要传入定义函数的源因子库, 多个以逗号分隔, 格式: 名称:因子库类, 比如: JYDB:JYDB,LDB:HDF5DB")
@click.option("-scfg", "--sdb_config", type=str, default="", help="源因子库配置文件, 多个以逗号分隔, 格式: /home/hst/JYDBConfig.json,/home/hst/HDF5DBConfig.json")
@click.option("-sarg", "--sdb_args", type=str, default="", help="源因子库参数, 字典字面量, 比如: {'主目录':'/home/hst/Data/HDF5Data'}")
@click.option("-tdb", "--tdb", type=str, default="TDB:HDF5DB", help="目标因子库, 比如: TDB:HDF5DB")
@click.option("-tcfg", "--tdb_config", type=str, default="", help="目标因子库配置文件")
@click.option("-targ", "--tdb_args", type=str, default="", help="目标因子库参数, 字典字面量, 比如: {'主目录':'/home/hst/Data/HDF5Data'}")
@click.option("-dtdb", "--dt_db", type=str, default=None, help="用于提取时点序列的因子库名称或者因子表名称, 比如 WDB 或者 LDB:stock_cn_day_bar")
@click.option("-iddb", "--id_db", type=str, default=None, help="用于提取 ID 序列的因子库名称或者因子表名称, 比如 WDB 或者 LDB:stock_cn_day_bar")
@click.option("-ll", "--log_level", type=str, default="INFO", help="log level")
@click.option("-ld", "--log_dir", type=str, default="", help="日志输出的文件目录")
def updateFactorData(def_file, table_name=None, start_dt=None, end_dt=None, start_look_back=0, end_look_back=0, ids=None, update_method="update", process_num=0, def_args=None, 
    sdb="", sdb_config="", sdb_args="", tdb="TDB:HDF5DB", tdb_config="", tdb_args="", dt_db=None, id_db=None, log_level=logging.INFO, log_dir=None):
    Logger = getLogger(log_dir, log_level)
    Logger.info("=================================================")
    
    # 导入因子定义
    DefFileName = ".".join(os.path.split(def_file)[-1].split(".")[:-1])
    DefModule = loadModule(DefFileName, def_file)
    UpdateArgs = DefModule.UpdateArgs
    Logger.info(f"导入因子定义: {def_file}")
    Logger.info(f"数据更新参数: {UpdateArgs}")
    
    DefArgs = {"logger": Logger}
    
    # 创建源因子库对象
    SDBs, SDBConfig, SDBArgs = sdb.split(","), sdb_config.split(","), sdb_args.split(",")
    if len(SDBConfig)!=len(SDBs):
        Logger.warning(f"源因子库数量({len(SDBs)})不等于其配置文件的数量({len(SDBConfig)}, 缺省的的将取默认值.")
        SDBConfig = SDBConfig + [""] * (len(SDBs) - len(SDBConfig))
    if len(SDBConfig)!=len(SDBs):
        Logger.warning(f"源因子库数量({len(SDBs)})不等于其参数数量({len(SDBArgs)}, 缺省的的将取默认值.")
        SDBArgs = SDBArgs + [""] * (len(SDBs) - len(SDBArgs))
    for i, iFDB in enumerate(SDBs):
        iName, iFDBType = iFDB.split(":")
        iName, iFDBType = iName.strip(), iFDBType.strip()
        iConfig = (SDBConfig[i].strip() if SDBConfig[i].strip() else None)
        iArgs = (eval(SDBArgs[i].strip()) if SDBArgs[i].strip() else {})
        if hasattr(QS.FactorDB, iFDBType):
            iFDBClass = getattr(QS.FactorDB, iFDBType)
        else:
            iModules = iFDBType.split(".")
            iFDBClass = getattr(importlib.import_module(".".join(iModules[:-1])), iModules[-1])
        DefArgs[iName] = iFDBClass(sys_args=iArgs, config_file=iConfig, logger=Logger)
        DefArgs[iName].connect()
        Logger.info(f"创建因子库({iFDB}): {DefArgs[iName].Args}")
    
    # 创建目标因子库
    iName, iFDBType = tdb.split(":")
    iName, iFDBType = iName.strip(), iFDBType.strip()
    iConfig = (tdb_config.strip() if tdb_config.strip() else None)
    iArgs = (eval(tdb_args.strip()) if tdb_args.strip() else {})
    if hasattr(QS.FactorDB, iFDBType):
        iFDBClass = getattr(QS.FactorDB, iFDBType)
    else:
        iModules = iFDBType.split(".")
        iFDBClass = getattr(importlib.import_module(".".join(iModules[:-1])), iModules[-1])
    DefArgs[iName] = TDB = iFDBClass(sys_args=iArgs, config_file=iConfig, logger=Logger)
    DefArgs[iName].connect()
    Logger.info(f"创建目标因子库({tdb}): {DefArgs[iName].Args}")
    
    # 目标因子表
    if table_name is None:
        table_name = UpdateArgs.get("因子表", None)
        if table_name:
            Logger.info(f"目标因子表: {table_name}, 未指定目标因子表, 使用了因子定义文件中设置的因子表")
        else:
            table_name = DefFileName
            Logger.info(f"目标因子表: {table_name}, 未指定目标因子表, 并且因子定义文件中也未设置目标因子表, 使用了文件名作为目标因子表")
    else:
        Logger.info(f"目标因子表: {table_name}")
    
    # 更新的起止时间
    if start_dt is None:
        if table_name in TDB.TableNames:
            FT = TDB.getTable(table_name)
            start_dt = FT.getDateTime()[-1] + dt.timedelta(1)
            Logger.info(f"初始起始时点: {start_dt}, 未指定起始时点, 使用了目标因子表中数据结束时点的下一个自然日作为起始时点")
        elif "默认起始日" in UpdateArgs:
            start_dt = UpdateArgs["默认起始日"]
            Logger.info(f"初始起始时点: {start_dt}, 未指定起始时点, 并且目标因子表中尚无数据, 使用了因子定义文件中设置的 '默认起始日' 作为起始时点")
        else:
            Logger.error("无法获取初始起始时点")
            return -1
    else:
        start_dt = dt.datetime.strptime(start_dt, "%Y-%m-%d")
        Logger.info(f"初始起始时点: {start_dt}")
    if start_look_back>0:
        start_dt -= dt.timedelta(start_look_back)
        Logger.info(f"最终起始时点: {start_dt}, 在初始起始时点基础上回溯 {start_look_back} 天得到")
    else:
        Logger.info(f"最终起始时点: {start_dt}, 等于初始起始时点")
    if end_dt is None:
        end_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
        Logger.info(f"初始结束时点: {end_dt}, 未指定结束时点, 使用了当前时点")
    else:
        end_dt = dt.datetime.strptime(end_dt, "%Y-%m-%d")
        Logger.info(f"初始结束时点: {end_dt}")
    if end_look_back>0:
        end_dt -= dt.timedelta(end_look_back)
        Logger.info(f"最终结束时点: {end_dt}, 在初始结束时点基础上回溯 {end_look_back} 天得到")
    else:
        Logger.info(f"最终结束时点: {end_dt}, 等于初始结束时点")
    
    # 设置时点序列
    DTType = UpdateArgs.get("时点类型", "交易日")
    if DTType=="交易日":
        dt_db = dt_db.split(":")
        if dt_db[0] not in DefArgs:
            Logger.error(f"提取时点序列的因子库对象({dt_db})不存在")
            return -1
        if len(dt_db)==1:
            DTs = DefArgs[dt_db[0]].getTradeDay(start_date=start_dt.date(), end_date=end_dt.date(), output_type="datetime")
            DTRuler = DefArgs[dt_db[0]].getTradeDay(start_date=start_dt.date() - dt.timedelta(UpdateArgs.get("最长回溯期", 3650)), end_date=end_dt.date(), output_type="datetime")
        else:
            iFactorName = (dt_db[2] if len(dt_db)>2 else None)
            FT = DefArgs[dt_db[0]].getTable(dt_db[1])
            DTs = FT.getDateTime(ifactor_name=iFactorName, start_dt=start_dt, end_dt=end_dt)
            DTRuler = FT.getDateTime(ifactor_name=iFactorName, start_dt=start_dt - dt.timedelta(UpdateArgs.get("最长回溯期", 3650)), end_dt=end_dt)
    elif DTType=="自然日":
        DTs = QS.Tools.DateTime.getDateTimeSeries(start_dt=start_dt, end_dt=end_dt, timedelta=dt.timedelta(1))
        DTRuler = QS.Tools.DateTime.getDateTimeSeries(start_dt=start_dt - dt.timedelta(UpdateArgs.get("最长回溯期", 3650)), end_dt=end_dt, timedelta=dt.timedelta(1))
    else:
        Logger.error(f"无法识别的时点类型: {DTType}")
        return -1
    # 调整时点频率
    UpdateFreq = UpdateArgs.get("更新频率", "日")
    if UpdateFreq in ("月", "月底"):
        DTs = QS.Tools.DateTime.getMonthLastDateTime(DTs)
        DTRuler = QS.Tools.DateTime.getMonthLastDateTime(DTRuler)
    elif UpdateFreq in ("年", "年底"):
        DTs = QS.Tools.DateTime.getYearLastDateTime(DTs)
        DTRuler = QS.Tools.DateTime.getYearLastDateTime(DTRuler)
    elif UpdateFreq!="日":
        Logger.error(f"无法识别的时点频率: {UpdateFreq}")
        return -1
    if DTs:
        Logger.info(f"时点序列: {DTs[0]} ~ {DTs[-1]}, 共 {len(DTs)} 天, 类型 '{DTType}', 频率 '{UpdateFreq}'")
        Logger.info(f"时点标尺序列: {DTRuler[0]} ~ {DTRuler[-1]}, 共 {len(DTRuler)} 天, 类型 '{DTType}', 频率 '{UpdateFreq}'")
    else:
        Logger.warning("没有需要更新的时点")
        return 0
    
    # 设置 ID 序列
    if isinstance(ids, str) and (ids!=""):
        IDs = sorted(ids.split(","))
        IDType = "外部指定"
    elif "IDs" in UpdateArgs:
        IDType = UpdateArgs["IDs"]
        if isinstance(IDType, str):
            id_db = id_db.split(":")
            if id_db[0] not in DefArgs:
                Logger.info(f"提取 ID 序列的因子库对象({id_db})不存在")
                return -1           
            if len(id_db)==1:
                if IDType=="股票":
                    IDs = DefArgs[id_db[0]].getStockID(is_current=False)
                elif IDType=="债券":
                    IDs = DefArgs[id_db[0]].getBondID(is_current=False)
                elif IDType=="公募基金":
                    IDs = DefArgs[id_db[0]].getMutualFundID(is_current=False)
                else:
                    Logger.error(f"不支持因子定义文件指定的 ID 类型: {IDType}")
                    return -1
            else:
                iFactorName = (id_db[2] if len(id_db)>2 else None)
                FT = DefArgs[id_db[0]].getTable(id_db[1])
                IDs = FT.getID(ifactor_name=iFactorName)
        else:
            IDs = sorted(IDType)
            IDType = "因子定义文件指定"
    else:
        Logger.error("没有指定 ID 序列")
        return -1
    Logger.info(f"ID 序列: {IDs[0]} ~ {IDs[-1]}, 共 {len(IDs)} 个, 类型 '{IDType}'")
    
    # 因子定义
    DefArgs["dt_ruler"] = DTRuler
    DefArgs["dts"] = DTs
    DefArgs["ids"] = IDs
    if def_args:
        iArgs = eval(def_args)
        DefArgs.update(iArgs)
        Logger.info(f"因子定义附加参数: {iArgs}")
    Factors = DefModule.defFactor(args=DefArgs)
    FactorNames = [iFactor.Name for iFactor in Factors]
    Logger.info(f"因子列表: {FactorNames}")
    
    # 生成因子数据
    CFT = QS.FactorDB.CustomFT(table_name, logger=Logger)
    CFT.addFactors(factor_list=Factors)
    Logger.info(f"生成因子数据: 更新方式 '{update_method}', 子进程数 {process_num}")
    Logger.info("=================================================")
    CFT.write2FDB(factor_names=CFT.FactorNames, ids=IDs, dts=DTs, factor_db=TDB, table_name=table_name, if_exists=update_method, dt_ruler=DTRuler, subprocess_num=process_num)
    
    # 关闭因子库连接
    for iKey, iVal in DefArgs.items():
        if isinstance(iVal, FactorDB):
            iVal.disconnect()
    return 0

if __name__=="__main__":
    # updateFactorData(r".\stock_cn_factor_momentum.py", start_dt="2019-04-15", end_dt="2019-04-30", 
    #     sdb="LDB:HDF5DB", sdb_config=r".\QSConfig\HDF5DBConfig.json", 
    #     tdb="TDB:HDF5DB", tdb_config=r".\QSConfig\HDF5DBConfig.json",
    #     dt_db="LDB:stock_cn_day_bar_nafilled", id_db="LDB:stock_cn_day_bar_nafilled")

    # from click.testing import CliRunner
    # Runner = CliRunner()
    # Result = Runner.invoke(updateFactorData, "./stock_cn_factor_momentum.py -sdt 2019-04-15 -edt 2019-04-30 -sdb LDB:HDF5DB -scfg ./QSConfig/HDF5DBConfig.json -tdb TDB:HDF5DB -tcfg ./QSConfig/HDF5DBConfig.json -dtdb LDB:stock_cn_day_bar_nafilled -iddb LDB:stock_cn_day_bar_nafilled -ll INFO")
    # print(Result)

    updateFactorData()
    
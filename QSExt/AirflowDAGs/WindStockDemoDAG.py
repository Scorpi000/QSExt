# -*- coding: utf-8 -*-
import os

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

PythonPath = "python3"
WorkDir = "/usr/src/app/FactorDef"
UpdateScript = f"{WorkDir}/updateFactorData.py"
FactorDefDir = WorkDir
TDBConfig = f"{WorkDir}/QSConfig/HDF5DBConfig.json"
LDBConfig = f"{WorkDir}/QSConfig/HDF5DBConfig.json"
DTDB = "LDB:stock_cn_day_bar_nafilled"# WDB
IDDB = "LDB:stock_cn_day_bar_nafilled"# WDB

os.chdir(WorkDir)

with DAG(dag_id="Wind-Stock", start_date=pendulum.datetime(2022, 1, 1, 19, tz="Asia/Shanghai"), schedule="0 0 19 * * *", catchup=False, 
    tags=["Wind", "Stock", "Test"], default_args={"retries": 1}) as dag:
    iScript = "stock_cn_info"
    stock_cn_info = BashOperator(task_id=iScript,
        # bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb WDB:WindDB2 -scfg {WDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb WDB -iddb WDB")
        bash_command=f"echo {iScript} updation finished!")

    iScript = "stock_cn_day_bar_nafilled"
    stock_cn_day_bar_nafilled = BashOperator(task_id=iScript,
        # bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb WDB:WindDB2 -scfg {WDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb WDB -iddb WDB")
        bash_command=f"echo {iScript} updation finished!")
    
    iScript = "stock_cn_day_bar_adj_backward_nafilled"
    stock_cn_day_bar_adj_backward_nafilled = BashOperator(task_id=iScript, 
        # bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb WDB:WindDB2 -scfg {WDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb WDB -iddb WDB")
        bash_command=f"echo {iScript} updation finished!")

    iScript = "stock_cn_factor_momentum"
    stock_cn_factor_momentum = BashOperator(task_id=iScript, 
        bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb LDB:HDF5DB -scfg {LDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb {DTDB} -iddb {IDDB}")

    iScript = "stock_cn_factor_technical"
    stock_cn_factor_technical = BashOperator(task_id=iScript, 
        bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb LDB:HDF5DB -scfg {LDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb {DTDB} -iddb {IDDB}")

    iScript = "stock_cn_multi_factor_classic"
    stock_cn_multi_factor_classic = BashOperator(task_id=iScript, 
        bash_command=f"{PythonPath} {UpdateScript} {FactorDefDir}/{iScript}.py -slb 3 -sdb LDB:HDF5DB -scfg {LDBConfig} -tdb TDB:HDF5DB -tcfg {TDBConfig} -dtdb {DTDB} -iddb {IDDB} -darg \"{{'factor_info_file':'{FactorDefDir}/conf/stock_cn_multi_factor_classic.csv'}}\"")

    # Set dependencies between tasks
    [stock_cn_info, stock_cn_day_bar_nafilled, stock_cn_day_bar_adj_backward_nafilled] >> stock_cn_factor_momentum
    [stock_cn_day_bar_nafilled, stock_cn_day_bar_adj_backward_nafilled] >> stock_cn_factor_technical
    [stock_cn_factor_momentum, stock_cn_factor_technical] >> stock_cn_multi_factor_classic
# -*- coding: utf-8 -*-
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(dag_id="Wind-Stock", start_date=datetime(2022, 1, 1), schedule="0 0 * * *") as dag:
    stock_cn_day_bar_nafilled = BashOperator(task_id="stock_cn_day_bar_nafilled",
        bash_command="/home/hst/Project/PythonEnv/QS/bin/python3 ../FactorDef/updateFactorData.py ../FactorDef/Wind/stock_cn_day_bar_nafilled.py -slb 3 -sdb WDB:WindDB2 -tdb TDB:HDF5DB -dtdb WDB -iddb WDB")
    
    stock_cn_day_bar_adj_backward_nafilled = BashOperator(task_id="stock_cn_day_bar_adj_backward_nafilled", 
        bash_command="/home/hst/Project/PythonEnv/QS/bin/python3 ../FactorDef/updateFactorData.py ../FactorDef/Wind/stock_cn_day_bar_adj_backward_nafilled.py -slb 3 -sdb WDB:WindDB2 -tdb TDB:HDF5DB -dtdb WDB -iddb WDB")
    
    stock_cn_momentum = BashOperator(task_id="stock_cn_momentum", 
        bash_command="/home/hst/Project/PythonEnv/QS/bin/python3 ../FactorDef/updateFactorData.py ../FactorDef/Wind/stock_cn_day_bar_momentum.py -slb 3 -sdb WDB:WindDB2 -tdb TDB:HDF5DB -dtdb WDB -iddb WDB")
    
    # Set dependencies between tasks
    [stock_cn_day_bar_nafilled, stock_cn_day_bar_adj_backward_nafilled] >> stock_cn_momentum
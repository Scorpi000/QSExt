#!/bin/sh
cd ./FactorDef
airflow db init
airflow users create --username admin --firstname Peter --lastname Parker --role Admin --password 123.com --email scorpi000@163.com
nohup airflow scheduler --daemon --subdir /usr/src/app/DAGs > airflow_scheduler.log 2>&1 &
airflow webserver
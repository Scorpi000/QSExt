#!/bin/sh
cd ./FactorDef

CONTAINER_ALREADY_STARTED="CONTAINER_ALREADY_STARTED_PLACEHOLDER"
if [ ! -e $CONTAINER_ALREADY_STARTED ]; then
    touch $CONTAINER_ALREADY_STARTED
    echo "-- First container startup --"
    airflow db init
    airflow users create --username admin --firstname Peter --lastname Parker --role Admin --password 123.com --email scorpi000@163.com
else
    echo "-- Not first container startup --"
fi

nohup airflow scheduler --daemon --subdir /usr/src/app/DAGs > airflow_scheduler.log 2>&1 &
airflow webserver
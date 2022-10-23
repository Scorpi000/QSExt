FROM python:3

WORKDIR /usr/src/app
COPY . .

# install python packages
# RUN mkdir ./Packages && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQS.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQSExt.txt -i https://mirrors.aliyun.com/pypi/simple
ENV PYTHONPATH="/usr/src/app/Packages/QuantStudio:/usr/src/app/Packages/QSExt"

# install airflow
ENV AIRFLOW_HOME=/usr/src/app/Airflow
RUN pip install mysqlclient -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir "apache-airflow==2.4.1" -i https://mirrors.aliyun.com/pypi/simple --constraint "./constraints-3.10.txt"

# setup airflow
ARG sql_alchemy_conn="sqlite:///$AIRFLOW_HOME/airflow.db"
ARG executor="SequentialExecutor"
ENV AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$sql_alchemy_conn"
ENV AIRFLOW__CORE__EXECUTOR="$executor"
RUN mkdir ./FactorDef && mkdir ./DAGs && chmod 777 start.sh
EXPOSE 8080
CMD ["sh", "./start.sh"]
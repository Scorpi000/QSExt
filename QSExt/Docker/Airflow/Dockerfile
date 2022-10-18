FROM python:3

WORKDIR /usr/src/app
COPY . .

# install python packages
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQS.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQSExt.txt -i https://mirrors.aliyun.com/pypi/simple

# install airflow
ENV AIRFLOW_HOME=/usr/src/app/Airflow
RUN pip install --no-cache-dir "apache-airflow==2.4.1" -i https://mirrors.aliyun.com/pypi/simple --constraint "./constraints-3.10.txt"

# start airflow
ENV PYTHONPATH="/usr/src/app/QSDemo/Data/Packages/QuantStudio:/usr/src/app/QSDemo/Data/Packages/QSExt"
EXPOSE 8080
CMD ["airflow", "standalone"]
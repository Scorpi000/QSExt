FROM python:3

WORKDIR /usr/src/app
COPY . .

# install python packages
RUN mkdir QSDemo && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && jupyter contrib nbextension install --system && pip install --no-cache-dir -r requirementsQS.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQSExt.txt -i https://mirrors.aliyun.com/pypi/simple

# start jupyter
WORKDIR ./QSDemo
ENV PYTHONPATH="/usr/src/app/QSDemo/Data/Packages/QuantStudio:/usr/src/app/QSDemo/Data/Packages/QSExt"
ENV JUPYTER_CONFIG_DIR="/usr/src/app"
EXPOSE 8888
CMD ["jupyter", "notebook", "--allow-root"]
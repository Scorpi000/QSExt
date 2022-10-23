FROM python:3

WORKDIR /usr/src/app
COPY . .

# install python packages
RUN mkdir Data && mkdir Packages && mkdir Research && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && jupyter contrib nbextension install --system
# RUN mkdir Data && mkdir Packages && mkdir Research && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && jupyter contrib nbextension install --system && pip install --no-cache-dir -r requirementsQS.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQSExt.txt -i https://mirrors.aliyun.com/pypi/simple

# start jupyter
WORKDIR ./Research
ENV PYTHONPATH="/usr/src/app/Packages/QuantStudio:/usr/src/app/Packages/QSExt"
ENV JUPYTER_CONFIG_DIR="/usr/src/app"
EXPOSE 8888
CMD ["jupyter", "notebook", "--allow-root"]
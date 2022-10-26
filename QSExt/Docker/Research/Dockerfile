FROM python:3.10

WORKDIR /usr/src/app
COPY . .

# 解决容器与宿主机时区不一致问题
RUN cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo "Asia/Shanghai" > /etc/timezone

# install python packages
# RUN mkdir Data && mkdir Packages && mkdir Research && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && jupyter contrib nbextension install --system
RUN mkdir Data && mkdir Packages && mkdir Research && pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple && jupyter contrib nbextension install --system && pip install --no-cache-dir -r requirementsQS.txt -i https://mirrors.aliyun.com/pypi/simple && pip install --no-cache-dir -r requirementsQSExt.txt -i https://mirrors.aliyun.com/pypi/simple

# 解决 matplotlib 中文字体问题
RUN mplpath=`python -c "import matplotlib;import os;print(os.path.split(matplotlib.matplotlib_fname())[0])"` && echo -e "font.family         : sans-serif\nfont.sans-serif     : arial unicode ms, Bitstream Vera Sans, Lucida Grande, Verdana, Geneva, Lucid, Arial, Helvetica, Avant Garde, sans-serif" >> $mplpath/matplotlibrc && cp ./arial\ unicode\ ms.ttf $mplpath/fonts/arial\ unicode\ ms.ttf && mv ./arial\ unicode\ ms.ttf /usr/share/fonts && rm -rf ~/.cache/matplotlib

# start jupyter
WORKDIR ./Research
ENV PYTHONPATH="/usr/src/app/Packages/QuantStudio:/usr/src/app/Packages/QSExt"
ENV JUPYTER_CONFIG_DIR="/usr/src/app"
EXPOSE 8888
CMD ["jupyter", "notebook", "--allow-root"]
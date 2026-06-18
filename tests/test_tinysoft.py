# coding=utf-8
import os
import json
import datetime as dt

# https://py3k.cn/pyTSL/
import pyTSL
import pandas as pd

from QSExt import __QS_ConfigPath__

with open(__QS_ConfigPath__ + os.sep + "TinySoftDBConfig.json", mode="r") as fp:
    conn_args = json.load(fp)

# 测试连接
c = pyTSL.Client(conn_args["User"], conn_args["Pwd"], conn_args["IPAddr"], conn_args["Port"])
c.login()
r = c.exec('''return "测试"; ''')
print(r.value())

# 读取数据
code='''
function get_data(begT, endT);
begin
    return select * from markettable datekey begT to endT of DefaultStockID() end;
end;
'''
r = c.call('get_data', dt.datetime(2026, 6, 15), dt.datetime.now(), stock="SZ000001", cycle="日线", code=code)
# r.value() 方法可以指定需要转换成datetime类型的字段
df = pd.DataFrame(data=r.value(parse_date=['date']))
df = df.set_index(["date"])
print(df.head())

# pyTSL也提供了把返回结果直接转成DataFrame的方法
df = r.dataframe()
# pyTSL提供了TSL的时间类型和python的datetime类型的转换方法
# DatetimeToDouble 转换datetime类型到TSL的时间类型
# DoubleToDatetime 转换TSL的时间类型到datetime类型
df['date'] = df['date'].apply(lambda x: pyTSL.DoubleToDatetime(x))
df = df.set_index(["date"])
print(df.head())

c.logout()
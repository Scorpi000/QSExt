# import sys
# sys.path.append(r"D:\Program Files\Tinysoft\Analyse.NET")
# import TSLPy3 as ts

# ErrorCode = ts.ConnectServer("tsl.tinysoft.com.cn", 443)
# if ErrorCode!=0:
#     raise Exception("TinySoft 服务器连接失败!")

# dl = ts.LoginServer("***", "***") #user为天软用户账号， password为用户密码
# if dl[0] == 0:
#     data = ts.RemoteExecute("return 1;", {})
#     print(data)
# else:
#     print(dl[1])

# ts.Disconnect() #交互完断开连接，避免占用资源


import pyTSL

c = pyTSL.Client("***", "***", "tsl.tinysoft.com", 443)
c.login()
r = c.exec('''return "测试"; ''')
print(r.value())
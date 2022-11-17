# -*- coding: utf-8 -*-
from QuantStudio import __QS_Object__
from QSExt.GUI.Notebook.FactorDBDlg import FactorDBDlg
from QSExt.GUI.Notebook.RiskDBDlg import RiskDBDlg
from QSExt.GUI.Notebook.ArgSetupDlg import ArgSetupDlg
from QSExt.GUI.Notebook.ResultDlg import ResultDlg

# 管理因子库
def manageFactorDB(fdbs, output=None):
    Dlg = FactorDBDlg(fdbs)
    Dlg.display(output=output)
    return Dlg

# 管理风险库
def manageRiskDB(rdbs, output=None):
    Dlg = RiskDBDlg(rdbs)
    Dlg.display(output=output)
    return Dlg

# 设置 QS 对象的参数
def setupArgs(qs_obj: __QS_Object__, output=None):
    Dlg = ArgSetupDlg(qs_obj.Args)
    Dlg.display(output=output)
    return Dlg

# 查看数据集
def showOutput(data, output=None, plot_engine="plotly"):
    Dlg = ResultDlg(data=data)
    Dlg.display(output=output)
    return Dlg
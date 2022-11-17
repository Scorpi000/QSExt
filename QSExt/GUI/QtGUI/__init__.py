# -*- coding: utf-8 -*-
import sys

from PyQt5 import QtWidgets

from QSExt.GUI.QtGUI.ResultDlg import PlotlyResultDlg, MatplotlibResultDlg
from QSExt.GUI.QtGUI.FactorDBDlg import FactorDBDlg
from QSExt.GUI.QtGUI.PreviewFactorDlg import PreviewDlg
from QSExt.GUI.QtGUI.RiskDBDlg import RiskDBDlg
from QSExt.GUI.QtGUI.DateTimeSetup import DateTimeSetupDlg
from QSExt.GUI.QtGUI.IDSetup import IDSetupDlg

_App = QtWidgets.QApplication(sys.argv)

# 以 GUI 的方式查看数据集
def showOutput(output, plot_engine="matplotlib"):
    if plot_engine=="plotly": Dlg = PlotlyResultDlg(None, output)
    elif plot_engine=="matplotlib": Dlg = MatplotlibResultDlg(None, output)
    Dlg.show()
    _App.exec_()
    return 0

# 以 GUI 的方式查看因子库
def showFactorDB(fdb):
    Dlg = FactorDBDlg(fdb)
    Dlg.show()
    _App.exec_()
    return 0

# 以 GUI 的方式查看因子
def showFactor(factor):
    Dlg = PreviewDlg(factor)
    Dlg.show()
    _App.exec_()
    return 0

# 以 GUI 的方式查看风险库
def showRiskDB(rdb):
    Dlg = RiskDBDlg(rdb)
    Dlg.show()
    _App.exec_()
    return 0

# 以 GUI 的方式设置日期时间
def setDateTime(dts=[], dates=[], times=[], ft=None):
    Dlg = DateTimeSetupDlg(dts=dts, dates=dates, times=times, ft=ft)
    Dlg.show()
    _App.exec_()
    if Dlg.isChanged: return (Dlg.DateTimes, Dlg.Dates, Dlg.Times)
    else: return (dts, dates, times)
    
# 以 GUI 的方式设置 ID
def setID(ids=[], ft=None):
    Dlg = IDSetupDlg(ids=ids, ft=ft)
    Dlg.show()
    _App.exec_()
    if Dlg.isChanged: return Dlg.IDs
    else: return ids
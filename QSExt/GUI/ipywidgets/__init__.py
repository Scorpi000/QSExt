# -*- coding: utf-8 -*-
from QuantStudio import __QS_Object__
from QSExt.GUI.ipywidgets.FactorDBDlg import FactorDBDlg
from QSExt.GUI.ipywidgets.RiskDBDlg import RiskDBDlg
from QSExt.GUI.ipywidgets.ArgSetupDlg import ArgSetupDlg

def manageFactorDB(fdbs, output=None):
    Dlg = FactorDBDlg(fdbs)
    Dlg.display(output=output)
    return Dlg

def manageRiskDB(rdbs, output=None):
    Dlg = RiskDBDlg(rdbs)
    Dlg.display(output=output)
    return Dlg

def setupArgs(qs_obj: __QS_Object__, output=None):
    Dlg = ArgSetupDlg(qs_obj.Args)
    Dlg.display(output=output)
    return Dlg
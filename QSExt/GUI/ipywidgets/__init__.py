# -*- coding: utf-8 -*-
from QuantStudio import __QS_Object__
from QSExt.GUI.ipywidgets.FactorDBDlg import FactorDBDlg
from QSExt.GUI.ipywidgets.ArgSetupDlg import ArgSetupDlg

def manageFactorDB(fdbs):
    pass

def setupArgs(qs_obj: __QS_Object__, output=None):
    Dlg = ArgSetupDlg(qs_obj.Args)
    Dlg.display(output=output)
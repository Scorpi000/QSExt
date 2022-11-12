# -*- coding: utf-8 -*-
"""结果集"""
import os
import tempfile
import datetime as dt

import pandas as pd
import ipywidgets as widgets
from ipytree import Node, Tree
from IPython.display import display, HTML

from QuantStudio import __QS_Object__
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB
from QuantStudio.Tools.AuxiliaryFun import genAvailableName
from QuantStudio.Tools.FileFun import listDirFile, loadCSVFactorData
from QSExt.GUI.ipywidgets.utils import createQuestionDlg, showQuestionDlg, createGetTextDlg, showGetTextDlg, createDataFrameDownload

class ResultDlg(__QS_Object__):
    def __init__(self, data={}, output=None, msg_output=None, sys_args={}, config_file=None, **kwargs):
        self.Data = data
        self.CurDF = pd.DataFrame()# 当前显示在 Table 中的数据，DataFrame
        self._Output = output# 显示 dlg 的 output
        self._MsgOutput = msg_output# 显示消息的 output
        self.Frame, self.Widgets = self.createWidgets()
        
    def createWidgets(self):
        self.Widgets["ControlOutput"] = widgets.Output()# 显示控件的 output
        self.Widgets["MainOutput"] = widgets.Output()# 显示数据的 output
        self.Widgets["MainResultTree"] = Tree()
        self.Frame = widgets.HBox(children=[
            self.Widgets["MainOutput"],
            widgets.VBox(children=[
                self.Widgets["MainResultTree"],
            ])
        ])
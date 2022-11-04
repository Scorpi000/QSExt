# -*- coding: utf-8 -*-
"""结果集"""
import os
import tempfile
import datetime as dt

import pandas as pd
import ipywidgets as widgets
from IPython.display import display, HTML

from QuantStudio import __QS_Object__
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB
from QuantStudio.Tools.AuxiliaryFun import genAvailableName
from QuantStudio.Tools.FileFun import listDirFile, loadCSVFactorData
from QSExt.GUI.ipywidgets.utils import createQuestionDlg, showQuestionDlg, createGetTextDlg, showGetTextDlg, createDataFrameDownload

# 基于 plotly 绘图的 ResultDlg
class ResultDlg(__QS_Object__):
    def __init__(self, fdbs, sys_args={}, config_file=None, **kwargs):
        pass
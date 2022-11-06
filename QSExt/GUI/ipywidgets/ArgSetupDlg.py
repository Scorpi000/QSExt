# -*- coding: utf-8 -*-
"""参数集"""
import os

import numpy as np
import ipywidgets as widgets
from ipyfilechooser import FileChooser

from QuantStudio import __QS_Object__, QSArgs, __QS_Error__

class FloatWidget:
    def __init__(self, value, min_val=-np.inf, max_val=np.inf, step=0.0001, decimals=4, disabled=False):
        self.Widgets = {}
        if (not np.isinf(min_val)) and (not np.isinf(max_val)):
            self.Widgets["Finite"] = widgets.BoundedFloatText(value=value, min=min_val, max=max_val, step=step, disabled=disabled)
            self.Frame = self.Widgets["Finite"]
            return
        Options, RadioValue = ["有限值"], "有限值"
        if np.isinf(min_val):
            Options.append("负无穷")
            RadioValue = ("负无穷" if value==-np.inf else RadioValue)
        if np.isinf(max_val):
            Options.append("正无穷")
            RadioValue = ("正无穷" if value==np.inf else RadioValue)
        self.Widgets["Condition"] = widgets.RadioButtons(options=Options, value=RadioValue, layout={"width": "max-content", "display": "flex", "flex-direction": "row", "flex-wrap": "wrap"}, disabled=disabled)
        self.Widgets["Finite"] = widgets.FloatText(value=value, step=step, disabled=(disabled or (RadioValue!="有限值")))
        self.Widgets["Condition"].observe(self._on_condition_change, names="value")
        self.Frame = widgets.HBox(children=(self.Widgets["Condition"], self.Widgets["Finite"]))
    
    def _on_condition_change(self, b):
        self.Widgets["Finite"].disabled = (self.Widgets["Condition"].value!="有限值")
    
    def frame(self):
        return self.Frame
    
    @property
    def value(self):
        if "Condition" not in self.Widgets:
            return self.Widgets["Finite"].value
        RadioValue = self.Widgets["Condition"].value
        if RadioValue=="有限值":
            return self.Widgets["Finite"].value
        elif RadioValue=="负无穷":
            return -np.inf
        elif RadioValue=="正无穷":
            return np.inf
        

class ArgSetupDlg(__QS_Object__):
    def __init__(self, args: QSArgs, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self._Args = args
        self.Widgets = {}
        self.Frame, self.Widgets = self.createArgWidgets(self._Args, {}, None)
    
    def createArgWidgets(self, args: QSArgs, widget_dict={}, parent_arg=None):
        Frame = []
        for iArgName in args.ArgNames:
            _, iTrait = args.getTrait(iArgName)
            iArgType, iArgVal = iTrait.arg_type, args[iArgName]
            iDisabled = (False if getattr(iTrait, "mutable") is None else (not getattr(iTrait, "mutable")))
            #iWidgetName = (iArgName if not parent_arg else f"{parent_arg}-{iArgName}")
            if iArgType=="String":
                widget_dict[iArgName] = widgets.Text(value=iArgVal, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
            elif iArgType=="Directory":
                Dir = (iArgVal if os.path.isdir(iArgVal) else os.getcwd())
                widget_dict[iArgName] = FileChooser(path=Dir, show_only_dirs=True)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
            elif iArgType=="Float":
                MinVal = (-np.inf if iTrait.low is None else iTrait.low)
                MaxVal = (np.inf if iTrait.high is None else iTrait.high)
                Step = (0.0001 if iTrait.single_step is None else iTrait.single_step)
                Decimals = (4 if iTrait.decimals is None else iTrait.decimals)
                widget_dict[iArgName] = FloatWidget(iArgVal, min_val=MinVal, max_val=MaxVal, step=Step, decimals=Decimals, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName].frame()]))
            elif iArgType=="ArgSet":
                iFrame, widget_dict[iArgName] = self.createArgWidgets(iArgVal, {}, iArgName)
                Frame.append(widgets.Accordion(children=[iFrame], titles=(iArgName,)))
            else:
                raise __QS_Error__(f"不支持的参数类型: {iTrait.arg_type}")
        return widgets.VBox(children=Frame), widget_dict
    
    def frame(self):
        return self.Frame

if __name__=="__main__":
    import QuantStudio.api as QS
    HDB = QS.FactorDB.HDF5DB()
    
    Dlg = ArgSetupDlg(HDB.Args)
    print("===")
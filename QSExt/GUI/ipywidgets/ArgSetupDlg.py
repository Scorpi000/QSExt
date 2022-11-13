# -*- coding: utf-8 -*-
"""参数集"""
import os
import datetime as dt

import numpy as np
import ipywidgets as widgets
from ipyfilechooser import FileChooser
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__, QSArgs, __QS_Error__

# 支持无穷大的 Float 控件
class FloatWithInfWidget:
    def __init__(self, value, min_val=-np.inf, max_val=np.inf, step=0.0001, decimals=4, disabled=False):
        self.Widgets = {}
        if (not np.isinf(min_val)) and (not np.isinf(max_val)):
            self.Widgets["Finite"] = widgets.BoundedFloatText(value=value, min=min_val, max=max_val, step=step, disabled=disabled)
            self.Frame = self.Widgets["Finite"]
            return
        Options, SelectedValue, FiniteValue = ["有限值"], "有限值", (0 if np.isinf(value) else value)
        if np.isinf(min_val):
            Options.append("负无穷")
            SelectedValue = ("负无穷" if value==-np.inf else SelectedValue)
            FiniteValue = np.clip(FiniteValue, min_val, np.inf)
        if np.isinf(max_val):
            Options.append("正无穷")
            SelectedValue = ("正无穷" if value==np.inf else SelectedValue)
            FiniteValue = np.clip(FiniteValue, -np.inf, max_val)
        self.Widgets["Condition"] = widgets.Dropdown(options=Options, value=SelectedValue, disabled=disabled)
        disabled = (disabled or (SelectedValue!="有限值"))
        self.Widgets["Finite"] = widgets.FloatText(value=FiniteValue, step=step, layout={"visibility": ("hidden" if disabled else "visible")}, disabled=disabled)
        self.Widgets["Condition"].observe(self._on_condition_change, names="value")
        self.Frame = widgets.HBox(children=(self.Widgets["Condition"], self.Widgets["Finite"]))

    def on_value_change(self, handler):
        self._ValueChangeHandler = handler
        self.Widgets["Finite"].observe(self._on_value_change, names="value")
        self.Widgets["Condition"].observe(self._on_value_change, names="value")
    
    def _on_value_change(self, change):
        change["owner"] = self
        change["new"] = self.value
        change["old"] = self._QSArgs[self._QSArgName]
        return self._ValueChangeHandler(change)

    def _on_condition_change(self, change):
        self.Widgets["Finite"].disabled = (change["new"]!="有限值")
        self.Widgets["Finite"].layout.visibility = ("hidden" if self.Widgets["Finite"].disabled else "visible")
    
    @property
    def value(self):
        if "Condition" not in self.Widgets:
            return self.Widgets["Finite"].value
        SelectedValue = self.Widgets["Condition"].value
        if SelectedValue=="有限值":
            return self.Widgets["Finite"].value
        elif SelectedValue=="负无穷":
            return -np.inf
        elif SelectedValue=="正无穷":
            return np.inf

class ArgSetupDlg(__QS_Object__):
    def __init__(self, args: QSArgs, msg_output=None, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self._Args = args
        self._MsgOutput = msg_output# 显示消息的 output
        self.Frame, self.Widgets = self.createArgWidgets(self._Args, {})
    
    def createArgWidgets(self, args: QSArgs, widget_dict={}):
        Frame = []
        for iArgName in args.ArgNames:
            _, iTrait = args.getTrait(iArgName)
            iArgType, iArgVal = iTrait.arg_type, args[iArgName]
            iDisabled = (False if getattr(iTrait, "mutable") is None else (not getattr(iTrait, "mutable")))
            if iArgType=="String":# traits: Str
                widget_dict[iArgName] = widgets.Text(value=iArgVal, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="Integer":# traits: Int
                widget_dict[iArgName] = widgets.IntText(value=iArgVal, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="Bool":# traits: Bool
                widget_dict[iArgName] = widgets.Checkbox(value=iArgVal, indent=False, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")            
            elif iArgType=="SingleOption":# traits: Enum
                widget_dict[iArgName] = widgets.Dropdown(value=iArgVal, options=[(str(iOption), iOption) for iOption in iTrait.option_range], disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="MultiOption":# traits: List
                widget_dict[iArgName] = widgets.SelectMultiple(value=iArgVal, options=[(str(iOption), iOption) for iOption in iTrait.option_range], disabled=iDisabled)
                widget_dict[iArgName]._QSValueFun = list
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="File":# traits: File
                if os.path.isfile(iArgVal):
                    iDir, iFile = os.path.split(os.path.abspath(iArgVal))
                else:
                    iDir, iFile = os.getcwd(), ""
                widget_dict[iArgName] = FileChooser(path=iDir, filename=iFile, filter_pattern=iTrait.filter, show_only_dirs=False, select_default=os.path.isfile(iArgVal))
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].register_callback(lambda w: self._on_value_change({"owner": w, "new": w.value, "old": w._QSArgs[w._QSArgName], "type": "change", "name": "value"}))
            elif iArgType=="Directory":# traits: Directory
                Dir = (os.path.abspath(iArgVal) if os.path.isdir(iArgVal) else os.getcwd())
                widget_dict[iArgName] = FileChooser(path=Dir, show_only_dirs=True, select_default=os.path.isdir(iArgVal))
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].register_callback(lambda w: self._on_value_change({"owner": w, "new": w.value, "old": w._QSArgs[w._QSArgName], "type": "change", "name": "value"}))
            elif iArgType=="Float":# traits: Float
                MinVal = (-np.inf if iTrait.low is None else iTrait.low)
                MaxVal = (np.inf if iTrait.high is None else iTrait.high)
                Step = (0.0001 if iTrait.single_step is None else iTrait.single_step)
                Decimals = (4 if iTrait.decimals is None else iTrait.decimals)
                widget_dict[iArgName] = FloatWithInfWidget(iArgVal, min_val=MinVal, max_val=MaxVal, step=Step, decimals=Decimals, disabled=iDisabled)
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName].Frame]))
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].on_value_change(self._on_value_change)
            elif iArgType=="DateTimeList":# traits: List(dt.datetime)
                widget_dict[iArgName] = widgets.Textarea(value=str(iArgVal), disabled=iDisabled, tooltip="List(dt.datetime)")
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSValueFun = eval
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="IDList":# traits: ListStr
                widget_dict[iArgName] = widgets.Textarea(value=str(iArgVal), disabled=iDisabled, tooltip="ListStr")
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
                widget_dict[iArgName]._QSValueFun = eval
                widget_dict[iArgName]._QSArgName = iArgName
                widget_dict[iArgName]._QSArgs = args
                widget_dict[iArgName].observe(self._on_value_change, names="value")
            elif iArgType=="ArgObject":
                iFrame, widget_dict[iArgName] = self.createArgWidgets(iArgVal, {})
                Frame.append(widgets.Accordion(children=[iFrame], titles=(iArgName,)))
            else:
                widget_dict[iArgName] = widgets.Label(value=f"暂不支持修改的参数类型: {iTrait.arg_type}, 请在程序里修改!")
                Frame.append(widgets.HBox(children=[widgets.Label(value=iArgName), widget_dict[iArgName]]))
        return widgets.VBox(children=Frame), widget_dict
    
    def display(self, output=None):
        if output:
            with output:
                output.clear_output()
                display(self.Frame)
        else:
            clear_output()
            display(self.Frame)
    
    def _on_value_change(self, change):
        iWidget = change["owner"]
        iArgName = iWidget._QSArgName
        iArgs = iWidget._QSArgs
        iValFun = getattr(iWidget, "_QSValueFun", None)
        try:
            if iValFun:
                iArgs[iArgName] = iValFun(change["new"])
            else:
                iArgs[iArgName] = change["new"]
        except Exception as e:
            Msg = f"参数 '{iArgName}' 修改( {change['old']} --> {change['new']} )失败: {e}"
            if self._MsgOutput:
                with self._MsgOutput:
                    print(Msg)
            else:
                self._QS_Logger.error(Msg)
        else:
            if iArgName in iArgs.ObservedArgs:
                self.Frame, self.Widgets = self.createArgWidgets(self._Args, {})
                self.display()

if __name__=="__main__":
    import QuantStudio.api as QS
    FDB = QS.FactorDB.HDF5DB(sys_args={"主目录": r"D:\HST\Research\QSDemo\Data\HDF5"})
    FT = FDB["stock_cn_day_bar_nafilled"]
    
    # Dlg = ArgSetupDlg(FDB.Args)
    Dlg = ArgSetupDlg(FT.Args)
    print("===")
# -*- coding: utf-8 -*-
"""ID设置"""
import datetime as dt

import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__
from QSExt.GUI.Notebook.DateTimeSetupDlg import mergeSet
from QSExt.GUI.Notebook.utils import exitDlg

class IDSetupDlg(__QS_Object__):
    # id_fun: {名称: 函数}, 函数: f(date, is_current)
    def __init__(self, ids=[], modal=False, id_fun={}, fts=[], sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self._Modal, self._Showed = modal, False
        self.OldIDs = ids
        self.IDFun = id_fun
        if isinstance(fts, dict):
            self.FTs = fts
        else:
            self.FTs = {iFT.Name: iFT for iFT in fts}
        self.Frame, self.Widgets = self.createWidgets(self.OldIDs)
    
    def showModalDlg(self, parent=None, output_widget=None, ok_callback=None, cancel_callback=None):
        self._Showed = True
        iWidgets = self.Widgets
        if ok_callback:
            for iCallback in iWidgets["OkButton"]._click_handlers.callbacks[:]:
                iWidgets["OkButton"].on_click(iCallback, remove=True)
            iWidgets["OkButton"].on_click(ok_callback)
        iWidgets["OkButton"].on_click(lambda b: exitDlg(self, output_widget=output_widget, parent=parent))
        if cancel_callback:
            for iCallback in iWidgets["CancelButton"]._click_handlers.callbacks[:]:
                iWidgets["CancelButton"].on_click(iCallback, remove=True)
            iWidgets["CancelButton"].on_click(cancel_callback)
        iWidgets["CancelButton"].on_click(lambda b: exitDlg(self, output_widget=output_widget, parent=parent))
        if output_widget:
            with output_widget:
                output_widget.clear_output()
                display(self.Frame)
    
    def showMsg(self, msg, clear=True):
        if clear: self.Widgets["MainOutput"].clear_output()
        with self.Widgets["MainOutput"]:
            if isinstance(msg, str):
                print(msg)
            else:
                display(msg)
    
    def display(self, output=None):
        if output:
            with output:
                output.clear_output()
                display(self.Frame)
        else:
            clear_output()
            display(self.Frame)
    
    @property
    def value(self):
        return sorted(self.Widgets["IDList"].options)
    
    def on_value_change(self, handler):
        self._ValueChangeHandler = handler
        self.Widgets["IDList"].observe(self._on_value_change, names="options")
    
    def _on_value_change(self, change):
        change["owner"] = self
        change["old"] = sorted(change["old"])
        change["new"] = sorted(change["new"])
        return self._ValueChangeHandler(change)
    
    def createWidgets(self, ids):
        Widgets = {}
        
        Widgets["TargetDTCheckbox"] = widgets.Checkbox(value=False, indent=False)
        Widgets["TargetDTCheckbox"].observe(self.on_TargetDTCheckbox_changed, names="value")
        TargetDT = dt.datetime.combine(dt.date.today(), dt.time(0))
        Widgets["TargetDatetimePicker"] = widgets.NaiveDatetimePicker(indent=False, description="目标时点", value=TargetDT, disabled=True)
        Widgets["TargetFactorDropdown"] = widgets.Dropdown(indent=False, description="目标因子", options=[], layout={"visibility": ("hidden" if self.IDFun else "visible")})
        Widgets["HistoryCheckbox"] = widgets.Checkbox(value=True, indent=True, description="历史ID", layout={"visibility": ("visible" if self.IDFun else "hidden")})
        IDTypes = list(self.IDFun) + (["来自因子表"] if self.FTs else [])
        Widgets["IDTypeDropdown"] = widgets.Dropdown(description="ID类型", options=IDTypes)
        Widgets["IDTypeDropdown"].observe(self.on_IDTypeDropdown_changed, names="value")
        Widgets["FTDropdown"] = widgets.Dropdown(indent=False, description="因子表", options=sorted(self.FTs), layout={"visibility": ("visible" if self.FTs and (not self.IDFun) else "hidden")})
        Widgets["FTDropdown"].observe(self.on_FTDropdown_changed, names="value")        
        Widgets["MergeDropdown"] = widgets.Dropdown(description="合并类型", options=("覆盖", "并集", "交集", "左差右", "右差左", "对称差"))
        Widgets["SelectButton"] = widgets.Button(description=">>", disabled=(not IDTypes))
        Widgets["SelectButton"].on_click(self.on_SelectButton_clicked)
        Widgets["DeleteButton"] = widgets.Button(description="删除")
        Widgets["DeleteButton"].on_click(self.on_DeleteButton_clicked)
        Widgets["RestoreButton"] = widgets.Button(description="复原")
        Widgets["RestoreButton"].on_click(self.on_RestoreButton_clicked)
        Widgets["OkButton"] = widgets.Button(description="确定")
        Widgets["CancelButton"] = widgets.Button(description="取消")
        Widgets["IDList"] = widgets.SelectMultiple(options=ids, rows=10, layout={"width": "100px"})
        
        Frame = widgets.HBox(children=[
            widgets.VBox(children=[
                widgets.HBox(children=[Widgets["TargetDatetimePicker"], Widgets["TargetDTCheckbox"]]),
                widgets.HBox(children=[Widgets["FTDropdown"], Widgets["TargetFactorDropdown"]]),
                widgets.HBox(children=[Widgets["IDTypeDropdown"], Widgets["HistoryCheckbox"]]),
                widgets.HBox(children=[Widgets["MergeDropdown"], Widgets["SelectButton"]]),
                widgets.HBox(children=([Widgets["DeleteButton"], Widgets["RestoreButton"], Widgets["CancelButton"], Widgets["OkButton"]] if self._Modal else [Widgets["DeleteButton"], Widgets["RestoreButton"]]))
            ], layout={"width": "500px"}),
            Widgets["IDList"]
        ])
        
        return Frame, Widgets
    
    def on_TargetDTCheckbox_changed(self, change):
        self.Widgets["TargetDatetimePicker"].disabled = (not change["new"])
    
    def on_IDTypeDropdown_changed(self, change):
        if change["new"]=="来自因子表":
            self.Widgets["FTDropdown"].layout.visibility = "visible"
            self.Widgets["TargetFactorDropdown"].layout.visibility = "visible"
            self.Widgets["HistoryCheckbox"].layout.visibility = "hidden"
            FT = self.FTs[self.Widgets["FTDropdown"].value]
            self.Widgets["TargetFactorDropdown"].options = FT.FactorNames
        else:
            self.Widgets["FTDropdown"].layout.visibility = "hidden"
            self.Widgets["TargetFactorDropdown"].layout.visibility = "hidden"
            self.Widgets["HistoryCheckbox"].layout.visibility = "visible"
    
    def on_FTDropdown_changed(self, change):
        FT = self.FTs[change["new"]]
        self.Widgets["TargetFactorDropdown"].options = FT.FactorNames
        
    def on_SelectButton_clicked(self, b):
        iWidgets = self.Widgets
        IDType = iWidgets["IDTypeDropdown"].value
        if iWidgets["TargetDTCheckbox"].value:
            TargetDT = iWidgets["TargetDatetimePicker"].value
        else:
            TargetDT = None
        if IDType=="来自因子表":
            TargetFactor = iWidgets["TargetFactorDropdown"].value
            FT = self.FTs[iWidgets["FTDropdown"].value]
            IDs = FT.getID(ifactor_name=TargetFactor, idt=TargetDT)
        else:
            isCurrent = (not iWidgets["HistoryCheckbox"].value)
            IDs = self.IDFun[IDType](date=TargetDT, is_current=isCurrent)
        IDs = mergeSet(set(IDs), set(self.value), merge_type=iWidgets["MergeDropdown"].value)
        iWidgets["IDList"].options = sorted(IDs)
        iWidgets["IDList"].value = []
        
    def on_DeleteButton_clicked(self, b):
        iWidgets = self.Widgets
        iWidgets["IDList"].options = sorted(set(iWidgets["IDList"].options).difference(iWidgets["IDList"].value))
        iWidgets["IDList"].value = []
        
    def on_RestoreButton_clicked(self, b):
        iWidgets = self.Widgets
        iWidgets["IDList"].options = self.OldIDs
        iWidgets["IDList"].value = []


if __name__=="__main__":
    pass
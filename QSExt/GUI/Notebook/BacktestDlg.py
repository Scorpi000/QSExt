# -*- coding: utf-8 -*-
"""回测模型"""
import inspect
import datetime as dt

import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__
from QuantStudio.BackTest.BackTestModel import BaseModule, BackTestModel
import QuantStudio.BackTest.api as BacktestAPI
from QSExt.GUI.Notebook.ArgSetupDlg import ArgSetupDlg

class BacktestDlg(__QS_Object__):
    def __init__(self, model=None, fts=[], sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        if isinstance(fts, dict):
            self.FTs = fts
        else:
            self.FTs = {iFT.Name: iFT for iFT in fts}
        self._kwargs = kwargs
        if model:
            self.BacktestModel = model
        else:
            self.BacktestModel = BackTestModel()
        self.BacktestModules = {}
        for iModuleTypeName in dir(BacktestAPI):
            iModuleType = getattr(BacktestAPI, iModuleTypeName)
            if (not iModuleTypeName.startswith("_")) and inspect.ismodule(iModuleType):
                iModuleTypeKey = (iModuleType.__doc__ if iModuleType.__doc__ else iModuleTypeName)
                self.BacktestModules[iModuleTypeKey] = self.BacktestModules.get(iModuleTypeKey, {})
                for ijBacktestModuleName in dir(iModuleType):
                    ijBacktestModule = getattr(iModuleType, ijBacktestModuleName)
                    if (not ijBacktestModuleName.startswith("_")) and issubclass(ijBacktestModule, BaseModule):
                        self.BacktestModules[iModuleTypeKey][ijBacktestModule.__doc__ if ijBacktestModule.__doc__ else ijBacktestModuleName] = ijBacktestModule
        
        self.Frame, self.Widgets = self.createWidgets()
        self.Output = {}
        
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
    
    def createWidgets(self):
        Widgets = {}
        
        NoFT = (not self.FTs)
        ModuleTypes = sorted(self.BacktestModules)
        FTNames = sorted(self.FTs)
        Widgets["ModuleTypeDropdown"] = widgets.Dropdown(options=ModuleTypes, value=ModuleTypes[0], description="回测类型", disabled=False)
        Widgets["ModuleDropdown"] = widgets.Dropdown(options=sorted(self.BacktestModules[ModuleTypes[0]]), description="回测模块", disabled=False)
        Widgets["FTDropdown"] = widgets.Dropdown(description="因子表", options=FTNames)
        Widgets["AddModuleButton"] = widgets.Button(description="添加模块", disabled=NoFT)
        Widgets["DeleteModuleButton"] = widgets.Button(description="删除模块")
        Widgets["ModuleTypeDropdown"].observe(self.on_ModuleTypeDropdown_change, names="value")
        Widgets["AddModuleButton"].on_click(self.on_AddModuleButton_clicked)
        Widgets["DeleteModuleButton"].on_click(self.on_DeleteModuleButton_clicked)
        
        EndDT = dt.datetime.combine(dt.date.today(), dt.time(0))
        Widgets["StartDatetimePicker"] = widgets.NaiveDatetimePicker(description="起始时点", value=EndDT-dt.timedelta(365), disabled=False)
        Widgets["EndDatetimePicker"] = widgets.NaiveDatetimePicker(description="结束时点", value=EndDT, disabled=False)
        Widgets["SubprocessNumInt"] = widgets.IntText(value=0, description="子进程数")
        Widgets["OutputTypeDropdown"] = widgets.Dropdown(options=("报告", "结果集"))
        Widgets["RunButton"] = widgets.Button(description="RUN")
        Widgets["RunButton"].on_click(self.on_RunButton_clicked)
        
        Widgets["ModuleTab"] = widgets.Tab()
        Widgets["ModuleList"] = []
        for iModule in self.BacktestModel.Modules: self.addModuleWidgets(iModule)
        Widgets["MainOutput"] = widgets.Output()       
        
        Frame = widgets.VBox(children=[
            widgets.HBox(children=[Widgets["StartDatetimePicker"], Widgets["EndDatetimePicker"], Widgets["OutputTypeDropdown"], Widgets["SubprocessNumInt"], Widgets["RunButton"]]),
            widgets.HBox(children=[Widgets["ModuleTypeDropdown"], Widgets["ModuleDropdown"], Widgets["FTDropdown"], Widgets["AddModuleButton"], Widgets["DeleteModuleButton"]]),
            Widgets["ModuleTab"],
            Widgets["MainOutput"]
        ])
        
        return Frame, Widgets
    
    def createModuleWidgets(self, module):
        iModuleWidgets = {
            "ModuleNameText": widgets.Text(description="名称", value=module.Name),
            "ArgOutput": widgets.Output(layout={"border": "1px solid black"}),
            "ArgDlg": ArgSetupDlg(module.Args, fts=self.FTs, **self._kwargs),
            "Output": widgets.Output()
        }
        iModuleWidgets["ModuleNameText"].observe(self.on_ModuleNameText_changed, names="value")
        return iModuleWidgets
        
    def addModuleWidgets(self, module):
        iWidgets = self.Widgets
        iModuleWidgets = self.createModuleWidgets(module)
        Titles = iWidgets["ModuleTab"].titles
        TabName = f"{len(Titles)}-{module.Name}"
        iWidgets["ModuleTab"].children = iWidgets["ModuleTab"].children + (widgets.VBox(children=[iModuleWidgets["ModuleNameText"], iModuleWidgets["ArgOutput"], iModuleWidgets["Output"]]),)
        iWidgets["ModuleTab"].titles = Titles + (TabName,)
        iWidgets["ModuleTab"].selected_index = len(Titles)
        iModuleWidgets["ArgDlg"].display(output=iModuleWidgets["ArgOutput"])
        iWidgets["ModuleList"].append(iModuleWidgets)
        return iModuleWidgets
    
    def on_ModuleTypeDropdown_change(self, change):
        self.Widgets["ModuleDropdown"].options = sorted(self.BacktestModules[change["new"]])
        
    def on_AddModuleButton_clicked(self, b):
        iWidgets = self.Widgets
        iModuleType, iModuleName = iWidgets["ModuleTypeDropdown"].value, iWidgets["ModuleDropdown"].value
        iFT = self.FTs[iWidgets["FTDropdown"].value]
        iModule = self.BacktestModules[iModuleType][iModuleName](factor_table=iFT)
        self.addModuleWidgets(iModule)
        self.BacktestModel.Modules.append(iModule)
        
    def on_DeleteModuleButton_clicked(self, b):
        iWidgets = self.Widgets
        TabIdx = iWidgets["ModuleTab"].selected_index
        Titles = iWidgets["ModuleTab"].titles
        iWidgets["ModuleTab"].children = iWidgets["ModuleTab"].children[:TabIdx] + iWidgets["ModuleTab"].children[TabIdx+1:]
        iWidgets["ModuleTab"].titles = Titles[:TabIdx] + Titles[TabIdx+1:]
        iWidgets["ModuleList"].pop(TabIdx)
        self.BacktestModel.Modules.pop(TabIdx)
    
    def on_ModuleNameText_changed(self, change):
        iWidgets = self.Widgets
        TabIdx = iWidgets["ModuleTab"].selected_index
        iModuleWidgets = iWidgets["ModuleList"][TabIdx]
        self.BacktestModel.Modules[TabIdx].Name = iModuleWidgets["ModuleNameText"].value
    
    def on_RunButton_clicked(self, b):
        self.BacktestModel.run()

if __name__=="__main__":
    Dlg = BacktestDlg(fdbs={})
    print("===")    
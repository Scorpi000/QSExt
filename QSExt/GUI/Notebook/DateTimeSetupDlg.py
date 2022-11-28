# -*- coding: utf-8 -*-
import datetime as dt

import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__

class DateTimeSetupDlg(__QS_Object__):
    def __init__(self, dts=[], trading_day_fun=None, fts=[], sys_args={}, config_file=None, **kwargs):
        self.OldDTs = dts
        self.NewDTs = dts.copy()
        self.TradingDayFun = trading_day_fun
        self.FTs = {iFT.Name: iFT for iFT in fts}
        self.Frame, self.Widgets = self.createWidgets(self.OldDTs)
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
    
    def createWidgets(self, dts):
        Widgets = {}
        
        EndDT = (dt.datetime.combine(dt.date.today(), dt.time(0)) if not dts else dts[-1])
        StartDT = (EndDT-dt.timedelta(365) if not dts else dts[0])
        Widgets["StartDatetimePicker"] = widgets.NaiveDatetimePicker(description="起始时点", value=StartDT, disabled=False)
        Widgets["EndDatetimePicker"] = widgets.NaiveDatetimePicker(description="结束时点", value=EndDT, disabled=False)
        Widgets["PeriodTypeDropdown"] = widgets.Dropdown(description="采样周期", options=["固定间隔", "周末日", "月末日", "季末日", "财报季末日", "年末日", "周初日", "月初日", "季初日", "财报季初日", "年初日", "月中日"])
        Widgets["PeriodTypeDropdown"].observe(self.on_PeriodTypeDropdown_changed, names="value")
        Widgets["PeriodInt"] = widgets.BoundedIntText(description="固定间隔", min=1, max=None, step=1, value=1, layout={"visibility": "visible"})
        DateTypes = ([] if self.TradingDayFun is None else ["交易日"]) + ["自然日"] + (["来自因子表"] if self.FTs else [])
        Widgets["DateTypeDropdown"] = widgets.Dropdown(description="时点类型", options=DateTypes)
        Widgets["DateTypeDropdown"].observe(self.on_DateTypeDropdown_changed, names="value")
        Widgets["FTDropdown"] = widgets.Dropdown(description="因子表", options=sorted(self.FTs), layout={"visibility": "hidden"})
        Widgets["MergeDropdown"] = widgets.Dropdown(description="合并类型", options=("并集", "交集", "左差右", "右差左"))
        Widgets["ChangeButton"] = widgets.Button(description="重采样")
        Widgets["SelectButton"] = widgets.Button(description=">>")
        Widgets["DeleteButton"] = widgets.Button(description="删除")
        Widgets["DeleteButton"].on_click(self.on_DeleteButton_clicked)
        Widgets["RestoreButton"] = widgets.Button(description="复原")
        Widgets["OkButton"] = widgets.Button(description="确定")
        Widgets["CancelButton"] = widgets.Button(description="取消")
        Widgets["DatetimeList"] = widgets.SelectMultiple(options=dts, rows=10, layout={"width": "150px"})
        
        Frame = widgets.HBox(children=[
            widgets.VBox(children=[
                widgets.HBox(children=[Widgets["StartDatetimePicker"], Widgets["EndDatetimePicker"]]),
                widgets.HBox(children=[Widgets["DateTypeDropdown"], Widgets["FTDropdown"]]),
                widgets.HBox(children=[Widgets["PeriodTypeDropdown"], Widgets["PeriodInt"], Widgets["ChangeButton"]]),
                widgets.HBox(children=[Widgets["MergeDropdown"], Widgets["SelectButton"]]),
                widgets.HBox(children=[Widgets["DeleteButton"], Widgets["RestoreButton"], Widgets["CancelButton"], Widgets["OkButton"]])
            ], layout={"width": "450px"}),
            Widgets["DatetimeList"]
        ])
        
        return Frame, Widgets
    
    def on_PeriodTypeDropdown_changed(self, change):
        if change["new"]=="固定间隔":
            self.Widgets["PeriodInt"].layout.visibility = "visible"
        else:
            self.Widgets["PeriodInt"].layout.visibility = "hidden"
    
    def on_DateTypeDropdown_changed(self, change):
        if change["new"]=="来自因子表":
            self.Widgets["FTDropdown"].layout.visibility = "visible"
        else:
            self.Widgets["FTDropdown"].layout.visibility = "hidden"
    
    def on_DeleteButton_clicked(self, b):
        iWidgets = self.Widgets
        iWidgets["DatetimeList"].options = sorted(set(iWidgets["DatetimeList"].options).difference(iWidgets["DatetimeList"].value))
        iWidgets["DatetimeList"].value = []
        
        
if __name__=="__main__":
    pass
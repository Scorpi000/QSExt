# -*- coding: utf-8 -*-
"""ID设置(TODO)"""
import datetime as dt

import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__
from QSExt.GUI.Notebook.DateTimeSetupDlg import mergeSet

class IDSetupDlg(__QS_Object__):
    def __init__(self, ids=[], id_fun={}, fts=[], sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self.OldIDs = ids
        self.IDFun = id_fun
        if isinstance(fts, dict):
            self.FTs = fts
        else:
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
    
    @property
    def value(self):
        return sorted(self.Widgets["DatetimeList"].options)
    
    def on_value_change(self, handler):
        self._ValueChangeHandler = handler
        self.Widgets["DatetimeList"].observe(self._on_value_change, names="options")
    
    def _on_value_change(self, change):
        change["owner"] = self
        change["old"] = sorted(change["old"])
        change["new"] = sorted(change["new"])
        return self._ValueChangeHandler(change)
    
    def createWidgets(self, dts):
        Widgets = {}
        
        EndDT = (dt.datetime.combine(dt.date.today(), dt.time(0)) if not dts else dts[-1])
        StartDT = (EndDT-dt.timedelta(365) if not dts else dts[0])
        Widgets["StartDatetimePicker"] = widgets.NaiveDatetimePicker(description="起始时点", value=StartDT, disabled=False)
        Widgets["EndDatetimePicker"] = widgets.NaiveDatetimePicker(description="结束时点", value=EndDT, disabled=False)
        Widgets["PeriodTypeDropdown"] = widgets.Dropdown(description="采样周期", options=["固定间隔", "周末日", "月末日", "季末日", "财报季末日", "年末日", "周初日", "月初日", "季初日", "财报季初日", "年初日", "月中日"])
        Widgets["PeriodTypeDropdown"].observe(self.on_PeriodTypeDropdown_changed, names="value")
        #Widgets["MiddleDayInt"] = widgets.BoundedIntText(description="月中分界日", min=1, max=31, step=1, value=15, layout={"display": "none"})
        Widgets["PeriodInt"] = widgets.BoundedIntText(description="固定间隔", min=1, max=None, step=1, value=1)
        DateTypes = (["来自因子表"] if self.FTs else []) + ([] if self.TradingDayFun is None else ["交易日"]) + ["自然日"]
        Widgets["DateTypeDropdown"] = widgets.Dropdown(description="时点类型", options=DateTypes)
        Widgets["DateTypeDropdown"].observe(self.on_DateTypeDropdown_changed, names="value")
        Widgets["FTDropdown"] = widgets.Dropdown(description="因子表", options=sorted(self.FTs), layout={"visibility": ("visible" if self.FTs else "hidden")})
        Widgets["MergeDropdown"] = widgets.Dropdown(description="合并类型", options=("覆盖", "并集", "交集", "左差右", "右差左", "对称差"))
        Widgets["ChangeButton"] = widgets.Button(description="重采样")
        Widgets["SelectButton"] = widgets.Button(description=">>")
        Widgets["SelectButton"].on_click(self.on_SelectButton_clicked)
        Widgets["DeleteButton"] = widgets.Button(description="删除")
        Widgets["DeleteButton"].on_click(self.on_DeleteButton_clicked)
        Widgets["RestoreButton"] = widgets.Button(description="复原")
        Widgets["RestoreButton"].on_click(self.on_RestoreButton_clicked)
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
            self.Widgets["PeriodInt"].description = "固定间隔"
            self.Widgets["PeriodInt"].min = 1
            self.Widgets["PeriodInt"].max = 9999
            self.Widgets["PeriodInt"].value = 1
            self.Widgets["PeriodInt"].disabled = False
        elif change["new"]=="月中日":
            self.Widgets["PeriodInt"].description = "月中分界日"
            self.Widgets["PeriodInt"].min = 1
            self.Widgets["PeriodInt"].max = 31
            self.Widgets["PeriodInt"].value = 15
            self.Widgets["PeriodInt"].disabled = False
        else:
            self.Widgets["PeriodInt"].disabled = True
    
    def on_DateTypeDropdown_changed(self, change):
        if change["new"]=="来自因子表":
            self.Widgets["FTDropdown"].layout.visibility = "visible"
        else:
            self.Widgets["FTDropdown"].layout.visibility = "hidden"
    
    def resampleDTs(self, dts, period_type, **kwargs):
        if period_type=="月末日": return DTTools.getMonthLastDateTime(dts)
        elif period_type=="周末日": return DTTools.getWeekLastDateTime(dts)
        elif period_type=="年末日": return DTTools.getYearLastDateTime(dts)
        elif period_type=="季末日": return DTTools.getQuarterLastDateTime(dts)
        elif period_type=="月初日": return DTTools.getMonthFirstDateTime(dts)
        elif period_type=="周初日": return DTTools.getWeekFirstDateTime(dts)
        elif period_type=="年初日": return DTTools.getYearFirstDateTime(dts)
        elif period_type=="季初日": return DTTools.getQuarterFirstDateTime(dts)
        elif period_type=="财报季初日": return DTTools.getFinancialQuarterFirstDateTime(dts)
        elif period_type=="财报季末日": return DTTools.getFinancialQuarterLastDateTime(dts)
        elif period_type=="月中日": return DTTools.getMonthMiddleDateTime(dts, middle_day=kwargs.get("period", 15))
        elif period_type=="固定间隔": return [dts[i] for i in range(0, len(dts), kwargs["period"])]
        return dts
    
    def on_SelectButton_clicked(self, b):
        iWidgets = self.Widgets
        StartDT, EndDT = iWidgets["StartDatetimePicker"].value, iWidgets["EndDatetimePicker"].value
        if iWidgets["DateTypeDropdown"].value=="自然日":
            DTs = DTTools.getDateTimeSeries(StartDT, EndDT)
        elif iWidgets["DateTypeDropdown"].value=="交易日":
            DTs = self.TradingDayFun(StartDT, EndDT)
        elif iWidgets["DateTypeDropdown"].value=="来自因子表":
            FT = self.FTs[iWidgets["FTDropdown"].value]
            DTs = FT.getDateTime(start_dt=StartDT, end_dt=EndDT)
        DTs = self.resampleDTs(DTs, iWidgets["PeriodTypeDropdown"].value, period=iWidgets["PeriodInt"].value)
        DTs = mergeSet(set(DTs), set(self.value), merge_type=iWidgets["MergeDropdown"].value)
        iWidgets["DatetimeList"].options = sorted(DTs)
        iWidgets["DatetimeList"].value = []        
        
    def on_DeleteButton_clicked(self, b):
        iWidgets = self.Widgets
        iWidgets["DatetimeList"].options = sorted(set(iWidgets["DatetimeList"].options).difference(iWidgets["DatetimeList"].value))
        iWidgets["DatetimeList"].value = []
        
    def on_RestoreButton_clicked(self, b):
        iWidgets = self.Widgets
        iWidgets["DatetimeList"].options = self.OldDTs
        iWidgets["DatetimeList"].value = []


if __name__=="__main__":
    pass
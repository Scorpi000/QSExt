# -*- coding: utf-8 -*-
"""因子库管理"""
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

# 因子库管理，基于 ipywidgets 的实现
class FactorDBDlg(__QS_Object__):
    def __init__(self, fdbs, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self.FDBs = fdbs
        self.FDBAttrs = {iFDBName: {"ReadOnly": not isinstance(iFDB, WritableFactorDB)} for iFDBName, iFDB in fdbs.items()}
        self.EndDT = dt.datetime.combine(dt.date.today(), dt.time(0))
        self._TmpDir = tempfile.TemporaryDirectory()
        
        iFDBName = list(fdbs.keys())[0]
        iFDB = fdbs[iFDBName].connect()
        iTableNames = iFDB.TableNames
        if not iTableNames:
            iFactorNames = []
        else:
            iFactorNames = iFDB.getTable(iTableNames[0]).FactorNames
        self.Widgets = {
            "FDBList": widgets.Dropdown(options=list(fdbs.keys()), value=iFDBName, description="", disabled=False),
            "TableList": widgets.Select(options=iTableNames, value=(None if not iTableNames else iTableNames[0]), rows=20, description="", disabled=False),
            "FactorList": widgets.SelectMultiple(options=iFactorNames, value=[], rows=20, description="", disabled=False),
            "Delete": widgets.Button(description="删除", disabled=self.FDBAttrs[iFDBName].get("ReadOnly", True)),
            "Rename": widgets.Button(description="重命名", disabled=self.FDBAttrs[iFDBName].get("ReadOnly", True)),
            "Preview": widgets.Button(description="预览"),
            "Upload": widgets.FileUpload(accept=".csv", multiple=False),
            "Update": widgets.Button(description="刷新"),
            "Download": widgets.Button(description="下载"),
            "StartDT": widgets.DatePicker(description="起始日期", disabled=False, value=(self.EndDT - dt.timedelta(31)).date()),
            "EndDT": widgets.DatePicker(description="截止日期", disabled=False, value=self.EndDT.date()),
            "IDNum": widgets.IntText(description="证券数量", disabled=False, value=10),
            "TargetTable": widgets.Combobox(placeholder="请输入目标表", options=iTableNames, description="上传目标表", ensure_option=True, disabled=False, value=genAvailableName("NewTable", iTableNames)),
            "TargetFactor": widgets.Combobox(placeholder="请输入目标因子", options=[], description="上传目标因子", ensure_option=True, disabled=False, value="NewFactor"),
            "Output": widgets.Output(layout={"overflow_x": "scroll"}),
            "FDBOutput": widgets.Output(),
            "ControlOutput": widgets.Output(),
        }
        
        self.Widgets["Frame"] = widgets.HBox(children=[self.Widgets["FDBOutput"], widgets.VBox(children=[self.Widgets["ControlOutput"], self.Widgets["Output"]])])
        self.Widgets["FDBFrame"] = widgets.VBox(children=[
            widgets.Label(value="因子库"),
            self.Widgets["FDBList"],
            widgets.Label(value="因子表"),
            self.Widgets["TableList"],
            widgets.Label(value="因子"),
            self.Widgets["FactorList"]
        ])
        self.Widgets["ControlFrame"] = widgets.VBox(children=[
            widgets.HBox(children=[self.Widgets["Preview"], self.Widgets["StartDT"], self.Widgets["EndDT"], self.Widgets["IDNum"]]),
            widgets.HBox(children=[self.Widgets["Upload"], self.Widgets["TargetTable"], self.Widgets["TargetFactor"]]),
            widgets.HBox(children=[self.Widgets["Download"], self.Widgets["Delete"], self.Widgets["Rename"], self.Widgets["Update"]])
        ])
        
        self.Widgets["QuestionDlg"] = createQuestionDlg(question="你真的确定这么干吗？")
        self.Widgets["GetTextDlg"] = createGetTextDlg(desc="请输入")
        
        with self.Widgets["FDBOutput"]:
            display(self.Widgets["FDBFrame"])
        with self.Widgets["ControlOutput"]:
            display(self.Widgets["ControlFrame"])
        self.Widgets["Update"].on_click(self.update)
        self.Widgets["Preview"].on_click(self.preview)
        self.Widgets["Download"].on_click(self.download)
        self.Widgets["Delete"].on_click(self.deleteTableFactor)
        self.Widgets["Rename"].on_click(self.rename)
        self.Widgets["Upload"].observe(self.upload, names="_counter")
        self.Widgets["FDBList"].observe(self.selectFDB, names="value")
        self.Widgets["TableList"].observe(self.selectTable, names="value")
        self.Widgets["Update"].click()
    def frame(self):
        return self.Widgets["Frame"]
    def selectFDB(self, change):
        iWidgets = self.Widgets
        iFDBName = change["new"]
        iFDB = self.FDBs[iFDBName]
        iFDB.connect()
        iTableNames = iFDB.TableNames
        iFactorNames = iFDB.getTable(iTableNames[0]).FactorNames
        iWidgets["TableList"].options = iTableNames
        iWidgets["TableList"].value = iTableNames[0]
        iWidgets["FactorList"].options = iFactorNames
        iWidgets["FactorList"].value = []
        iWidgets["TargetTable"].options = iTableNames
        iWidgets["TargetTable"].value = genAvailableName("NewTable", iTableNames)
        iWidgets["TargetFactor"].options = []
        iWidgets["TargetFactor"].value = "NewFactor"
        
        iReadOnly = self.FDBAttrs[iFDBName].get("ReadOnly", True) or (not isinstance(iFDB, WritableFactorDB))
        iWidgets["Delete"].disabled = iReadOnly
        iWidgets["Rename"].disabled = iReadOnly
        iWidgets["Upload"].disabled = iReadOnly
        iWidgets["TargetTable"].disabled = iReadOnly
        iWidgets["TargetFactor"].disabled = iReadOnly
        
    def selectTable(self, change):
        iWidgets = self.Widgets
        FDB = self.FDBs[iWidgets["FDBList"].value]
        iTableName = change["new"]
        iWidgets["FactorList"].options = FDB.getTable(iTableName).FactorNames
        iWidgets["FactorList"].value = []
    
    def getSelectedTableFactor(self):
        iWidgets = self.Widgets
        TableFactor = {}
        for iTableName in [iWidgets["TableList"].value]:
            TableFactor[iTableName] = list(iWidgets["FactorList"].value)
        return TableFactor
    
    def readData(self, id_num=0, start_dt=None, end_dt=None):
        iWidgets = self.Widgets
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        TableFactor = self.getSelectedTableFactor()
        if (len(TableFactor)==0): return None
        
        if (len(TableFactor)==1) and (len(TableFactor[list(TableFactor.keys())[0]])==1):# 只选择了一个因子
            iTableName = list(TableFactor.keys())[0]
            iFactorName = TableFactor[iTableName][0]
            iFT = FDB.getTable(iTableName)
            iDTs = iFT.getDateTime(ifactor_name=iFactorName, start_dt=start_dt, end_dt=end_dt)
            iIDs = iFT.getID(ifactor_name=iFactorName)
            if id_num>0: iIDs = iIDs[:id_num]
            elif id_num<0: iIDs = iIDs[id_num:]
            Data = iFT.readData(factor_names=[iFactorName], dts=iDTs, ids=iIDs).iloc[0]
        else:
            Data = None
            for iTableName, iFactorNames in TableFactor.items():
                iFT = FDB.getTable(iTableName)
                iDTs = iFT.getDateTime(start_dt=start_dt, end_dt=end_dt)
                iIDs = iFT.getID()
                if not iFactorNames: iFactorNames = iFT.FactorNames
                iData = iFT.readData(factor_names=iFactorNames, dts=iDTs, ids=iIDs).to_frame()
                iData.index = iData.index.set_names(["datetime","code"])
                if Data is None: Data = iData
                else: Data = pd.merge(Data, iData, how="inner", left_index=True, right_index=True)
            if id_num>0:
                Data = Data.groupby(axis=0, level=0).apply(lambda df: df.reset_index(level=0).iloc[:id_num, 1:])
            elif id_num<0:
                Data = Data.groupby(axis=0, level=0).apply(lambda df: df.reset_index(level=0).iloc[id_num:, 1:])
        return Data
    
    def update(self, b):
        iWidgets = self.Widgets
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        
        iTableNames = FDB.TableNames
        iWidgets["TableList"].options = iTableNames
        if iTableNames:
            iWidgets["TableList"].value = iTableNames[0]
            iFactorNames = FDB.getTable(iTableNames[0]).FactorNames
            iWidgets["FactorList"].options = iFactorNames
            iWidgets["FactorList"].value = []
    
    def preview(self, b):
        iWidgets = self.Widgets
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            print("数据加载中...")
        
        iStartDT = dt.datetime.combine(iWidgets["StartDT"].value, dt.time(0))
        iEndDT = dt.datetime.combine(iWidgets["EndDT"].value, dt.time(0))
        iIDNum = iWidgets["IDNum"].value    
        Data = self.readData(iIDNum, iStartDT, iEndDT)    
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            if Data is None:
                print("请选择要预览的因子!")
            else:
                pd.set_option("display.max_rows", None)
                pd.set_option("display.max_columns", None)
                display(Data)
                pd.reset_option("display.max_rows")
                pd.reset_option("display.max_columns")
    
    def download(self, b):
        iWidgets = self.Widgets
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            print("数据加载中...")
        
        iStartDT = dt.datetime.combine(iWidgets["StartDT"].value, dt.time(0))
        iEndDT = dt.datetime.combine(iWidgets["EndDT"].value, dt.time(0))
        iIDNum = iWidgets["IDNum"].value
        Data = self.readData(iIDNum, iStartDT, iEndDT)
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            display(HTML(createDataFrameDownload(Data, name="FactorDataDownload")))
    
    def upload(self, f):
        iWidgets = self.Widgets
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        iTargetTable = iWidgets["TargetTable"].value
        iFactorName = iWidgets["TargetFactor"].value
        iContent = iWidgets["Upload"].value
        if not iContent: return
        iContent = list(iContent.values())[0]["content"]
        
        iTmpFilePath = self._TmpDir.name+os.sep+genAvailableName("FactorData", listDirFile(self._TmpDir.name, "csv"))+".csv"
        with open(iTmpFilePath, "wb") as File:
            File.write(iContent)
        iFactorData = loadCSVFactorData(iTmpFilePath)
        OldTableNames = FDB.TableNames
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            try:
                FDB.writeData(pd.Panel({iFactorName:iFactorData}), iTargetTable, if_exists="replace")
            except:
                print("上传失败, 请检查数据格式!")
                return
            else:
                print("上传成功!")
        if iTargetTable not in OldTableNames:
            iWidgets["TableList"].options = FDB.TableNames
            iWidgets["TableList"].value = iTargetTable
    
    def deleteTableFactor(self, b):
        iWidgets = self.Widgets
        if not iWidgets["QuestionDlg"]["Showed"]:
            return showQuestionDlg(iWidgets["QuestionDlg"], parent=iWidgets["ControlFrame"], output_widget=iWidgets["ControlOutput"], ok_callback=self.deleteTableFactor)
        TableFactor = self.getSelectedTableFactor()
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        for iTable in TableFactor:
            try:
                if not TableFactor[iTable]:
                    FDB.deleteTable(iTable)
                else:
                    FDB.deleteFactor(iTable, TableFactor[iTable])
            except Exception as e:
                with iWidgets["Output"]:
                    iWidgets["Output"].clear_output()
                    print(f"错误: {str(e)}")
        return iWidgets["Update"].click()
    
    def renameTable(self, itable):
        iWidgets = self.Widgets
        if not iWidgets["GetTextDlg"]["Showed"]:
            return showGetTextDlg(iWidgets["GetTextDlg"], parent=iWidgets["ControlFrame"], output_widget=iWidgets["ControlOutput"], ok_callback=lambda b: self.renameTable(itable), desc="请输入新表名: ", default_value=itable)
        NewTableName = iWidgets["GetTextDlg"]["Text"].value
        if NewTableName==itable: return
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        if NewTableName in FDB.TableNames:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: 当前库中包含重名表 {NewTableName} !")
            return
        try:
            FDB.renameTable(itable, NewTableName)
        except Exception as e:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: {str(e)}")
        return iWidgets["Update"].click()
    
    def renameFactor(self, itable, ifactor):
        iWidgets = self.Widgets
        if not iWidgets["GetTextDlg"]["Showed"]:
            return showGetTextDlg(iWidgets["GetTextDlg"], parent=iWidgets["ControlFrame"], output_widget=iWidgets["ControlOutput"], ok_callback=lambda b: self.renameFactor(itable, ifactor), desc="请输入新因子名: ", default_value=ifactor)
        NewFactorName = iWidgets["GetTextDlg"]["Text"].value
        if NewFactorName==ifactor: return
        FDB = self.FDBs[iWidgets["FDBList"].value]
        FDB.connect()
        if NewFactorName in FDB.getTable(itable).FactorNames:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: 表 {itable} 中包含重名因子 {NewFactorName} !")
            return
        try:
            FDB.renameFactor(itable, ifactor, NewFactorName)
        except Exception as e:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: {str(e)}")
        return iWidgets["Update"].click()
    
    def rename(self, b):
        iWidgets = self.Widgets
        iWidgets["Output"].clear_output()
        TableFactor = self.getSelectedTableFactor()
        if len(TableFactor)!=1:
            with iWidgets["Output"]:
                print("请选择一张表或一个因子!")
            return
        iTable = list(TableFactor.keys())[0]
        if not TableFactor[iTable]:# 用户选择了一张表
            return self.renameTable(iTable)
        elif len(TableFactor[iTable])!=1:
            with iWidgets["Output"]:
                print("请选择一个因子!")
            return
        else:# 用户选择了一个因子
            return self.renameFactor(iTable, TableFactor[iTable][0])
# -*- coding: utf-8 -*-
"""因子库管理"""
import os
import tempfile
import datetime as dt

import pandas as pd
import ipywidgets as widgets
from IPython.display import display, HTML, clear_output

from QuantStudio import __QS_Object__
from QuantStudio.RiskDataBase.RiskDB import FactorRDB
from QuantStudio.Tools.AuxiliaryFun import genAvailableName
from QuantStudio.Tools.FileFun import listDirFile, loadCSVFactorData
from QuantStudio.RiskModel.RiskModelFun import dropRiskMatrixNA
from QSExt.GUI.ipywidgets.utils import createQuestionDlg, showQuestionDlg, createGetTextDlg, showGetTextDlg, createDataFrameDownload

# 风险库管理，基于 ipywidgets 的实现
class RiskDBDlg(__QS_Object__):
    def __init__(self, rdbs, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self.RDBs = rdbs
        self._TmpDir = tempfile.TemporaryDirectory()
        
        RDBNames = list(rdbs.keys())
        iRDB = rdbs[RDBNames[0]].connect()
        iTableNames = iRDB.TableNames
        if not iTableNames:
            iDTs = []
            iFactorNames = []
        else:
            iDTs = [iDT.strftime("%Y-%m-%d %H:%M:%S") for iDT in iRDB.getTable(iTableNames[0]).getDateTime()]
            iFactorNames = (iRDB.getTable(iTableNames[0]).FactorNames if isinstance(iRDB, FactorRDB) else [])
        self.Widgets = {
            "RDBList": widgets.Dropdown(options=RDBNames, value=RDBNames[0], description="", disabled=False, layout={"width": "130px"}),
            "TableList": widgets.Select(options=iTableNames, value=(None if not iTableNames else iTableNames[0]), rows=5, description="", disabled=False, layout={"width": "130px"}),
            "DTList": widgets.SelectMultiple(options=iDTs, value=[], rows=20, description="", disabled=False, layout={"width": "130px"}),
            "FactorLabel": widgets.Label("因子", layout={"visibility": "visible" if isinstance(iRDB, FactorRDB) else "hidden"}),
            "FactorList": widgets.SelectMultiple(options=iFactorNames, value=[], rows=20, description="", disabled=False, layout={"width": "100px", "visibility": "visible" if isinstance(iRDB, FactorRDB) else "hidden"}),
            "Delete": widgets.Button(description="删除"),
            "Rename": widgets.Button(description="重命名"),
            "Preview": widgets.Button(description="预览"),
            "Upload": widgets.FileUpload(accept=".csv", multiple=False),
            "Update": widgets.Button(description="刷新"),
            "Download": widgets.Button(description="下载"),
            "DataTypeList": widgets.Dropdown(description="数据类型", disabled=False, options=("协方差阵", "相关系数阵")+(("因子协方差阵","因子暴露","特异性风险","因子收益","特异性收益") if isinstance(iRDB, FactorRDB) else tuple())),
            "DropNaCheckBox": widgets.Checkbox(value=True, description="删除缺失", indent=False),
            "IDNum": widgets.IntText(description="证券数量", disabled=False, value=10, layout={"width": "130px"}),
            "TargetTable": widgets.Combobox(placeholder="请输入目标表", options=iTableNames, description="上传目标表", ensure_option=True, disabled=False, value=genAvailableName("NewTable", iTableNames)),
            "TargetDT": widgets.DatePicker(description="目标日期", disabled=False, value=dt.date.today()),
            "Output": widgets.Output(layout={"width": "800px", "overflow_x": "scroll"}),
            "RDBOutput": widgets.Output(),
            "ControlOutput": widgets.Output(),

        }
        
        self.Frame = widgets.HBox(children=[
            self.Widgets["RDBOutput"], 
            widgets.VBox(children=[
                self.Widgets["ControlOutput"], 
                widgets.HBox(children=[
                    widgets.VBox(children=[self.Widgets["FactorLabel"], self.Widgets["FactorList"]]), 
                    self.Widgets["Output"]])
            ])
        ])
        self.Widgets["RDBFrame"] = widgets.VBox(children=[
            widgets.Label(value="风险库"),
            self.Widgets["RDBList"],
            widgets.Label(value="风险表"),
            self.Widgets["TableList"],
            widgets.Label(value="时点"),
            self.Widgets["DTList"]
        ])
        self.Widgets["ControlFrame"] = widgets.VBox(children=[
            widgets.HBox(children=[self.Widgets["Preview"], self.Widgets["DataTypeList"], self.Widgets["IDNum"], self.Widgets["DropNaCheckBox"]], layout={"width": "800px", "display": "flex", "flex": "0 1 auto"}),
            widgets.HBox(children=[self.Widgets["Upload"], self.Widgets["TargetTable"]], layout={"width": "800px", "display": "flex", "flex": "0 1 auto"}),
            widgets.HBox(children=[self.Widgets["Download"], self.Widgets["Delete"], self.Widgets["Rename"], self.Widgets["Update"]], layout={"width": "800px", "display": "flex", "flex": "0 1 auto"}),
        ], layout={"width": "800px"})
        
        self.Widgets["QuestionDlg"] = createQuestionDlg(question="你真的确定这么干吗？")
        self.Widgets["GetTextDlg"] = createGetTextDlg(desc="请输入")
        
        with self.Widgets["RDBOutput"]:
            display(self.Widgets["RDBFrame"])
        with self.Widgets["ControlOutput"]:
            display(self.Widgets["ControlFrame"])
        self.Widgets["Update"].on_click(self.update)
        self.Widgets["Preview"].on_click(self.preview)
        self.Widgets["Download"].on_click(self.download)
        self.Widgets["Delete"].on_click(self.deleteTableDT)
        self.Widgets["Rename"].on_click(self.rename)
        self.Widgets["Upload"].observe(self.upload, names="_counter")
        self.Widgets["RDBList"].observe(self.selectRDB, names="value")
        self.Widgets["TableList"].observe(self.selectTable, names="value")
        self.Widgets["Update"].click()
    
    def display(self, output=None):
        if output:
            with output:
                output.clear_output()
                display(self.Frame)
        else:
            clear_output()
            display(self.Frame)
    
    def selectRDB(self, change):
        iWidgets = self.Widgets
        iRDBName = change["new"]
        iRDB = self.RDBs[iRDBName]
        iRDB.connect()
        iTableNames = iRDB.TableNames
        iWidgets["TableList"].options = iTableNames
        iWidgets["TableList"].value = (None if not iTableNames else iTableNames[0])
        iWidgets["TargetTable"].options = iTableNames
        iWidgets["TargetTable"].value = genAvailableName("NewTable", iTableNames)
        
    def selectTable(self, change):
        iWidgets = self.Widgets
        RDB = self.RDBs[iWidgets["RDBList"].value]
        iTableName = change["new"]
        if not iTableName:
            iDTs = []
            iFactorNames = []
        else:
            iDTs = [iDT.strftime("%Y-%m-%d %H:%M:%S") for iDT in RDB.getTable(iTableName).getDateTime()]
            iFactorNames = (RDB.getTable(iTableName).FactorNames if isinstance(RDB, FactorRDB) else [])
        iWidgets["DTList"].options = iDTs
        iWidgets["DTList"].value = []
        if isinstance(RDB, FactorRDB):
            iWidgets["FactorList"].options = iFactorNames
            iWidgets["FactorList"].value = []
            iWidgets["FactorList"].layout.visibility = "visible"
            iWidgets["FactorLabel"].layout.visibility = "visible"
            iWidgets["DataTypeList"].options = ("协方差阵","相关系数阵","因子协方差阵","因子暴露","特异性风险","因子收益","特异性收益")
        else:
            iWidgets["FactorList"].layout.visibility = "hidden"
            iWidgets["FactorLabel"].layout.visibility = "hidden"
            iWidgets["DataTypeList"].options = ("协方差阵","相关系数阵")
    
    def readData(self):
        iWidgets = self.Widgets
        RDB = self.RDBs[iWidgets["RDBList"].value]
        RDB.connect()
        iTableName = iWidgets["TableList"].value
        iDTs = [dt.datetime.strptime(iDT, "%Y-%m-%d %H:%M:%S") for iDT in iWidgets["DTList"].value]
        if (not iTableName) or (not iDTs): return None
        iDataType = iWidgets["DataTypeList"].value
        iDropNa = iWidgets["DropNaCheckBox"].value
        iRT = RDB.getTable(iTableName)
        iIDs = iRT.getID()
        iIDNum = iWidgets["IDNum"].value
        if iIDNum>0: iIDs = iIDs[:iIDNum]
        elif iIDNum<0: iIDs = iIDs[iIDNum:]
        if iDataType=="协方差阵":
            Data = iRT.readCov(dts=iDTs, ids=iIDs)
            if Data.shape[0]==1: Data = (dropRiskMatrixNA(Data.iloc[0]) if iDropNa else Data.iloc[0])
            else: Data = Data.to_frame(filter_observations=iDropNa)
        elif iDataType=="相关系数阵":
            Data = iRT.readCorr(dts=iDTs, ids=iIDs)
            if Data.shape[0]==1: Data = (dropRiskMatrixNA(Data.iloc[0]) if iDropNa else Data.iloc[0])
            else: Data = Data.to_frame(filter_observations=iDropNa)
        elif iDataType=="因子协方差阵":
            Data = iRT.readFactorCov(dts=iDTs)
            if Data.shape[0]==1: Data = (dropRiskMatrixNA(Data.iloc[0]) if iDropNa else Data.iloc[0])
            else: Data = Data.to_frame(filter_observations=iDropNa)
        elif iDataType=="因子暴露":
            Data = iRT.readFactorData(dts=iDTs, ids=iIDs).to_frame(filter_observations=iDropNa)
        elif iDataType=="特异性风险":
            Data = iRT.readSpecificRisk(dts=iDTs, ids=iIDs)
            if iDropNa: Data = Data.dropna(how="all")
        elif iDataType=="因子收益":
            Data = iRT.readFactorReturn(dts=iDTs)
            if iDropNa: Data = Data.dropna(how="all")
        elif iDataType=="特异性收益":
            Data = iRT.readSpecificReturn(dts=iDTs, ids=iIDs)
            if iDropNa: Data = Data.dropna(how="all")
        else:
            Data = None
        return Data
    
    def update(self, b):
        iWidgets = self.Widgets
        RDB = self.RDBs[iWidgets["RDBList"].value]
        RDB.connect()
        iTableNames = RDB.TableNames
        iWidgets["TableList"].options = iTableNames
        iWidgets["TableList"].value = (None if not iTableNames else iTableNames[0])
    
    def preview(self, b):
        iWidgets = self.Widgets
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            print("数据加载中...")
        
        Data = self.readData()
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            if Data is None:
                print("请选择要预览的表和时点!")
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
        Data = self.readData()
        with iWidgets["Output"]:
            iWidgets["Output"].clear_output()
            if Data is None:
                print("请选择要下载的表和时点!")
            else:
                display(HTML(createDataFrameDownload(Data, name="FactorDataDownload")))
    
    def upload(self, f):# TODO
        iWidgets = self.Widgets
        RDB = self.RDBs[iWidgets["FDBList"].value]
        RDB.connect()
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
    
    def deleteTableDT(self, b):
        iWidgets = self.Widgets
        if not iWidgets["QuestionDlg"]["Showed"]:
            return showQuestionDlg(iWidgets["QuestionDlg"], parent=iWidgets["ControlFrame"], output_widget=iWidgets["ControlOutput"], ok_callback=self.deleteTableFactor)
        RDB = self.RDBs[iWidgets["RDBList"].value]
        RDB.connect()
        iTableName = iWidgets["TableList"].value
        iDTs = iWidgets["DTList"].value
        try:
            RDB.deleteDateTime(table_name=iTableName, dts=iDTs)
        except Exception as e:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: {str(e)}")
        return iWidgets["Update"].click()
    
    def renameTable(self, itable):
        iWidgets = self.Widgets
        if not iWidgets["GetTextDlg"]["Showed"]:
            return showGetTextDlg(iWidgets["GetTextDlg"], parent=iWidgets["ControlFrame"], output_widget=iWidgets["ControlOutput"], ok_callback=lambda b: self.renameTable(itable), desc="请输入新表名: ", default_value=itable)
        NewTableName = iWidgets["GetTextDlg"]["MainWidget"].value
        if NewTableName==itable: return
        RDB = self.RDBs[iWidgets["RDBList"].value]
        RDB.connect()
        if NewTableName in RDB.TableNames:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: 当前库中包含重名表 {NewTableName} !")
            return
        try:
            RDB.renameTable(itable, NewTableName)
        except Exception as e:
            with iWidgets["Output"]:
                iWidgets["Output"].clear_output()
                print(f"错误: {str(e)}")
        return iWidgets["Update"].click()
    
    def rename(self, b):
        iWidgets = self.Widgets
        iWidgets["Output"].clear_output()
        iTableName = iWidgets["TableList"].value
        if not iTableName:
            with iWidgets["Output"]:
                print("请选择一张表!")
            return
        return self.renameTable(iTableName)
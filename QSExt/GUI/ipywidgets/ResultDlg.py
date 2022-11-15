# -*- coding: utf-8 -*-
"""结果集"""
import os
import tempfile
import datetime as dt

import pandas as pd
import ipywidgets as widgets
from ipytree import Node, Tree
from ipydatagrid import DataGrid
from ipyevents import Event
from IPython.display import display, HTML, clear_output

from QuantStudio import __QS_Object__, QSArgs
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB
from QuantStudio.Tools.AuxiliaryFun import genAvailableName, joinList
from QuantStudio.Tools.FileFun import listDirFile, loadCSVFactorData
from QuantStudio.Tools.DataTypeFun import getNestedDictItems, getNestedDictValue
from QSExt.GUI.ipywidgets.utils import createGetItemDlg, showGetItemDlg, createGetArgsDlg, showGetArgsDlg, createDataFrameDownload

# 用嵌套字典填充 Tree
def populateTreeWidgetWithNestedDict(parent, nested_dict, selected_callback=None):
    Keys = sorted(nested_dict)
    for iKey in Keys:
        iValue = nested_dict[iKey]
        iNode = Node(iKey)
        parent.add_node(iNode)
        if isinstance(parent, Tree):
            iNode._QSKeys = (iKey,)
        else:
            iNode._QSKeys = parent._QSKeys + (iKey,)
        if isinstance(iValue, dict):
            populateTreeWidgetWithNestedDict(iNode, iValue, selected_callback)
        elif selected_callback is not None:
            iNode.observe(selected_callback, names="selected")
    return 0

# 获取选中的 output, 返回 [(key_list, value)]
def getSelectedOutput(parent, parent_selected, flatten_output):
    Outputs = []
    for iNode in parent.nodes:
        if not iNode.nodes:# 叶节点
            if parent_selected or iNode.selected:
                Outputs.append((iNode._QSKeys, flatten_output[iNode._QSKeys]))
        else:
            Outputs += getSelectedOutput(iNode, parent_selected or iNode.selected, flatten_output)
    return Outputs

class ResultDlg(__QS_Object__):
    def __init__(self, data={}, name="数据集", msg_output="auto", sys_args={}, config_file=None, **kwargs):
        self.Data = data
        self.Name = name
        self.CurDF = pd.DataFrame(columns=[""])# 当前显示在 Table 中的数据，DataFrame
        self._FlattenData = dict(getNestedDictItems(self.Data))
        self._MsgOutput = msg_output# 显示消息的 output
        self.Frame, self.Widgets, self.Events = self.createWidgets()
    
    def showMsg(self, msg):
        if self._MsgOutput:
            with self._MsgOutput:
                #self._MsgOutput.clear_output()
                print(msg)
        else:
            self._QS_Logger.warning(msg)
    
    def createWidgets(self):
        Widgets, Events = {}, {}
        Widgets["ControlOutput"] = widgets.Output()# 显示控件的 output
        Widgets["GenTableButton"] = widgets.Button(description=">>")
        Widgets["GenTableButton"].on_click(self.on_GenTableButton_clicked)
        Widgets["MainOutput"] = widgets.Output(layout={'border': '1px solid black', "width": "1000px"})# 显示数据的 output
        if self._MsgOutput=="auto":
            self._MsgOutput = Widgets["MsgOutput"] = widgets.Output()# 显示消息的 output
        Widgets["MainDataGrid"] = DataGrid(dataframe=self.CurDF, selection_mode="column")# 显示数据的 DataGrid(ipydatagrid)
        Widgets["MainResultTree"] = Tree(layout={"width": "200px", "overflow": "scroll"})
        populateTreeWidgetWithNestedDict(Widgets["MainResultTree"], self.Data, self.on_MainResultTreeNode_selected)
        Events["MainResultTreeDblClick"] = Event(source=Widgets["MainResultTree"], watched_events=["dblclick"])
        Events["MainResultTreeDblClick"].on_dom_event(self.on_MainResultTree_dblclicked)
        Widgets["ControlFrame"] = widgets.VBox(children=[
            Widgets["MainResultTree"],
            widgets.GridBox(children=[
                Widgets["GenTableButton"]
            ], layout=widgets.Layout(grid_template_columns="repeat(2, 100px)"))
        ])
        
        Tabs = [
            widgets.HBox(children=[
                Widgets["ControlFrame"],
                Widgets["MainOutput"]
            ])
        ]
        TabNames = [self.Name]
        if "MsgOutput" in Widgets:
            Tabs.append(Widgets["MsgOutput"])
            TabNames.append("消息")
        Widgets["ResultTab"] = widgets.Tab(children=Tabs)
        Widgets["ResultTab"].titles = TabNames
        
        Widgets["GetItemDlg"] = createGetItemDlg()
        
        with Widgets["MainOutput"]:
            display(Widgets["MainDataGrid"])
        
        return Widgets["ResultTab"], Widgets, Events
    
    def on_GenTableButton_clicked(self, b, selected_output=[]):
        iWidgets = self.Widgets
        iWidgets["ControlFrame"].layout.visibility = "hidden"
        if iWidgets["GetItemDlg"]["Showed"]:
            MergeHow = iWidgets["GetItemDlg"]["MainWidget"].value
            self.CurDF = selected_output[0][1].copy()
            iPrefix = joinList(selected_output[0][0],"-")
            self.CurDF.columns = [iPrefix+"-"+str(iCol) for iCol in self.CurDF.columns]
            for iKeyList, iOutput in selected_output[1:]:
                iOutput = iOutput.copy()
                iPrefix = joinList(iKeyList,"-")
                iOutput.columns = [iPrefix+"-"+str(iCol) for iCol in iOutput.columns]
                self.CurDF = pd.merge(self.CurDF, iOutput, left_index=True, right_index=True, how=MergeHow)
            if self.CurDF.shape[0]==0:
                self.showMsg("你选择的结果集索引可能不一致!")
            if self.CurDF.shape[1]>0:
                iWidgets["MainDataGrid"].data = self.CurDF
            else:
                iWidgets["MainDataGrid"].data = pd.DataFrame(index=self.CurDF.index, columns=[""])
            iWidgets["ControlFrame"].layout.visibility = "visible"
            return
        SelectedOutput = getSelectedOutput(iWidgets["MainResultTree"], False, self._FlattenData)
        nOutput = len(SelectedOutput)
        if nOutput==0:
            iWidgets["MainDataGrid"].data = pd.DataFrame(columns=[""])
            iWidgets["ControlFrame"].layout.visibility = "visible"
            return
        elif nOutput==1:
            self.CurDF = SelectedOutput[0][1]
            self.CurDF.Name = SelectedOutput[0][0][-1]
            if self.CurDF.shape[1]>0:
                iWidgets["MainDataGrid"].data = self.CurDF
            else:
                iWidgets["MainDataGrid"].data = pd.DataFrame(index=self.CurDF.index, columns=[""])
            iWidgets["ControlFrame"].layout.visibility = "visible"
            return
        if not iWidgets["GetItemDlg"]["Showed"]:
            return showGetItemDlg(iWidgets["GetItemDlg"], parent=iWidgets["MainDataGrid"], output_widget=iWidgets["MainOutput"], 
                                  ok_callback=lambda b: self.on_GenTableButton_clicked(iWidgets["GenTableButton"], SelectedOutput),
                                  cancel_callback=lambda b: setattr(iWidgets["ControlFrame"].layout, "visibility", "visible"),
                                  desc="请选择连接方式: ", options=['inner','outer','left','right'], default_value="inner")
    
    def on_MainResultTreeNode_selected(self, change):
        if self.Widgets["MainResultTree"]._QSDblClicked:
            if change["new"]:
                self.Widgets["MainResultTree"]._QSDblClicked = False
                return self.on_GenTableButton_clicked(self.Widgets["GenTableButton"])
    
    def on_MainResultTree_dblclicked(self, event):
        self.Widgets["MainResultTree"]._QSDblClicked = True
    
    def display(self, output=None):
        if output:
            with output:
                output.clear_output()
                display(self.Frame)
        else:
            clear_output()
            display(self.Frame)

if __name__=="__main__":
    import numpy as np
    Bar2 = pd.DataFrame(np.random.randn(3,2), index=["中文", "b2", "b3"], columns=["中文", "我是个例子"])
    Bar2.iloc[0,0] = np.nan
    TestData = {"Bar1":{"a": {"a1": pd.DataFrame(np.random.rand(5,3)),
                                              "a2": pd.DataFrame(np.random.rand(4,3))},
                                      "b": pd.DataFrame(['a']*150,columns=['c'])},
                         "Bar2": Bar2}
    
    Dlg = ResultDlg(data=TestData)
    Dlg.on_GenTableButton_clicked(None)
    print("===")
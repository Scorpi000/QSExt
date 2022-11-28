# -*- coding: utf-8 -*-
"""结果集"""
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
import ipywidgets as widgets
from ipytree import Node, Tree
from ipydatagrid import DataGrid
from ipyevents import Event
from IPython.display import display, clear_output, HTML
from traits.api import Enum
import plotly

from QuantStudio import __QS_Object__, QSArgs
from QuantStudio.Tools.AuxiliaryFun import joinList, genAvailableName
from QuantStudio.Tools.DataTypeFun import getNestedDictItems
from QSExt.GUI.Notebook.utils import createDataFrameDownload, createGetItemDlg, showGetItemDlg, createGetArgsDlg, showGetArgsDlg, createGetIntDlg, showGetIntDlg, createQuestionDlg, showQuestionDlg

# 用嵌套字典填充 Tree
def populateTreeWidgetWithNestedDict(parent, nested_dict, leaf_selected_callback=None, nonleaf_selected_callback=None):
    Keys = sorted(nested_dict)
    for iKey in Keys:
        iValue = nested_dict[iKey]
        iNode = Node(iKey, icon=("folder" if isinstance(iValue, dict) else "file"))
        parent.add_node(iNode)
        if isinstance(parent, Tree):
            iNode._QSKeys = (iKey,)
        else:
            iNode._QSKeys = parent._QSKeys + (iKey,)
        if isinstance(iValue, dict):
            populateTreeWidgetWithNestedDict(iNode, iValue, leaf_selected_callback, nonleaf_selected_callback)
            if nonleaf_selected_callback:
                iNode.observe(nonleaf_selected_callback, names="selected")
        elif leaf_selected_callback is not None:
            iNode.observe(leaf_selected_callback, names="selected")
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

class PlotArgs(QSArgs):
    def __init__(self, plots, owner=None, sys_args={}, config_file=None, **kwargs):
        self._Plots = plots
        self._PlotModes = ("Line", "Bar", "Stack")
        self._PlotAxes = ("左轴", "右轴")
        return super().__init__(owner=owner, sys_args=sys_args, config_file=config_file, **kwargs)
    def __QS_initArgs__(self):
        super().__QS_initArgs__()
        for i, iPlot in enumerate(self._Plots):
            self.add_trait(f"Mode{i}", Enum(*self._PlotModes, label=f"{iPlot} 图像模式", arg_type="SingleOption", order=2*i, option_range=self._PlotModes))
            self.add_trait(f"Axes{i}", Enum(*self._PlotAxes, label=f"{iPlot} 坐标轴", arg_type="SingleOption", order=2*i+1, option_range=self._PlotAxes))

class ResultDlg(__QS_Object__):
    def __init__(self, data={}, name="数据集", msg_output="auto", sys_args={}, config_file=None, **kwargs):
        self.Data = data
        self.Name = name
        self.CurDF = pd.DataFrame(columns=[""])# 当前显示在 Table 中的数据，DataFrame
        self._FlattenData = dict(getNestedDictItems(self.Data))
        self.Frame, self.Widgets, self.Events = self.createWidgets(msg_output)
        self.Figs = {}
    
    def showMsg(self, msg, jmp=True):
        if self.Widgets["MsgOutput"]:
            with self.Widgets["MsgOutput"]:
                if isinstance(msg, str):
                    print(msg)
                else:
                    display(msg)
            if jmp:
                self.Widgets["ResultTab"].selected_index = 1
        else:
            self._QS_Logger.warning(msg)
    
    def clearMsg(self, b):
        if self.Widgets["MsgOutput"]:
            self.Widgets["MsgOutput"].clear_output()
    
    def createWidgets(self, msg_output):
        ControlWidth = "87px"
        Widgets, Events = {}, {}
        Widgets["ControlOutput"] = widgets.Output()# 显示控件的 output
        Widgets["DlgOutput"] = widgets.Output()# 显示对话框的 output
        Widgets["GenTableButton"] = widgets.Button(description=">>", layout={"width": ControlWidth})
        Widgets["GenTableButton"].on_click(self.on_GenTableButton_clicked)
        Widgets["TransposeButton"] = widgets.Button(description="转置", layout={"width": ControlWidth})
        Widgets["TransposeButton"].on_click(self.on_TransposeButton_clicked)
        Widgets["PlotTypeDropdown"] = widgets.Dropdown(options=("Line", "Hist", "CDF", "Scatter", "Scatter3D", "HeatMap"), layout={"width": ControlWidth})
        Widgets["PlotButton"] = widgets.Button(description="绘图", layout={"width": ControlWidth})
        Widgets["PlotButton"].on_click(self.on_PlotButton_clicked)
        Widgets["ExportButton"] = widgets.Button(description="导出", layout={"width": ControlWidth})
        Widgets["ExportButton"].on_click(self.on_ExportButton_clicked)
        Widgets["UpdateButton"] = widgets.Button(description="刷新", layout={"width": ControlWidth})
        Widgets["UpdateButton"].on_click(self.on_UpdateButton_clicked)        
        Widgets["MainOutput"] = widgets.Output(layout={"border": "1px solid black", "width": "750px", "height": "600px"})# 显示数据的 output
        if msg_output=="auto":
            Widgets["MsgOutput"] = widgets.Output()# 显示消息的 output
            Widgets["MsgClearButton"] = widgets.Button(description="清空")
            Widgets["MsgClearButton"].on_click(self.clearMsg)
        else:
            Widgets["MsgOutput"] = msg_output
        Widgets["MainDataGrid"] = DataGrid(dataframe=self.CurDF, selection_mode="column")# 显示数据的 DataGrid(ipydatagrid)
        Widgets["MainResultTree"] = Tree(layout={"width": "180px", "height": "500px", "overflow": "auto"})
        populateTreeWidgetWithNestedDict(Widgets["MainResultTree"], self.Data, self.on_MainResultTreeLeaf_selected, self.on_MainResultTreeNonleaf_selected)
        Events["MainResultTreeDblClick"] = Event(source=Widgets["MainResultTree"], watched_events=["dblclick"])
        Events["MainResultTreeDblClick"].on_dom_event(self.on_MainResultTree_dblclicked)
        Widgets["ControlFrame"] = widgets.VBox(children=[
            Widgets["MainResultTree"],
            widgets.GridBox(children=[
                Widgets["TransposeButton"],
                Widgets["GenTableButton"],
                Widgets["PlotTypeDropdown"],
                Widgets["PlotButton"],
                Widgets["ExportButton"],
                Widgets["UpdateButton"]
            ], layout=widgets.Layout(grid_template_columns="repeat(2, 90px)", overflow="auto"))
        ])
        
        Tabs = [
            widgets.HBox(children=[
                Widgets["ControlFrame"],
                widgets.VBox(children=[
                    Widgets["DlgOutput"],
                    Widgets["MainOutput"]
                ])
            ])
        ]
        TabNames = [self.Name]
        if msg_output=="auto":
            Tabs.append(widgets.VBox(children=[Widgets["MsgClearButton"], Widgets["MsgOutput"]]))
            TabNames.append("消息")
        Widgets["ResultTab"] = widgets.Tab(children=Tabs)
        Widgets["ResultTab"].titles = TabNames
        Widgets["ResultTab"].observe(self.redraw, names="selected_index")
        
        Widgets["QuestionDlg"] = createQuestionDlg()
        Widgets["GetIntDlg"] = createGetIntDlg()
        Widgets["GetItemDlg"] = createGetItemDlg()
        Widgets["GetArgsDlg"] = createGetArgsDlg(QSArgs())
        
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
    
    def on_MainResultTreeLeaf_selected(self, change):
        if self.Widgets["MainResultTree"]._QSDblClicked:
            if change["new"]:
                self.Widgets["MainResultTree"]._QSDblClicked = False
                return self.on_GenTableButton_clicked(self.Widgets["GenTableButton"])
    
    def on_MainResultTreeNonleaf_selected(self, change):
        if change["new"]:
            self.Widgets["MainResultTree"]._QSDblClicked = False
    
    def on_MainResultTree_dblclicked(self, event):
        self.Widgets["MainResultTree"]._QSDblClicked = True
    
    def on_TransposeButton_clicked(self, b):
        iWidgets = self.Widgets
        CurDF = iWidgets["MainDataGrid"].get_visible_data()
        CurDF = CurDF.T
        if CurDF.shape[1]==0:
            CurDF = pd.DataFrame(columns=[""], index=CurDF.index)
        if (CurDF.shape[0]==1) and (CurDF.index[0]==""):
            CurDF = CurDF.iloc[:0]
        iWidgets["MainDataGrid"].data = CurDF
    
    def createPlotTab(self):
        iWidgets = self.Widgets
        iCloseButton = widgets.Button(description="关闭绘图区")
        iOutput = widgets.Output()
        Titles = iWidgets["ResultTab"].titles
        TabName = genAvailableName("绘图区", Titles)
        iWidgets["ResultTab"].children = iWidgets["ResultTab"].children + (widgets.VBox(children=[iCloseButton, iOutput]),)
        iWidgets["ResultTab"].titles = Titles + (TabName,)
        iCloseButton._QSTabName = TabName
        iCloseButton.on_click(self.closePlotTab)
        return TabName, iOutput
        
    def closePlotTab(self, b):
        iWidgets = self.Widgets
        TabName = b._QSTabName
        Titles = iWidgets["ResultTab"].titles
        TabIdx = Titles.index(TabName)
        iWidgets["ResultTab"].selected_index = 0
        iWidgets["ResultTab"].children = iWidgets["ResultTab"].children[:TabIdx] + iWidgets["ResultTab"].children[TabIdx+1:]
        iWidgets["ResultTab"].titles = Titles[:TabIdx] + Titles[TabIdx+1:]
        self.Figs.pop(TabName)
    
    def redraw(self, change):
        SelectedIdx = change["new"]
        if SelectedIdx>=2:
            iTabName = self.Widgets["ResultTab"].titles[SelectedIdx]
            iFig = self.Figs.get(iTabName, None)
            if iFig:
                iOutput = self.Widgets["ResultTab"].children[SelectedIdx].children[1]
                iOutput.clear_output()
                with iOutput:
                    iFig.show()
    
    def getSelectedDF(self, all_num):
        iWidgets = self.Widgets
        SelectedColumns = sum((list(range(iSelection["c1"], iSelection["c2"]+1)) for iSelection in iWidgets["MainDataGrid"].selections), [])
        if not SelectedColumns: return (None, "没有选中数据列!")
        CurDF = iWidgets["MainDataGrid"].get_visible_data()
        SelectedDF = CurDF.iloc[:, SelectedColumns].copy()
        if all_num:
            try:
                SelectedDF = SelectedDF.astype("float")
            except:
                return (None, "选择的数据中包含非数值型数据!")
        return (SelectedDF, "")
    
    def plotHist(self, plot_data=None):# 直方图
        iWidgets = self.Widgets
        if not iWidgets["GetIntDlg"]["Showed"]:
            SelectedDF, Msg = self.getSelectedDF(all_num=True)
            if SelectedDF is None: return self.showMsg(Msg)
            elif SelectedDF.shape[1]!=1: return self.showMsg("请选择一列!")
            iWidgets["ControlFrame"].layout.visibility = "hidden"
            SelectedDF = SelectedDF.iloc[:, 0]
            return showGetIntDlg(iWidgets["GetIntDlg"], parent=None, output_widget=iWidgets["DlgOutput"], 
                                 ok_callback=lambda b: self.plotHist(SelectedDF),
                                 cancel_callback=lambda b: setattr(iWidgets["ControlFrame"].layout, "visibility", "visible"),
                                 desc="分组数", default_value=10)
        SelectedDF = plot_data
        GroupNum = iWidgets["GetIntDlg"]["MainWidget"].value
        yData = SelectedDF[pd.notnull(SelectedDF)].values
        xData = np.linspace(np.nanmin(yData), np.nanmax(yData), yData.shape[0]*10)
        yNormalData = stats.norm.pdf(xData, loc=np.nanmean(yData), scale=np.nanstd(yData))
        GraphObj = [
            plotly.graph_objs.Histogram(x=yData, histnorm='probability', name='直方图', nbinsx=GroupNum),
            plotly.graph_objs.Scatter(x=xData, y=yNormalData, name='Normal Distribution', line={'color':'rgb(255,0,0)','width':2})
        ]
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(title="直方图"))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def plotCDF(self):# 经验分布图
        iWidgets = self.Widgets
        SelectedDF, Msg = self.getSelectedDF(all_num=True)
        if SelectedDF is None: return self.showMsg(Msg)
        elif SelectedDF.shape[1]!=1: return self.showMsg("请选择一列!")
        iWidgets["ControlFrame"].layout.visibility = "hidden"
        SelectedDF = SelectedDF.iloc[:, 0]
        xData = SelectedDF[pd.notnull(SelectedDF)].values
        xData.sort()
        nData = xData.shape[0]
        Delta = (xData[-1]-xData[0])/nData
        xData = np.append(xData[0]-Delta,xData)
        xData = np.append(xData,xData[-1]+Delta)
        yData = (np.linspace(0,nData+1,nData+2))/(nData)
        yData[-1] = yData[-2]
        GraphObj = [plotly.graph_objs.Scatter(x=xData,y=yData,name="经验分布函数")]
        xNormalData = np.linspace(xData[0],xData[-1],(nData+2)*10)
        yNormalData = stats.norm.cdf(xNormalData,loc=np.mean(xData[1:-1]),scale=np.std(xData[1:-1]))
        GraphObj.append(plotly.graph_objs.Scatter(x=xNormalData,y=yNormalData,name="Normal Distribution"))
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(title="经验分布"))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def plotScatter(self, plot_data=None, add_regress_line=False):# 二维散点图
        iWidgets = self.Widgets
        if not iWidgets["QuestionDlg"]["Showed"]:
            SelectedDF, Msg = self.getSelectedDF(all_num=True)
            if SelectedDF is None: return self.showMsg(Msg)
            elif (SelectedDF.shape[1]<1) or (SelectedDF.shape[1]>3): return self.showMsg("请选择一到三列!")
            iWidgets["ControlFrame"].layout.visibility = "hidden"
            return showQuestionDlg(iWidgets["QuestionDlg"], parent=None, output_widget=iWidgets["DlgOutput"], 
                                   ok_callback=lambda b: self.plotScatter(SelectedDF, True),
                                   cancel_callback=lambda b: self.plotScatter(SelectedDF, False),
                                   question="是否添加回归线?")
        SelectedDF = plot_data
        SelectedDF = SelectedDF.dropna()
        GraphObj = []
        if SelectedDF.shape[1]==1:
            xData = np.linspace(0, SelectedDF.shape[0]-1, SelectedDF.shape[0])
            yData = SelectedDF.iloc[:, 0].values
            GraphObj.append(plotly.graph_objs.Scatter(x=xData, y=yData, mode="markers", name=str(SelectedDF.columns[0])))
        if SelectedDF.shape[1]==2:
            xData = SelectedDF.iloc[:, 0].values
            yData = SelectedDF.iloc[:, 1].values
            GraphObj.append(plotly.graph_objs.Scatter(x=xData, y=yData, mode="markers", name=str(SelectedDF.columns[0])+"-"+str(SelectedDF.columns[1])))
        elif SelectedDF.shape[1]==3:
            xData = SelectedDF.iloc[:,0].values
            yData = SelectedDF.iloc[:,1].values
            zData = SelectedDF.iloc[:,2].astype('float')
            Size = ((zData - zData.mean()) / zData.std() * 50).values
            GraphObj.append(plotly.graph_objs.Scatter(x=xData, y=yData, marker=dict(size=Size), mode="markers", name=str(SelectedDF.columns[0])+"-"+str(SelectedDF.columns[1])+"-"+str(SelectedDF.columns[2])))
        if add_regress_line:
            xData = sm.add_constant(xData, prepend=True)
            Model = sm.OLS(yData,xData,missing='drop')
            Result = Model.fit()
            xData = xData[:,1]
            xData.sort()
            yRegressData = Result.params[0]+Result.params[1]*xData
            GraphObj.append(plotly.graph_objs.Scatter(x=xData,y=yRegressData,name="回归线"))
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(title="散点图"))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def plotScatter3D(self, plot_data=None, add_regress_surface=False):# 三维散点图
        iWidgets = self.Widgets
        if not iWidgets["QuestionDlg"]["Showed"]:
            SelectedDF, Msg = self.getSelectedDF(all_num=True)
            if SelectedDF is None: return self.showMsg(Msg)
            elif SelectedDF.shape[1]!=3: return self.showMsg("请选择三列!")
            iWidgets["ControlFrame"].layout.visibility = "hidden"
            return showQuestionDlg(iWidgets["QuestionDlg"], parent=None, output_widget=iWidgets["DlgOutput"], 
                                   ok_callback=lambda b: self.plotScatter3D(SelectedDF, True),
                                   cancel_callback=lambda b: self.plotScatter3D(SelectedDF, False),
                                   question="是否添加回归面?")
        SelectedDF = plot_data
        SelectedDF = SelectedDF.dropna()
        xData = SelectedDF.iloc[:,0].values
        yData = SelectedDF.iloc[:,1].values
        zData = SelectedDF.iloc[:,2].values
        GraphObj = [plotly.graph_objs.Scatter3d(x=xData, y=yData, z=zData, mode='markers', name=str(SelectedDF.columns[0])+"-"+str(SelectedDF.columns[1])+"-"+str(SelectedDF.columns[2]))]
        if add_regress_surface:
            xRegressData = np.ones((SelectedDF.shape[0],3))
            xRegressData[:,1] = xData
            xRegressData[:,2] = yData
            Model = sm.OLS(zData,xRegressData,missing='drop')
            Result = Model.fit()
            xData.sort()
            yData.sort()
            X,Y = np.meshgrid(xData,yData)
            zRegressData = Result.params[0]+Result.params[1]*X+Result.params[2]*Y
            GraphObj.append(plotly.graph_objs.Surface(x=X, y=Y, z=zRegressData, colorscale='Viridis', name='回归面'))
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(title="3D散点图"))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def plotHeatMap(self):# 热图
        iWidgets = self.Widgets
        SelectedDF, Msg = self.getSelectedDF(all_num=True)
        if SelectedDF is None: return self.showMsg(Msg)
        elif SelectedDF.shape[1]<2: return self.showMsg("请选择至少两列!")
        iWidgets["ControlFrame"].layout.visibility = "hidden"
        #SelectedIndex = [str(iIndex) for iIndex in SelectedDF.columns]
        GraphObj = [plotly.graph_objs.Heatmap(z=SelectedDF.astype('float').values)]
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(title="热图"))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def plotLine(self, plot_data=None):
        iWidgets = self.Widgets
        if not iWidgets["GetArgsDlg"]["Showed"]:
            iWidgets["ControlFrame"].layout.visibility = "hidden"
            # 获取绘图数据
            PlotResult, Msg = self.getSelectedDF(all_num=True)
            if PlotResult is None:
                return self.showMsg(Msg)
            iPlotArgs = PlotArgs(PlotResult.columns)
            return showGetArgsDlg(iWidgets["GetArgsDlg"], parent=None, output_widget=iWidgets["DlgOutput"], 
                                  ok_callback=lambda b: self.plotLine(PlotResult),
                                  cancel_callback=lambda b: setattr(iWidgets["ControlFrame"].layout, "visibility", "visible"),
                                  qsargs=iPlotArgs)
        # 设置绘图模式
        iPlotArgs = iWidgets["GetArgsDlg"]["MainWidget"].Args
        PlotMode, PlotAxes = [], []
        for i in range(plot_data.shape[1]):
            PlotMode.append(getattr(iPlotArgs, f"Mode{i}"))
            PlotAxes.append(getattr(iPlotArgs, f"Axes{i}"))
        # 设置要绘制的索引
        PlotResult = plot_data
        xData = PlotResult.index
        xTickLabels = []
        isStr = False
        for iData in xData:
            xTickLabels.append(str(iData))
            if isinstance(iData, str): isStr = True
        if isStr: xData = xTickLabels
        LayoutDict = {"title":','.join([str(iCol) for iCol in PlotResult.columns])}
        if ('左轴' in PlotAxes): LayoutDict['yaxis'] = dict(title='Left Axis')
        if ('右轴' in PlotAxes): LayoutDict['yaxis2'] = dict(title='Right Axis', titlefont=dict(color='rgb(148, 103, 189)'), tickfont=dict(color='rgb(148, 103, 189)'), overlaying='y', side='right')
        GraphObj = []
        for i in range(PlotResult.shape[1]):
            iArgs = ({} if PlotAxes[i]=="左轴" else {"yaxis":"y2"})
            yData = PlotResult.iloc[:,i]
            if PlotMode[i]=='Line':
                iGraphObj = plotly.graph_objs.Scatter(x=xData, y=yData.values, name=str(yData.name), **iArgs)
            elif PlotMode[i]=='Bar':
                iGraphObj = plotly.graph_objs.Bar(x=xData, y=yData.values, name=str(yData.name), **iArgs)
            elif PlotMode[i]=='Stack':
                iGraphObj = plotly.graph_objs.Scatter(x=xData, y=yData.values, name=str(yData.name), fill='tonexty', **iArgs)
            GraphObj.append(iGraphObj)
        Fig = plotly.graph_objs.Figure(data=GraphObj, layout=plotly.graph_objs.Layout(**LayoutDict))
        iTabName, iOutput = self.createPlotTab()
        with iOutput:
            Fig.show()
        self.Figs[iTabName] = Fig
        iWidgets["ResultTab"].selected_index = len(iWidgets["ResultTab"].children) - 1
        iWidgets["ControlFrame"].layout.visibility = "visible"
    
    def on_PlotButton_clicked(self, b):
        PlotType = self.Widgets["PlotTypeDropdown"].value
        if PlotType=="Line":
            return self.plotLine()
        elif PlotType=="Hist":
            return self.plotHist()
        elif PlotType=="CDF":
            return self.plotCDF()
        elif PlotType=="Scatter":
            return self.plotScatter()
        elif PlotType=="Scatter3D":
            return self.plotScatter3D()
        elif PlotType=="HeatMap":
            return self.plotHeatMap()
    
    def on_ExportButton_clicked(self, b):
        CurDF = self.Widgets["MainDataGrid"].get_visible_data()
        if CurDF.shape[0] * CurDF.shape[1]==0: return
        return self.showMsg(HTML(createDataFrameDownload(CurDF, name="导出的数据")))
    
    def on_UpdateButton_clicked(self, b):
        with self.Widgets["MainOutput"]:
            self.Widgets["MainOutput"].clear_output()
            display(self.Widgets["MainDataGrid"])
    
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
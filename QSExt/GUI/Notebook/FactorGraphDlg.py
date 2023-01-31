# -*- coding: utf-8 -*-
import datetime as dt
from collections import OrderedDict

import pandas as pd
import networkx as nx
import ipycytoscape
from ipydatagrid import DataGrid
import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__
from QuantStudio.FactorDataBase.FactorDB import FactorDB, WritableFactorDB, FactorTable, Factor
from QuantStudio.FactorDataBase.FactorOperation import DerivativeFactor
from QuantStudio.Tools.DateTimeFun import getDateTimeSeries
from QSExt.Tools.FactorFun import loadFactorDef

__CSS__ = [
    {
        "selector": "node.Factor",
        "style": {
            "color": "black",
            "background-color": "DeepSkyBlue",
            "label": "data(label)",
            "font-family": "helvetica",
            "font-size": "10px",
            "text-valign": "center",
            "text-halign": "center",
            "opacity": 1.0
        }
    },
    {
        "selector": "node.Unselected",
        "style": {
            "opacity": 0.3
        }
    },
    {
        "selector": "node.DerivativeFactor",
        "style": {
            "background-color": "SteelBlue",
        }
    },
    {
        "selector": "node.FactorTable",
        "style": {
            "color": "black",
            "background-color": "LightGreen",
            "label": "data(label)",
            "font-family": "helvetica",
            "font-size": "10px",
            "text-valign": "center",
            "text-halign": "center",
        }
    },
    {
        "selector": "node.CustomFT",
        "style": {
            "background-color": "ForestGreen",
        }
    },
    {
        "selector": "node.FactorDB",
        "style": {
            "color": "black",
            "background-color": "yellow",
            "label": "data(label)",
            "font-family": "helvetica",
            "font-size": "10px",
            "text-valign": "center",
            "text-halign": "center",
        }
    },
    {
        "selector": "node.WritableFactorDB",
        "style": {
            "background-color": "orange",
        }
    },
    {
        "selector": "edge.directed",
        "style": {
            "line-color": "gray",
            "width": 2,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "gray",
            "opacity": 1
        },
    },
    {
        "selector": "edge.Unselected",
        "style": {
            "opacity": 0.3
        }
    },
]

class QSNode(ipycytoscape.Node):
    def __init__(self, qs_obj, classes):
        super().__init__()
        self._QSObj = qs_obj
        self.data["id"] = str(id(qs_obj))
        self.data["label"] = getattr(qs_obj, "Name", "")
        self.data["classes"] = classes
        self.classes = classes
    
    @property
    def QSObj(self):
        return self._QSObj

    @classmethod
    def on_Node_clicked(cls, node, dlg):
        dlg.Widgets["MsgOutput"].clear_output()
        Nodes = dlg._FactorNodes.copy()
        Nodes.update(dlg._FTNodes)
        Nodes.update(dlg._FDBNodes)

        SelectedID = node["data"]["id"]
        SelectedNode = Nodes[SelectedID]
        if SelectedID not in dlg.Widgets["NodeWidgets"]:
            if isinstance(SelectedNode._QSObj, (Factor, FactorTable)):
                dlg.Widgets["NodeWidgets"][SelectedID] = OrderedDict()
                dlg.Widgets["NodeWidgets"][SelectedID]["EndDT"] = widgets.DatePicker(description="截止日", disabled=False, style={"description_width": "45px"}, layout={"width": "165px"})
                dlg.Widgets["NodeWidgets"][SelectedID]["DTNum"] = widgets.IntText(description="日期数", disabled=False, value=5, style={"description_width": "45px"}, layout={"width": "165px"})
                dlg.Widgets["NodeWidgets"][SelectedID]["IDNum"] = widgets.IntText(description="证券数", disabled=False, value=5, style={"description_width": "45px"}, layout={"width": "165px"})
                dlg.Widgets["NodeWidgets"][SelectedID]["PreviewButton"] = widgets.Button(description="预览", layout={"width": "165px"})
                dlg.Widgets["NodeWidgets"][SelectedID]["PreviewButton"].on_click(lambda b: SelectedNode.on_PreviewButton_clicked(b, dlg))
            if isinstance(SelectedNode._QSObj, FactorTable) and isinstance(SelectedNode._QSObj.FactorDB, WritableFactorDB):
                dlg.Widgets["NodeWidgets"][SelectedID]["FTExtendCheckbox"] = widgets.Checkbox(description="展开因子表", indent=False, value=False, layout={"width": "165px"})
                dlg.Widgets["NodeWidgets"][SelectedID]["FTExtendCheckbox"].observe(lambda change: SelectedNode.on_FTFoldCheckbox_changed(change, dlg), names="value")
        with dlg.Widgets["InfoOutput"]:
            dlg.Widgets["InfoOutput"].clear_output()
            if SelectedID in dlg.Widgets["NodeWidgets"]:
                if "Frame" not in dlg.Widgets["NodeWidgets"][SelectedID]:
                    # dlg.Widgets["NodeWidgets"][SelectedID]["Frame"] = widgets.GridBox(list(dlg.Widgets["NodeWidgets"][SelectedID].values()), layout=widgets.Layout(grid_template_columns="repeat(2, 100px)"))
                    dlg.Widgets["NodeWidgets"][SelectedID]["Frame"] = widgets.VBox(list(dlg.Widgets["NodeWidgets"][SelectedID].values()))
                display(dlg.Widgets["NodeWidgets"][SelectedID]["Frame"])
            display(SelectedNode.QSObj)
        SelectedNodes = nx.descendants(dlg._nxGraph, SelectedNode)
        SelectedNodes.add(SelectedNode)
        for iID, iNode in Nodes.items():
            if iNode in SelectedNodes:
                iNode.classes = iNode.classes.replace(" Unselected", "")
            elif "Unselected" not in iNode.classes:
                iNode.classes = iNode.classes + " Unselected"
        for iEdge in dlg.Widgets["Graph"].graph.edges:
            if (Nodes[iEdge.data["source"]] not in SelectedNodes) or (Nodes[iEdge.data["target"]] not in SelectedNodes) and ("Unselected" not in iEdge.classes):
                iEdge.classes = iEdge.classes + " Unselected"
            else:
                iEdge.classes = iEdge.classes.replace(" Unselected", "")

    def on_PreviewButton_clicked(self, b, dlg):
        SelectedID = self.data["id"]
        EndDT = dlg.Widgets["NodeWidgets"][SelectedID]["EndDT"].value
        if EndDT: EndDT = dt.datetime.combine(EndDT, dt.time(0))
        DTNum = dlg.Widgets["NodeWidgets"][SelectedID]["DTNum"].value
        IDNum = dlg.Widgets["NodeWidgets"][SelectedID]["IDNum"].value
        if isinstance(self._QSObj, Factor):
            Data = self.readFactorData(self._QSObj, id_num=IDNum, end_dt=EndDT, dt_num=DTNum)
        elif isinstance(self._QSObj, FactorTable):
            Data = self.readFactorTableData(self._QSObj, id_num=IDNum, end_dt=EndDT, dt_num=DTNum)
        else:
            return
        if Data.shape[1]==0:
            Data = pd.DataFrame(columns=[""])
        dlg.Widgets["MainDataGrid"].data = Data
        with dlg.Widgets["MsgOutput"]:
            display(dlg.Widgets["MainDataGrid"])

    def readFactorData(self, f, id_num=0, end_dt=None, dt_num=0):
        iDTs = f.getDateTime(end_dt=end_dt)
        if not iDTs:
            if end_dt is None: end_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
            iDTs = getDateTimeSeries(end_dt - dt.timedelta(dt_num), end_dt)
        else:
            iDTs = iDTs[-dt_num:]
        iIDs = f.getID()
        if id_num > 0:
            iIDs = iIDs[:id_num]
        elif id_num < 0:
            iIDs = iIDs[id_num:]
        return f.readData(dts=iDTs, ids=iIDs)

    def readFactorTableData(self, ft, id_num=0, end_dt=None, dt_num=0):
        iDTs = ft.getDateTime(end_dt=end_dt)
        if not iDTs:
            if end_dt is None: end_dt = dt.datetime.combine(dt.date.today(), dt.time(0))
            iDTs = getDateTimeSeries(end_dt - dt.timedelta(dt_num), end_dt)
        else:
            iDTs = iDTs[-dt_num:]
        iIDs = ft.getID()
        if id_num > 0:
            iIDs = iIDs[:id_num]
        elif id_num < 0:
            iIDs = iIDs[id_num:]
        return ft.readData(factor_names=ft.FactorNames, dts=iDTs, ids=iIDs).to_frame(filter_observations=False)

    def on_FTFoldCheckbox_changed(self, change, dlg):
        FT = self._QSObj
        if change["new"]:
            Factors = loadFactorDef(FT, context=dlg._Context)
            if not Factors: return
            Neibhors = {iNode._QSObj._NameInFT: iNode for iNode in nx.all_neighbors(dlg._nxGraph, self) if isinstance(iNode._QSObj, Factor)}
            FactorNodes = dlg.addFactors(factor_list=Factors)
            self._ConnFactorNodes = []
            for iNode in FactorNodes:
                dlg._nxGraph.add_edge(self, iNode)
                dlg.Widgets["Graph"].graph.add_edge(QSEdge(source_id=self.data["id"], target_id=iNode.data["id"]), directed=True)
                if iNode._QSObj.Name in Neibhors:
                    iDevNode = Neibhors[iNode._QSObj.Name]
                    dlg._nxGraph.add_edge(iDevNode, iNode)
                    dlg.Widgets["Graph"].graph.add_edge(QSEdge(source_id=iDevNode.data["id"], target_id=iNode.data["id"]), directed=True)
                    dlg._nxGraph.remove_edge(iDevNode, self)
                    dlg.Widgets["Graph"].graph.remove_edge_by_id(source_id=iDevNode.data["id"], target_id=self.data["id"])
                    self._ConnFactorNodes.append(iDevNode)
        else:
            for iNode in self._ConnFactorNodes:
                dlg._nxGraph.add_edge(iNode, self)
                dlg.Widgets["Graph"].graph.add_edge(QSEdge(source_id=iNode.data["id"], target_id=self.data["id"]), directed=True)
            Descendants = nx.descendants(dlg._nxGraph, self)
            for iNode in Descendants:
                if not isinstance(iNode._QSObj, FactorDB):
                    dlg._nxGraph.remove_node(iNode)
                    dlg.Widgets["Graph"].graph.remove_node(iNode)
        dlg.updateGraph()

class QSEdge(ipycytoscape.Edge):
    def __init__(self, source_id, target_id, classes=""):
        super().__init__()
        self.data["source"] = source_id
        self.data["target"] = target_id
        self.classes = classes


class FactorGraphDlg(__QS_Object__):
    def __init__(self, factor_list=[], cfts=[], context={}, css=None, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)
        self._Context = context
        self._Factors = factor_list
        self._CFTs = cfts
        self._CSS = (__CSS__ if not css else css)
        self._FactorNodes = {}
        self._FTNodes = {}
        self._FDBNodes = {}
        self._nxGraph = nx.DiGraph()
        self.Frame, self.Widgets = self.createWidgets()
        self.addFactors(self._Factors)
        for iCFT in cfts: self.addCustomFT(iCFT)
        # self.Widgets["Graph"].graph.add_graph_from_networkx(self._nxGraph, directed=True)
        self.updateGraph()

    def createGraphWidget(self):
        GraphWidget = ipycytoscape.CytoscapeWidget()
        GraphWidget.set_style(self._CSS)
        GraphWidget.set_layout(name="dagre")
        GraphWidget.on("node", "click", lambda node: QSNode.on_Node_clicked(node, self))
        # GraphWidget.on("node", "mouseover", lambda node: QSNode.on_Node_clicked(node, self))
        return GraphWidget

    def createWidgets(self):
        Widgets = {}
        
        Widgets["GraphOutput"] = widgets.Output(layout={"width": "100%", "border": "1px solid black"})
        Widgets["MsgOutput"] = widgets.Output(layout={"width": "100%"})
        Widgets["CtrlOutput"] = widgets.Output()
        Widgets["InfoOutput"] = widgets.Output()
        Widgets["FactorTableCheckbox"] = widgets.Checkbox(description="因子表", indent=False, value=True, layout={"width": "80px"})
        Widgets["FactorTableCheckbox"].observe(self._on_FactorTableCheckbox_changed, names="value")
        Widgets["FactorDBCheckbox"] = widgets.Checkbox(description="因子库", indent=False, value=True, layout={"width": "80px"})
        Widgets["FactorDBCheckbox"].observe(self._on_FactorDBCheckbox_changed, names="value")
        Widgets["MainDataGrid"] = DataGrid(dataframe=pd.DataFrame(columns=[""]), selection_mode="column")
        Widgets["NodeWidgets"] = {}
        Widgets["Graph"] = self.createGraphWidget()

        Frame = widgets.HBox(children=[
            widgets.VBox(children=[Widgets["GraphOutput"], Widgets["MsgOutput"]], layout={"min_width": "30%"}),
            widgets.VBox(children=[Widgets["CtrlOutput"], Widgets["InfoOutput"]], layout={"min_width": "0", "max_width": "50%"})
        ])

        with Widgets["CtrlOutput"]:
            display(widgets.HBox(children=[Widgets["FactorTableCheckbox"], Widgets["FactorDBCheckbox"]]))

        return Frame, Widgets    
    
    def showMsg(self, msg, clear=True):
        if clear: self.Widgets["InfoOutput"].clear_output()
        with self.Widgets["InfoOutput"]:
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
    
    def updateGraph(self):
        self.Widgets["GraphOutput"].clear_output()
        with self.Widgets["GraphOutput"]:
            display(self.Widgets["Graph"])
    
    def addCustomFT(self, cft):
        g, wg = self._nxGraph, self.Widgets["Graph"].graph
        iID = str(id(cft))
        if iID not in self._FTNodes:
            FTNode = QSNode(qs_obj=cft, classes="FactorTable CustomFT")
            self._FTNodes[iID] = FTNode
            g.add_node(FTNode)
            wg.add_node(FTNode)
        else:
            FTNode = self._FTNodes[iID]
        FactorNodes = self.addFactors([cft.getFactor(iFactorName) for iFactorName in cft.FactorNames])
        for i, iFactorNode in enumerate(FactorNodes):
            g.add_edge(FTNode, iFactorNode, order=i)
            wg.add_edge(QSEdge(source_id=FTNode.data["id"], target_id=iFactorNode.data["id"]), directed=True)
        return FTNode
            
    def addFactors(self, factor_list, parent_factor_node=None):
        g, wg = self._nxGraph, self.Widgets["Graph"].graph
        FactorNodes = []
        for i, iFactor in enumerate(factor_list):
            iID = str(id(iFactor))
            if iID not in self._FactorNodes:
                if isinstance(iFactor, DerivativeFactor):
                    iFactorNode = QSNode(iFactor, classes="Factor DerivativeFactor")
                else:
                    iFactorNode = QSNode(iFactor, classes="Factor")
                self._FactorNodes[iID] = iFactorNode
                g.add_node(iFactorNode)
                wg.add_node(iFactorNode)
            else:
                iFactorNode = self._FactorNodes[iID]
            if parent_factor_node:
                g.add_edge(parent_factor_node, iFactorNode, order=i)
                wg.add_edge(QSEdge(source_id=parent_factor_node.data["id"], target_id=iFactorNode.data["id"]), directed=True)
            _ = self.addFactors(iFactor.Descriptors, iFactorNode)
            FactorNodes.append(iFactorNode)
            iFT = iFactor.FactorTable
            if iFT is None: continue
            iFTID = str(id(iFT))
            if iFTID not in self._FTNodes:
                iFTNode = QSNode(iFT, classes="FactorTable")
                self._FTNodes[iFTID] = iFTNode
                g.add_node(iFTNode)
                wg.add_node(iFTNode)
            else:
                iFTNode = self._FTNodes[iFTID]
            g.add_edge(iFactorNode, iFTNode)
            wg.add_edge(QSEdge(source_id=iFactorNode.data["id"], target_id=iFTNode.data["id"]), directed=True)
            iFDB = iFT.FactorDB
            if iFDB is None: continue
            iFDBID = str(id(iFDB))
            if iFDBID not in self._FDBNodes:
                if isinstance(iFDB, WritableFactorDB):
                    iFDBNode = QSNode(iFDB, classes="FactorDB WritableFactorDB")
                else:
                    iFDBNode = QSNode(iFDB, classes="FactorDB")                    
                self._FDBNodes[iFDBID] = iFDBNode
                g.add_node(iFDBNode)
                wg.add_node(iFDBNode)
            else:
                iFDBNode = self._FDBNodes[iFDBID]
            g.add_edge(iFTNode, iFDBNode)
            wg.add_edge(QSEdge(source_id=iFTNode.data["id"], target_id=iFDBNode.data["id"]), directed=True)
        return FactorNodes

    def _on_FactorTableCheckbox_changed(self, change):
        iWidgets = self.Widgets
        if change["new"]:
            iWidgets["Graph"].graph.add_nodes(list(self._FTNodes.values()))
            for iID, iFTNode in self._FTNodes.items():
                if not iWidgets["FactorDBCheckbox"].value:
                    iNodes = [iNode for iNode in nx.all_neighbors(self._nxGraph, iFTNode) if not isinstance(iNode.QSObj, FactorDB)]
                else:
                    iNodes = list(nx.all_neighbors(self._nxGraph, iFTNode))
                iEdges = [QSEdge(source_id=iNode1.data["id"], target_id=iNode2.data["id"]) for iNode1, iNode2 in nx.edges(self._nxGraph, iNodes+[iFTNode])]
                iWidgets["Graph"].graph.add_edges(iEdges, directed=True)
        else:
            for iID, iFTNode in self._FTNodes.items():
                iWidgets["Graph"].graph.remove_node(iFTNode)
        self.updateGraph()
    
    def _on_FactorDBCheckbox_changed(self, change):
        iWidgets = self.Widgets
        if change["new"]:
            iWidgets["Graph"].graph.add_nodes(list(self._FDBNodes.values()))
            for iID, iFDBNode in self._FDBNodes.items():
                if not iWidgets["FactorTableCheckbox"].value:
                    iNodes = [iNode for iNode in nx.all_neighbors(self._nxGraph, iFDBNode) if not isinstance(iNode.QSObj, FactorTable)]
                else:
                    iNodes = list(nx.all_neighbors(self._nxGraph, iFDBNode))
                iEdges = [QSEdge(source_id=iNode1.data["id"], target_id=iNode2.data["id"]) for iNode1, iNode2 in nx.edges(self._nxGraph, iNodes+[iFDBNode])]
                iWidgets["Graph"].graph.add_edges(iEdges, directed=True)
        else:
            for iID, iFDBNode in self._FDBNodes.items():
                iWidgets["Graph"].graph.remove_node(iFDBNode)
        self.updateGraph()

if __name__=="__main__":
    import QuantStudio.api as QS
    fd = QS.FactorDB.FactorTools

    Factor1 = QS.FactorDB.DataFactor(name="Factor1", data=1)
    Factor2 = QS.FactorDB.DataFactor(name="Factor2", data=2)
    Factor3 = fd.rolling_cov(Factor1, Factor2, window=5, factor_name="Factor3")
    Factor4 = QS.FactorDB.Factorize((Factor1 + Factor2) / 2, factor_name="Factor4")
    Factor5 = fd.nansum(Factor1, Factor3, Factor4, factor_name="Factor5")

    CFT = QS.FactorDB.CustomFT(name="MyFT")
    CFT.addFactors(factor_list=[Factor2, Factor5])

    Dlg = FactorGraphDlg(factor_list=[Factor1, Factor2, Factor3, Factor4, Factor5], ft_list=[CFT])

    # g = nx.DiGraph()
    # g.add_nodes_from([1, 2, 3, 4, 5])
    # g.add_edge(3, 1)
    # g.add_edge(3, 2)
    # g.add_edge(4, 1)
    # g.add_edge(4, 2)
    # g.add_edge(5, 1)
    # g.add_edge(5, 3)
    # g.add_edge(5, 4)
    print("===")
# -*- coding: utf-8 -*-
import networkx as nx
import ipycytoscape
import ipywidgets as widgets
from IPython.display import display, clear_output

from QuantStudio import __QS_Object__
from QuantStudio.FactorDataBase.FactorDB import WritableFactorDB
from QuantStudio.FactorDataBase.FactorOperation import DerivativeFactor

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
    #{
        #"selector": "edge",
        #"style": {
            #"line-color": "gray",
            #"width": 2,
        #}
    #},
    {
        "selector": "edge.directed",
        "style": {
            "line-color": "gray",
            "width": 2,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "gray"
        },
    }
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
    def on_Node_clicked(cls, node, nodes, info_output):
        iNode = nodes[node["data"]["id"]]
        with info_output:
            info_output.clear_output()
            display(iNode.QSObj)
            

class FactorGraphDlg(__QS_Object__):
    def __init__(self, factor_list=[], cfts=[], css=None, sys_args={}, config_file=None, **kwargs):
        super().__init__(sys_args=sys_args, config_file=config_file, **kwargs)        
        self._Factors = factor_list
        self._CFTs = cfts
        self._CSS = (__CSS__ if not css else css)
        self._FactorNodes = {}
        self._FTNodes = {}
        self._FDBNodes = {}
        self._nxGraph = nx.DiGraph()
        self.addFactors(self._nxGraph, self._Factors)
        for iCFT in cfts: self.addCustomFT(self._nxGraph, iCFT)
        self.Frame, self.Widgets = self.createWidgets()
        self.Widgets["Graph"].graph.add_graph_from_networkx(self._nxGraph, directed=True)
        self.updateGraph()
    
    def createWidgets(self):
        Widgets = {}
        
        Widgets["GraphOutput"] = widgets.Output(layout={"width": "80%"})
        Widgets["InfoOutput"] = widgets.Output()
        #Widgets["FactorCheckbox"] = widgets.Checkbox(description="因子", indent=False, value=True)
        #Widgets["FactorCheckbox"].observe(self._on_FactorCheckbox_changed, names="value")
        Widgets["FactorTableCheckbox"] = widgets.Checkbox(description="因子表", indent=False, value=True)
        Widgets["FactorTableCheckbox"].observe(self._on_FactorTableCheckbox_changed, names="value")
        Widgets["FactorDBCheckbox"] = widgets.Checkbox(description="因子库", indent=False, value=True)
        Widgets["FactorDBCheckbox"].observe(self._on_FactorDBCheckbox_changed, names="value")
        
        Widgets["Graph"] = ipycytoscape.CytoscapeWidget()
        Widgets["Graph"].set_style(self._CSS)
        Widgets["Graph"].set_layout(name="dagre")
        Nodes = self._FactorNodes.copy()
        Nodes.update(self._FTNodes)
        Nodes.update(self._FDBNodes)
        Widgets["Graph"].on("node", "click", lambda node: QSNode.on_Node_clicked(node, Nodes, Widgets["InfoOutput"]))
        #Widgets["Graph"].on("node", "mouseover", lambda node: QSNode.on_Node_clicked(node, Nodes, Widgets["InfoOutput"]))
        
        Frame = widgets.HBox(children=[
            Widgets["GraphOutput"],
            widgets.VBox(children=[
                widgets.HBox(children=[Widgets["FactorTableCheckbox"], Widgets["FactorDBCheckbox"]]),
                Widgets["InfoOutput"]
            ], layout={"width": "20%"}),
        ])
        
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
    
    def addCustomFT(self, g, cft):
        iID = str(id(cft))
        if iID not in self._FTNodes:
            FTNode = QSNode(qs_obj=cft, classes="FactorTable CustomFT")
            self._FTNodes[iID] = FTNode
            g.add_node(FTNode)
        else:
            FTNode = self._FTNodes[iID]
        FactorNodes = self.addFactors(g, [cft.getFactor(iFactorName) for iFactorName in cft.FactorNames])
        for i, iFactorNode in enumerate(FactorNodes):
            g.add_edge(FTNode, iFactorNode, order=i)
        return FTNode
            
    def addFactors(self, g, factor_list, parent_factor_node=None):
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
            else:
                iFactorNode = self._FactorNodes[iID]
            if parent_factor_node:
                g.add_edge(parent_factor_node, iFactorNode, order=i)
            _ = self.addFactors(g, iFactor.Descriptors, iFactorNode)
            FactorNodes.append(iFactorNode)
            iFT = iFactor.FactorTable
            if iFT is None: continue
            iFTID = str(id(iFT))
            if iFTID not in self._FTNodes:
                iFTNode = QSNode(iFT, classes="FactorTable")
                self._FTNodes[iFTID] = iFTNode
                g.add_node(iFTNode)
            else:
                iFTNode = self._FTNodes[iFTID]
            g.add_edge(iFactorNode, iFTNode)
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
            else:
                iFDBNode = self._FDBNodes[iFDBID]
            g.add_edge(iFTNode, iFDBNode)
        return FactorNodes
            
    
    def removeFTNode(self):
        iWidgets = self.Widgets
        for iID, iFTNode in self._FTNodes.items():
            iWidgets["Graph"].graph.remove_node(iFTNode)
    
    def removeFDBNode(self):
        iWidgets = self.Widgets
        for iID, iFDBNode in self._FDBNodes.items():
            iWidgets["Graph"].graph.remove_node(iFDBNode)
    
    def _on_FactorTableCheckbox_changed(self, change):
        iWidgets = self.Widgets
        if change["new"]:
            iWidgets["Graph"].graph.clear()
            iWidgets["Graph"].graph.add_graph_from_networkx(self._nxGraph, directed=True)
            if not iWidgets["FactorDBCheckbox"].value:
                self.removeFDBNode()
        else:
            self.removeFTNode()
        self.updateGraph()
    
    def _on_FactorDBCheckbox_changed(self, change):
        iWidgets = self.Widgets
        if change["new"]:
            iWidgets["Graph"].graph.clear()
            iWidgets["Graph"].graph.add_graph_from_networkx(self._nxGraph, directed=True)
            if not iWidgets["FactorTableCheckbox"].value:
                self.removeFTNode()
        else:
            self.removeFDBNode()
        self.updateGraph()
    
if __name__=="__main__":
    import QuantStudio.api as QS
    fd = QS.FactorDB.FactorTools
    
    Factor1 = QS.FactorDB.DataFactor(name="Factor1", data=1)
    Factor2 = QS.FactorDB.DataFactor(name="Factor2", data=2)
    Factor3 = fd.rolling_cov(Factor1, Factor2, window=5, factor_name="Factor3")
    Factor4 = QS.FactorDB.Factorize((Factor1 + Factor2) / 2, factor_name="Factor4")
    Factor5 = fd.nansum(Factor1, Factor3, Factor4, factor_name="Factor5")
    
    print(Factor1._repr_html_())
    
    CFT = QS.FactorDB.CustomFT(name="MyFT")
    CFT.addFactors(factor_list=[Factor2, Factor5])
    
    Dlg = FactorGraphDlg(factor_list=[Factor1, Factor3, Factor4], ft_list=[CFT])
    print("===")
# -*- coding: utf-8 -*-
import ipycytoscape
import networkx as nx

class FactorNode(ipycytoscape.Node):
    def __init__(self, factor, classes="Factor"):
        super().__init__()
        self._Factor = factor
        self.data["id"] = factor.Name
        self.data["label"] = factor.Name
        self.data["classes"] = classes
        self.classes = classes

class FactorTableNode(ipycytoscape.Node):
    def __init__(self, factor_table, classes="FactorTable"):
        super().__init__()
        self._FactorTable = factor_table
        self.data["id"] = factor_table.Name
        self.data["label"] = factor_table.Name
        self.data["classes"] = classes
        self.classes = classes

class FactorGraph:
    def __init__(self, factor_list=[], ft_list=[]):
        self._nxGraph = nx.Graph()
        self.addFactors(factor_list)
        for iFT in ft_list:
            self.addFactors([iFT.getFactor(iFactorName) for iFactorName in iFT.FactorNames])
    
    def addFactors(self, factor_list, parent=None):
        for iFactor in factor_list:
            iFactorNode = FactorNode(iFactor)
            self._nxGraph.add_node(iFactorNode)
            if parent:
                self._nxGraph.add_edge(parent, iFactorNode)
            self.addFactors(iFactor.Descriptors, iFactorNode)
    
    def getCytoscapeWidget(self):
        Widget = ipycytoscape.CytoscapeWidget()
        Widget.graph.add_graph_from_networkx(self._nxGraph)
        return Widget

if __name__=="__main__":
    import QuantStudio.api as QS
    fd = QS.FactorDB.FactorTools
    
    Factor1 = QS.FactorDB.DataFactor(name="Factor1", data=1)
    Factor2 = QS.FactorDB.DataFactor(name="Factor2", data=2)
    Factor3 = fd.rolling_cov(Factor1, Factor2, window=5, factor_name="Factor3")
    Factor4 = QS.FactorDB.Factorize((Factor1 + Factor2) / 2, factor_name="Factor4")
    Factor5 = fd.nansum(Factor1, Factor3, Factor4, factor_name="Factor5")
    
    FG = FactorGraph(factor_list=[Factor1, Factor2, Factor3, Factor4, Factor5])
    Widget = FG.getCytoscapeWidget()
    print(Widget)
    
    print("===")
# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtWidgets

# 用 DataFrame 填充 QTableWidget, 数据形式
def populateTableWithDataFrame(table_widget, df):
    table_widget.blockSignals(True)
    table_widget.clear()
    nRow,nCol = df.shape
    ColumnLabels = [str(iLabel) for iLabel in df.columns]
    table_widget.setColumnCount(nCol)
    table_widget.setHorizontalHeaderLabels(ColumnLabels)
    RowLabels = [str(iLabel) for iLabel in df.index]
    table_widget.setRowCount(nRow)
    table_widget.setVerticalHeaderLabels(RowLabels)
    for jRow in range(nRow):
        for kCol in range(nCol):
            table_widget.setItem(jRow, kCol, QtWidgets.QTableWidgetItem(str(df.iloc[jRow,kCol])))
    table_widget.blockSignals(False)
    return 0
# 用嵌套字典填充 QTreeWidget
def populateQTreeWidgetWithNestedDict(tree_widget, nested_dict):
    Keys = list(nested_dict.keys())
    Keys.sort()
    for iKey in Keys:
        iValue = nested_dict[iKey]
        iParent = QtWidgets.QTreeWidgetItem(tree_widget, [iKey])
        if isinstance(tree_widget, QtWidgets.QTreeWidget):
            iParent.setData(0, QtCore.Qt.UserRole, (iKey,))
        else:
            iParent.setData(0, QtCore.Qt.UserRole, iParent.parent().data(0, QtCore.Qt.UserRole)+(iKey,))
        if isinstance(iValue, dict):
            populateQTreeWidgetWithNestedDict(iParent, iValue)
    return 0


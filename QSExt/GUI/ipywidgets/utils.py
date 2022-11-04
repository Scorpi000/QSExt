# -*- coding: utf-8 -*-
import base64

from IPython.display import display, clear_output
import ipywidgets as widgets

def createDataFrameDownload(df, name="Download"):
    CSV = df.to_csv()
    b64 = base64.b64encode(CSV.encode())
    Payload = b64.decode()
    Html = '<a download="{name}.csv" href="data:text/csv;base64,{payload}" target="_blank">{name}</a>'
    Html = Html.format(payload=Payload, name=name)
    return Html

def showDlg(dlg, output_widget=None):
    dlg["Showed"] = True
    if output_widget:
        with output_widget:
            output_widget.clear_output()
            display(dlg["Frame"])
    else:
        clear_output()
        display(dlg["Frame"])

def exitDlg(dlg, output_widget=None, parent=None):
    dlg["Showed"] = False
    if output_widget:
        with output_widget:
            output_widget.clear_output()
            if parent: display(parent)
    else:
        clear_output()
        if parent: display(parent)

def createQuestionDlg(question="", ok_text="确定", cancel_text="取消"):
    Dlg = {
        "Showed": False,
        "QuestionLabel": widgets.Label(value=question),
        "OkButton": widgets.Button(description=ok_text),
        "CancelButton": widgets.Button(description=cancel_text),
   }
    Dlg["Frame"] = widgets.VBox(children=[
        Dlg["QuestionLabel"],
        widgets.HBox(children=[Dlg["OkButton"], Dlg["CancelButton"]])
    ])
    return Dlg

def showQuestionDlg(dlg, parent=None, output_widget=None, ok_callback=None, cancel_callback=None, question=None):
    dlg["Showed"] = True
    if question is not None:
        dlg["QuestionLabel"].value = question
    if ok_callback:
        for iCallback in dlg["OkButton"]._click_handlers.callbacks[:]:
            dlg["OkButton"].on_click(iCallback, remove=True)
        dlg["OkButton"].on_click(ok_callback)
    if parent: dlg["OkButton"].on_click(lambda b: exitDlg(dlg, output_widget=output_widget, parent=parent))
    if cancel_callback:
        for iCallback in dlg["CancelButton"]._click_handlers.callbacks[:]:
            dlg["CancelButton"].on_click(iCallback, remove=True)
        dlg["CancelButton"].on_click(cancel_callback)
    if parent: dlg["CancelButton"].on_click(lambda b: exitDlg(dlg, output_widget=output_widget, parent=parent))
    if output_widget:
        with output_widget:
            output_widget.clear_output()
            display(dlg["Frame"])

def createGetTextDlg(desc="", default_value="", ok_text="确定", cancel_text="取消"):
    Dlg = {
        "Showed": False,
        "Text": widgets.Text(value=default_value, description=desc, disabled=False),
        "OkButton": widgets.Button(description=ok_text),
        "CancelButton": widgets.Button(description=cancel_text),
    }
    Dlg["Frame"] = widgets.VBox(children=[
        Dlg["Text"],
        widgets.HBox(children=[Dlg["OkButton"], Dlg["CancelButton"]])
    ])
    return Dlg

def showGetTextDlg(dlg, parent=None, output_widget=None, ok_callback=None, cancel_callback=None, desc=None, default_value=None):
    if desc is not None:
        dlg["Text"].description = desc
    if default_value is not None:
        dlg["Text"].value = default_value
    if ok_callback:
        for iCallback in dlg["OkButton"]._click_handlers.callbacks[:]:
            dlg["OkButton"].on_click(iCallback, remove=True)
        dlg["OkButton"].on_click(ok_callback)
    if parent: dlg["OkButton"].on_click(lambda b: exitDlg(dlg, output_widget=output_widget, parent=parent))
    if cancel_callback:
        for iCallback in dlg["CancelButton"]._click_handlers.callbacks[:]:
            dlg["CancelButton"].on_click(iCallback, remove=True)
        dlg["CancelButton"].on_click(cancel_callback)
    if parent: dlg["CancelButton"].on_click(lambda b: exitDlg(dlg, output_widget=output_widget, parent=parent))
    return showDlg(dlg, output_widget=output_widget)
# -*- coding: utf-8 -*-
import os
import tempfile
import importlib

def loadFactorDef(ft, context):
    FactorDefScript = ft.getMetaData(key="_QS_FactorDef")
    if not FactorDefScript: return None
    Factors = []
    TmpDir = tempfile.TemporaryDirectory()
    for i, iFactorDef in enumerate(FactorDefScript):
        iFilePath = TmpDir.name + os.sep + f"FactorDef{i}.py"
        with open(iFilePath, mode="w") as iDefFile:
            iDefFile.write(iFactorDef)
        ModuleSpec = importlib.util.spec_from_file_location("FactorDef", iFilePath)
        Module = importlib.util.module_from_spec(ModuleSpec)
        ModuleSpec.loader.exec_module(Module)
        iFactors, _ = getattr(Module, "defFactor")(args=context)
        Factors += iFactors
    return Factors
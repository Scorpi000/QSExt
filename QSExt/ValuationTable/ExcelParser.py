# -*- coding: utf-8 -*-
import os
import io
import requests
import packaging
from tempfile import TemporaryFile

import pandas as pd
import openpyxl
from traits.api import File, Str, Bytes, on_trait_change

from QSExt.ValuationTable.Parser import ValuationTableParser


class ExcelParser(ValuationTableParser):
    """将 Excel 类型的估值表数据标准化"""

    class __QS_ArgClass__(ValuationTableParser.__QS_ArgClass__):
        FilePath = File(label="数据文件", arg_type="File", order=0)
        URL = Str(label="URL", arg_type="String", order=1)
        FileContent = Bytes(label="文件内容", arg_type="Bytes", order=2)

        @on_trait_change("FilePath")
        def _on_FilePath_changed(self, obj, name, old, new):
            self._Owner._QS_SourceLocation = new

    # 解析文件名称
    def parseFileName(self, args={}):
        DataFile = args.get("数据文件", self.Args["数据文件"])
        URL = args.get("URL", self.Args["URL"])
        if not URL:# 本地文件
            FileName = os.path.split(DataFile)[-1]
        else:# 网络文件
            FileName = DataFile.split("/")[-1]
        return FileName

    # 读取 Excel 文件，返回：(文件内容 DataFrame, 文件名称 str)
    def readExcelFile(self, args={}):
        DataFile = args.get("数据文件", self.Args["数据文件"])
        URL = args.get("URL", self.Args["URL"])
        FileContent = args.get("文件内容", self.Args["文件内容"])
        if not URL:# 本地文件
            FileName = os.path.split(DataFile)[-1]
            if not FileContent: FileContent = DataFile
        else:# 网络文件
            FileName = DataFile.split("/")[-1]
            if not FileContent:
                Rsp = requests.get(URL)
                FileContent = Rsp.content
        # pandas <= 1.1.5 版本直接读取可能会丢失行
        if (packaging.version.parse(pd.__version__) > packaging.version.parse("1.1.5")) or (DataFile.split(".")=="xls"):
            try:
                with pd.ExcelFile(FileContent) as xlsFile:
                    xls = {iSheetName: pd.read_excel(xlsFile, sheet_name=iSheetName, header=None, dtype={0: "O"}) for iSheetName in xlsFile.sheet_names}
            except:
                if DataFile.split(".")[-1]=="xls":
                    with open(FileContent, mode="b+r") as iFile:
                        with pd.ExcelFile(iFile, engine="openpyxl") as xlsFile:
                            xls = {iSheetName: pd.read_excel(xlsFile, sheet_name=iSheetName, header=None, dtype={0: "O"}) for iSheetName in xlsFile.sheet_names}
                else:
                    with pd.ExcelFile(FileContent, engine="openpyxl") as xlsFile:
                        xls = {iSheetName: pd.read_excel(xlsFile, sheet_name=iSheetName, header=None, dtype={0: "O"}) for iSheetName in xlsFile.sheet_names}
        else:
            if isinstance(FileContent, bytes): FileContent = io.BytesIO(FileContent)
            wb = openpyxl.load_workbook(FileContent)
            with TemporaryFile(mode="w+b") as tf:
                wb.save(tf)
                try:
                    xlsFile = pd.ExcelFile(tf)
                except:
                    xlsFile = pd.ExcelFile(tf, engine="openpyxl")
                with xlsFile:
                    xls = {iSheetName: pd.read_excel(xlsFile, sheet_name=iSheetName, header=None, dtype={0: "O"}) for iSheetName in xlsFile.sheet_names}
        return xls, FileName

    def parse(self, args={}):
        xls, file_name = self.readExcelFile(args=args)
        Detail, Summary = [], []
        for iSheetName in sorted(xls.keys()):
            if (xls[iSheetName].shape[0] < 3) or (xls[iSheetName].shape[1] < 3): continue
            try:
                iDetail, iSummary = self.parseContent(xls[iSheetName], file_name, args=args)
            except Exception as e:
                Msg = f"估值文件 {self._QS_SourceLocation} 中解析失败的 sheet '{iSheetName}': {e}"
                self._QS_Logger.warning({"msg": Msg, "alarm": True, "name": "parse_failed", "source": self._QS_SourceLocation})
                continue
            Detail.append(iDetail)
            Summary.append(iSummary)
        return pd.concat(Detail, ignore_index=True), pd.concat(Summary, ignore_index=True)


# 解析本地文件
if __name__=="__main__":
    import logging
    import zipfile
    import rarfile
    from tqdm import tqdm

    from QuantStudio.Tools.FileFun import traverseDir
    from QuantStudio import __QS_Error__
    from QSExt import __QS_MainPath__
    from QSExt.ValuationTable.utils import writeValuationTable2FDB

    iLogger = logging.getLogger()

    # TargetDir = ""
    # TargetFiles = list(traverseDir(TargetDir))
    TargetFiles = [""]

    # 创建解析器
    Parser = ExcelParser(sys_args={}, logger=iLogger)

    EncodingList = [("cp437", "gbk"), ("cp437", "utf8")]
    Detail, Summary = [], []
    for iFilePath in tqdm(TargetFiles):
        iDir, iFile = os.path.split(iFilePath)
        iSuffix = iFile.split(".")[-1]
        if (iSuffix not in ("xls", "xlsx", "zip", "rar")) or iFile.startswith("~$"): continue
        if iSuffix in ("zip", "rar"):
            with (zipfile.ZipFile(iFilePath, "r") if iSuffix=="zip" else rarfile.RarFile(iFilePath, "r")) as ZipFile:
                FileList = (ZipFile.filelist if iSuffix=="zip" else ZipFile.infolist())
                for iFile in FileList:
                    if iFile.is_dir() or ("__MACOSX"+os.sep in iFile.filename): continue
                    for iSourceEncoding, iTargetEncoding in EncodingList:
                        try:
                            iParsedFile = iFile.filename.encode(iSourceEncoding).decode(iTargetEncoding)
                        except:
                            pass
                        else:
                            break
                    else:
                        iParsedFile = iFile.filename
                    iSuffix = iParsedFile.split(".")[-1]
                    if iSuffix not in ("xls", "xlsx"):
                        iLogger.error(f"不支持的文件类型: {iFilePath}/{iParsedFile}")
                        continue
                    Parser.Args["文件内容"] = ZipFile.read(iFile.filename)
                    Parser.Args["数据文件"] = os.path.split(iParsedFile)[-1]
                    Parser.Args["URL"] = ""
                    iLogger.info(f"====================== 开始解析: {iFilePath}/{iParsedFile} =======================")
                    iDetail, iSummary = Parser.parse()
                    Detail.append(iDetail)
                    iSummary.append(iSummary)
        else:
            Parser.Args["数据文件"] = iFilePath
            iDetail, iSummary = Parser.parse()
            Detail.append(iDetail)
            iSummary.append(iSummary)
    Detail = pd.concat(Detail, ignore_index=True)
    Summary = pd.concat(Summary, ignore_index=True)

    with pd.ExcelFile("VTTable.xlsx") as xlsFile:
        Detail.to_excel(xlsFile, "pf_cn_valuation_detail", index=False, header=True)
        Summary.to_excel(xlsFile, "pf_cn_valuation_summary", index=False, header=True)

    # 写入因子库
    import QuantStudio.api as QS
    TDB = QS.FactorDB.HDF5DB().connect()
    writeValuationTable2FDB(Detail, "pf_cn_valuation_detail", Summary, "pf_cn_valuation_summary", TDB, if_exists="update")

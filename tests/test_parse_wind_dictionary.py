"""验证 Wind PDF 解析的坐标归属、跨页字段和 Excel 输出约定。"""

import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from scripts import parse_wind_dictionary as parser


def make_page(rows, title="", primary_key=""):
    """构造不含私人数据的页面坐标样本。"""
    rectangles, fragments = [], []
    if title:
        fragments.append(parser.Fragment(2, 150, title, 16))
    if primary_key:
        fragments.append(parser.Fragment(2, 140, primary_key, 10))
    for index, row in enumerate(rows):
        bottom = 100 - index * 20
        for column, text in enumerate(row):
            left = column * 100
            rectangles.append((left, bottom, left + 100, bottom + 20))
            if text:
                fragments.append(parser.Fragment(left + 2, bottom + 5, text, 10))
    return rectangles, fragments


class ParseWindDictionaryTests(unittest.TestCase):
    """覆盖解析失败条件和导出结构。"""

    def test_original_pdf_text_and_watermark_filter(self):
        """直接读取原始文本，排除水印并保留完整列名。"""
        writer = PdfWriter()
        page = writer.add_blank_page(width=400, height=400)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        stream = DecodedStreamObject()
        stream.set_data(
            b"0 0 100 40 re S\n100 0 100 40 re S\n"
            b"BT /F1 15 Tf 1 0 0 1 5 20 Tm (DF1234567890) Tj ET\n"
            b"BT /F1 10 Tf 1 0 0 1 5 10 Tm (S_INFO_WINDCODE) Tj ET\n"
            b"BT /F1 10 Tf 1 0 0 1 105 10 Tm (VARCHAR2\\(40\\)) Tj ET\n"
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            writer.write(path)
            rectangles, fragments = parser.extract_page(PdfReader(path).pages[0])
        self.assertEqual(parser.cell_text(rectangles[0], fragments), "S_INFO_WINDCODE")
        self.assertEqual(parser.cell_text(rectangles[1], fragments), "VARCHAR2(40)")
        self.assertEqual(len(fragments), 2)

    def parse_pages(self, pages):
        """用模拟页面解析跨页字段样本。"""
        with patch.object(parser, "PdfReader", return_value=SimpleNamespace(pages=list(range(len(pages))))):
            with patch.object(parser, "extract_page", side_effect=pages):
                return parser.parse_pdf(Path("Example_数据字典_V2.pdf"))

    def test_multi_page_and_wrapped_title(self):
        pages = [
            make_page([
                parser.PDF_HEADERS,
                ("1", "Wind代码", "S_INFO_WINDCODE", "VARCHAR2(40)", "WindCustomCode", "100.00%", "证券编码"),
            ], "示例表 -Example", "业务主键：Wind代码"),
            make_page([("2", "收盘价(元)", "S_DQ_CLOSE", "NUMBER(20,4)", "", "99.00%", "当日收盘价")]),
        ]
        result = self.parse_pages(pages)
        self.assertEqual(result.name, "示例表")
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.fields[1][:3], ("收盘价(元)", "s_dq_close", "NUMBER(20,4)"))
        self.assertIn("枚举/外部引用：WindCustomCode", result.fields[0][3])

    def test_missing_sequence_rejected(self):
        with self.assertRaisesRegex(ValueError, "字段序号不连续"):
            self.parse_pages([make_page([
                parser.PDF_HEADERS, ("2", "代码", "CODE", "VARCHAR2(40)", "", "", ""),
            ], "示例表 - Example")])

    def test_duplicate_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "英文列名重复"):
            self.parse_pages([make_page([
                parser.PDF_HEADERS,
                ("1", "代码", "CODE", "VARCHAR2(40)", "", "", ""),
                ("2", "代码二", "CODE", "VARCHAR2(40)", "", "", ""),
            ], "示例表 - Example")])

    def test_excel_headers_blanks_and_literal_description(self):
        table = parser.ParsedTable("sample.pdf", "示例", "Example", "说明", [
            ("字段", "field", "NUMBER(20,4)", "=原始释义"),
        ], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.xlsx"
            parser.write_workbook([table], path)
            workbook = load_workbook(path)
            self.assertEqual(workbook.sheetnames, ["TableInfo", "FactorInfo"])
            self.assertEqual(tuple(c.value for c in workbook["TableInfo"][1]), parser.TABLE_HEADERS)
            self.assertEqual(tuple(c.value for c in workbook["FactorInfo"][1]), parser.FACTOR_HEADERS)
            for coordinate in ("C2", "D2"):
                self.assertIsNone(workbook["TableInfo"][coordinate].value)
            for coordinate in ("E2", "F2", "H2"):
                self.assertIsNone(workbook["FactorInfo"][coordinate].value)
            self.assertEqual(workbook["FactorInfo"]["G2"].data_type, "s")
            self.assertEqual(workbook["FactorInfo"]["G2"].value, "=原始释义")
            workbook.close()

    def test_latest_version_and_partial_failure_report(self):
        """保留最高版本，明确记录失败，且返回失败状态。"""
        old = parser.ParsedTable("Example_数据字典_V1.pdf", "示例", "Example", "", [
            ("旧字段", "old_field", "VARCHAR2(10)", ""),
        ], 1)
        new = parser.ParsedTable("Example_数据字典_V2.pdf", "示例", "Example", "", [
            ("新字段", "new_field", "VARCHAR2(40)", ""),
        ], 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("Bad_数据字典_V1.pdf", old.source, new.source):
                (root / name).touch()
            output = root / "result.xlsx"
            with patch.object(parser, "parse_pdf", side_effect=[ValueError("样本损坏"), old, new]):
                with redirect_stdout(io.StringIO()):
                    status = parser.main(["--input-dir", str(root), "--output", str(output)])
            self.assertEqual(status, 1)
            workbook = load_workbook(output)
            self.assertEqual(workbook["TableInfo"].max_row, 2)
            self.assertEqual(workbook["FactorInfo"]["C2"].value, "new_field")
            workbook.close()
            report = output.with_suffix(".解析记录.csv").read_text(encoding="utf-8-sig")
            self.assertIn("旧版本未导出", report)
            self.assertIn("样本损坏", report)


if __name__ == "__main__":
    unittest.main()

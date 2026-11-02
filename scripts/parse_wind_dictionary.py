"""将 Wind 数据字典 PDF 批量解析为与 WindDB2Info 相同结构的 Excel。

实现逻辑：使用 pypdf 读取 PDF 原始文本和矩形单元格坐标，过滤重复水印，
按单元格归属恢复中文名、完整英文列名、类型和说明，不依赖 OCR 或视觉换行。
逐表校验字段序号、字段名、类型以及重复项；同一物理表采用最高版本。
失败文件写入旁置 CSV，返回非零退出码。
Excel 只生成 TableInfo、FactorInfo 两张表，指定的五个配置列始终留空。

使用方法：先安装 ``pypdf`` 和 ``openpyxl``，然后在 QSExt 仓库根目录执行：
    python scripts/parse_wind_dictionary.py --input-dir <PDF目录> --output <结果.xlsx>
可用 ``--pattern AShare*.pdf`` 限制试验范围。默认不覆盖已有输出；重新生成时
显式传入 ``--overwrite``。旁置的 ``<结果名>.解析记录.csv`` 记录逐文件结果。
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pypdf import PdfReader


TABLE_HEADERS = ("TableName", "DBTableName", "TableClass", "DefaultArgs", "Description")
FACTOR_HEADERS = (
    "TableName", "FieldName", "DBFieldName", "DataType", "FieldType",
    "Supplementary", "Description", "RelatedSQL",
)
PDF_HEADERS = ("序号", "字段中文名", "字段名", "字段类型", "枚举/外部引用", "有值率", "释义")
DATA_TYPE = re.compile(r"[A-Z][A-Z0-9_]*(?:\(\d+(?:,\d+)?\))?")


@dataclass(frozen=True)
class Fragment:
    """保存 PDF 原始文本的定位信息。"""

    x: float
    y: float
    text: str
    size: float


@dataclass
class ParsedTable:
    """保存一份数据字典及其校验所需信息。"""

    source: str
    name: str
    db_name: str
    description: str
    fields: list[tuple[str, ...]]
    pages: int


def transform(x, y, matrix):
    """将局部坐标转换为页面坐标。"""
    return (
        x * float(matrix[0]) + y * float(matrix[2]) + float(matrix[4]),
        x * float(matrix[1]) + y * float(matrix[3]) + float(matrix[5]),
    )


def extract_page(page):
    """读取页面的矩形边框和文本，过滤水印。

    Args:
        page: pypdf 页面对象。

    Returns:
        二元组，分别为单元格矩形列表和文本片段列表。
    """
    rectangles = set()
    fragments = []

    def visit_operand(operator, operands, cm, tm):
        if operator == b"re":
            x, y, width, height = map(float, operands)
            x0, y0 = transform(x, y, cm)
            x1, y1 = transform(x + width, y + height, cm)
            if abs(x1 - x0) > 1 and abs(y1 - y0) > 1:
                rectangles.add(tuple(round(v, 2) for v in (
                    min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                )))

    def visit_text(text, cm, tm, font, size):
        text = text.replace("\r", "").replace("\n", "").strip()
        if not text:
            return
        # 此批 PDF 的水印为 15 磅账号和邮箱，正文为 10/12/16 磅。
        if abs(size - 15) < 0.01 and re.fullmatch(r"(?:DF\d+|\S+@\S+)", text):
            return
        x, y = transform(float(tm[4]), float(tm[5]), cm)
        fragments.append(Fragment(x, y, text, size))

    page.extract_text(visitor_operand_before=visit_operand, visitor_text=visit_text)
    return sorted(rectangles, key=lambda r: (-r[3], r[0])), fragments


def cell_text(rectangle, fragments):
    """按文本起点归属恢复单元格，避免视觉换行破坏完整列名。"""
    x0, y0, x1, y1 = rectangle
    return "".join(
        item.text for item in fragments
        if x0 <= item.x < x1 and y0 <= item.y < y1
    )


def parse_pdf(path: Path) -> ParsedTable:
    """解析单份 PDF，并检查字段序号及字段定义。

    Args:
        path: 数据字典 PDF 路径。

    Returns:
        已通过结构校验的数据字典。

    Raises:
        ValueError: 标题、字段表头、字段序号或字段定义不符合预期。
    """
    reader = PdfReader(path)
    filename = re.fullmatch(r"(.+)_数据字典_V\d+", path.stem)
    if not filename:
        raise ValueError("文件名须采用 <物理表名>_数据字典_V<版本号>.pdf 格式")
    db_name = filename[1]
    name = ""
    metadata = []
    fields = []
    header_seen = False
    for page_number, page in enumerate(reader.pages, 1):
        rectangles, fragments = extract_page(page)
        if page_number == 1:
            title = "".join(f.text for f in fragments if abs(f.size - 16) < 0.01)
            match = re.fullmatch(r"(.+?)\s*-\s*" + re.escape(db_name), title)
            if not match:
                raise ValueError(f"标题与文件名不匹配：{title!r}")
            name = match[1].strip()
            metadata.extend(
                f.text for f in fragments if f.text.startswith("业务主键")
            )
        rows = defaultdict(list)
        for rect in rectangles:
            rows[(round(rect[1], 1), round(rect[3], 1))].append(rect)
        for _, cells in sorted(rows.items(), key=lambda item: -item[0][1]):
            cells.sort(key=lambda rect: rect[0])
            values = tuple(cell_text(cell, fragments) for cell in cells)
            if len(values) == 4 and page_number == 1:
                for label, value in zip(values[::2], values[1::2]):
                    if label and value:
                        metadata.append(label + value)
            elif len(values) == 7:
                if values == PDF_HEADERS:
                    header_seen = True
                    continue
                if not header_seen:
                    raise ValueError(f"第 {page_number} 页的字段表缺少预期表头")
                if not values[0].isdigit() or int(values[0]) != len(fields) + 1:
                    raise ValueError(f"第 {page_number} 页字段序号不连续：{values[0]!r}")
                _, field_name, db_field, data_type, reference, coverage, meaning = values
                db_field = re.sub(r"\s+", "", db_field).lower()
                data_type = re.sub(r"\s+", "", data_type).upper()
                if not field_name or not re.fullmatch(r"[a-z][a-z0-9_$#]*", db_field):
                    raise ValueError(f"字段名称无效：{field_name!r} / {db_field!r}")
                if not DATA_TYPE.fullmatch(data_type):
                    raise ValueError(f"字段 {db_field} 类型无效：{data_type!r}")
                descriptions = [meaning] if meaning else []
                if reference:
                    descriptions.append("枚举/外部引用：" + reference)
                if coverage:
                    descriptions.append("有值率：" + coverage)
                fields.append((field_name, db_field, data_type, "\n".join(descriptions)))
    if not name or not fields:
        raise ValueError("未提取到表名或字段")
    duplicates = [key for key, count in Counter(f[1] for f in fields).items() if count > 1]
    if duplicates:
        raise ValueError(f"英文列名重复：{duplicates}")
    return ParsedTable(path.name, name, db_name, "\n".join(metadata), fields, len(reader.pages))


def write_workbook(tables: list[ParsedTable], output: Path):
    """导出固定表头，并对中文表名重复的情况添加物理表名以保持关联唯一。"""
    workbook = Workbook()
    table_sheet = workbook.active
    table_sheet.title = "TableInfo"
    factor_sheet = workbook.create_sheet("FactorInfo")
    table_sheet.append(TABLE_HEADERS)
    factor_sheet.append(FACTOR_HEADERS)
    names = Counter(table.name for table in tables)
    for table in tables:
        name = table.name if names[table.name] == 1 else f"{table.name}（{table.db_name}）"
        for value in (name, table.db_name, table.description, *(v for f in table.fields for v in f)):
            if len(value) > 32767:
                raise ValueError(f"表 {table.db_name} 的内容超出 Excel 单元格长度限制")
        table_sheet.append((name, table.db_name, None, None, table.description))
        for field_name, db_field, data_type, description in table.fields:
            factor_sheet.append((name, field_name, db_field, data_type, None, None, description, None))
    for sheet, widths in (
        (table_sheet, (40, 42, 20, 20, 100)),
        (factor_sheet, (40, 36, 42, 22, 20, 20, 100, 20)),
    ):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24476B")
        for column, width in enumerate(widths, 1):
            sheet.column_dimensions[sheet.cell(1, column).column_letter].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                # PDF 内容一律保存为字符串，避免以等号开头的释义成为公式。
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    workbook.save(output)


def main(argv=None):
    """解析命令行参数，执行导出并写入逐文件解析记录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="PDF 所在目录")
    parser.add_argument("--output", type=Path, required=True, help="输出 Excel 路径")
    parser.add_argument("--pattern", default="*.pdf", help="文件匹配规则")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有输出和记录")
    args = parser.parse_args(argv)
    report_path = args.output.with_suffix(".解析记录.csv")
    if not args.overwrite and (args.output.exists() or report_path.exists()):
        parser.error("输出已存在；如需覆盖，请使用 --overwrite")
    files = sorted(args.input_dir.glob(args.pattern))
    if not files:
        parser.error("输入目录中没有匹配的 PDF")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tables, report = [], []
    for index, path in enumerate(files, 1):
        try:
            table = parse_pdf(path)
            tables.append(table)
            report.append((path.name, table.name, table.db_name, table.pages, len(table.fields), "成功", ""))
        except Exception as error:
            report.append((path.name, "", "", "", 0, "失败", str(error)))
            print(f"解析失败：{path.name}：{error}", flush=True)
        if index % 50 == 0 or index == len(files):
            print(f"已处理 {index}/{len(files)}，成功 {len(tables)}", flush=True)
    selected = {}
    for table in tables:
        version = int(re.search(r"_V(\d+)\.pdf$", table.source, re.IGNORECASE)[1])
        key = table.db_name.lower()
        if key not in selected or version > selected[key][0]:
            selected[key] = (version, table)
    exported = [item[1] for item in selected.values()]
    # 所有版本均解析并校验，Excel 中每个物理表只使用最高版本。
    retained = {table.source for table in exported}
    report = [
        row if row[5] == "失败" or row[0] in retained
        else (*row[:5], "成功（旧版本未导出）", "Excel 使用同表的最高版本")
        for row in report
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("文件", "TableName", "DBTableName", "页数", "字段数", "状态", "说明"))
        writer.writerows(report)
    if exported:
        write_workbook(exported, args.output)
    print(f"结果：{len(exported)} 张表，{sum(len(t.fields) for t in exported)} 个字段，失败 {len(files) - len(tables)}，旧版本 {len(tables) - len(exported)}", flush=True)
    print(f"Excel：{args.output}\n解析记录：{report_path}", flush=True)
    return int(len(files) != len(tables))


if __name__ == "__main__":
    raise SystemExit(main())

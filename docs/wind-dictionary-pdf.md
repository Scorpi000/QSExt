# Wind 数据字典 PDF 转 Excel

`scripts/parse_wind_dictionary.py` 将 Wind 导出的逐表 PDF 数据字典转换为
与 `QSExt/Resource/WindDB2Info.xlsx` 列结构相同的 Excel。
生成文件单独保存，不覆盖参考模板。

## 运行

以下命令均在 QSExt 项目根目录执行，使用已安装脚本依赖的 Python 环境：

```powershell
python -m pip install pypdf openpyxl
python scripts/parse_wind_dictionary.py --input-dir "<Wind数据字典目录>" --output "<输出目录>/WindDB2Info_from_pdf.xlsx"
```

可用 `--pattern "AShare*.pdf"` 限制输入范围。已有 Excel 或解析记录时默认拒绝
覆盖；确认重新生成后增加 `--overwrite`。

输出为 Excel 和同名的 `.解析记录.csv`。CSV 使用带 BOM 的 UTF-8 编码，
记录每份 PDF 的物理表名、中文表名、页数、字段数、解析状态和失败原因。
部分文件解析失败时仍导出成功部分，命令返回退出码 1；全部成功时返回 0。
生成文件属于导出产物，无需提交到源码仓库。

## 解析和映射

此批 PDF 含可直接读取的文本，无需 OCR。脚本使用 PDF 的原始文字定位和
矩形单元格边界恢复内容，过滤账号与邮箱水印。视觉排版中的列名折行不会
变成 Excel 中的空格或换行。文件名须为 `<物理表名>_数据字典_V<版本号>.pdf`。
同一物理表的所有版本都会解析、校验，Excel 只使用最高版本，CSV 保留旧版本记录。

| Sheet | 列 | 来源或处理方式 |
| --- | --- | --- |
| TableInfo | TableName | PDF 标题中的中文表名 |
| TableInfo | DBTableName | PDF 标题与文件名交叉验证后的物理表名，保留大小写 |
| TableInfo | TableClass、DefaultArgs | 留空 |
| TableInfo | Description | 业务主键和简介中的数据库、模块、数据范围、产品说明等信息 |
| FactorInfo | TableName | 对应 TableInfo 的中文表名 |
| FactorInfo | FieldName | 字段中文名，包含原始单位 |
| FactorInfo | DBFieldName | 完整物理列名，按参考 Excel 统一转为小写 |
| FactorInfo | DataType | 完整原始类型，例如 `VARCHAR2(40)`、`NUMBER(20,4)` |
| FactorInfo | FieldType、Supplementary、RelatedSQL | 留空 |
| FactorInfo | Description | 释义，并附加非空的枚举/外部引用、有值率 |

若中文表名重复，会附加物理表名，以保持两张 Sheet 的关联唯一。
字段序号必须从 1 连续递增，物理列名不得重复，字段名和类型必须有效。
不会补造 PDF 未提供的内部字段，例如部分旧模板中的 `object_id`。
由于配置列按要求留空，产物是元数据整理结果，后续用于数据库适配器时仍需补充配置。

## 本次验证

2026-11-02 对目录中全部 794 份 PDF 进行了试验，全部解析成功。
其中 `AShareIntroduction` 同时存在 V5、V6，采用 V6，最终输出
793 张表、14,761 个字段。结果文件为源 PDF 目录中的
`WindDB2Info_from_pdf.xlsx`，解析记录为 `WindDB2Info_from_pdf.解析记录.csv`。

使用 PyMuPDF 独立读取全部 794 份 PDF 的单元格边框，逐文件核对字段行数，
均与解析记录一致。Excel 中的 793 个物理表名及中文表名与原目录
`导出结果汇总.csv` 中的成功记录完全一致；另外检查了固定表头、关联唯一性、
指定配置列全部为空，以及没有账号、邮箱水印混入。这些是结构校验，
未逐字人工审核所有释义。

自动化测试覆盖原始 PDF 文字提取、水印过滤、跨页字段、长标题分隔空格变化、
序号缺失、重复列名、最高版本选择、部分失败记录、Excel 留空列与字面字符串：

```powershell
python -m unittest discover -s tests -p test_parse_wind_dictionary.py -v
```

试验使用 pypdf 6.21.4；PyMuPDF 仅用于本次独立核对，不是导出脚本的运行依赖。

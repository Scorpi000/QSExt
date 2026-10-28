"""定义源码的静态格式转换与 notebook 单元位置映射。"""
import json
from pathlib import PurePosixPath
import traceback


class NotebookDefinitionMissing(ValueError):
    """未标记定义区域的交互 notebook 不属于定义库条目。"""


def format_definition_error(error, source_maps):
    """将生成源码中的异常位置还原为 notebook 单元位置。

    Args:
        error: 编译或执行定义时产生的异常。
        source_maps: 以生成 Python 路径为键的单元映射。

    Returns:
        包含原 notebook 路径、单元序号及行号的错误消息。
    """
    locations = [(frame.filename, frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]
    if isinstance(error, SyntaxError):
        locations.append((error.filename or "", error.lineno or 1))
    for filename, line in reversed(locations):
        for generated, source in source_maps.items():
            if filename != generated and not filename.replace("\\", "/").endswith("/" + generated):
                continue
            for cell in source["cells"]:
                if cell["start_line"] <= line <= cell["end_line"]:
                    detail = error.msg if isinstance(error, SyntaxError) else str(error)
                    return f'{source["path"]}: 第 {cell["cell"]} 个单元，第 {line - cell["start_line"] + 1} 行: {detail}'
    return str(error)


def extract_notebook_source(content, path):
    """静态提取最后一个定义标签及之前的代码，不读取执行输出。

    Args:
        content: 原始 notebook JSON 文本。
        path: notebook 相对路径，用于错误定位。

    Returns:
        Python 源码及其单元位置映射。

    Raises:
        ValueError: notebook 格式、标签或定义区域中的 Python 语法无效。
    """
    try:
        notebook = json.loads(content)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{path}: notebook JSON 无效") from error
    if not isinstance(notebook, dict) or notebook.get("nbformat") != 4 or not isinstance(notebook.get("cells"), list):
        raise ValueError(f"{path}: 需要 nbformat 4 的 notebook")
    metadata = notebook.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: notebook 元信息无效")
    language_info = metadata.get("language_info", {})
    if not isinstance(language_info, dict):
        raise ValueError(f"{path}: notebook 语言元信息无效")
    language = language_info.get("name", "python")
    if not isinstance(language, str) or language.lower() != "python":
        raise ValueError(f"{path}: 仅支持 Python notebook")
    selected, last_tagged = [], -1
    for index, cell in enumerate(notebook["cells"], 1):
        if not isinstance(cell, dict):
            raise ValueError(f"{path}: 第 {index} 个单元格式无效")
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list) and all(isinstance(line, str) for line in source):
            source = "".join(source)
        if not isinstance(source, str) or not isinstance(cell.get("metadata", {}), dict):
            raise ValueError(f"{path}: 第 {index} 个单元源码或元信息无效")
        selected.append((index, cell.get("id"), source))
        tags = cell.get("metadata", {}).get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"{path}: 第 {index} 个单元标签无效")
        if {"node-def", "strategy-def"}.intersection(tags):
            last_tagged = len(selected)
    if last_tagged < 0:
        raise NotebookDefinitionMissing(f"{path}: 请为定义区域的最后一个代码单元添加 node-def 标签（兼容 strategy-def）")
    code, cells, line = [], [], 1
    for index, cell_id, source in selected[:last_tagged]:
        # 单元之间固定分隔，不将输出、执行次数或单元序号加入源码摘要。
        text = source.rstrip("\r\n") + "\n"
        length = len(text.splitlines())
        cells.append({"cell": index, "id": cell_id, "start_line": line, "end_line": line + length - 1})
        code.append(text + "\n")
        line += length + 1
    code = "".join(code)
    generated = str(PurePosixPath(path).with_suffix(".py"))
    mapping = {"path": path, "cells": cells}
    try:
        compile(code, generated, "exec")
    except SyntaxError as error:
        raise ValueError(format_definition_error(error, {generated: mapping})) from error
    return code, mapping


def normalize_definition_sources(files):
    """将混合 Python/notebook 文件转换为无模块名冲突的 Python 源码。

    Args:
        files: 相对文件路径到原始文本的映射。

    Returns:
        可供模块加载和快照保存的 Python 源码映射，以及 notebook 来源映射。

    Raises:
        ValueError: 文件路径无效，或转换后存在模块名冲突。
    """
    sources, source_maps, names = {}, {}, set()
    for path, content in files.items():
        item = PurePosixPath(path)
        if item.suffix not in (".py", ".ipynb") or item.is_absolute() or any(
            not part.isidentifier() for part in item.with_suffix("").parts
        ) or "\\" in path:
            raise ValueError(f"无效的 Python 定义路径: {path}")
        generated = item.with_suffix(".py").as_posix()
        parts = item.with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts).casefold()
        if module in names:
            raise ValueError(f"定义模块名冲突: {path}，不能同时提供同名 .py 和 .ipynb 或仅大小写不同的文件")
        names.add(module)
        if item.suffix == ".ipynb":
            content, source_maps[generated] = extract_notebook_source(content, path)
        sources[generated] = content
    return sources, source_maps

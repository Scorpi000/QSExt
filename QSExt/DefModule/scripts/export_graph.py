"""将定义脚本导出为 GraphDocument JSON；节点实现由组件目录提供。"""
import argparse
import json
from pathlib import Path

from QSExt.DefModule.DefContent import DefInput
from QSExt.Graph.api import import_definition, load_component_directory


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出计算图；不会运行引擎或写入因子库")
    parser.add_argument("--source-dir", type=Path, required=True, help="定义脚本及依赖的根目录")
    parser.add_argument("--entry", required=True, help="入口相对于 source-dir 的 .py 路径")
    parser.add_argument("--components-dir", type=Path, required=True, help="提供全部节点与算子的组件目录")
    parser.add_argument("--model-args", default="{}", help="模型参数 JSON 对象")
    parser.add_argument("--output", type=Path, required=True, help="输出 GraphDocument JSON 文件")
    options = parser.parse_args(argv)
    args = json.loads(options.model_args)
    if not isinstance(args, dict):
        parser.error("--model-args 必须是 JSON 对象")
    root = options.source_dir.resolve(strict=True)
    files = {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))
             if path.resolve().is_relative_to(root)}
    registry = load_component_directory(options.components_dir)
    document = import_definition(files, options.entry, registry, DefInput(), model_args=args)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    return document


if __name__ == "__main__":
    main()

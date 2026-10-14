"""导出供 GUI 或其他客户端复用的图协议 JSON Schema。

实现逻辑：仅导入 QSExt.Graph.Protocol，调用 Pydantic 的模型 Schema
生成器，不加载 QuantStudio 对象、数据库组件或应用服务。

使用方法：在仓库根目录执行 ``python scripts/export_graph_schema.py``，
默认写入 ``docs/Graph/graph.schema.json``；通过 ``--output`` 指定其他文件。

Args:
    --output: 目标 JSON 文件路径，父目录不存在时自动创建。
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from QSExt.Graph.Protocol import GraphDocument


def main():
    """解析输出路径并写入 UTF-8 Schema。"""
    parser = argparse.ArgumentParser(description="导出计算图协议 Schema")
    parser.add_argument("--output", default="docs/Graph/graph.schema.json")
    arguments = parser.parse_args()
    path = Path(arguments.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(GraphDocument.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()

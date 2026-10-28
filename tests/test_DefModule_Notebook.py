"""notebook 统一入口、源码转换、错误定位和通用节点回归。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorDB import FactorDB
from QSExt.DefModule.DefContent import DefInput, build_graph_def
from QSExt.DefModule.Source import extract_notebook_source, normalize_definition_sources
from QSExt.DefModule.utils import load_notebook_as_module
from QSExt.Graph.api import create_default_registry, import_definition


def notebook(code, *, debug='raise AssertionError("不应执行调试单元")', tags=None):
    """生成不依赖 Jupyter 的最小定义 notebook。"""
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"cell_type": "markdown", "source": "说明", "metadata": {}},
        {"cell_type": "code", "source": code, "metadata": {"tags": tags or ["node-def"]},
         "id": "definition", "execution_count": 99, "outputs": [{"text": "历史结果"}]},
        {"cell_type": "code", "source": debug, "metadata": {}},
    ]}, ensure_ascii=False)


class NotebookDefinitionTests(unittest.TestCase):
    """验证提取结果与 Python 文件共用同一构图协议。"""

    def test_static_extraction_order_source_forms_and_output_independence(self):
        text = notebook('def defNode(di):\n    return []\n')
        data = json.loads(text)
        data["cells"].insert(1, {"cell_type": "code", "source": ["value = 1\n", "other = 2"], "metadata": {}})
        sources, mappings = normalize_definition_sources({"model.ipynb": json.dumps(data)})
        self.assertIn("value = 1\nother = 2", sources["model.py"])
        self.assertNotIn("AssertionError", sources["model.py"])
        self.assertEqual(mappings["model.py"]["cells"][-1]["cell"], 3)
        data["cells"][2].update(outputs=[], execution_count=None)
        self.assertEqual(sources, normalize_definition_sources({"model.ipynb": json.dumps(data)})[0])

    def test_rejects_missing_tags_invalid_paths_and_module_collisions(self):
        text = notebook("pass")
        data = json.loads(text)
        data["cells"][1]["metadata"] = {}
        with self.assertRaisesRegex(ValueError, "node-def"):
            extract_notebook_source(json.dumps(data), "model.ipynb")
        for files in ({"model.py": "", "model.ipynb": text}, {"../model.ipynb": text}, {"A.py": "", "a.py": ""}):
            with self.subTest(files=list(files)), self.assertRaises(ValueError):
                normalize_definition_sources(files)

    def test_error_location_and_no_fallback_execution(self):
        with self.assertRaisesRegex(ValueError, "model.ipynb: 第 2 个单元，第 1 行"):
            extract_notebook_source(notebook("def broken(:"), "model.ipynb")
        code = 'def defNode(di):\n    raise RuntimeError("定义失败")\n'
        with self.assertRaisesRegex(ValueError, "model.ipynb: 第 2 个单元，第 2 行: 定义失败"):
            import_definition({"model.ipynb": notebook(code)}, "model.ipynb", create_default_registry(), DefInput())

    def test_python_and_notebook_graphs_are_equivalent(self):
        code = 'from QuantStudio.Factor.Factor import DataFactor\ndef defNode(di):\n    return [DataFactor(di.ModelArgs["value"],args={"Name":"value"})]\n'
        registry = create_default_registry()
        python = import_definition({"model.py": code}, "model.py", registry, DefInput(), model_args={"value": 4})
        converted = import_definition({"model.ipynb": notebook(code, tags=["strategy-def"])}, "model.ipynb", registry,
                                      DefInput(), model_args={"value": 4})
        for document in (python, converted):
            self.assertEqual(list(document.outputs), ["value"])
            self.assertEqual(document.blocks[0].args["Data"], 4)
        self.assertEqual(converted.extensions["qsweb"]["definition_import"]["entry"], "model.ipynb")

    def test_local_loader_keeps_meta_and_uses_uniform_entry(self):
        code = '__GRAPH_META__={"MaxLookBack":0}\nfrom QuantStudio.Factor.Factor import DataFactor\ndef defNode(di): return [DataFactor(7)]'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.ipynb"
            path.write_text(notebook(code), encoding="utf-8")
            module = load_notebook_as_module(str(path))
            built = build_graph_def([(module, {}, {})], DefInput())
            self.assertEqual(built.requested[0].NodeList[0].Args.Data, 7)
            self.assertEqual(built.max_lookback, 0)

    def test_example_builds_factor_account_statistics_and_report_without_connecting(self):
        path = Path(__file__).resolve().parents[1] / "QSExt/DefModule/examples/stock_cn_strategy_example.ipynb"
        with patch("QuantStudio.Factor.BaoStockDB.BaoStockDB.connect", side_effect=AssertionError("导入不应连接数据库")):
            module = load_notebook_as_module(str(path))
        database = Mock(spec=FactorDB)
        database.getTable.return_value.getFactor.return_value = DataFactor(10, args={"Name": "close"})
        nodes = module.defNode(DefInput(FDB={"BSDB": database}, SectionIDs=["A"]))
        self.assertEqual(len(nodes), 5)
        self.assertEqual([node.Name for node in nodes], ["short_ma", "long_ma", "ma_strategy", "strategy_stats", "strategy_report"])
        self.assertIs(nodes[3].Deps[0], nodes[2])


if __name__ == "__main__":
    unittest.main()

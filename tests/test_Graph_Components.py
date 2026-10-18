"""组件列表的显式公开、自动注册、稳定标识与错误定位验收。"""
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from QSExt.Graph.api import compile_graph, describe_block, load_component_directory, validate_graph


class ComponentTests(unittest.TestCase):
    """使用独立的临时服务目录验证完整加载入口。"""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name, source):
        """写入测试组件源码。"""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")

    def test_only_listed_classes_are_exposed(self):
        """文件名不限于 definition，普通导入与辅助模型不被注册。"""
        self.write("operators.py", '''
            from QuantStudio.Factor.FactorOperator import RollingMean, RollingRank
            CATEGORY = "因子加工"
            COMPONENTS = [RollingMean]
        ''')
        registry = load_component_directory(self.root)
        descriptions = registry.list_definitions()
        self.assertEqual(len(descriptions), 1)
        self.assertEqual(descriptions[0].definition.id, "QuantStudio.Factor.FactorOperator.RollingMean")
        self.assertEqual(descriptions[0].category, "因子加工")
        self.assertEqual(descriptions[0].operations, ["apply", "bind"])
        self.assertEqual(descriptions[0].inputs[0].name, "x")
        with self.assertRaisesRegex(ValueError, "冻结"):
            registry.register(registry.get(descriptions[0].definition))

    def test_relative_import_and_package_execute_once(self):
        """先由相对导入加载的声明模块不会再次执行或漏掉列表。"""
        self.write("operators/__init__.py", '''
            from .helper import calls
            calls.append("package")
        ''')
        self.write("operators/a.py", '''
            from .z import LocalFactor
            from QSExt.Graph.api import Component
            COMPONENTS = [Component(LocalFactor, id="named", category="自选", version=2)]
        ''')
        self.write("operators/helper.py", "calls = []\n")
        self.write("operators/z.py", '''
            from .helper import calls
            from QuantStudio.Factor.Factor import DataFactor
            calls.append("definition")
            class LocalFactor(DataFactor):
                """自定义常量。"""
                def __init__(self, *args, **kwargs):
                    raise AssertionError("加载元信息不能创建节点")
            COMPONENTS = [LocalFactor]
        ''')
        registry = load_component_directory(self.root)
        self.assertEqual(len(registry.list_definitions()), 2)
        descriptor = registry.describe_definition("named", 2)
        self.assertEqual(descriptor.category, "自选")
        local_class = registry.types._types["components.operators.z.LocalFactor"]
        helper = sys.modules[local_class.__module__.rsplit(".", 1)[0] + ".helper"]
        self.assertEqual(helper.calls, ["package", "definition"])
        self.assertEqual(set(registry.sources), {"operators/__init__.py", "operators/a.py", "operators/helper.py", "operators/z.py"})

    def test_local_id_survives_relocation_and_source_change(self):
        """标识不依赖绝对路径、源码摘要或导入批次。"""
        source = '''
            from QuantStudio.Factor.Factor import DataFactor
            class LocalFactor(DataFactor):
                """本地常量。"""
            COMPONENTS = [LocalFactor]
        '''
        self.write("custom/factors.py", source)
        first = load_component_directory(self.root)
        self.write("custom/factors.py", textwrap.dedent(source) + "\n# 修改说明\n")
        second = load_component_directory(self.root)
        with tempfile.TemporaryDirectory() as relocated:
            path = Path(relocated) / "custom"
            path.mkdir()
            (path / "factors.py").write_text(textwrap.dedent(source), encoding="utf-8")
            third = load_component_directory(relocated)
        for registry in (first, second, third):
            descriptor = registry.list_definitions()[0]
            self.assertEqual(descriptor.definition.id, "components.custom.factors.LocalFactor")
            self.assertEqual(descriptor.outputs["result"].type_id, "components.custom.factors.LocalFactor")
        self.assertNotEqual(first.sources, second.sources)

    def test_factory_declares_concrete_output_and_builds_on_demand(self):
        """组合组件延迟构图，先出现的报告仍能检查具体结果类型。"""
        self.write("a_report.py", '''
            from QuantStudio.Core.Input import InputModel
            from QuantStudio.Core.Node import Node
            from .z_analysis import Result
            class Report(Node):
                class __QS_DepClass__(InputModel):
                    result: Result
            COMPONENTS = [Report]
        ''')
        self.write("z_analysis.py", '''
            from QuantStudio.Core.Input import InputModel
            from QuantStudio.Factor.Factor import DataFactor
            from QSExt.Graph.api import Component
            calls = []
            class Args(InputModel):
                value: int = 7
            class Result(DataFactor):
                """组合组件的具体结果。"""
            def build(block, args, inputs):
                calls.append("build")
                return Result(args["value"])
            COMPONENTS = [Component(id="analysis", args_model=Args, input_model=InputModel,
                output_type=Result, builder=build)]
        ''')
        registry = load_component_directory(self.root)
        builder = registry.get("analysis").builder
        module = sys.modules[builder.__module__]
        self.assertEqual(module.calls, [])
        doc = {"blocks": [
            {"id": "analysis", "definition": {"id": "analysis"}, "operation": "build"},
            {"id": "report", "definition": {"id": "components.a_report.Report"}, "operation": "build",
             "inputs": {"result": {"kind": "reference", "block": "analysis"}}},
        ], "outputs": {"result": {"kind": "reference", "block": "analysis"}}}
        self.assertFalse([error for error in validate_graph(doc, registry) if error.severity == "error"])
        self.assertEqual(module.calls, [])
        compiled = compile_graph(doc, registry)
        self.assertIsInstance(compiled.outputs["result"], module.Result)
        self.assertEqual(module.calls, ["build"])

    def test_bad_declarations_fail_with_list_position(self):
        """错误列表项、重复标识和错误模型都在启动期失败。"""
        prefix = "from QuantStudio.Factor.Factor import DataFactor\nfrom QSExt.Graph.api import Component\n"
        cases = [
            ("COMPONENTS = [object]", "COMPONENTS\\[0\\]"),
            ("COMPONENTS = [DataFactor, DataFactor]", "COMPONENTS\\[1\\]"),
            ("COMPONENTS = (DataFactor,)", "COMPONENTS 必须为列表"),
            ("COMPONENTS = [Component(DataFactor, version=0)]", "正整数"),
            ("COMPONENTS = [Component(DataFactor, id='')]", "非空字符串"),
            ("CATEGORY = 1\nCOMPONENTS = [DataFactor]", "CATEGORY"),
            ("COMPONENTS = [Component(builder=lambda *args: None)]", "args_model"),
            ("COMPONENTS = [Component(args_model=dict, input_model=dict, output_type=DataFactor, builder=lambda *args: None)]", "Pydantic"),
            ("from QuantStudio.Factor.FactorOperation import FactorOperator\nCOMPONENTS = [FactorOperator]", "基类"),
        ]
        for source, message in cases:
            with self.subTest(source=source):
                self.write("invalid.py", prefix + source)
                before = {name for name in sys.modules if name.startswith("qs_components_")}
                with self.assertRaisesRegex(ValueError, message) as error:
                    load_component_directory(self.root)
                self.assertIn("invalid.py", str(error.exception))
                self.assertEqual(before, {name for name in sys.modules if name.startswith("qs_components_")})

    def test_no_component_list_fails_without_calling_legacy_registration(self):
        """辅助文件可缺少列表，但空目录或旧注册入口不能生成组件目录。"""
        self.write("helper.py", '''
            def register(registry):
                raise AssertionError("不应调用旧的注册入口")
        ''')
        with self.assertRaisesRegex(ValueError, "COMPONENTS"):
            load_component_directory(self.root)

    def test_paths_preserve_arbitrary_directories_and_root_scripts(self):
        """任意目录和根目录脚本保留真实路径，不生成固定板块分类。"""
        folders = ("research", "research/local", "custom_tools", "自定义")
        for folder in folders:
            self.write(f"{folder}/nested/components.py", f'''
                from QuantStudio.Factor.Factor import DataFactor
                from QSExt.Graph.api import Component
                CATEGORY = "任意分类"
                COMPONENTS = [Component(DataFactor, id="{folder}")]
            ''')
        registry = load_component_directory(self.root)
        for folder in folders:
            with self.subTest(folder=folder):
                description = registry.describe_definition(folder)
                self.assertNotIn("section", description.model_dump())
                self.assertEqual(description.source_path, f"{folder}/nested/components.py")
                doc = {"blocks": [{"id": "node", "definition": {"id": folder}, "operation": "build"}]}
                self.assertEqual(describe_block(doc, "node", registry).source_path, description.source_path)
                self.assertNotIn("section", describe_block(doc, "node", registry).model_dump())
        self.write("direct.py", '''
            from QuantStudio.Factor.Factor import DataFactor
            from QSExt.Graph.api import Component
            COMPONENTS = [Component(DataFactor, id="direct")]
        ''')
        registry = load_component_directory(self.root)
        self.assertEqual(registry.describe_definition("direct").source_path, "direct.py")

    def test_directory_categories_come_from_each_init_file(self):
        """无组件列表的包声明也能命名目录，类别不向子目录或脚本继承。"""
        self.write("__init__.py", 'CATEGORY = "根目录名称"\n')
        self.write("research/__init__.py", 'CATEGORY = "研究组件"\n')
        self.write("research/nested/__init__.py", 'CATEGORY = "嵌套类别"\n')
        self.write("research/plain/__init__.py", '"""未声明目录类别。"""\n')
        for folder in ("research/nested", "research/plain", "research/no_init"):
            self.write(folder + "/definition.py", f'''
                from QuantStudio.Factor.Factor import DataFactor
                from QSExt.Graph.api import Component
                CATEGORY = "脚本类别"
                COMPONENTS = [Component(DataFactor, id="{folder}")]
            ''')
        registry = load_component_directory(self.root)
        nested = registry.describe_definition("research/nested")
        self.assertEqual(nested.directory_categories, {"research": "研究组件", "research/nested": "嵌套类别"})
        self.assertEqual(nested.source_category, "脚本类别")
        for folder in ("research/plain", "research/no_init"):
            self.assertEqual(registry.describe_definition(folder).directory_categories, {"research": "研究组件"})
        doc = {"blocks": [{"id": "node", "definition": {"id": "research/nested"}, "operation": "build"}]}
        self.assertEqual(describe_block(doc, "node", registry).directory_categories, nested.directory_categories)

    def test_invalid_directory_category_fails_at_init_file(self):
        """目录 CATEGORY 与脚本 CATEGORY 使用同样的非空字符串校验。"""
        self.write("research/definition.py", '''
            from QuantStudio.Factor.Factor import DataFactor
            COMPONENTS = [DataFactor]
        ''')
        for value in ("7", "' '"):
            with self.subTest(value=value):
                self.write("research/__init__.py", "CATEGORY = " + value + "\n")
                with self.assertRaisesRegex(ValueError, "__init__.py.*CATEGORY"):
                    load_component_directory(self.root)

    def test_script_category_is_separate_from_component_category(self):
        """脚本类别独立保留，单个组件覆盖分类不改变脚本的展示名。"""
        self.write("operators/rolling.py", '''
            from QuantStudio.Factor.FactorOperator import RollingMean
            from QSExt.Graph.api import Component
            CATEGORY = "时间序列"
            COMPONENTS = [Component(RollingMean, id="rolling", category="单组件分类")]
        ''')
        self.write("operators/rank.py", '''
            from QuantStudio.Factor.FactorOperator import RollingRank
            COMPONENTS = [RollingRank]
        ''')
        registry = load_component_directory(self.root)
        description = registry.describe_definition("rolling")
        self.assertEqual(description.source_category, "时间序列")
        self.assertEqual(description.category, "单组件分类")
        self.assertEqual(description.source_path, "operators/rolling.py")
        fallback = registry.describe_definition("QuantStudio.Factor.FactorOperator.RollingRank")
        self.assertEqual(fallback.source_category, "")
        doc = {"blocks": [{"id": "operator", "definition": {"id": "rolling"}, "operation": "apply"}]}
        self.assertEqual(describe_block(doc, "operator", registry).source_category, "时间序列")


if __name__ == "__main__":
    unittest.main()

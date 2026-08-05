# -*- coding: utf-8 -*-
"""
DefKey 单元测试。

测试 make_def_key 和 _dep_key_to_def_key 函数。
"""
import os
import sys
import importlib
import unittest

# 将 QSExt 加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from QSExt.FactorDef.FactorDefContent import make_def_key, _dep_key_to_def_key


class TestMakeDefKey(unittest.TestCase):
    """make_def_key 单元测试"""

    def test_same_file_same_args_same_key(self):
        """相同文件 + 相同参数 → 相同 key"""
        import QSExt.FactorDef.FactorDefContent as mod
        key1 = make_def_key(mod, {"a": 1})
        key2 = make_def_key(mod, {"a": 1})
        self.assertEqual(key1, key2)

    def test_empty_model_args(self):
        """空 model_args → 纯文件路径，无 @ 后缀"""
        import QSExt.FactorDef.FactorDefContent as mod
        key = make_def_key(mod, {})
        self.assertNotIn("@", key)
        self.assertTrue(key.endswith("FactorDefContent.py"))

    def test_different_model_args_different_key(self):
        """不同 model_args → 不同 key"""
        import QSExt.FactorDef.FactorDefContent as mod
        key1 = make_def_key(mod, {"lookback": 20})
        key2 = make_def_key(mod, {"lookback": 60})
        self.assertNotEqual(key1, key2)

    def test_args_sorted_consistency(self):
        """ModelArgs 不同顺序但相同内容 → 相同 key"""
        import QSExt.FactorDef.FactorDefContent as mod
        key1 = make_def_key(mod, {"b": 2, "a": 1})
        key2 = make_def_key(mod, {"a": 1, "b": 2})
        self.assertEqual(key1, key2)

    def test_same_file_different_loading_same_key(self):
        """同一文件不同加载方式（import vs spec_from_file_location）→ 相同 key"""
        import importlib.util
        import QSExt.FactorDef.FactorDefContent as mod1

        spec = importlib.util.spec_from_file_location(
            "_test_fd_content_alt",
            mod1.__file__,
        )
        mod2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod2)

        key1 = make_def_key(mod1, {})
        key2 = make_def_key(mod2, {})
        self.assertEqual(key1, key2)


class TestDepKeyToDefKey(unittest.TestCase):
    """_dep_key_to_def_key 单元测试"""

    def setUp(self):
        import QSExt.FactorDef.FactorDefContent as mod
        self.test_mod = mod
        self.def_key = make_def_key(mod, {})

    def test_match_via_import(self):
        """通过 import 匹配成功"""
        target = {self.def_key: "found"}
        result = _dep_key_to_def_key("QSExt.FactorDef.FactorDefContent", target)
        self.assertEqual(result, self.def_key)

    def test_dep_not_found_returns_none(self):
        """依赖模块不存在返回 None"""
        result = _dep_key_to_def_key("nonexistent.module.xyz", {"some_key": "val"})
        self.assertIsNone(result)

    def test_windows_case_insensitive(self):
        """Windows 路径大小写不敏感匹配"""
        # 构造一个大写版本的 def_key
        upper_key = self.def_key.upper().split("@")[0]
        if "@" in self.def_key:
            upper_key += "@" + self.def_key.split("@")[1]
        target = {upper_key: "found"}
        result = _dep_key_to_def_key("QSExt.FactorDef.FactorDefContent", target)
        self.assertEqual(result, upper_key)

    def test_empty_target_dict(self):
        """空 target_dict 返回 None"""
        result = _dep_key_to_def_key("QSExt.FactorDef.FactorDefContent", {})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

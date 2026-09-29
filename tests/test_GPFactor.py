# -*- coding: utf-8 -*-
"""遗传规划因子挖掘模块测试。

测试 GPLearner 核心功能：工具函数、随机生成、遗传操作、进化循环、配置加载。
"""
import datetime as dt
import unittest

import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorOperation import DerivativeFactor
import QuantStudio.Factor.BasicOperator as fo

from QSExt.GPFactor.GPLearn import (
    GPLearner,
    flattenFactor2PN,
    flattenFactor2RPN,
    calcDepth,
    toExprStr,
    toNameList,
    exportGraphviz,
)


def _make_test_data():
    """构造测试用的基础因子和算子。"""
    np.random.seed(42)
    IDs = [f"00000{i}.SZ" for i in range(1, 6)]
    DTs = [dt.datetime(2020, 1, 1) + dt.timedelta(i) for i in range(7)]
    Open = DataFactor(
        data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs),
        args={"Name": "Open"},
    )
    Close = DataFactor(
        data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs),
        args={"Name": "Close"},
    )
    Volume = DataFactor(
        data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10000, index=DTs, columns=IDs),
        args={"Name": "Volume"},
    )
    return {
        "IDs": IDs, "DTs": DTs,
        "Open": Open, "Close": Close, "Volume": Volume,
        "terminal_factors": [Open, Close, Volume],
        "operator_list": [fo.add, fo.sub, fo.mul, fo.div, fo.qs_abs, fo.neg],
    }


def _dummy_fitness(factors):
    """简单的适应度函数，返回随机值。"""
    return np.array([np.random.rand() for _ in factors])


def _make_learner(setup_data, **kwargs):
    """创建 GPLearner 实例。"""
    return GPLearner(
        operator_list=setup_data["operator_list"],
        terminal_factors=setup_data["terminal_factors"],
        fitness_fun=_dummy_fitness,
        args=kwargs,
    )


# ============================================================================
#  工具函数测试
# ============================================================================

class TestFactorTreeUtils(unittest.TestCase):
    """因子树工具函数测试。"""

    @classmethod
    def setUpClass(cls):
        cls.data = _make_test_data()

    def test_flatten_pn(self):
        """PN 表示法：基础因子长度为 1，派生因子长度为节点数。"""
        pn = flattenFactor2PN(self.data["Open"])
        self.assertEqual(len(pn), 1)

        derived = fo.add(self.data["Open"], self.data["Close"])
        pn = flattenFactor2PN(derived)
        self.assertEqual(len(pn), 3)
        self.assertIsInstance(pn[0], DerivativeFactor)

    def test_flatten_rpn(self):
        """RPN 表示法：终端在前，算子在后。"""
        derived = fo.add(self.data["Open"], self.data["Close"])
        rpn = flattenFactor2RPN(derived)
        self.assertEqual(len(rpn), 3)
        self.assertIsInstance(rpn[-1], DerivativeFactor)

    def test_calc_depth(self):
        """深度计算：基础因子为 0，嵌套递增。"""
        self.assertEqual(calcDepth(self.data["Open"]), 0)
        self.assertEqual(calcDepth(fo.add(self.data["Open"], self.data["Close"])), 1)
        inner = fo.sub(self.data["Open"], self.data["Close"])
        self.assertEqual(calcDepth(fo.mul(inner, self.data["Volume"])), 2)

    def test_to_expr_str(self):
        """表达式字符串转换。"""
        self.assertEqual(toExprStr(self.data["Open"]), "Open")
        derived = fo.add(self.data["Open"], self.data["Close"])
        s = toExprStr(derived)
        self.assertIn("add", s)
        self.assertIn("Open", s)

    def test_to_name_list(self):
        """名称列表转换。"""
        derived = fo.add(self.data["Open"], self.data["Close"])
        names = toNameList(flattenFactor2PN(derived))
        self.assertIn("add", names)
        self.assertIn("Open", names)

    def test_export_graphviz(self):
        """Graphviz 导出。"""
        derived = fo.add(self.data["Open"], self.data["Close"])
        dot = exportGraphviz(flattenFactor2PN(derived))
        self.assertIsNotNone(dot)
        self.assertIn("digraph", dot)


# ============================================================================
#  GPLearner 核心功能测试
# ============================================================================

class TestGPLearnerBuild(unittest.TestCase):
    """随机因子生成测试。"""

    @classmethod
    def setUpClass(cls):
        cls.data = _make_test_data()

    def test_build_random_expr(self):
        """随机生成的表达式应以 DerivativeFactor 开头。"""
        np.random.seed(0)
        learner = _make_learner(self.data)
        expr = learner.buildRandomPNExpr()
        self.assertIsInstance(expr, list)
        self.assertGreater(len(expr), 0)
        self.assertIsInstance(expr[0], DerivativeFactor)

    def test_build_with_grow_method(self):
        """grow 方法应正常工作。"""
        np.random.seed(0)
        learner = _make_learner(self.data, InitMethod="grow")
        expr = learner.buildRandomPNExpr()
        self.assertIsInstance(expr[0], DerivativeFactor)

    def test_build_without_const(self):
        """禁用常数时不应生成常数节点。"""
        np.random.seed(0)
        learner = _make_learner(self.data, ConstRangeEnabled=False)
        expr = learner.buildRandomPNExpr()
        for node in expr:
            if not isinstance(node, DerivativeFactor):
                self.assertIn(node, self.data["terminal_factors"])


class TestGPLearnerMutation(unittest.TestCase):
    """遗传操作测试。"""

    @classmethod
    def setUpClass(cls):
        cls.data = _make_test_data()
        np.random.seed(0)
        cls.learner = _make_learner(cls.data)
        cls.expr = cls.learner.buildRandomPNExpr()

    def test_crossover(self):
        """交叉操作应产生有效表达式。"""
        np.random.seed(1)
        donor = self.learner.buildRandomPNExpr()
        result, removed, donor_removed = self.learner.crossover(self.expr, donor)
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], DerivativeFactor)

    def test_subtree_mutation(self):
        """子树变异应产生有效表达式。"""
        np.random.seed(2)
        result, removed, _ = self.learner.mutateSubtree(self.expr)
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], DerivativeFactor)

    def test_hoist_mutation(self):
        """提升变异应产生有效表达式。"""
        np.random.seed(0)
        learner = _make_learner(self.data, InitDepthMin=4, InitDepthMax=6)
        expr = learner.buildRandomPNExpr()
        result, removed = GPLearner.mutateHoist(expr)
        self.assertIsInstance(result, list)

    def test_point_mutation(self):
        """点变异应产生有效表达式。"""
        np.random.seed(3)
        result, mutated = self.learner.mutatePoint(self.expr)
        self.assertIsInstance(result, list)
        self.assertIsInstance(mutated, list)

    def test_tournament(self):
        """锦标赛选择应返回有效个体。"""
        fitness = np.array([0.1, 0.5, 0.3, 0.8, 0.2])
        individuals = list(range(5))
        selected, idx = GPLearner.tournament(fitness, individuals, tournament_size=3)
        self.assertIn(selected, individuals)
        self.assertGreaterEqual(idx, 0)
        self.assertLess(idx, 5)


# ============================================================================
#  进化循环测试
# ============================================================================

class TestGPLearnerEvolve(unittest.TestCase):
    """进化循环测试。"""

    @classmethod
    def setUpClass(cls):
        cls.data = _make_test_data()

    def test_evolve_basic(self):
        """基本进化循环：种群和适应度历史长度正确。"""
        np.random.seed(123)
        learner = _make_learner(self.data, PopulationSize=5, TournamentSize=2)
        parents = [learner.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([np.random.rand() for _ in parents])
        populations, fitness, ancestry = learner.evolve(
            n_generations=3, parents=parents, parent_fitness=parent_fitness,
        )
        self.assertEqual(len(populations), 4)  # 初始 + 3 代
        self.assertEqual(len(fitness), 4)

    def test_evolve_auto_init(self):
        """不传 parents 时应自动生成初始种群。"""
        np.random.seed(123)
        learner = _make_learner(self.data, PopulationSize=3, TournamentSize=2)
        populations, fitness, ancestry = learner.evolve(n_generations=2)
        self.assertEqual(len(populations), 3)

    def test_hall_of_fame(self):
        """Hall of Fame 应按适应度降序排列。"""
        np.random.seed(123)
        learner = _make_learner(self.data, PopulationSize=5, TournamentSize=2)
        parents = [learner.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([np.random.rand() for _ in parents])
        learner.evolve(n_generations=3, parents=parents, parent_fitness=parent_fitness)
        self.assertGreater(len(learner.hall_of_fame), 0)
        fits = [f for f, _ in learner.hall_of_fame]
        self.assertEqual(fits, sorted(fits, reverse=True))

    def test_parsimony_coefficient(self):
        """复杂度惩罚应降低长表达式的适应度。"""
        np.random.seed(123)
        learner1 = _make_learner(self.data, PopulationSize=5, TournamentSize=2, ParsimonyCoefficient=0.0)
        parents = [learner1.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([1.0] * 5)
        _, fitness1, _ = learner1.evolve(n_generations=2, parents=list(parents), parent_fitness=parent_fitness.copy())

        learner2 = _make_learner(self.data, PopulationSize=5, TournamentSize=2, ParsimonyCoefficient=0.1)
        _, fitness2, _ = learner2.evolve(n_generations=2, parents=list(parents), parent_fitness=parent_fitness.copy())
        self.assertLessEqual(fitness2[-1].mean(), fitness1[-1].mean() + 1e-10)


# ============================================================================
#  配置加载测试
# ============================================================================

class TestGPLearnerConfig(unittest.TestCase):
    """配置加载测试。"""

    def test_default_config(self):
        """默认配置值正确。"""
        learner = GPLearner(operator_list=[], terminal_factors=[], fitness_fun=_dummy_fitness)
        self.assertEqual(learner.Args.PopulationSize, 1000)
        self.assertEqual(learner.Args.TournamentSize, 20)
        self.assertEqual(learner.Args.PCrossover, 0.9)
        self.assertEqual(learner.Args.ParsimonyCoefficient, 0.0)
        self.assertEqual(learner.ConstRange, (-1.0, 1.0))

    def test_custom_args(self):
        """通过 args 字典覆盖默认配置。"""
        learner = GPLearner(
            operator_list=[], terminal_factors=[], fitness_fun=_dummy_fitness,
            args={"PopulationSize": 50, "PCrossover": 0.8, "ParsimonyCoefficient": 0.01},
        )
        self.assertEqual(learner.Args.PopulationSize, 50)
        self.assertEqual(learner.Args.PCrossover, 0.8)
        self.assertEqual(learner.Args.ParsimonyCoefficient, 0.01)

    def test_const_range_disabled(self):
        """禁用常数范围时 ConstRange 返回 None。"""
        learner = GPLearner(
            operator_list=[], terminal_factors=[], fitness_fun=_dummy_fitness,
            args={"ConstRangeEnabled": False},
        )
        self.assertIsNone(learner.ConstRange)

    def test_yaml_config_file(self):
        """从 YAML 文件加载配置。"""
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "QSExt" / "GPFactor" / "conf" / "gp_config.yaml"
        if not config_path.exists():
            self.skipTest(f"配置文件不存在: {config_path}")

        learner = GPLearner(
            operator_list=[], terminal_factors=[], fitness_fun=_dummy_fitness,
            config_file=str(config_path),
        )
        self.assertEqual(learner.Args.PopulationSize, 1000)
        self.assertEqual(learner.Args.NGenerations, 10)
        self.assertEqual(learner.ConstRange, (-1.0, 1.0))

    def test_args_override_config_file(self):
        """args 应覆盖配置文件中的值。"""
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "QSExt" / "GPFactor" / "conf" / "gp_config.yaml"
        if not config_path.exists():
            self.skipTest(f"配置文件不存在: {config_path}")

        learner = GPLearner(
            operator_list=[], terminal_factors=[], fitness_fun=_dummy_fitness,
            args={"PopulationSize": 999},
            config_file=str(config_path),
        )
        self.assertEqual(learner.Args.PopulationSize, 999)
        # 其他值来自配置文件
        self.assertEqual(learner.Args.TournamentSize, 20)


if __name__ == "__main__":
    unittest.main()

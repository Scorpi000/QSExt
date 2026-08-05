# -*- coding: utf-8 -*-
"""GPLearn 基本功能测试"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorOperation import DerivativeFactor
import QuantStudio.Factor.BasicOperator as fo

from QSExt.GPFactor.GPLearn import (
    GPLearner,
    GPConfig,
    flattenFactor2PN,
    flattenFactor2RPN,
    calcDepth,
    toExprStr,
    toNameList,
    exportGraphviz,
)


@pytest.fixture
def setup_data():
    """构造测试用的基础因子和算子"""
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
    terminal_factors = [Open, Close, Volume]
    operator_list = [fo.add, fo.sub, fo.mul, fo.div, fo.qs_abs, fo.neg]

    def dummy_fitness(factors):
        return np.array([np.random.rand() for _ in factors])

    return {
        "IDs": IDs,
        "DTs": DTs,
        "Open": Open,
        "Close": Close,
        "Volume": Volume,
        "terminal_factors": terminal_factors,
        "operator_list": operator_list,
        "dummy_fitness": dummy_fitness,
    }


def _make_learner(setup_data, **config_kwargs):
    config = GPConfig(**config_kwargs)
    return GPLearner(
        operator_list=setup_data["operator_list"],
        terminal_factors=setup_data["terminal_factors"],
        fitness_fun=setup_data["dummy_fitness"],
        config=config,
    )


class TestFlattenFactor:
    """测试因子树的波兰/逆波兰表示法转换"""

    def test_basic_factor_pn(self, setup_data):
        pn = flattenFactor2PN(setup_data["Open"])
        assert len(pn) == 1
        assert pn[0] is setup_data["Open"]

    def test_basic_factor_rpn(self, setup_data):
        rpn = flattenFactor2RPN(setup_data["Open"])
        assert len(rpn) == 1
        assert rpn[0] is setup_data["Open"]

    def test_derived_factor_pn(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        pn = flattenFactor2PN(derived)
        assert len(pn) == 3
        assert pn[0] is derived
        assert isinstance(pn[0], DerivativeFactor)

    def test_derived_factor_rpn(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        rpn = flattenFactor2RPN(derived)
        assert len(rpn) == 3
        assert rpn[-1] is derived
        assert isinstance(rpn[-1], DerivativeFactor)

    def test_nested_factor_pn(self, setup_data):
        inner = fo.sub(setup_data["Open"], setup_data["Close"])
        outer = fo.mul(inner, setup_data["Volume"])
        pn = flattenFactor2PN(outer)
        assert len(pn) == 5


class TestCalcDepth:
    """测试因子树深度计算"""

    def test_basic_factor_depth(self, setup_data):
        assert calcDepth(setup_data["Open"]) == 0

    def test_single_operator_depth(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        assert calcDepth(derived) == 1

    def test_nested_depth(self, setup_data):
        inner = fo.sub(setup_data["Open"], setup_data["Close"])
        outer = fo.mul(inner, setup_data["Volume"])
        assert calcDepth(outer) == 2


class TestGPLearnerBuild:
    """测试 GPLearner 随机因子生成"""

    def test_returns_list(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        assert isinstance(expr, list)
        assert len(expr) > 0

    def test_root_is_derived(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        assert isinstance(expr[0], DerivativeFactor)

    def test_with_const_range(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data, const_range=(-1.0, 1.0))
        expr = learner.buildRandomPNExpr()
        assert isinstance(expr[0], DerivativeFactor)

    def test_grow_method(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data, init_method="grow")
        expr = learner.buildRandomPNExpr()
        assert isinstance(expr[0], DerivativeFactor)

    def test_half_and_half_method(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data, init_method="half and half")
        expr = learner.buildRandomPNExpr()
        assert isinstance(expr[0], DerivativeFactor)

    def test_to_expr_str(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        s = toExprStr(expr[0])
        assert isinstance(s, str)
        assert len(s) > 0

    def test_to_name_list(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        names = toNameList(expr)
        assert isinstance(names, list)
        assert len(names) == len(expr)


class TestGPLearnerSubtree:
    """测试子树操作"""

    def test_returns_valid_range(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        start, end = GPLearner.getSubtree(expr)
        assert 0 <= start < end <= len(expr)

    def test_subtree_contains_complete_nodes(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        start, end = GPLearner.getSubtree(expr)
        subtree = expr[start:end]
        assert len(subtree) > 0


class TestGPLearnerCrossover:
    """测试交叉操作"""

    def test_crossover_produces_valid_expr(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        e1 = learner.buildRandomPNExpr()
        e2 = learner.buildRandomPNExpr()
        result, removed, donor_removed = learner.crossover(e1, e2)
        assert isinstance(result, list)
        assert isinstance(result[0], DerivativeFactor)

    def test_crossover_returns_removed_info(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        e1 = learner.buildRandomPNExpr()
        e2 = learner.buildRandomPNExpr()
        result, removed, donor_removed = learner.crossover(e1, e2)
        assert isinstance(removed, list)
        assert isinstance(donor_removed, list)


class TestGPLearnerMutation:
    """测试变异操作"""

    def test_subtree_mutation(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        result, removed, donor_removed = learner.mutateSubtree(expr)
        assert isinstance(result, list)
        assert isinstance(result[0], DerivativeFactor)

    def test_hoist_mutation(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data, init_depth=(4, 6))
        expr = learner.buildRandomPNExpr()
        result, removed = GPLearner.mutateHoist(expr)
        assert isinstance(result, list)

    def test_point_mutation(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        result, mutated = learner.mutatePoint(expr)
        assert isinstance(result, list)
        assert isinstance(mutated, list)

    def test_point_mutation_variable_arity(self, setup_data):
        """可变入参算子不应导致 KeyError"""
        np.random.seed(0)
        learner = _make_learner(setup_data)
        expr = learner.buildRandomPNExpr()
        result, mutated = learner.mutatePoint(expr)
        assert isinstance(result, list)


class TestGPLearnerTournament:
    """测试锦标赛选择"""

    def test_tournament_selects_individual(self, setup_data):
        fitness = np.array([0.1, 0.5, 0.3, 0.8, 0.2])
        individuals = list(range(5))
        selected, idx = GPLearner.tournament(fitness, individuals, tournament_size=3)
        assert selected in individuals
        assert 0 <= idx < 5


class TestGPLearnerEvolve:
    """测试进化循环"""

    def test_evolve_basic(self, setup_data):
        np.random.seed(123)
        learner = _make_learner(setup_data, population_size=5, tournament_size=2)
        parents = [learner.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([np.random.rand() for _ in parents])
        populations, fitness, ancestry = learner.evolve(
            n_generations=3, parents=parents, parent_fitness=parent_fitness,
        )
        assert len(populations) == 4  # 初始 + 3 代
        assert len(fitness) == 4

    def test_evolve_auto_init(self, setup_data):
        """不传 parents 时应自动生成初始种群"""
        np.random.seed(123)
        learner = _make_learner(setup_data, population_size=3, tournament_size=2)
        populations, fitness, ancestry = learner.evolve(n_generations=2)
        assert len(populations) == 3

    def test_hall_of_fame(self, setup_data):
        np.random.seed(123)
        learner = _make_learner(setup_data, population_size=5, tournament_size=2)
        parents = [learner.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([np.random.rand() for _ in parents])
        learner.evolve(n_generations=3, parents=parents, parent_fitness=parent_fitness)
        assert len(learner.hall_of_fame) > 0
        fits = [f for f, _ in learner.hall_of_fame]
        assert fits == sorted(fits, reverse=True)

    def test_parsimony_coefficient(self, setup_data):
        """复杂度惩罚应降低长表达式的适应度"""
        np.random.seed(123)
        learner1 = _make_learner(setup_data, population_size=5, tournament_size=2, parsimony_coefficient=0.0)
        parents = [learner1.buildRandomPNExpr() for _ in range(5)]
        parent_fitness = np.array([1.0] * 5)
        _, fitness1, _ = learner1.evolve(n_generations=2, parents=list(parents), parent_fitness=parent_fitness.copy())

        learner2 = _make_learner(setup_data, population_size=5, tournament_size=2, parsimony_coefficient=0.1)
        _, fitness2, _ = learner2.evolve(n_generations=2, parents=list(parents), parent_fitness=parent_fitness.copy())
        assert fitness2[-1].mean() <= fitness1[-1].mean() + 1e-10


class TestExprConversion:
    """测试表达式转换"""

    def test_to_expr_str_basic(self, setup_data):
        s = toExprStr(setup_data["Open"])
        assert s == "Open"

    def test_to_expr_str_derived(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        s = toExprStr(derived)
        assert "add" in s
        assert "Open" in s
        assert "Close" in s

    def test_to_name_list_basic(self, setup_data):
        names = toNameList([setup_data["Open"]])
        assert names == ["Open"]

    def test_to_name_list_derived(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        pn = flattenFactor2PN(derived)
        names = toNameList(pn)
        assert "add" in names
        assert "Open" in names
        assert "Close" in names

    def test_export_graphviz(self, setup_data):
        derived = fo.add(setup_data["Open"], setup_data["Close"])
        pn = flattenFactor2PN(derived)
        dot = exportGraphviz(pn)
        assert dot is not None
        assert "digraph" in dot


class TestGPConfig:
    """测试 GPConfig 配置"""

    def test_defaults(self):
        config = GPConfig()
        assert config.population_size == 1000
        assert config.tournament_size == 20
        assert config.p_crossover == 0.9
        assert config.parsimony_coefficient == 0.0

    def test_custom(self):
        config = GPConfig(population_size=50, p_crossover=0.8, parsimony_coefficient=0.01)
        assert config.population_size == 50
        assert config.p_crossover == 0.8
        assert config.parsimony_coefficient == 0.01

    def test_init_config(self, setup_data):
        """GPLearner 应正确读取 config 中的算子映射"""
        learner = _make_learner(setup_data)
        assert 2 in learner.operator_arity
        assert 1 in learner.operator_arity
        assert fo.add in learner.operator_arity[2]
        assert fo.neg in learner.operator_arity[1]

    def test_generate_initial_population(self, setup_data):
        np.random.seed(0)
        learner = _make_learner(setup_data, population_size=3)
        parents, fitness = learner.generate_initial_population()
        assert len(parents) == 3
        assert len(fitness) == 3

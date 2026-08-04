# -*- coding: utf-8 -*-
"""基于遗传编程 (Genetic Programming) 的因子挖掘模块。

核心思想：将 QuantStudio 的因子算子作为树的内部节点，基础因子作为叶节点，
通过 GP 演化（选择、交叉、变异）自动搜索具有预测能力的因子组合。

典型用法:
    learner = GPLearner(
        operator_list=[fo.add, fo.sub, fo.mul, fo.div, fo.qs_abs, fo.neg],
        terminal_factors=[Open, Close, Volume],
        fitness_fun=my_fitness_func,
    )
    result = learner.evolve(n_generations=10, population_size=100)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorOperation import DerivativeFactor, FactorOperator

logger = logging.getLogger(__name__)

MAX_INT = np.iinfo(np.int32).max


# ============================================================================
#  纯工具函数（无状态，不属于任何类）
# ============================================================================

def flattenFactor2PN(f) -> list:
    """将因子树转换为波兰表示法 (Polish Notation)。

    Args:
        f: 因子对象

    Returns:
        PN 序列，算子节点在前，终端节点在后
    """
    if not f.Descriptors:
        return [f]
    else:
        return [f] + sum((flattenFactor2PN(iFactor) for iFactor in f.Descriptors), start=[])


def flattenFactor2RPN(f) -> list:
    """将因子树转换为逆波兰表示法 (Reverse Polish Notation)。

    Args:
        f: 因子对象

    Returns:
        RPN 序列，终端节点在前，算子节点在后
    """
    if not f.Descriptors:
        return [f]
    else:
        return sum((flattenFactor2RPN(iFactor) for iFactor in f.Descriptors), start=[]) + [f]


def calcDepth(f) -> int:
    """计算因子树的最大深度。基础因子深度为 0。"""
    if isinstance(f, DerivativeFactor):
        return 1 + max(calcDepth(iFactor) for iFactor in f.Descriptors)
    else:
        return 0


def toExprStr(f) -> str:
    """将因子对象转换为中缀表达式字符串。

    示例: ``toExprStr(fo.add(Open, Close))`` → ``"add(Open, Close)"``
    """
    if isinstance(f, DerivativeFactor):
        return f"""{f.Operator.Name}({", ".join(toExprStr(iFactor) for i, iFactor in enumerate(f.Descriptors))})"""
    elif (not isinstance(f, DataFactor)) or (f._DataContent != "Value") or (f._QSArgs.DataType not in ("double", "string")):
        return f.Name
    else:
        return str(f._Data)


def toNameList(expr: list) -> list:
    """将 PN 序列转换为名称列表。"""
    return [
        (iFactor.Operator.Name if isinstance(iFactor, DerivativeFactor) else iFactor.Name)
        if ((not isinstance(iFactor, DataFactor)) or (iFactor._DataContent != "Value") or (iFactor._QSArgs.DataType not in ("double", "string")))
        else iFactor._Data
        for iFactor in expr
    ]


def exportGraphviz(pn_expr: list, fade_nodes: list | None = None) -> str | None:
    """将 PN 序列渲染为 Graphviz DOT 脚本。

    Args:
        pn_expr: PN 序列
        fade_nodes: 需要灰显的节点索引列表

    Returns:
        DOT 脚本字符串，可用 ``graphviz.Source()`` 渲染
    """
    terminals = []
    if fade_nodes is None:
        fade_nodes = []
    output = 'digraph Factor {\nnode [style=filled]\n'
    for i, iFactor in enumerate(pn_expr):
        fill = '#cecece'
        if isinstance(iFactor, DerivativeFactor):
            if i not in fade_nodes:
                fill = '#136ed4'
            terminals.append([len(iFactor.Descriptors), i])
            output += f'{i} [label="{iFactor.Operator.Name}", fillcolor="{fill}"] ;\n'
        else:
            if i not in fade_nodes:
                fill = '#60a6f6'
            if (not isinstance(iFactor, DataFactor)) or (iFactor._DataContent != "Value") or (iFactor._QSArgs.DataType not in ("double", "string")):
                output += f'{i} [label="{iFactor.Name}", fillcolor="{fill}"] ;\n'
            else:
                output += f'{i} [label="{iFactor._Data}", fillcolor="{fill}"] ;\n'
            if i == 0:
                return output + '}'
            terminals[-1][0] -= 1
            terminals[-1].append(i)
            while terminals[-1][0] == 0:
                output += '%d -> %d ;\n' % (terminals[-1][1], terminals[-1][-1])
                terminals[-1].pop()
                if len(terminals[-1]) == 2:
                    parent = terminals[-1][-1]
                    terminals.pop()
                    if not terminals:
                        return output + '}'
                    terminals[-1].append(parent)
                    terminals[-1][0] -= 1
    return None


# ============================================================================
#  GP 配置
# ============================================================================

@dataclass
class GPConfig:
    """遗传编程配置参数。"""
    # 种群与进化
    population_size: int = 1000
    tournament_size: int = 20
    # 初始化
    init_depth: Tuple[int, int] = (2, 6)
    init_method: str = "half and half"
    # 算子入参（对 Arity=None 的算子生效）
    min_arity: int = 1
    max_arity: int = 3
    # 常数
    const_range: Optional[Tuple[float, float]] = (-1.0, 1.0)
    # 遗传操作概率
    p_crossover: float = 0.9
    p_subtree_mutation: float = 0.01
    p_hoist_mutation: float = 0.01
    p_point_mutation: float = 0.01
    p_point_replace: float = 0.05
    # 复杂度惩罚系数（0 表示不惩罚）
    parsimony_coefficient: float = 0.0


# ============================================================================
#  GPLearner 核心类
# ============================================================================

class GPLearner:
    """基于遗传编程的因子挖掘器。

    Args:
        operator_list: 可用算子列表，如 ``[fo.add, fo.sub, fo.neg]``
        terminal_factors: 终端因子列表，如 ``[Open, Close, Volume]``
        fitness_fun: 适应度函数，接受 ``[Factor, ...]``，返回 ``ndarray``
        config: GP 配置参数，未指定的字段使用默认值
    """

    def __init__(
        self,
        operator_list: List[FactorOperator],
        terminal_factors: List[DataFactor],
        fitness_fun: Callable[[List], np.ndarray],
        config: GPConfig | None = None,
    ):
        self.operator_list = list(operator_list)
        self.terminal_factors = list(terminal_factors)
        self.fitness_fun = fitness_fun
        self.config = config or GPConfig()
        self.operator_arity: Dict[int, List[FactorOperator]] = self._build_operator_arity()
        self.hall_of_fame: list = []  # [(fitness, pn_expr)]

    def _build_operator_arity(self) -> Dict[int, List[FactorOperator]]:
        """从算子列表自动构建 ``{arity: [operator]}`` 映射。"""
        arity_map: Dict[int, List[FactorOperator]] = {}
        for op in self.operator_list:
            a = op._QSArgs.Arity
            if a is not None:
                arity_map.setdefault(a, []).append(op)
            # Arity=None 的算子不放入固定映射，在需要时动态处理
        return arity_map

    # ----------------------------------------------------------------
    #  随机因子生成
    # ----------------------------------------------------------------

    def _random_arity(self, op: FactorOperator) -> int:
        """为算子选择一个入参数量。固定入参直接返回，可变入参在范围内随机。"""
        if op._QSArgs.Arity is not None:
            return op._QSArgs.Arity
        return np.random.randint(self.config.min_arity, self.config.max_arity + 1)

    def buildRandomPNExpr(self) -> list:
        """随机生成一个因子表达式 (PN 序列)。

        Returns:
            PN 序列，第一个元素为根节点 (DerivativeFactor)
        """
        cfg = self.config
        if cfg.init_method == 'half and half':
            method = 'full' if np.random.randint(2) else 'grow'
        else:
            method = cfg.init_method
        MaxDepth = np.random.randint(*cfg.init_depth)

        # 以算子开头，避免退化为单节点
        iOperator = self.operator_list[np.random.randint(len(self.operator_list))]
        PNExpr, Arities = [iOperator], [self._random_arity(iOperator)]
        TerminalStack = [Arities[-1]]

        while TerminalStack:
            depth = len(TerminalStack)
            choice = len(self.terminal_factors) + len(self.operator_list)
            choice = np.random.randint(choice)
            if (depth < MaxDepth) and (method == 'full' or choice <= len(self.operator_list)):
                iOperator = self.operator_list[np.random.randint(len(self.operator_list))]
                PNExpr.append(iOperator)
                Arities.append(self._random_arity(iOperator))
                TerminalStack.append(Arities[-1])
            else:
                iTerminal = np.random.randint(len(self.terminal_factors) + int(cfg.const_range is not None))
                if iTerminal == len(self.terminal_factors):
                    iTerminal = np.random.uniform(*cfg.const_range)
                    iTerminal = DataFactor(data=iTerminal, args={"Name": str(iTerminal)})
                else:
                    iTerminal = self.terminal_factors[iTerminal]
                PNExpr.append(iTerminal)
                Arities.append(0)
                TerminalStack[-1] -= 1
                while TerminalStack[-1] == 0:
                    TerminalStack.pop()
                    if not TerminalStack:
                        break
                    TerminalStack[-1] -= 1

        # 将算子对象替换为因子对象
        DescriptorStack = []
        for i, iObj in enumerate(reversed(PNExpr)):
            if isinstance(iObj, FactorOperator):
                iIdx = len(PNExpr) - 1 - i
                iFactor = iObj(*reversed(DescriptorStack[-Arities[iIdx]:]))
                PNExpr[iIdx] = iFactor
                DescriptorStack = DescriptorStack[:-Arities[iIdx]] + [iFactor]
            else:
                DescriptorStack.append(iObj)
        return PNExpr

    # ----------------------------------------------------------------
    #  子树操作
    # ----------------------------------------------------------------

    @staticmethod
    def getSubtree(pn_expr: list, start: int | None = None, terminal_prob: float = 0.1) -> Tuple[int, int]:
        """从 PN 序列中选取一个子树范围。

        Args:
            pn_expr: PN 序列
            start: 起始位置，None 表示按概率随机选择
            terminal_prob: 选择叶节点的概率

        Returns:
            ``(start, end)`` — 子树在 PN 序列中的左闭右开区间
        """
        if start is None:
            Probs = np.array([
                (1 - terminal_prob) if isinstance(iFactor, DerivativeFactor) else terminal_prob
                for iFactor in pn_expr
            ])
            Probs = np.cumsum(Probs / Probs.sum())
            start = np.searchsorted(Probs, np.random.uniform())
        Stack = 1
        end = start
        while Stack > end - start:
            iFactor = pn_expr[end]
            if isinstance(iFactor, DerivativeFactor):
                Stack += len(iFactor.Descriptors)
            end += 1
        return start, end

    @staticmethod
    def _updateFactor(pn_expr: list, max_idx: int, update_list: list | None = None) -> list:
        """更新因子表达式中受影响的节点。

        位于 update_list 处的因子发生了更改，对其上游依赖因子重新生成。
        """
        update_set = set(update_list or [])
        Stack, Updated = [], []
        for i in range(max_idx, -1, -1):
            iFactor = pn_expr[i]
            if isinstance(iFactor, DerivativeFactor):
                iArity = len(iFactor.Descriptors)
                if any(Updated[-iArity:]) or (i in update_set):
                    pn_expr[i] = iFactor.Operator(*reversed(Stack[-iArity:]), *iFactor.Descriptors[len(Stack):])
                    Stack = Stack[:-iArity]
                    Updated = Updated[:-iArity]
                    Stack.append(pn_expr[i])
                    Updated.append(True)
                else:
                    Stack = Stack[:-iArity]
                    Updated = Updated[:-iArity]
                    Stack.append(pn_expr[i])
                    Updated.append(i == max_idx)
            elif i in update_set:
                Stack.append(iFactor)
                Updated.append(True)
            else:
                Stack.append(iFactor)
                Updated.append(False)
        return pn_expr

    # ----------------------------------------------------------------
    #  遗传操作
    # ----------------------------------------------------------------

    def crossover(self, pn_expr: list, donor: list) -> Tuple[list, list, list]:
        """交叉操作：从父代中选取子树，替换为供体的子树。

        Returns:
            ``(new_expr, removed, donor_removed)``
        """
        Start, End = self.getSubtree(pn_expr)
        Removed = list(range(Start, End))
        DonorStart, DonorEnd = self.getSubtree(donor)
        DonorRemoved = list(set(range(len(donor))) - set(range(DonorStart, DonorEnd)))
        New = pn_expr[:Start] + donor[DonorStart:DonorEnd] + pn_expr[End:]
        return self._updateFactor(New, Start), Removed, DonorRemoved

    def mutateSubtree(self, pn_expr: list) -> Tuple[list, list, list]:
        """子树变异：用随机生成的新子树替换原有子树。

        Returns:
            ``(new_expr, removed, donor_removed)``
        """
        Chicken = self.buildRandomPNExpr()
        return self.crossover(pn_expr, Chicken)

    @staticmethod
    def mutateHoist(pn_expr: list) -> Tuple[list, list]:
        """提升变异：用子树的子树替换原位置，用于控制表达式膨胀。

        Returns:
            ``(new_expr, removed)``
        """
        Start, End = GPLearner.getSubtree(pn_expr)
        Subtree = pn_expr[Start:End]
        SubStart, SubEnd = GPLearner.getSubtree(Subtree)
        if SubStart == 0:
            return pn_expr, []
        Hoist = Subtree[SubStart:SubEnd]
        Removed = list(set(range(Start, End)) - set(range(Start + SubStart, Start + SubEnd)))
        New = pn_expr[:Start] + Hoist + pn_expr[End:]
        return GPLearner._updateFactor(New, Start), Removed

    def mutatePoint(self, pn_expr: list) -> Tuple[list, list]:
        """点变异：随机替换表达式中的某些节点。

        算子替换为同入参数量的其他算子，终端替换为其他终端或常数。

        Returns:
            ``(new_expr, mutated_indices)``
        """
        cfg = self.config
        pn_expr = pn_expr.copy()
        MutateIdx = np.where(np.random.uniform(size=len(pn_expr)) < cfg.p_point_replace)[0].tolist()
        UpdateIdx = []
        for iIdx in MutateIdx:
            if isinstance(pn_expr[iIdx], DerivativeFactor):
                iArity = len(pn_expr[iIdx].Descriptors)
                candidates = self.operator_arity.get(iArity, [])
                if not candidates:
                    continue
                iReplacement = candidates[np.random.randint(len(candidates))]
                if iReplacement is not pn_expr[iIdx].Operator:
                    pn_expr[iIdx] = iReplacement(*pn_expr[iIdx].Descriptors)
                    UpdateIdx.append(iIdx)
            else:
                if cfg.const_range is not None:
                    terminal = np.random.randint(len(self.terminal_factors) + 1)
                else:
                    terminal = np.random.randint(len(self.terminal_factors))
                if terminal == len(self.terminal_factors):
                    terminal = np.random.uniform(*cfg.const_range)
                    terminal = DataFactor(data=terminal, args={"Name": str(terminal)})
                else:
                    terminal = self.terminal_factors[terminal]
                if terminal is not pn_expr[iIdx]:
                    pn_expr[iIdx] = terminal
                    UpdateIdx.append(iIdx)
        if UpdateIdx:
            return self._updateFactor(pn_expr, max_idx=max(UpdateIdx), update_list=UpdateIdx), MutateIdx
        return pn_expr, MutateIdx

    # ----------------------------------------------------------------
    #  选择与繁殖
    # ----------------------------------------------------------------

    @staticmethod
    def tournament(
        fitness: np.ndarray,
        individuals: list,
        tournament_size: int,
        greater_is_better: bool = True,
    ) -> Tuple[Any, int]:
        """锦标赛选择。"""
        Contenders = np.random.randint(0, len(individuals), tournament_size).tolist()
        if greater_is_better:
            SelectedIdx = Contenders[np.argmax(fitness[Contenders])]
        else:
            SelectedIdx = Contenders[np.argmin(fitness[Contenders])]
        return individuals[SelectedIdx], SelectedIdx

    def _select_parents(self, fitness: np.ndarray, population: list) -> Tuple[list, int]:
        """选择一个亲代，返回 (个体, 索引)。"""
        return self.tournament(fitness, population, self.config.tournament_size)

    def breed(self, fitness: np.ndarray, population: list) -> Tuple[list, dict]:
        """产生下一代种群。

        Returns:
            ``(offspring_list, ancestry_dict)``
        """
        cfg = self.config
        MethodProbs = np.cumsum([
            cfg.p_crossover, cfg.p_subtree_mutation,
            cfg.p_hoist_mutation, cfg.p_point_mutation,
        ])
        Ancestry, Offspring = {}, []
        for i in range(cfg.population_size):
            iParent, iParentIndex = self._select_parents(fitness, population)
            iMethod = np.random.uniform()
            if iMethod < MethodProbs[0]:
                iDonor, iDonorIndex = self._select_parents(fitness, population)
                iOffspring, iRemoved, iRemains = self.crossover(iParent, iDonor)
                iGenome = {'method': 'Crossover', 'parent_idx': iParentIndex,
                           'parent_nodes': iRemoved, 'donor_idx': iDonorIndex, 'donor_nodes': iRemains}
            elif iMethod < MethodProbs[1]:
                iOffspring, iRemoved, _ = self.mutateSubtree(iParent)
                iGenome = {'method': 'Subtree Mutation', 'parent_idx': iParentIndex, 'parent_nodes': iRemoved}
            elif iMethod < MethodProbs[2]:
                iOffspring, iRemoved = self.mutateHoist(iParent)
                iGenome = {'method': 'Hoist Mutation', 'parent_idx': iParentIndex, 'parent_nodes': iRemoved}
            elif iMethod < MethodProbs[3]:
                iOffspring, iMutated = self.mutatePoint(iParent)
                iGenome = {'method': 'Point Mutation', 'parent_idx': iMutated, 'parent_nodes': iMutated}
            else:
                iOffspring = iParent
                iGenome = {'method': 'Reproduction', 'parent_idx': iParentIndex, 'parent_nodes': []}
            Offspring.append(iOffspring)
            Ancestry[iOffspring[0].QSID] = iGenome
        return Offspring, Ancestry

    # ----------------------------------------------------------------
    #  进化主循环
    # ----------------------------------------------------------------

    def evolve(
        self,
        n_generations: int,
        parents: list | None = None,
        parent_fitness: np.ndarray | None = None,
        n_jobs: int = 1,
        verbose: int = 0,
        progress_callback: Callable | None = None,
    ) -> Tuple[list, list, dict]:
        """执行完整的进化循环。

        Args:
            n_generations: 进化代数
            parents: 初始种群 (PN 序列列表)。None 则随机生成
            parent_fitness: 初始种群适应度。None 则自动计算
            n_jobs: 并行任务数 (当前未启用)
            verbose: 日志详细程度
            progress_callback: 逐代进度回调，签名为 ``callback(gen_idx, fitness, hall_of_fame)``

        Returns:
            ``(populations, fitness_history, ancestry)``
            - populations: 各代种群列表，长度 = n_generations + 1
            - fitness_history: 各代适应度列表
            - ancestry: 祖先信息字典
        """
        cfg = self.config

        # 初始化种群
        if parents is None:
            parents = [self.buildRandomPNExpr() for _ in range(cfg.population_size)]
        if parent_fitness is None:
            parent_fitness = self.fitness_fun([p[0] for p in parents])

        Populations = [parents]
        Fitness = [parent_fitness]
        Ancestry: Dict[str, dict] = {}

        # 更新 Hall of Fame
        self._update_hall_of_fame(parent_fitness, parents)

        for i in range(n_generations):
            iPopulation, iAncestry = self.breed(Fitness[-1], Populations[-1])
            iFitness = self.fitness_fun([iExpr[0] for iExpr in iPopulation])

            # 复杂度惩罚
            if cfg.parsimony_coefficient > 0:
                penalties = np.array([len(p) * cfg.parsimony_coefficient for p in iPopulation])
                iFitness = iFitness - penalties

            Populations.append(iPopulation)
            Fitness.append(iFitness)
            Ancestry.update(iAncestry)
            self._update_hall_of_fame(iFitness, iPopulation)

            if progress_callback:
                progress_callback(i, Fitness, self.hall_of_fame)

            if verbose > 0:
                best_fit = Fitness[-1].max()
                avg_fit = Fitness[-1].mean()
                logger.info(f"Gen {i+1}/{n_generations}: best={best_fit:.6f}, avg={avg_fit:.6f}")

        return Populations, Fitness, Ancestry

    def _update_hall_of_fame(self, fitness: np.ndarray, population: list, max_size: int = 10):
        """更新 Hall of Fame，保留历史最优因子。"""
        for fit, expr in zip(fitness, population):
            if len(self.hall_of_fame) < max_size or fit > self.hall_of_fame[-1][0]:
                self.hall_of_fame.append((fit, expr))
                self.hall_of_fame.sort(key=lambda x: -x[0])
                self.hall_of_fame = self.hall_of_fame[:max_size]

    def generate_initial_population(self, population_size: int | None = None) -> Tuple[list, np.ndarray]:
        """生成初始种群并计算适应度。

        Returns:
            ``(parents, parent_fitness)``
        """
        size = population_size or self.config.population_size
        parents = [self.buildRandomPNExpr() for _ in range(size)]
        parent_fitness = self.fitness_fun([p[0] for p in parents])
        return parents, parent_fitness

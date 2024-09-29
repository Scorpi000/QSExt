# -*- coding: utf-8 -*-
import inspect
import itertools
from functools import partial

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from QuantStudio.FactorDataBase.FactorDB import DataFactor
from QuantStudio.FactorDataBase.FactorOperation import FactorOperator, DerivativeFactor
from QuantStudio.FactorDataBase.FactorModelOperators import IC

MAX_INT = np.iinfo(np.int32).max

# 将因子转成波兰表示法(Polish Notation)
# 返回: [因子对象]
def flattenFactor2PN(f):
    if not f.Descriptors:# 基础因子
        return [f]
    else:# 衍生因子
        return [f] + sum((flattenFactor2PN(iFactor) for iFactor in f.Descriptors), start=[])

# 将因子转成逆波兰表示法(Reverse Polish Notation)
# 返回: [因子对象]
def flattenFactor2RPN(f):
    if not f.Descriptors:# 基础因子
        return [f]
    else:# 衍生因子
        return sum((flattenFactor2RPN(iFactor) for iFactor in f.Descriptors), start=[]) + [f]

# Calculates the maximum depth of the factor
def calcDepth(f):
    if isinstance(f, DerivativeFactor):
        return 1 + max(calcDepth(iFactor) for iFactor in f.Descriptors)
    else:
        return 0
    
# 生成随机因子
# init_method : str
# - 'grow' : Nodes are chosen at random from both functions and terminals, allowing for smaller trees than `init_depth` allows. Tends to grow asymmetrical trees.
# - 'full' : Functions are chosen until the `init_depth` is reached, and then terminals are selected. Tends to grow 'bushy' trees.
# - 'half and half' : Trees are grown through a 50/50 mix of 'full' and 'grow', making for a mix of tree shapes in the initial population.
# init_depth : tuple of two ints
# The range of tree depths for the initial population of naive formulas.
# Individual trees will randomly choose a maximum depth from this range.
# When combined with `init_method='half and half'` this yields the well-
# known 'ramped half and half' initialization method.
def buildRandomPNExpr(operator_list, terminal_factors, init_method, init_depth, const_range=None):
    if init_method == 'half and half': init_method = ('full' if np.random.randint(2) else 'grow')
    MaxDepth = np.random.randint(*init_depth)

    # Start a program with a operator to avoid degenerative programs
    iOperator = operator_list[np.random.randint(len(operator_list))]
    PNExpr, Arities = [iOperator], [np.random.randint(iOperator.Args["入参数"], iOperator.Args["最大入参数"]+1)]
    TerminalStack = [Arities[-1]]
    
    while TerminalStack:
        depth = len(TerminalStack)
        choice = len(terminal_factors) + len(operator_list)
        choice = np.random.randint(choice)
        # Determine if we are adding a operator or terminal
        if (depth < MaxDepth) and (init_method == 'full' or choice <= len(operator_list)):
            iOperator = operator_list[np.random.randint(len(operator_list))]
            PNExpr.append(iOperator)
            Arities.append(np.random.randint(iOperator.Args["入参数"], iOperator.Args["最大入参数"]+1))
            TerminalStack.append(Arities[-1])
        else:
            # We need a terminal, add a factor or constant
            iTerminal = np.random.randint(len(terminal_factors) + int(const_range is not None))
            if iTerminal == len(terminal_factors):
                iTerminal = np.random.uniform(*const_range)
                iTerminal = DataFactor(name=str(iTerminal), data=iTerminal)
            else:
                iTerminal = terminal_factors[iTerminal]
            PNExpr.append(iTerminal)
            Arities.append(0)
            TerminalStack[-1] -= 1
            while TerminalStack[-1] == 0:
                TerminalStack.pop()
                if not TerminalStack:
                    break
                TerminalStack[-1] -= 1
    # 将其中的算子替换成因子
    DescriptorStack = []
    for i, iObj in enumerate(reversed(PNExpr)):
        if isinstance(iObj, FactorOperator):
            iIdx = len(PNExpr)-1-i
            iFactor = iObj(*reversed(DescriptorStack[-Arities[iIdx]:]))
            PNExpr[iIdx] = iFactor
            DescriptorStack = DescriptorStack[:-Arities[iIdx]] + [iFactor]
        else:
            DescriptorStack.append(iObj)
    return PNExpr

# 获取因子的一个子树
# pn_expr: 因子的波兰表示法
# start: 子树的开始位置, None 表示随机生成
# terminal_prob: 叶节点选取的概率, Koza's (1992) widely used approach of choosing functions 90% of the time and leaves 10% of the time.
def getSubtree(pn_expr, start=None, terminal_prob=0.1):
    if start is None:
        Probs = np.array([(1 - terminal_prob) if isinstance(iFactor, DerivativeFactor) else terminal_prob for iFactor in pn_expr])
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

# 位于 idx_list 处的因子发生了更改，对于依赖它的因子重新生成
def updateFactor(pn_expr, max_idx, update_list=[]):
    update_list = set(update_list)
    Stack, Updated = [], []
    for i in range(max_idx, -1, -1):
        iFactor = pn_expr[i]
        if isinstance(iFactor, DerivativeFactor):
            iArity = len(iFactor.Descriptors)
            if any(Updated[-iArity:]) or (i in update_list):
                pn_expr[i] = iFactor.Operator(*reversed(Stack[-iArity:]), *iFactor.Descriptors[len(Stack):], factor_args=iFactor.Args.to_dict())
                Stack = Stack[:-iArity]
                Updated = Updated[:-iArity]
                Stack.append(pn_expr[i])
                Updated.append(True)
            else:
                Stack = Stack[:-iArity]
                Updated = Updated[:-iArity]
                Stack.append(pn_expr[i])
                Updated.append(i==max_idx)
        elif i in update_list:
            Stack.append(iFactor)
            Updated.append(True)
        else:
            Stack.append(iFactor)
            Updated.append(False)
    return pn_expr

# Perform the crossover genetic operation on the program.
# Crossover selects a random subtree from the embedded program to be
# replaced. A donor also has a subtree selected at random and this is
# inserted into the original parent to form an offspring.
def crossover(pn_expr, donor):
    # Get a subtree to replace
    Start, End = getSubtree(pn_expr)
    Removed = list(range(Start, End))
    # Get a subtree to donate
    DonorStart, DonorEnd = getSubtree(donor)
    DonorRemoved = list(set(range(len(donor))) - set(range(DonorStart, DonorEnd)))
    # Insert genetic material from donor
    New = pn_expr[:Start] + donor[DonorStart:DonorEnd] + pn_expr[End:]
    return updateFactor(New, Start), Removed, DonorRemoved

# Perform the subtree mutation operation on the program.
# Subtree mutation selects a random subtree from the embedded program to
# be replaced. A donor subtree is generated at random and this is
# inserted into the original parent to form an offspring. This
# implementation uses the "headless chicken" method where the donor
# subtree is grown using the initialization methods and a subtree of it
# is selected to be donated to the parent.
def mutateSubtree(pn_expr, operator_list, terminal_factors, init_method, init_depth, const_range=None):
    # Build a new naive program
    Chicken = buildRandomPNExpr(operator_list, terminal_factors, init_method, init_depth, const_range=const_range)
    # Do subtree mutation via the headless chicken method!
    return crossover(pn_expr, Chicken)

# Perform the hoist mutation operation on the program.
# Hoist mutation selects a random subtree from the embedded program to
# be replaced. A random subtree of that subtree is then selected and this
# is 'hoisted' into the original subtrees location to form an offspring.
# This method helps to control bloat.
def mutateHoist(pn_expr):
    # Get a subtree to replace
    Start, End = getSubtree(pn_expr)
    Subtree = pn_expr[Start:End]
    # Get a subtree of the subtree to hoist
    SubStart, SubEnd = getSubtree(Subtree)
    if SubStart==0: return pn_expr, []
    Hoist = Subtree[SubStart:SubEnd]
    # Determine which nodes were removed for plotting
    Removed = list(set(range(Start, End)) - set(range(Start + SubStart, Start + SubEnd)))
    New = pn_expr[:Start] + Hoist + pn_expr[End:]
    return updateFactor(New, Start), Removed

# Perform the point mutation operation on the program.
# Point mutation selects random nodes from the embedded program to be
# replaced. Terminals are replaced by other terminals and functions are
# replaced by other functions that require the same number of arguments
# as the original node. The resulting tree forms an offspring.
# operator_arity: {arity: [operator]}
# terminal_factors: 基本因子列表
# p_point_replace: Point Mutation 的概率
# const_range: 常数项的区间
def mutatePoint(pn_expr, operator_arity, terminal_factors, p_point_replace, const_range=None):
    pn_expr = pn_expr.copy()
    # Get the nodes to modify
    MutateIdx = np.where(np.random.uniform(size=len(pn_expr)) < p_point_replace)[0].tolist()
    UpdateIdx = []
    for iIdx in MutateIdx:
        if isinstance(pn_expr[iIdx], DerivativeFactor):
            iArity = len(pn_expr[iIdx].Descriptors)
            # Find a valid replacement with same arity
            iReplacement = np.random.randint(len(operator_arity[iArity]))
            iReplacement = operator_arity[iArity][iReplacement]
            if iReplacement is not pn_expr[iIdx].Operator:
                pn_expr[iIdx] = iReplacement(*pn_expr[iIdx].Descriptors)
                UpdateIdx.append(iIdx)
        else:
            # We've got a terminal, add a const or variable
            if const_range is not None:
                terminal = np.random.randint(len(terminal_factors) + 1)
            else:
                terminal = np.random.randint(len(terminal_factors))
            if terminal == len(terminal_factors):
                terminal = np.random.uniform(*const_range)
                if const_range is None:
                    # We should never get here
                    raise ValueError('A constant was produced with const_range=None.')
                terminal = DataFactor(name=str(terminal), data=terminal)
            else:
                terminal = terminal_factors[terminal]
            if terminal is not pn_expr[iIdx]:
                pn_expr[iIdx] = terminal
                UpdateIdx.append(iIdx)
    return (updateFactor(pn_expr, max_idx=max(UpdateIdx), update_list=UpdateIdx) if UpdateIdx else pn_expr), MutateIdx




# Find the fittest individual from a sub-population.
def tournament(fitness, individuals, tournament_size, greater_is_better=True):
    Contenders = np.random.randint(0, len(individuals), tournament_size).tolist()
    if greater_is_better:
        SelectedIdx = Contenders[np.argmax(fitness[Contenders])]
    else:
        SelectedIdx = Contenders[np.argmin(fitness[Contenders])]
    return individuals[SelectedIdx], SelectedIdx

# 产生下一代
def breed(n_offspring, parents, parent_fitness, operator_list, operator_arity, terminal_factors, args=dict(
    tournament_size=20, 
    const_range=(-1., 1.),
    init_depth=(2, 6),
    init_method='half and half',
    p_crossover=0.9,
    p_subtree_mutation=0.01,
    p_hoist_mutation=0.01,
    p_point_mutation=0.01,
    p_point_replace=0.05
)):
    Args = inspect.signature(breed).parameters["args"].default
    Args.update(args)
    MethodProbs = np.cumsum([Args["p_crossover"], Args["p_subtree_mutation"], Args["p_hoist_mutation"], Args["p_point_mutation"]])
    Ancestry, Offspring = {}, []
    for i in range(n_offspring):
        iParent, iParentIndex = tournament(parent_fitness, parents, Args["tournament_size"])
        iMethod = np.random.uniform()
        if iMethod < MethodProbs[0]:
            # crossover
            iDonor, iDonorIndex = tournament(parent_fitness, parents, Args["tournament_size"])
            iOffspring, iRemoved, iRemains = crossover(iParent, iDonor)
            iGenome = {
                'method': 'Crossover',
                'parent_idx': iParentIndex,
                'parent_nodes': iRemoved,
                'donor_idx': iDonorIndex,
                'donor_nodes': iRemains
            }
        elif iMethod < MethodProbs[1]:
            # subtree_mutation
            iOffspring, iRemoved, _ = mutateSubtree(iParent, operator_list, terminal_factors, Args["init_method"], Args["init_depth"], const_range=Args["const_range"])
            iGenome = {
                'method': 'Subtree Mutation',
                'parent_idx': iParentIndex,
                'parent_nodes': iRemoved
            }
        elif iMethod < MethodProbs[2]:
            # hoist_mutation
            iOffspring, iRemoved = mutateHoist(iParent)
            iGenome = {
                'method': 'Hoist Mutation',
                'parent_idx': iParentIndex,
                'parent_nodes': iRemoved
            }
        elif iMethod < MethodProbs[3]:
            # point_mutation
            iOffspring, iMutated = mutatePoint(iParent, operator_arity, terminal_factors, Args["p_point_replace"], const_range=Args["const_range"])
            iGenome = {
                'method': 'Point Mutation',
                'parent_idx': iMutated,
                'parent_nodes': iMutated
            }
        else:
            # reproduction
            iOffspring = iParent
            iGenome = {
                'method': 'Reproduction',
                'parent_idx': iParentIndex,
                'parent_nodes': []
            }
        Offspring.append(iOffspring)
        Ancestry[iOffspring[0].QSID] = iGenome
    return Offspring, Ancestry

def _get_n_jobs(n_jobs):
    """Get number of jobs for the computation.

    This function reimplements the logic of joblib to determine the actual
    number of jobs depending on the cpu count. If -1 all CPUs are used.
    If 1 is given, no parallel computing code is used at all, which is useful
    for debugging. For n_jobs below -1, (n_cpus + 1 + n_jobs) are used.
    Thus for n_jobs = -2, all CPUs but one are used.

    Parameters
    ----------
    n_jobs : int
        Number of jobs stated in joblib convention.

    Returns
    -------
    n_jobs : int
        The actual number of jobs as positive integer.

    """
    if n_jobs < 0:
        return max(cpu_count() + 1 + n_jobs, 1)
    elif n_jobs == 0:
        raise ValueError('Parameter n_jobs == 0 has no meaning.')
    else:
        return n_jobs


def _partition_estimators(n_estimators, n_jobs):
    """Private function used to partition estimators between jobs."""
    # Compute the number of jobs
    n_jobs = min(_get_n_jobs(n_jobs), n_estimators)

    # Partition estimators between jobs
    n_estimators_per_job = (n_estimators // n_jobs) * np.ones(n_jobs,
                                                              dtype=int)
    n_estimators_per_job[:n_estimators % n_jobs] += 1
    starts = np.cumsum(n_estimators_per_job)

    return n_jobs, n_estimators_per_job.tolist(), [0] + starts.tolist()

def _verbose_reporter(self, run_details=None):
    """A report of the progress of the evolution process.

    Parameters
    ----------
    run_details : dict
        Information about the evolution.

    """
    if run_details is None:
        print('    |{:^25}|{:^42}|'.format('Population Average',
                                           'Best Individual'))
        print('-' * 4 + ' ' + '-' * 25 + ' ' + '-' * 42 + ' ' + '-' * 10)
        line_format = '{:>4} {:>8} {:>16} {:>8} {:>16} {:>16} {:>10}'
        print(line_format.format('Gen', 'Length', 'Fitness', 'Length',
                                 'Fitness', 'OOB Fitness', 'Time Left'))

    else:
        # Estimate remaining time for run
        gen = run_details['generation'][-1]
        generation_time = run_details['generation_time'][-1]
        remaining_time = (self.generations - gen - 1) * generation_time
        if remaining_time > 60:
            remaining_time = '{0:.2f}m'.format(remaining_time / 60.0)
        else:
            remaining_time = '{0:.2f}s'.format(remaining_time)

        oob_fitness = 'N/A'
        line_format = '{:4d} {:8.2f} {:16g} {:8d} {:16g} {:>16} {:>10}'
        if self.max_samples < 1.0:
            oob_fitness = run_details['best_oob_fitness'][-1]
            line_format = '{:4d} {:8.2f} {:16g} {:8d} {:16g} {:16g} {:>10}'

        print(line_format.format(run_details['generation'][-1],
                                 run_details['average_length'][-1],
                                 run_details['average_fitness'][-1],
                                 run_details['best_length'][-1],
                                 run_details['best_fitness'][-1],
                                 oob_fitness,
                                 remaining_time))

# 进化
def evolve(n_generations, fitness_fun, parents, parent_fitness, operator_list, operator_arity, terminal_factors, args=dict(
    population_size=1000,
    tournament_size=20, 
    const_range=(-1., 1.),
    init_depth=(2, 6),
    init_method='half and half',
    p_crossover=0.9,
    p_subtree_mutation=0.01,
    p_hoist_mutation=0.01,
    p_point_mutation=0.01,
    p_point_replace=0.05,
    n_jobs=1,
    verbose=0
)):
    Args = inspect.signature(breed).parameters["args"].default
    Args.update(args)
    Populations, Fitness, Ancestry = [parents], [parent_fitness], {}
    #n_jobs, n_programs, _ = _partition_estimators(Args["population_size"], Args["n_jobs"])
    for i in range(n_generations):
        ## Parallel loop
        #iPopulation = Parallel(n_jobs=n_jobs, verbose=int(Args["verbose"] > 1))(delayed(breed)(n_programs[j], parents, parent_fitness, operator_list, operator_arity, terminal_factors, args=Args) for j in range(n_jobs))
        ## Reduce, maintaining order across different n_jobs
        #iPopulation = list(itertools.chain.from_iterable(iPopulation))
        iPopulation, iAncestry = breed(Args["population_size"], Populations[-1], Fitness[-1], operator_list, operator_arity, terminal_factors, args=Args)
        iFitness = fitness_fun([iExpr[0] for iExpr in iPopulation])
        Populations.append(iPopulation)
        Fitness.append(iFitness)
        Ancestry.update(iAncestry)
    return Populations, Fitness, Ancestry


# 将因子(波兰表示法)渲染为 Graphviz Script
def exportGraphviz(pn_expr, fade_nodes=None):
    terminals = []
    if fade_nodes is None: fade_nodes = []
    output = 'digraph Factor {\nnode [style=filled]\n'
    for i, iFactor in enumerate(pn_expr):
        fill = '#cecece'
        if isinstance(iFactor, DerivativeFactor):
            if i not in fade_nodes: fill = '#136ed4'
            terminals.append([len(iFactor.Descriptors), i])
            output += f'{i} [label="{iFactor.Operator.Name}", fillcolor="{fill}"] ;\n'
        else:
            if i not in fade_nodes: fill = '#60a6f6'
            if (not isinstance(iFactor, DataFactor)) or (iFactor.DataContent!="Value") or (iFactor.Args["数据类型"] not in ("double", "string")):
                output += f'{i} [label="{iFactor.Name}", fillcolor="{fill}"] ;\n'
            else:
                output += f'{i} [label="{iFactor.Data}", fillcolor="{fill}"] ;\n'
            if i == 0:
                # A degenerative program of only one node
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
    # We should never get here
    return None

# 将因子转换为中缀表达式字符串
def toExprStr(f):
    if isinstance(f, DerivativeFactor):
        return f"""{f.Operator.Name}({", ".join(toExprStr(iFactor) for i, iFactor in enumerate(f.Descriptors))})"""
    elif (not isinstance(f, DataFactor)) or (f.DataContent!="Value") or (f.Args["数据类型"] not in ("double", "string")):
        return f.Name
    else:
        return str(f.Data)

def toNameList(expr):
    return [(iFactor.Operator.Name if isinstance(iFactor, DerivativeFactor) else iFactor.Name) if ((not isinstance(iFactor, DataFactor)) or (iFactor.DataContent!="Value") or (iFactor.Args["数据类型"] not in ("double", "string"))) else iFactor.Data for iFactor in expr]


if __name__=="__main__1":
    import datetime as dt
    np.random.seed(0)
    
    #from examples.FactorDef import RngRank
    #print(toExprStr(RngRank))
    #PNExpr = flattenFactor2PN(RngRank)
    #print(toNameList(PNExpr))
    #RPNExpr = flattenFactor2RPN(RngRank)
    #print(toNameList(RPNExpr))
    
    #import graphviz
    #GraphvizScript = exportGraphviz(RngRank)
    #Graph = graphviz.Source(GraphvizScript)
    #Graph.render(filename="/home/hst/桌面/tmp", format="jpg", view=True)
    
    import QuantStudio.FactorDataBase.BasicOperators as fo
    OperatorArity = {
        2: [fo.add, fo.sub, fo.mul, fo.div],
        1: [fo.qs_abs, fo.neg]
    }
    OperatorList = sum(OperatorArity.values(), start=[])
    # 构造用于测试的基础因子
    IDs = [f"00000{i}.SZ" for i in range(1, 6)]
    DTs = [dt.datetime(2020, 1, 1) + dt.timedelta(i) for i in range(7)]
    Open = DataFactor(name="Open", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs))
    Close = DataFactor(name="Close", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs))
    Volume = DataFactor(name="Volume", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10000, index=DTs, columns=IDs))
    #Industry = DataFactor(name="Industry", data=pd.Series(np.random.choice(["Fin", "TMT", "Ind"], size=(len(IDs),)), index=IDs))
    TerminalFactors = [Open, Close, Volume]
    
    ## 随机生成
    #PNExpr = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    
    ## 获取子树
    #PNExpr = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    #print(getSubtree(PNExpr))
    
    ## Crossover
    #PNExpr1 = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #PNExpr2 = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #PNExpr, Removed, DonorRemoved = crossover(PNExpr1, PNExpr2)
    #print(toExprStr(PNExpr1[0]))
    #print(toNameList(PNExpr1))
    #print(toExprStr(PNExpr2[0]))
    #print(toNameList(PNExpr2))
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    #print(Removed)
    #print(DonorRemoved)
    
    ## Subtree Mutation
    #PNExpr = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #NewPNExpr, Removed, DonorRemoved = mutateSubtree(PNExpr, OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    #print(toExprStr(NewPNExpr[0]))
    #print(toNameList(NewPNExpr))
    #print(Removed)
    #print(DonorRemoved)
    
    ## Hoist Mutation
    #PNExpr = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #NewPNExpr, Removed = mutateHoist(PNExpr)
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    #print(toExprStr(NewPNExpr[0]))
    #print(toNameList(NewPNExpr))
    #print(Removed)
    
    ## Point Mutation
    #PNExpr = buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5))
    #NewPNExpr, Removed = mutatePoint(PNExpr, OperatorArity, TerminalFactors, 0.5)
    #print(toExprStr(PNExpr[0]))
    #print(toNameList(PNExpr))
    #print(toExprStr(NewPNExpr[0]))
    #print(toNameList(NewPNExpr))
    #print(Removed)

if __name__=="__main__":
    import datetime as dt
    import QuantStudio.FactorDataBase.BasicOperators as fo
    
    np.random.seed(1)
    OperatorArity = {
        2: [fo.add, fo.sub, fo.mul, fo.div],
        1: [fo.qs_abs, fo.neg]
    }
    OperatorList = sum(OperatorArity.values(), start=[])
    # 构造用于测试的基础因子
    IDs = [f"00000{i}.SZ" for i in range(1, 6)]
    DTs = [dt.datetime(2020, 1, 1) + dt.timedelta(i) for i in range(7)]
    Rtn = DataFactor(name="Return", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs))
    Open = DataFactor(name="Open", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs))
    Close = DataFactor(name="Close", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10, index=DTs, columns=IDs))
    Volume = DataFactor(name="Volume", data=pd.DataFrame(np.random.rand(len(DTs), len(IDs)) * 10000, index=DTs, columns=IDs))
    #Industry = DataFactor(name="Industry", data=pd.Series(np.random.choice(["Fin", "TMT", "Ind"], size=(len(IDs),)), index=IDs))
    TerminalFactors = [Open, Close, Volume]
    
    calcIC = IC()
    def calcFitness(factors):
        FitnessFactor = calcIC(Rtn, *factors, descriptor_ids=IDs)
        Fitness = FitnessFactor.readData(dts=DTs, ids=[f"d{i}" for i in range(len(factors))])
        return Fitness.mean().values
    Parents = [buildRandomPNExpr(OperatorList, TerminalFactors, init_method="full", init_depth=(3, 5), const_range=None) for i in range(3)]
    ParentFitness = calcFitness(factors=[iExpr[0] for iExpr in Parents])
    
    # Evolution
    Populations, Fitness, Ancestry = evolve(5, calcFitness, Parents, ParentFitness, OperatorList, OperatorArity, TerminalFactors, args=dict(population_size=3, tournament_size=2))
    
    print("===")
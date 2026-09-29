# -*- coding: utf-8 -*-
"""遗传规划因子挖掘模块。

主要组件:
    - GPLearner: 基于 __QS_Object__ 的遗传规划学习器
    - fitness: 适应度评估模块

典型用法:
    from QSExt.GPFactor.GPLearn import GPLearner
    from QSExt.GPFactor.fitness import ICFitnessEvaluator

    # 创建适应度评估器
    evaluator = ICFitnessEvaluator(...)

    # 创建学习器并执行进化
    learner = GPLearner(
        operator_list=[...],
        terminal_factors=[...],
        fitness_fun=evaluator,
        config_file="QSExt/GPFactor/conf/gp_config.yaml",
    )
    populations, fitness, ancestry = learner.evolve()
"""

from QSExt.GPFactor.GPLearn import GPLearner
from QSExt.GPFactor.fitness import FitnessEvaluator, ICFitnessEvaluator

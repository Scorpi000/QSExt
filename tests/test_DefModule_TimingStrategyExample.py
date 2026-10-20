# -*- coding: utf-8 -*-
"""验证均线策略示例的独立择时输出及回测结果存储节点。"""
import datetime as dt
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from QuantStudio.BackTest.Strategy.Strategy import AccountStats
from QuantStudio.BackTest.Strategy.TimingStrategy import MakeTimingAccount, TimingAccountStats
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.Node import DTInitData, DTLocalContext
from QuantStudio.Factor.Factor import DataFactor, FactorContext, FactorInitData, FactorLocalContext
from QuantStudio.Factor.FactorDB import FactorDB, WritableFactorDB
from QSExt.DefModule.DefContent import Def, DefInput, DefMeta, _classify
from QSExt.DefModule.examples.stock_cn_strategy_example import __STRATEGY_META__, defStrategy
from QSExt.DefModule.scripts import run_def


class TestTimingStrategyExample(unittest.TestCase):
    """使用本地价格因子替代行情服务，验证完整账户计算。"""

    def setUp(self):
        self.ids = ["A", "B"]
        self.dates = [dt.datetime(2024, 6, 1) + dt.timedelta(days=i) for i in range(10)]
        price = DataFactor(pd.DataFrame({
            "A": [10, 10, 10, 12, 14, 10, 8, 12, 14, 14],
            "B": [20, 20, 20, 20, 18, 16, 20, 22, np.nan, 22],
        }, index=self.dates))
        database = Mock(spec=FactorDB)
        database.getTable.return_value.getFactor.return_value = price
        self.di = DefInput(
            FDB={"BSDB": database}, IDs=self.ids, SectionIDs=self.ids,
            DTRuler=self.dates, DTs=self.dates[2:],
            ModelArgs={"short_window": 1, "long_window": 2, "start_dt": self.dates[2],
                       "init_cash": 1000, "timing_init_cash": 200},
        )
        self.strategies = defStrategy(self.di)

    def test_returns_three_accounts_and_keeps_timing_signal_raw(self):
        """第三个账户使用每标的本金与原始方向信号，连续看多不再平衡。"""
        self.assertEqual([account.Name for account in self.strategies], [
            "strategy_from_signal", "strategy_from_custom_class", "strategy_from_timing_account",
        ])
        factors, strategies = _classify(self.strategies)
        self.assertEqual(factors, [])
        self.assertEqual(len(strategies), 3)
        account = strategies[-1]
        self.assertIsInstance(account.Operator, MakeTimingAccount)
        self.assertEqual(account.Operator.Args.ModelArgs.init_cash, 200)
        with FactorContext(DTRuler=self.dates, SectionIDs=self.ids) as context:
            with Engine() as engine:
                result, = engine.run(
                    [account], context,
                    init_data_list=[FactorInitData(DTRange=(self.dates[2], self.dates[-1]))],
                    fwd_data_list=[FactorLocalContext(DTs=self.dates[2:], IDs=self.ids)],
                )
        fields = result.values.astype(np.dtype([(name, float) for name, _ in account.Operator.Args.CompoundType]))
        np.testing.assert_allclose(fields["Signal"][0], [1, 1])
        np.testing.assert_allclose(fields["Deposit"][0], [200, 200])
        self.assertAlmostEqual(fields["Position"][1, 0], 20)
        self.assertEqual(fields["Position"][2, 1], 0)
        self.assertEqual(fields["Withdrawal"][-2, 1], 0)
        self.assertAlmostEqual(fields["Withdrawal"][-1, 1], 198)

    def test_timing_capital_defaults_to_shared_configuration(self):
        """未单独指定择时本金时，沿用 init_cash 配置。"""
        self.di.ModelArgs.pop("timing_init_cash")
        self.assertEqual(defStrategy(self.di)[-1].Operator.Args.ModelArgs.init_cash, 1000)

    def test_statistics_dispatch_and_actual_timing_metrics(self):
        """为择时账户选择专用统计，并正确生成资金流、胜率与赔率。"""
        nodes = [run_def._make_account_stats(account, self.ids) for account in self.strategies]
        self.assertIs(type(nodes[0]), AccountStats)
        self.assertIs(type(nodes[1]), AccountStats)
        self.assertIs(type(nodes[2]), TimingAccountStats)
        self.assertEqual(nodes[2].Name, "strategy_from_timing_account")
        with FactorContext(DTRuler=self.dates, SectionIDs=self.ids) as context:
            with Engine() as engine:
                output, = engine.run(
                    [nodes[2]], context,
                    init_data_list=[DTInitData(DTRange=(self.dates[2], self.dates[-1]))],
                    fwd_data_list=[DTLocalContext(DTs=self.dates[2:])],
                )
        self.assertAlmostEqual(output["时间序列"]["入金"].sum(), 400)
        self.assertAlmostEqual(output["时间序列"]["出金"].sum(), 198)
        stats = output["择时统计"]["总计"]
        self.assertEqual(stats["交易次数"], 3)
        self.assertAlmostEqual(stats["胜率"], 1/3)
        self.assertAlmostEqual(stats["赔率"], .9)

    def test_both_storer_paths_use_timing_statistics(self):
        """策略模式与混合模式均为第三个账户创建专用统计存储节点。"""
        definition = Def(StrategyList=self.strategies, Meta=DefMeta(**__STRATEGY_META__))
        definitions = [(definition, {})]
        with tempfile.TemporaryDirectory() as directory:
            settings = SimpleNamespace(target_db="output", factor_storer_config={},
                                       bt_store=SimpleNamespace(args={"MainDir": directory}))
            pool = {"output": WritableFactorDB(config_file=None)}
            with patch.object(run_def, "build_dep_sd", return_value=({}, definitions)):
                strategy_storers, _, _ = run_def._build_strategy_storers(settings, pool, self.di, [])
            mixed_storers, _, _ = run_def._build_strategy_storers_from_defs(
                settings, pool, self.di, definitions
            )
            for storers in (strategy_storers, mixed_storers):
                with self.subTest(path=storers):
                    stats = storers[-1].Deps[-1].Deps[0]
                    self.assertIs(type(stats), TimingAccountStats)
                    self.assertEqual(stats.Name, "strategy_from_timing_account")


if __name__ == "__main__":
    unittest.main()

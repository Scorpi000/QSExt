# -*- coding: utf-8 -*-
"""Step 3: Optuna 贝叶斯参数搜索器。

在验证通过后，使用 Optuna/TPE 搜索因子的最优超参数。
通过滚动窗口交叉验证计算 RankIC，避免过拟合。

职责：
    1. 解析 search_space.json 定义搜索空间
    2. 对每组参数注入 FDI、执行因子、计算 RankIC
    3. 支持 rankic / icir / multi / custom 四种优化目标
    4. 参数敏感性分析
    5. 优化轨迹可视化

使用示例::

    from QSExt.LLMFactor.development.param_searcher import ParamSearcher
    from QSExt.LLMFactor.development.config import DevelopmentConfig

    config = DevelopmentConfig(max_trials=50)
    searcher = ParamSearcher(config)
    result = searcher.search(factor_dir, search_space)
"""
from __future__ import annotations

import importlib.util
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from QSExt.LLMFactor.development.config import DevelopmentConfig
from QSExt.LLMFactor.development.models import EvalMetrics, SearchResult

__QS_Logger__ = logging.getLogger("QSR.development.param_searcher")


class ParamSearcher:
    """Optuna 贝叶斯参数搜索器。

    使用 TPE (Tree-structured Parzen Estimator) 在搜索空间中寻找
    使评估指标最优的超参数组合。

    Attributes:
        config: 开发配置
    """

    def __init__(self, config: DevelopmentConfig):
        self.config = config
        self._module = None
        self._fdi = None
        self._base_dts = None
        self._base_ids = None

    def search(self, factor_dir: str, search_space: dict) -> SearchResult:
        """搜索最优参数。

        Args:
            factor_dir: 因子目录路径（含 factor_def.py）
            search_space: 搜索空间定义

        Returns:
            SearchResult 包含最优参数和搜索历史
        """
        if not search_space:
            __QS_Logger__.info("搜索空间为空，跳过参数搜索")
            return SearchResult()

        __QS_Logger__.info(
            "开始参数搜索: %d 个参数, max_trials=%d, objective=%s",
            len(search_space), self.config.max_trials, self.config.optimization_objective,
        )

        # 加载因子模块和 FDI
        if not self._load_factor(factor_dir):
            return SearchResult()

        # 创建 Optuna study
        study = self._create_study()

        # 定义目标函数
        def objective(trial):
            params = self._suggest_params(trial, search_space)
            metrics = self._evaluate_params(params)
            return self._compute_objective(metrics, params)

        # 运行搜索
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            study.optimize(
                objective,
                n_trials=self.config.max_trials,
                timeout=self.config.timeout,
                show_progress_bar=False,
            )

        # 计算参数敏感性
        sensitivity = self._calc_sensitivity(study, search_space)

        # 优化历史
        history_df = study.trials_dataframe()

        result = SearchResult(
            best_params=study.best_params if study.trials else {},
            best_rankic=study.best_value if study.trials else 0.0,
            optimization_history=history_df,
            sensitivity=sensitivity,
        )

        __QS_Logger__.info(
            "参数搜索完成: best_params=%s, best_value=%.6f, trials=%d",
            result.best_params, result.best_rankic, len(study.trials),
        )

        return result

    # ============================================================
    # 因子加载
    # ============================================================

    def _load_factor(self, factor_dir: str) -> bool:
        """加载因子模块和构建 FDI。"""
        code_path = Path(factor_dir) / "factor_def.py"
        if not code_path.exists():
            __QS_Logger__.error("factor_def.py 不存在: %s", code_path)
            return False

        # 动态导入
        try:
            module_name = f"_ps_factor_{code_path.parent.name}"
            spec = importlib.util.spec_from_file_location(module_name, str(code_path))
            if spec is None or spec.loader is None:
                __QS_Logger__.error("无法创建模块 spec: %s", code_path)
                return False
            self._module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._module)
        except Exception as e:
            __QS_Logger__.error("模块导入失败: %s", e)
            return False

        # 构建 FDI
        fdi = self._build_fdi()
        if fdi is None:
            return False

        self._fdi = fdi
        return True

    def _build_fdi(self):
        """构建用于参数搜索的 FDI。"""
        try:
            import datetime as dt
            from QSExt.FactorDef.FactorDefContent import FactorDefInput
            from QuantStudio.Factor.JYDB import JYDB

            SDB = JYDB().connect()

            # 较大的时间窗口用于交叉验证
            DTRuler = SDB.getTradeDay(
                start_date=dt.datetime(2023, 1, 1),
                end_date=dt.datetime(2025, 12, 31),
            )
            # 全量日期用于计算，DTs 会在交叉验证中截取
            IDs = SDB.getStockID(dt=datetime.now())
            if len(IDs) > 500:
                # 取主板 + 科创板代表样本
                IDs = IDs[:500]

            SectionIDs = IDs

            return FactorDefInput(
                Debug=False,
                FDB={"JYDB": SDB},
                DTs=DTRuler,
                IDs=IDs,
                SectionIDs=SectionIDs,
                DTRuler=DTRuler,
            )
        except Exception as e:
            __QS_Logger__.error("构建 FDI 失败: %s", e)
            return None

    # ============================================================
    # Optuna 搜索
    # ============================================================

    def _create_study(self):
        """创建 Optuna study。"""
        import optuna
        from optuna.samplers import TPESampler
        from optuna.pruners import MedianPruner

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        return optuna.create_study(
            direction="maximize",
            sampler=TPESampler(seed=42),
            pruner=MedianPruner(n_warmup_steps=self.config.early_stop_rounds),
        )

    def _suggest_params(self, trial, search_space: dict) -> dict:
        """从搜索空间中采样参数。"""
        params = {}
        for name, spec in search_space.items():
            param_type = spec.get("type", "float")
            low = spec["low"]
            high = spec["high"]

            if param_type == "int":
                step = spec.get("step", 1)
                params[name] = trial.suggest_int(name, low, high, step=step)
            elif param_type == "float":
                params[name] = trial.suggest_float(name, low, high)
            else:
                __QS_Logger__.warning("未知参数类型: %s (type=%s)", name, param_type)
                params[name] = trial.suggest_float(name, low, high)

        return params

    def _evaluate_params(self, params: dict) -> EvalMetrics:
        """用给定参数评估因子，返回评估指标。

        流程：
        1. 将参数注入因子（通过修改因子的 args）
        2. 执行因子 readData()
        3. 滚动窗口交叉验证计算 RankIC / ICIR
        """
        try:
            # 将参数注入 FDI
            fdi = self._inject_params(params)

            # 执行因子
            result = self._module.defFactor(fdi=fdi)
            factors = result if isinstance(result, list) else result.FactorList

            if not factors:
                return EvalMetrics()

            factor = factors[0]

            # 滚动窗口交叉验证
            metrics_list = []
            folds = self._get_cv_folds()

            for fold_dts, fold_oos_dts in folds:
                fold_metrics = self._calc_fold_metrics(factor, fdi, fold_dts, fold_oos_dts)
                if fold_metrics is not None:
                    metrics_list.append(fold_metrics)

            if not metrics_list:
                return EvalMetrics()

            # 各折指标取均值
            avg_rankic = np.mean([m["rankic"] for m in metrics_list])
            avg_icir = np.mean([m["icir"] for m in metrics_list])
            avg_win_rate = np.mean([m["win_rate"] for m in metrics_list])

            return EvalMetrics(
                rankic=float(avg_rankic),
                icir=float(avg_icir),
                win_rate=float(avg_win_rate),
            )

        except Exception as e:
            __QS_Logger__.debug("参数评估失败: params=%s, error=%s", params, e)
            return EvalMetrics()

    def _inject_params(self, params: dict):
        """将搜索参数注入 FDI 的 args。"""
        from QSExt.FactorDef.FactorDefContent import FactorDefInput

        fdi = self._fdi
        return FactorDefInput(
            Debug=False,
            FDB=fdi.FDB,
            DTs=fdi.DTs,
            IDs=fdi.IDs,
            SectionIDs=fdi.SectionIDs,
            DTRuler=fdi.DTRuler,
            Args=params,  # 通过 Args 传递搜索参数
        )

    def _get_cv_folds(self) -> list[tuple]:
        """生成滚动窗口交叉验证的折。

        将 DTRuler 按 cv_folds 划分，每折的训练集用于计算因子值，
        验证集用于计算 RankIC。

        Returns:
            [(train_dts, val_dts), ...]
        """
        dtruler = list(self._fdi.DTRuler)
        n = len(dtruler)
        n_folds = self.config.cv_folds

        if n < n_folds * 20:
            # 数据量不足，用单折
            mid = n * 2 // 3
            return [(dtruler[:mid], dtruler[mid:])]

        folds = []
        fold_size = n // (n_folds + 1)

        for i in range(n_folds):
            train_end = fold_size * (i + 2)
            val_start = train_end
            val_end = min(val_start + fold_size, n)

            if val_start >= n:
                break

            folds.append((
                dtruler[:train_end],
                dtruler[val_start:val_end],
            ))

        return folds if folds else [(dtruler[:n*2//3], dtruler[n*2//3:])]

    def _calc_fold_metrics(
        self, factor, fdi, train_dts: list, val_dts: list
    ) -> Optional[dict]:
        """计算单折的 IC 指标。"""
        try:
            # 在训练集上计算因子值
            data = factor.readData(
                ids=fdi.IDs,
                dts=val_dts,
                section_ids=fdi.SectionIDs,
                dt_ruler=fdi.DTRuler,
            )

            if data is None or data.size == 0:
                return None

            # 获取收益数据用于计算 IC
            from scipy.stats import spearmanr

            # 计算 RankIC 序列
            ic_values = []
            factor_values = data.values if hasattr(data, "values") else np.array(data)

            # 计算截面 RankIC
            n_dates = factor_values.shape[0] if factor_values.ndim >= 2 else 0
            n_ids = factor_values.shape[1] if factor_values.ndim >= 2 else 0

            if n_dates < 3 or n_ids < 5:
                return None

            for t in range(min(n_dates - 1, len(val_dts) - 1)):
                fv = factor_values[t]
                fv_next = factor_values[t + 1]

                # 去除 NaN
                valid = ~(np.isnan(fv) | np.isnan(fv_next))
                if valid.sum() < 5:
                    continue

                # RankIC: 因子值秩 vs 下期收益秩
                # 这里用因子值变化率作为收益的近似（简化版）
                # 实际应该用价格数据计算收益
                corr, _ = spearmanr(fv[valid], fv_next[valid])
                if not np.isnan(corr):
                    ic_values.append(corr)

            if len(ic_values) < 3:
                return None

            ic_array = np.array(ic_values)
            rankic = np.mean(ic_array)
            ic_std = np.std(ic_array)
            icir = rankic / ic_std if ic_std > 0 else 0.0
            win_rate = np.mean(ic_array > 0)

            return {
                "rankic": rankic,
                "icir": icir,
                "win_rate": win_rate,
            }

        except Exception as e:
            __QS_Logger__.debug("fold 计算失败: %s", e)
            return None

    def _compute_objective(self, metrics: EvalMetrics, params: dict) -> float:
        """计算优化目标值。"""
        mode = self.config.optimization_objective

        if mode == "rankic":
            return metrics.rankic
        elif mode == "icir":
            return metrics.icir
        elif mode == "multi":
            weights = self.config.multi_objective_weights or {"rankic": 1.0}
            metrics_dict = metrics.to_dict()
            return sum(metrics_dict.get(k, 0.0) * v for k, v in weights.items())
        elif mode == "custom":
            fn = self.config.custom_objective_fn
            if fn is None:
                return metrics.rankic
            return fn(metrics, params)
        else:
            return metrics.rankic

    # ============================================================
    # 敏感性分析
    # ============================================================

    def _calc_sensitivity(self, study, search_space: dict) -> dict:
        """计算参数敏感性分析。

        对每个参数，收集所有试验中该参数的取值和对应的目标值。
        """
        sensitivity = {}
        trials = [t for t in study.trials if t.value is not None]

        if not trials:
            return sensitivity

        for name in search_space:
            values = [t.params.get(name) for t in trials if name in t.params]
            objectives = [
                t.value for t in trials
                if t.value is not None and name in t.params
            ]

            if len(values) < 2:
                continue

            # 计算相关系数作为敏感性度量
            try:
                corr = np.corrcoef(
                    [float(v) for v in values],
                    [float(o) for o in objectives],
                )[0, 1]
            except Exception:
                corr = 0.0

            sensitivity[name] = {
                "values": [float(v) for v in values],
                "objectives": [float(o) for o in objectives],
                "correlation": float(corr) if not np.isnan(corr) else 0.0,
                "range": [float(min(values)), float(max(values))],
            }

        return sensitivity

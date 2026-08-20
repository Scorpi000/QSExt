# coding=utf-8
"""投资组合或者配置型策略相关的因子运算

本模块定义了一组将投资组合信号在不同资产集合之间迁移或调整的因子算子:

- MigrateAllocStrategy: 基于收益相关性, 将信号一对一迁移到最相关资产
- AlphaEnhanceStrategy: 基于选股因子得分, 在基准权重上倾斜仓位
- OptMigrateAllocStrategy: 基于优化求解, 将源资产信号迁移到目标资产

所有算子均继承自 QuantStudio 的标准算子基类 (PanelOperator/SectionOperator),
通过 DescriptorSection 机制支持异构截面的数据对齐。
"""
import datetime as dt
from typing import Optional, List, Literal, Dict

import cvxpy as cp
import numpy as np
import pandas as pd

from QuantStudio.Core import __QS_Error__
from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorOperation import PanelOperator, PanelOperation, SectionOperator, SectionOperation


# ----------------------截面运算--------------------------------
class ReplaceDownSignal(SectionOperator):
    """将上层配置型策略信号中的证券用下层策略替换，得到融合后的策略信号
    
    Args:
        top_ids: 上层信号的截面 ID 序列
        top2down_ids: 上层信号的 ID 到下层信号截面的映射, 比如: {"000300.SH": ["000001.SZ", ...], ...}
    """
    def __init__(self, top_ids:List[str], top2down_ids:Dict[str, List[str]], args:dict={}, config_file:Optional[str]=None, **kwargs):
        Arity = args.get("Arity", None) or 1 + len(top2down_ids)
        Args = {"Name": "replaceDownSignal"} | args | {"DTMode": "多时点", "Arity": Arity}
        if "DescriptorSection" not in Args:
            Args["DescriptorSection"] = [top_ids] + [top2down_ids[iID] for iID in sorted(top2down_ids.keys())]
        Args["ModelArgs"] = {"top2down_ids": top2down_ids} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        Signal = pd.DataFrame(x[0], index=idt, columns=self.Args.DescriptorSection[0])
        top2down_ids = args["top2down_ids"]
        DownSignal = {iID: pd.DataFrame(x[i+1], index=idt, columns=(top2down_ids[iID] or iid)) for i, iID in enumerate(sorted(top2down_ids.keys()))}
        for iID in sorted(top2down_ids.keys()):
            Signal = Signal.add((DownSignal[iID].T * Signal.pop(iID)).T, fill_value=0.0)
        return Signal.reindex(index=idt, columns=iid).values

    def __call__(self, top_signal:Factor, top2down_signal:Dict[str, Factor], factor_args:dict={}, **kwargs) -> SectionOperation:
        """将算子作用在若干个因子对象上以产生新的因子
                
        Args:
            top_signal: 上层策略信号
            top2down_signal: 上层信号的 ID 到下层信号的映射, 比如: {"000300.SH": Factor1, ...}
            factor_args: 创建新因子时传递给它的参数集
            kwargs: 创建新因子时传递给它的其他入参

        Returns:
            算子作用后产生的新配置型策略信号
        """
        if set(top2down_signal.keys()) != set(self.Args["ModelArgs"]["top2down_ids"]):
            raise __QS_Error__(f"算子的上层信号的 ID 到下层信号截面的映射与到下层信号的映射不匹配")
        Factors = [top_signal] + [top2down_signal[iID] for iID in sorted(top2down_signal.keys())]
        return super().__call__(*Factors, factor_args=factor_args, **kwargs)
    

class MergeTopDownSignal(SectionOperator):
    """将上下两个配置型策略信号(比如行业配置和选股)融合成一个策略信号
    
    Args:
        top_ids: 上层信号的截面 ID 序列
    """
    def __init__(self, top_ids:List[str], args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "mergeTopDownSignal"} | args | {"DTMode": "多时点", "Arity": 3}
        if "DescriptorSection" not in Args:
            Args["DescriptorSection"] = [top_ids, None, None]
        Args["ModelArgs"] = {} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        TopIDs = self.Args.DescriptorSection[0]
        TopSignal, DownSignal, Down2Top = pd.DataFrame(x[0], index=idt, columns=TopIDs), pd.DataFrame(x[1], index=idt, columns=iid), pd.DataFrame(x[2], index=idt, columns=iid)
        TopSignal = TopSignal.stack().reset_index()
        TopSignal.columns = ["datetime", "top_id", "top_signal"]
        Down2Top = Down2Top.stack().reset_index()
        Down2Top.columns = ["datetime", "down_id", "top_id"]
        Signal = pd.merge(Down2Top, TopSignal, how="left", left_on=["datetime", "top_id"], right_on=["datetime", "top_id"])
        DownSignal = DownSignal.stack().reset_index()
        DownSignal.columns = ["datetime", "down_id", "down_signal"]
        Signal = pd.merge(Signal, DownSignal, how="left", left_on=["datetime", "down_id"], right_on=["datetime", "down_id"])
        TopWeight = Signal.groupby(["datetime", "top_id"])[["down_signal"]].sum().rename(columns={"down_signal": "top_weight"})
        Signal = pd.merge(Signal, TopWeight, how="left", left_on=["datetime", "top_id"], right_index=True)
        Signal["signal"] = Signal["down_signal"] / Signal["top_weight"] * Signal["top_signal"]
        return Signal.set_index(["datetime", "down_id"])["signal"].unstack().reindex(index=idt, columns=iid).values

    def __call__(self, top_signal:Factor, down_signal:Factor, down2top:Factor, factor_args:dict={}, **kwargs) -> SectionOperation:
        """将算子作用在若干个因子对象上以产生新的因子
        
        Args:
            top_signal: 上层策略信号
            down_signal: 下层策略信号
            down2top: 下层资产属于哪个上层资产的映射因子
            factor_args: 创建新因子时传递给它的参数集
            kwargs: 创建新因子时传递给它的其他入参

        Returns:
            算子作用后产生的新配置型策略信号
        """
        return super().__call__(top_signal, down_signal, down2top, factor_args=factor_args, **kwargs)

# ----------------------面板运算--------------------------------
class AlphaEnhanceStrategy(SectionOperator):
    """基于选股因子增强基准配置策略，在基准权重基础上，按因子得分倾斜仓位。

    signal 和 alpha_factor 共享同一截面。每期在截面内对 alpha_factor 做标准化,
    按 scale 缩放后调整各标的权重, 零权重标的默认不参与调整。
    总权重在增强后保持守恒。

    Args:
        scale: 增强力度，控制因子得分对权重的最大偏离程度，默认 0.5
        allow_new_positions: 是否允许因子在零权重标的上开新仓，默认 False
        norm_method: 因子标准化方法，"zscore" 或 "rank"，默认 "zscore"
    """

    def __init__(self, scale:float=0.5, allow_new_positions:bool=False, norm_method:str="zscore", args:dict={}, config_file:Optional[str]=None, **kwargs):
        Args = {"Name": "alphaEnhanceStrategy"} | args | {"DTMode": "多时点"}
        Args["ModelArgs"] = {"scale": scale, "allow_new_positions": allow_new_positions, "norm_method": norm_method} | Args.get("ModelArgs", {})
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: list, args: dict) -> np.ndarray:
        signal = x[0].copy()   # (T, N)
        alpha = x[1].copy()    # (T, N)
        scale = args["scale"]
        allow_new_positions = args["allow_new_positions"]
        norm_method = args["norm_method"]

        # 因子截面标准化 (每期独立)
        if norm_method == "zscore":
            mu = np.nanmean(alpha, axis=1, keepdims=True)    # (T, 1)
            sigma = np.nanstd(alpha, axis=1, keepdims=True)   # (T, 1)
            sigma[sigma == 0] = np.nan
            alpha_norm = (alpha - mu) / sigma
        elif norm_method == "rank":
            rank = np.argsort(np.argsort(alpha, axis=1), axis=1)  # (T, N)
            alpha_norm = (rank / (rank.shape[1] - 1) - 0.5) * 2   # 映射到 [-1, 1]
        else:
            raise __QS_Error__(f"不支持的标准化方法: {norm_method}")

        alpha_norm = np.nan_to_num(alpha_norm, nan=0.0)

        # 增强调整
        tilt = np.maximum(0, 1 + scale * alpha_norm)

        if allow_new_positions:
            # 零权重标的也参与增强，赋予信号均值为基础权重
            base = np.where(signal > 0, signal, np.nanmean(np.where(signal > 0, signal, np.nan), axis=1, keepdims=True))
            base = np.nan_to_num(base, nan=0.0)
            adjusted = base * tilt
        else:
            adjusted = signal * tilt

        # 重归一化
        new_total = np.nansum(adjusted, axis=1, keepdims=True)
        total_weight = np.nansum(signal, axis=1, keepdims=True)
        mask = (total_weight == 0) | (new_total == 0)
        result = np.divide(adjusted, new_total, out=np.zeros_like(adjusted), where=~mask) * np.where(~mask, total_weight, 0)
        return result

    def __call__(self, signal:Factor, alpha_factor:Factor, factor_args:dict={}, **kwargs) -> SectionOperation:
        """将算子作用在若干因子对象上以产生新的因子

        Args:
            signal: 基准配置信号, 取值为投资于某证券上的比例，取值范围 [0, 1]
            alpha_factor: 选股因子，值越大表示未来预期收益越高
            factor_args: 创建新因子时传递给它的参数集
            kwargs: 创建新因子时传递给它的其他入参

        Returns:
            增强后的配置信号
        """
        Factors = [signal, alpha_factor]
        operator_kwargs = kwargs.pop("operator_kwargs", {})
        operator_kwargs["args"] = operator_kwargs.get("args", {}) | {"Arity": 2}
        return super(AlphaEnhanceStrategy, self.new(**operator_kwargs)).__call__(*Factors, factor_args=factor_args, **kwargs)

class MigrateAllocStrategy(PanelOperator):
    """基于收益相关性迁移配置型策略，每期针对原始策略的每个投资标的，计算与新投资标的过去一段时间收益率的相关性，取最相关的标的进行替代

    signal 和 old_price 的截面为 old_ids, new_price 和 mask 的截面为 new_ids,
    两个截面可以不同, 通过 DescriptorSection 机制处理不同截面的数据对齐。
    因子的截面(iid)取决于计算图, 通常为 old_ids ∪ new_ids 或 new_ids。

    Args:
        window: 计算收益率相关性的回溯窗口长度
        old_ids: 原始策略标的 ID 列表, None 表示所有因子共享同一截面
        min_periods: 计算相关性需要的最小收益率数据量, None 表示等于 window-1 (即全部收益率数据)
        min_corr: 相关性的最小阈值, 小于该值的标的不予考虑, 默认 0
        fallback_id: 兜底标的 ID, 当某 old_id 无法找到满足要求的替代标的时, 将权重迁移到该标的上, 默认 None 表示直接丢弃
    """

    def __init__(self, window:int=240, old_ids:Optional[List[str]]=None, min_periods:Optional[int]=None, min_corr:float=0.0, fallback_id:Optional[str]=None, args:dict={}, config_file:Optional[str]=None, **kwargs):
        Arity = args.get("Arity", None) or 3
        Args = {"Name": "migrateAllocStrategy"} | args | {"DTMode": "单时点"}
        Args["ModelArgs"] = {"window": window, "old_ids": old_ids or [], "min_periods": min_periods, "min_corr": min_corr, "fallback_id": fallback_id} | Args.get("ModelArgs", {})
        effective_old_ids = Args["ModelArgs"]["old_ids"]
        if effective_old_ids and "DescriptorSection" not in Args:
            Args["DescriptorSection"] = [effective_old_ids, effective_old_ids] + [None] * (Arity - 2)
        Args["LookBack"] = [0, Args["ModelArgs"]["window"] - 1, Args["ModelArgs"]["window"] - 1] + [0] * max(0, Arity - 3)
        Args["StartDT"] = [None] * Arity
        return super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: List[dt.datetime], iid: List[str], x: List[np.ndarray], args: dict) -> np.ndarray:
        signal = x[0][-1]
        if np.all(np.isnan(signal)): return np.full(shape=(nIID, ), fill_value=np.nan, dtype=float)

        old_ids_list = args["old_ids"]
        min_periods = args["min_periods"] if args["min_periods"] is not None else args["window"] - 1
        min_corr = args["min_corr"]
        nIID = len(iid)

        if not old_ids_list:
            old_price_data = x[1]
            new_price_data = x[2]
            # 同截面时迁移由 mask 控制：无 mask 则全部可投，直接返回原信号
            if len(x) <= 3:
                return signal.copy()
            mask = x[3][-1] == 1
            old_ids_list = list(iid)
            new_ids = list(iid)
        else:
            old_ids_set = set(old_ids_list)
            iid_set = set(iid)
            old_price_data = x[1]
            if old_ids_set & iid_set:
                new_idx_in_iid = [i for i, id_ in enumerate(iid) if id_ not in old_ids_set]
                new_price_data = x[2][:, new_idx_in_iid] if new_idx_in_iid else np.empty((x[2].shape[0], 0))
                if len(x) > 3:
                    mask = x[3][-1, new_idx_in_iid] == 1 if new_idx_in_iid else np.array([], dtype=bool)
                else:
                    mask = np.ones(len(new_idx_in_iid), dtype=bool)
                new_ids = [iid[i] for i in new_idx_in_iid]
            else:
                new_price_data = x[2]
                mask = (x[3][-1] == 1) if len(x) > 3 else np.ones(x[2].shape[1], dtype=bool)
                new_ids = list(iid)

        nNew = len(new_ids)
        if nNew == 0:
            return np.zeros(nIID)

        # 计算收益率
        with np.errstate(divide='ignore', invalid='ignore'):
            old_returns = np.diff(old_price_data, axis=0) / old_price_data[:-1]
            new_returns = np.diff(new_price_data, axis=0) / new_price_data[:-1]
        old_returns[np.isinf(old_returns)] = np.nan
        new_returns[np.isinf(new_returns)] = np.nan

        nOld = old_returns.shape[1]
        T = old_returns.shape[0]
        result = np.zeros(nIID)

        # 向量化计算相关系数矩阵: (nOld, nNew)
        old_nan = np.isnan(old_returns)  # (T, nOld)
        new_nan = np.isnan(new_returns)  # (T, nNew)

        # 有效数据掩码: (T, nOld, nNew)
        valid = ~(old_nan[:, :, np.newaxis] | new_nan[:, np.newaxis, :])
        valid_count = valid.sum(axis=0)  # (nOld, nNew)

        # 用 0 替换 NaN 参与运算
        old_clean = np.where(old_nan, 0, old_returns)[:, :, np.newaxis]  # (T, nOld, 1)
        new_clean = np.where(new_nan, 0, new_returns)[:, np.newaxis, :]  # (T, 1, nNew)

        # 统计量
        sum_xy = (valid * old_clean * new_clean).sum(axis=0)  # (nOld, nNew)
        sum_x = (valid * old_clean).sum(axis=0)
        sum_y = (valid * new_clean).sum(axis=0)
        sum_x2 = (valid * old_clean ** 2).sum(axis=0)
        sum_y2 = (valid * new_clean ** 2).sum(axis=0)

        # Pearson 相关系数
        num = valid_count * sum_xy - sum_x * sum_y
        den_sq = (valid_count * sum_x2 - sum_x ** 2) * (valid_count * sum_y2 - sum_y ** 2)
        den = np.sqrt(np.maximum(den_sq, 0))
        with np.errstate(divide='ignore', invalid='ignore'):
            corr_raw = np.where(den > 0, num / den, np.nan)
        corr_matrix = np.where((den > 0) & (valid_count >= min_periods) & (corr_raw >= min_corr), corr_raw, np.nan)

        # 应用 mask
        if not np.all(mask):
            corr_matrix[:, ~mask] = np.nan


        # 每个 old_id 找最相关的 new_id
        corr_filled = np.where(np.isnan(corr_matrix), -np.inf, corr_matrix)
        best_k = np.argmax(corr_filled, axis=1)  # (nOld,)
        best_corr = corr_matrix[np.arange(nOld), best_k]  # (nOld,)

        # 向量化分配权重
        new_id_to_iid_idx = {id_: i for i, id_ in enumerate(iid)}
        new_id_idx_arr = np.array([new_id_to_iid_idx.get(id_, -1) for id_ in new_ids])
        target_idx = new_id_idx_arr[best_k]  # (nOld,)
        valid_migration = (~np.isnan(signal) & (signal != 0) & ~np.isnan(best_corr) & (target_idx >= 0))

        np.add.at(result, target_idx[valid_migration], signal[valid_migration])

        # 兜底标的: 未成功迁移的权重迁移到 fallback_id
        fallback_id = args.get("fallback_id")
        if fallback_id is not None and fallback_id in iid:
            fallback_failed = ~np.isnan(signal) & (signal != 0) & ~valid_migration
            if np.any(fallback_failed):
                fallback_idx = iid.index(fallback_id)
                result[fallback_idx] += np.nansum(signal[fallback_failed])

        return result

    def __call__(self, signal:Factor, old_price:Factor, new_price:Factor, mask:Optional[Factor]=None, factor_args:dict={}, **kwargs) -> PanelOperation:
        """将算子作用在若干个因子对象上以产生新的因子

        Args:
            signal: 原始配置型策略信号, 取值为投资于某证券上的比例, 截面为 old_ids
            old_price: 原始配置型策略标的的价格因子, 截面为 old_ids
            new_price: 新配置型策略标的的价格因子, 截面为 new_ids
            mask: 新配置型策略每期可投标的的 0-1 标识因子, 截面为 new_ids, None 表示所有标的每期均可投
            factor_args: 创建新因子时传递给它的参数集
            kwargs: 创建新因子时传递给它的其他入参

        Returns:
            算子作用后产生的新配置型策略信号

        Note:
            若初始化时指定了 fallback_id, 当某 old_id 无法找到满足相关性阈值的替代标的时,
            其权重会迁移到 fallback_id 而非被丢弃。fallback_id 必须存在于因子截面 iid 中。
        """
        Factors = [signal, old_price, new_price]
        if mask is not None:
            Factors.append(mask)
        nArity = len(Factors)
        window = self._QSArgs.ModelArgs["window"]
        old_ids = self._QSArgs.ModelArgs["old_ids"]
        operator_kwargs = kwargs.pop("operator_kwargs", {})
        operator_kwargs["args"] = operator_kwargs.get("args", {}) | {
            "Arity": nArity,
            "LookBack": [0, window - 1, window - 1] + [0] * max(0, nArity - 3),
            "StartDT": [None] * nArity,
        }
        if old_ids:
            operator_kwargs["args"]["DescriptorSection"] = [old_ids, old_ids] + [None] * (nArity - 2)
        return super(MigrateAllocStrategy, self.new(**operator_kwargs)).__call__(*Factors, factor_args=factor_args, **kwargs)

class OptMigrateAllocStrategy(SectionOperator):
    """将源资产上的配置信号迁移到目标资产上，通过优化求解目标资产权重。

    源资产信号 (source_signal) 定义源资产的权重或得分, 每只目标资产通过一对 list 因子
    (target_exposure_ids, target_exposure_weights) 表达其在源资产上的暴露。
    算子逐期展开暴露列表, 构建暴露矩阵, 通过 cvxpy 求解最优目标资产权重,
    使组合的源暴露尽可能逼近或最大化源信号。

    source_signal 的截面为 source_ids, target_exposure_ids 和
    target_exposure_weights 的截面与算子输出截面一致。
    无有效目标资产或求解失败时返回全 NaN。

    Args:
        source_ids: 源资产 ID 列表, None 表示所有因子共享同一截面
        mode: 优化模式
            - "min_deviation": 最小化组合源暴露与 source_signal 的 L1 偏差
            - "max_score": 最大化组合的加权源得分 (source_signal 作为各源资产的得分)
        single_limit: 单个目标资产权重上限, None 表示不限制
        min_weight: 求解后剔除权重低于此值的目标资产并重归一化
        allow_cash: max_score 模式下是否允许总仓位 < 1, 默认 False
    """

    def __init__(self, source_ids: Optional[List[str]] = None,
                 mode: Literal["min_deviation", "max_score"] = "min_deviation",
                 single_limit: Optional[float] = 0.25, min_weight: float = 0.0,
                 allow_cash: bool = False, args: dict = {},
                 config_file: Optional[str] = None, **kwargs):
        Arity = args.get("Arity", None) or 3
        Args = {"Name": "optmigrateAllocStrategy"} | args | {"DTMode": "单时点"}
        Args["ModelArgs"] = {
            "mode": mode, "single_limit": single_limit,
            "min_weight": min_weight, "allow_cash": allow_cash,
            "source_ids": source_ids or [],
        } | Args.get("ModelArgs", {})
        if source_ids and "DescriptorSection" not in Args:
            Args["DescriptorSection"] = [source_ids] + [None] * (Arity - 1)
        super().__init__(args=Args, config_file=config_file, **kwargs)

    def calculate(self, f: Factor, idt: dt.datetime, iid: List[str], x: list, args: dict) -> np.ndarray:
        source_ids = args["source_ids"] or iid[:len(x[0])]
        mode = args["mode"]
        single_limit = args["single_limit"]
        min_weight = args["min_weight"]

        n_iid = len(iid)
        n_source = len(source_ids)

        # 用 DataFrame 批量展开 exposure: columns=source_ids, index=range(n_target)
        target_count = len(iid)
        target_mask = (x[3][:target_count] == 1) if len(x) > 3 else np.ones(target_count, dtype=bool)

        # 构建 (n_target, n_source) 暴露矩阵, 通过 Series.apply 填充
        source_idx_map = pd.Series(range(n_source), index=source_ids)
        rows = np.repeat(np.arange(target_count), [len(ids) if isinstance(ids, list) else 0 for ids in x[1][:target_count]])
        flat_ids = np.concatenate([ids for ids in x[1][:target_count] if isinstance(ids, list) and len(ids) > 0])
        flat_weights = np.concatenate([ws for ws in x[2][:target_count] if isinstance(ws, list) and len(ws) > 0])

        # 映射源 ID 到索引
        col_indices = np.array([source_idx_map.get(sid, -1) for sid in flat_ids])
        valid = (col_indices >= 0) & np.isfinite(flat_weights) & (flat_weights > 0)
        rows, col_indices, flat_weights = rows[valid], col_indices[valid], flat_weights[valid]

        if len(rows) == 0:
            return np.full(n_iid, np.nan)

        exposure_mat = np.zeros((target_count, n_source))
        exposure_mat[rows, col_indices] = flat_weights

        # 行归一化 + mask 过滤
        row_sum = exposure_mat.sum(axis=1)
        valid_rows = (row_sum > 0) & target_mask
        valid_iid_indices = np.where(valid_rows)[0]
        exposure_mat = exposure_mat[valid_rows]
        row_sum = row_sum[valid_rows, np.newaxis]
        exposure_mat = exposure_mat / row_sum

        n_valid = len(valid_iid_indices)
        if n_valid == 0:
            return np.full(n_iid, np.nan)

        target_dist = np.nan_to_num(x[0], nan=0.0)

        try:
            w = cp.Variable(n_valid, nonneg=True)

            if mode == "min_deviation":
                objective = cp.Minimize(cp.sum(cp.abs(exposure_mat.T @ w - target_dist)))
                constraints = [cp.sum(w) == 1]
                if single_limit is not None:
                    constraints.append(w <= single_limit)
            else:  # max_score
                scores = exposure_mat @ target_dist
                objective = cp.Maximize(scores @ w)
                constraints = [cp.sum(w) == 1, w >= 1e-8]
                k = int(np.sum(target_dist > 0))
                if k > 0:
                    constraints.append(exposure_mat.T @ w <= 1.0 / k)
                if not args.get("allow_cash", False):
                    constraints.append(cp.sum(w) == 1)
                if single_limit is not None:
                    constraints.append(w <= single_limit)

            prob = cp.Problem(objective, constraints)
            prob.solve(solver=cp.CLARABEL)

            if w.value is None:
                return np.full(n_iid, np.nan)

            result_w = np.maximum(w.value, 0)
            total = result_w.sum()
            if total > 0:
                result_w = result_w / total

            if min_weight > 0:
                keep = result_w >= min_weight
                result_w = result_w[keep]
                valid_iid_indices = valid_iid_indices[keep]
                total = result_w.sum()
                if total > 0:
                    result_w = result_w / total

            output = np.zeros(n_iid)
            output[valid_iid_indices] = result_w
            return output

        except cp.error.SolverError:
            return np.full(n_iid, np.nan)

    def __call__(self, source_signal: Factor, target_exposure_ids: Factor,
                 target_exposure_weights: Factor, target_mask: Optional[Factor] = None,
                 factor_args: dict = {}, **kwargs) -> SectionOperation:
        """将算子作用在因子对象上以产生新的因子

        Args:
            source_signal: 源资产上的配置信号, 截面为源资产 ID
            target_exposure_ids: 每只目标资产在各期映射到的源资产 ID 列表, 截面与输出截面一致
            target_exposure_weights: 对应的暴露权重列表, 截面与输出截面一致
            target_mask: 每期可投目标资产的 0-1 标识, 截面与输出截面一致, None 表示全部可投
            factor_args: 创建新因子时传递给它的参数集
            kwargs: 创建新因子时传递给它的其他入参

        Returns:
            目标资产上的配置权重信号
        """
        Factors = [source_signal, target_exposure_ids, target_exposure_weights]
        if target_mask is not None:
            Factors.append(target_mask)
        nArity = len(Factors)
        operator_kwargs = kwargs.pop("operator_kwargs", {})
        operator_kwargs["args"] = operator_kwargs.get("args", {}) | {"Arity": nArity}
        source_ids = self._QSArgs.ModelArgs.get("source_ids")
        if source_ids and "DescriptorSection" not in operator_kwargs["args"]:
            operator_kwargs["args"]["DescriptorSection"] = [source_ids] + [None] * (nArity - 1)
        return super(OptMigrateAllocStrategy, self.new(**operator_kwargs)).__call__(*Factors, factor_args=factor_args, **kwargs)

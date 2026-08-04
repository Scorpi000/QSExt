# -*- coding: utf-8 -*-
"""评测缓存管理器。

管理 FeatherFactorCache 的创建和生命周期，支持跨轮次复用缓存。

当 start_mode="continue" 且 state.pkl 不存在时，Cache 内部会自动
降级为 new 模式并给出警告，外部调用者无需手动检测。

使用示例::

    from QSExt.LLMFactor.evaluation.cache_manager import EvalCacheManager

    # 创建管理器
    manager = EvalCacheManager(cache_dir="/tmp/qs_cache", start_mode="continue")

    # 获取 Cache 实例（首次创建，后续复用）
    cache = manager.get_or_create(dt_ruler)

    # 传递给 evaluator
    evaluator.evaluate(..., cache=cache)

    # 使用完毕后关闭（持久化状态到 state.pkl）
    manager.close()
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

__QS_Logger__ = logging.getLogger("QSR.evaluation.cache_manager")


class EvalCacheManager:
    """评测缓存管理器。

    Attributes:
        cache_dir: 缓存目录路径
        start_mode: 启动模式（"new" 清空，"continue" 复用）
        enabled: 是否启用缓存
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        start_mode: str = "continue",
        enabled: bool = True,
    ):
        self.cache_dir = cache_dir
        self.start_mode = start_mode
        self.enabled = enabled
        self._cache = None
        self._dt_ruler = None
        self._temp_dir = None  # 持有临时目录引用，防止被 GC 回收

    def get_or_create(self, dt_ruler):
        """获取或创建 FeatherFactorCache 实例。

        若已创建且 dt_ruler 未变，则直接复用。

        Args:
            dt_ruler: 交易日序列

        Returns:
            FeatherFactorCache 实例，若 enabled=False 则返回 None
        """
        if not self.enabled:
            return None

        # dt_ruler 未变则复用
        if self._cache is not None and self._dt_ruler is dt_ruler:
            return self._cache

        # 关闭旧 cache
        if self._cache is not None:
            self.close()

        # 解析缓存目录
        resolved_dir = self._resolve_cache_dir()

        from QuantStudio.Factor.FactorCache import FeatherFactorCache

        self._cache = FeatherFactorCache(args={
            "DTRuler": dt_ruler,
            "PIDs": ["0"],
            "CacheDir": resolved_dir,
            "StartMode": self.start_mode,
        })
        # 启动缓存（初始化内部目录结构）
        # 当 StartMode="continue" 且 state.pkl 不存在时，Cache 内部会自动警告并降级
        self._cache.start()
        self._dt_ruler = dt_ruler

        __QS_Logger__.info(
            "Cache 已创建: dir=%s, mode=%s",
            resolved_dir, self.start_mode,
        )
        return self._cache

    def close(self):
        """关闭 Cache，持久化状态到磁盘。"""
        if self._cache is not None:
            try:
                self._cache.end()
            except Exception as e:
                __QS_Logger__.warning("关闭 Cache 时出错: %s", e)
            self._cache = None
            self._dt_ruler = None
            __QS_Logger__.info("Cache 已关闭")

    def _resolve_cache_dir(self) -> str:
        """解析缓存目录路径。

        Returns:
            缓存目录的绝对路径
        """
        if self.cache_dir:
            return self.cache_dir

        # 使用系统临时目录
        self._temp_dir = tempfile.mkdtemp(prefix="qs_eval_cache_")
        return self._temp_dir

    def __del__(self):
        """析构时关闭 Cache。"""
        self.close()

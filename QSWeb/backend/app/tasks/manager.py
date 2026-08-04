"""
异步任务管理器

支持任务提交、进度跟踪、结果存储和 WebSocket 进度推送。
基于 asyncio，内存存储，适用于小团队部署。
"""

import asyncio
import traceback
import uuid
import datetime as dt_mod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import OrderedDict


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """单个任务"""

    def __init__(self, task_id: str, name: str):
        self.task_id = task_id
        self.name = name
        self.status = TaskStatus.PENDING
        self.progress = 0.0  # 0.0 - 100.0 (百分制，与后端传递保持一致)
        self.progress_message = ""
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.created_at = dt_mod.datetime.now(dt_mod.timezone.utc).isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self._callbacks: List[Callable] = []  # 状态变更回调（用于 WebSocket 推送）

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class TaskManager:
    """
    异步任务管理器（内存存储）。

    用法:
        # 提交任务
        task = await task_manager.submit("回测", coro_or_func)

        # 任务内部更新进度
        await task_manager.update_progress(task_id, 50, "计算 IC...")

        # 等待完成
        result = await task_manager.wait(task_id)
    """

    def __init__(self, max_history: int = 200):
        self._tasks: OrderedDict[str, Task] = OrderedDict()
        self._max_history = max_history
        self._running: Dict[str, asyncio.Task] = {}
        self._subscribers: Dict[str, Set[Callable]] = {}  # task_id -> set of callbacks
        self._on_cancel_callbacks: Dict[str, Callable] = {}  # task_id -> cancel callback

    def subscribe(self, task_id: str, callback: Callable):
        """注册状态变更回调（WebSocket 推送用）"""
        if task_id not in self._subscribers:
            self._subscribers[task_id] = set()
        self._subscribers[task_id].add(callback)

    def unsubscribe(self, task_id: str, callback: Callable):
        """移除回调"""
        if task_id in self._subscribers:
            self._subscribers[task_id].discard(callback)
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]

    async def _notify(self, task: Task):
        """通知所有订阅者"""
        data = task.to_dict()
        callbacks = self._subscribers.get(task.task_id, set())
        for cb in list(callbacks):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception:
                pass

    async def submit(
        self,
        name: str,
        coro_or_func,
        task_id: Optional[str] = None,
    ) -> str:
        """
        提交异步任务。

        Parameters
        ----------
        name : str
            任务名称
        coro_or_func : coroutine or callable
            要执行的协程或可调用对象。如果是 callable，会被作为 asyncio.to_thread 包装。
        task_id : str, optional
            自定义任务 ID，不提供时自动生成

        Returns
        -------
        str
            任务 ID
        """
        if task_id is None:
            task_id = uuid.uuid4().hex[:12]

        task = Task(task_id, name)
        self._tasks[task_id] = task

        # 清理过期任务
        while len(self._tasks) > self._max_history:
            oldest = next(iter(self._tasks))
            if oldest in self._running:
                break
            del self._tasks[oldest]

        # 异步执行
        async def _run():
            task.status = TaskStatus.RUNNING
            task.started_at = dt_mod.datetime.now(dt_mod.timezone.utc).isoformat()
            await self._notify(task)

            try:
                if asyncio.iscoroutine(coro_or_func):
                    result = await coro_or_func
                else:
                    result = await asyncio.to_thread(coro_or_func)

                task.status = TaskStatus.COMPLETED
                task.result = result
                task.progress = 100.0
                task.progress_message = "完成"
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.progress_message = f"失败: {str(e)}"
                traceback.print_exc()
            finally:
                task.completed_at = dt_mod.datetime.now(dt_mod.timezone.utc).isoformat()
                await self._notify(task)
                self._running.pop(task_id, None)

        self._running[task_id] = asyncio.create_task(_run())
        return task_id

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str = ""
    ):
        """更新任务进度（由执行中的任务调用）"""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.progress = min(max(progress, 0.0), 100.0)
        task.progress_message = message
        await self._notify(task)

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息"""
        return self._tasks.get(task_id)

    def get_task_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息的字典格式"""
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def get_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务列表（最近的任务在前）"""
        tasks = list(self._tasks.values())[-limit:]
        tasks.reverse()
        return [t.to_dict() for t in tasks]

    async def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """等待任务完成并返回结果"""
        running = self._running.get(task_id)
        if running is not None:
            try:
                await asyncio.wait_for(running, timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"任务 {task_id} 超时")

        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")

        if task.status == TaskStatus.FAILED:
            raise RuntimeError(task.error or "任务执行失败")

        return task.result

    def cancel(self, task_id: str) -> bool:
        """取消任务。先调用 on_cancel 回调（如有），再取消 asyncio Task。"""
        # 先执行 on_cancel 回调（如 LLMFactor 的 proc.kill()）
        on_cancel = self._on_cancel_callbacks.pop(task_id, None)
        if on_cancel is not None:
            try:
                on_cancel()
            except Exception:
                pass

        running = self._running.get(task_id)
        if running is not None:
            running.cancel()
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = "任务已取消"
                task.completed_at = dt_mod.datetime.now(dt_mod.timezone.utc).isoformat()
            return True
        return False

    def set_on_cancel(self, task_id: str, callback: Callable):
        """注册取消回调（框架级清理逻辑，如 proc.kill()）"""
        self._on_cancel_callbacks[task_id] = callback


# 全局实例
task_manager = TaskManager()

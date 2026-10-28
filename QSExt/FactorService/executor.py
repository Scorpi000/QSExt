"""有界单线程资源执行器，保证连接和调用的线程归属。"""

import queue
import threading
import time
from concurrent.futures import Future

from .protocol import RemoteFactorError


class ResourceExecutor:
    """同一资源顺序执行，未开始的过期任务不调用后端。"""

    def __init__(self, max_queue, queue_timeout, close_callback):
        self._queue = queue.Queue(maxsize=max_queue)
        self._timeout = queue_timeout
        self._close = close_callback
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="qs-factor-resource")
        self._thread.start()

    def submit(self, callback):
        """非阻塞入队，返回线程 Future。"""
        future = Future()
        with self._lock:
            if self._closed:
                raise RemoteFactorError("因子库服务正在关闭", code="CLOSED", status=503, effect="not_started")
            try:
                self._queue.put_nowait((time.monotonic(), future, callback))
            except queue.Full:
                raise RemoteFactorError("资源队列已满", code="QUEUE_FULL", status=429, retryable=True, effect="not_started") from None
        return future

    def _run(self):
        while True:
            try:
                task = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._closed:
                    break
                continue
            try:
                if task is None:
                    break
                queued_at, future, callback = task
                if not future.set_running_or_notify_cancel():
                    continue
                if time.monotonic() - queued_at > self._timeout:
                    future.set_exception(RemoteFactorError("排队超时，操作未执行", code="QUEUE_TIMEOUT", status=504, effect="not_started"))
                    continue
                try:
                    future.set_result(callback())
                except BaseException as exc:
                    future.set_exception(exc)
            finally:
                self._queue.task_done()
        self._close()

    def close(self):
        """停止接收并排空队列，在资源线程内关闭连接。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._thread.join(timeout=self._timeout)

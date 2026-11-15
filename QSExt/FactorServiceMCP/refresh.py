"""因子目录后台初始化、周期刷新与状态管理。"""

import datetime as dt
import threading
import time


def _iso(timestamp):
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


class CatalogRefreshManager:
    """单线程刷新调度器；失败时保留 FactorCatalog 的上一份事务快照。"""

    def __init__(self, service, interval_seconds=86400):
        self.service = service
        self.interval_seconds = interval_seconds
        self._condition = threading.Condition()
        self._pending_source = None
        self._running = False
        self._source = None
        self._started_at = None
        self._completed_at = None
        self._next_refresh_at = None
        self._last_error = None
        self._last_result = None
        self._stopped = False
        self._thread = None

    def start(self):
        with self._condition:
            if self._thread is not None:
                return
            refreshed = self.service.catalog.state("refreshed_at")
            due_at = float(refreshed) + self.interval_seconds if refreshed else None
            if not self.service.catalog.count() or due_at is None or due_at <= time.time():
                self._pending_source = "startup"
            else:
                self._next_refresh_at = due_at
            self._thread = threading.Thread(target=self._run, name="factor-catalog-refresh", daemon=True)
            self._thread.start()

    def stop(self, timeout=5):
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def request_refresh(self, source="manual"):
        with self._condition:
            if self._stopped or self._running or self._pending_source is not None:
                return False
            self._pending_source = source
            self._condition.notify_all()
            return True

    def status(self):
        catalog = self.service.catalog
        with self._condition:
            status = "running" if self._running else "error" if self._last_error else "idle"
            result = {
                "status": status,
                "source": self._source,
                "pending": self._pending_source is not None,
                "started_at": _iso(self._started_at),
                "completed_at": _iso(self._completed_at),
                "next_refresh_at": _iso(self._next_refresh_at),
                "last_error": self._last_error,
                "last_result": self._last_result,
                "interval_seconds": self.interval_seconds,
            }
        refreshed = catalog.state("refreshed_at")
        result.update(factor_count=catalog.count(),
                      catalog_refreshed_at=_iso(float(refreshed)) if refreshed else None,
                      catalog_stale=catalog.is_stale())
        return result

    def _run(self):
        while True:
            with self._condition:
                while not self._stopped and self._pending_source is None:
                    timeout = None if self._next_refresh_at is None else max(0, self._next_refresh_at - time.time())
                    self._condition.wait(timeout)
                    if (not self._stopped and self._pending_source is None
                            and self._next_refresh_at is not None and time.time() >= self._next_refresh_at):
                        self._pending_source = "scheduled"
                if self._stopped:
                    return
                self._source = self._pending_source
                self._pending_source = None
                self._running = True
                self._started_at = time.time()
                self._last_error = None
            try:
                result = self.service.refresh_catalog()
            except Exception as error:
                with self._condition:
                    self._last_error = f"{type(error).__name__}: {error}"
                    self._last_result = None
            else:
                with self._condition:
                    self._last_result = result
                    self._last_error = None
            finally:
                with self._condition:
                    self._running = False
                    self._completed_at = time.time()
                    self._next_refresh_at = self._completed_at + self.interval_seconds
                    self._condition.notify_all()

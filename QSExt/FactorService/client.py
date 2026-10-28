"""同步 HTTP 客户端；进程间只传认证来源，不传 socket 或令牌。"""

import os
import threading
import time
import uuid
from urllib.parse import quote, urlsplit

import httpx

from .codec import dumps_control, loads_control, pack, unpack
from .protocol import PREFIX, PROTOCOL_VERSION, RemoteFactorError


class FactorDBServiceClient:
    """发现远程库并发送受限数据源请求。"""

    def __init__(self, server_url, token_env="QS_FACTOR_CLIENT_TOKEN", timeout_seconds=120, connect_timeout_seconds=10):
        parsed = urlsplit(server_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ServerURL 必须为不含凭据、查询或片段的 HTTP(S) 地址")
        self.server_url = server_url.rstrip("/")
        self.token_env = token_env
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self._client = None
        self._pid = None
        self._verified_pid = None
        self._lock = threading.Lock()
        self.info = None

    def __getstate__(self):
        state = self.__dict__.copy()
        state.update(_client=None, _pid=None, _verified_pid=None, _lock=None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.Lock()

    def _transport(self):
        with self._lock:
            if self._client is None or self._pid != os.getpid():
                self._client = httpx.Client(timeout=httpx.Timeout(self.timeout_seconds, connect=self.connect_timeout_seconds), follow_redirects=False)
                self._pid = os.getpid()
            return self._client

    def _request(self, method, path, value=None, binary=False, mutation=False):
        if self.info is not None and self._verified_pid != os.getpid() and path != "/info":
            self.connect()
        token = os.environ.get(self.token_env)
        if not token:
            raise RemoteFactorError("客户端认证令牌环境变量未设置", code="UNAUTHORIZED", status=401)
        limit = self.info["limits"]["MaxResponseBytes"] if self.info else 8 * 1024 * 1024
        headers = {"Authorization": "Bearer " + token}
        data = pack(value, self.info["limits"]["MaxRequestBytes"]) if binary else (dumps_control(value) if value is not None else None)
        if data is not None and self.info and len(data) > self.info["limits"]["MaxRequestBytes"]:
            raise RemoteFactorError("请求超过服务端字节限制", code="TOO_LARGE", status=413)
        headers["Content-Type"] = "application/vnd.quantstudio.factor+binary" if binary else "application/json"
        try:
            with self._transport().stream(method, self.server_url + PREFIX + path, content=data, headers=headers) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise RemoteFactorError("响应超过字节限制", code="TOO_LARGE", status=413)
                body = bytes(body)
                if response.status_code >= 400:
                    error = loads_control(body)
                    if mutation:
                        operation = value.get("request", value)
                        error.setdefault("operation_id", operation.get("operation_id"))
                    raise RemoteFactorError(error.pop("message", "远程调用失败"), code=error.pop("code", "REMOTE_ERROR"), status=response.status_code, **error)
                if response.headers.get("content-type", "").startswith("application/vnd.quantstudio.factor+binary"):
                    self.last_read_metadata = {"read_at": response.headers.get("X-QS-Read-At"), "metadata_revision": response.headers.get("X-QS-Metadata-Revision"), "data_version": None}
                    return unpack(body, limit)
                return loads_control(body)
        except httpx.HTTPError as exc:
            operation = value.get("request", value) if isinstance(value, dict) else {}
            raise RemoteFactorError("网络调用失败；已开始的写操作结果可能未知" if mutation else "远程网络调用失败", code="TRANSPORT_ERROR", status=503, operation_id=operation.get("operation_id"), effect="unknown" if mutation else None) from exc
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            operation = value.get("request", value) if isinstance(value, dict) else {}
            raise RemoteFactorError("远程响应不完整或编码无效", code="INVALID_RESPONSE", status=502, operation_id=operation.get("operation_id"), effect="unknown" if mutation else None) from exc

    def connect(self):
        """协商协议，校验服务身份并刷新启动标识。"""
        info = self._request("GET", "/info")
        if info["protocol_version"] != PROTOCOL_VERSION:
            raise RemoteFactorError("协议主版本不兼容", code="PROTOCOL_MISMATCH", status=409)
        if self.info and self.info["service_id"] != info["service_id"]:
            raise RemoteFactorError("服务器公开身份变化", code="RESOURCE_CHANGED", status=409)
        self.info = info
        self._verified_pid = os.getpid()
        return self

    def listDatabases(self):
        """返回可见的公开库目录。"""
        if self.info is None:
            self.connect()
        return self._request("GET", "/databases")

    def getDatabase(self, name):
        """创建一个使用相同传输配置的库代理。"""
        from QSExt.Factor.RemoteDB import RemoteFactorDB
        return RemoteFactorDB(args={"ServerURL": self.server_url, "Database": name, "TokenEnv": self.token_env, "TimeoutSeconds": self.timeout_seconds, "ConnectTimeoutSeconds": self.connect_timeout_seconds})

    def call(self, database, identity, target, operation="describe", kwargs=None, action="invoke", data=None, mutation=False):
        """构造明确目标请求；写请求一次发送，不自动重放。"""
        if self.info is None:
            self.connect()
        request = {"request_id": uuid.uuid4().hex, "resource_id": identity["resource_id"], "config_revision": identity["config_revision"], "target": target, "operation": operation, "kwargs": kwargs or {}}
        if mutation:
            request.update(operation_id=uuid.uuid4().hex, epoch=self.info["epoch"], expires_at=time.time() + min(120, self.info["limits"]["OperationTTLSeconds"] * 0.9))
            self.last_operation_id = request["operation_id"]
        path = "/databases/" + quote(database, safe="") + "/" + action
        value = {"request": request, "data": data} if action == "write" else request
        return self._request("POST", path, value, binary=action == "write", mutation=mutation)

    def readBatch(self, database, requests):
        """批量读取原子规格，返回与请求一一对应的数据。"""
        response = self._request("POST", "/databases/" + quote(database, safe="") + "/read-batch", {"requests": requests})
        if [item["read_spec_id"] for item in response] != [item["request_id"] for item in requests]:
            raise RemoteFactorError("批量响应映射不一致", code="INVALID_RESPONSE", status=502)
        return [item["data"] for item in response]

    def getOperation(self, operation_id):
        """查询写入状态，不重新提交写入。"""
        return self._request("GET", "/operations/" + quote(operation_id, safe=""))

    def close(self):
        """释放当前进程的 HTTP 连接。"""
        with self._lock:
            if self._client is not None and self._pid == os.getpid():
                self._client.close()
            self._client = None
            self._verified_pid = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.close()

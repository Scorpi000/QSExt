"""客户端网络失败、身份协商及受限重试行为测试。"""

import os
import unittest
from unittest import mock

import httpx

from QSExt.FactorService.client import FactorDBServiceClient
from QSExt.FactorService.codec import dumps_control
from QSExt.FactorService.protocol import RemoteFactorError


class TestClient(unittest.TestCase):
    """写入响应丢失只报告未知结果，不自动重新提交。"""

    def client(self, handler):
        client = FactorDBServiceClient("https://example.test", "QS_TEST_TRANSPORT_TOKEN")
        client.info = {"service_id": "s", "epoch": "epoch", "protocol_version": 1, "limits": {"MaxRequestBytes": 1024 * 1024, "MaxResponseBytes": 1024 * 1024, "OperationTTLSeconds": 300}}
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        client._pid = client._verified_pid = os.getpid()
        self.addCleanup(client.close)
        patcher = mock.patch.dict(os.environ, {"QS_TEST_TRANSPORT_TOKEN": "temporary-value"})
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_write_response_lost_is_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            raise httpx.ReadTimeout("模拟服务器已执行但响应丢失", request=request)
        client = self.client(handler)
        with self.assertRaises(RemoteFactorError) as error:
            client.call("db", {"resource_id": "r", "config_revision": "v"}, {"kind": "database"}, "deleteTable", {"table_name": "daily"}, mutation=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(error.exception.details["effect"], "unknown")
        self.assertEqual(error.exception.operation_id, client.last_operation_id)

    def test_server_identity_change_after_restore(self):
        def handler(request):
            return httpx.Response(200, content=dumps_control({"service_id": "different", "protocol_version": 1}))
        client = self.client(handler)
        client._verified_pid = None
        with self.assertRaises(RemoteFactorError) as error:
            client.listDatabases()
        self.assertEqual(error.exception.code, "RESOURCE_CHANGED")

    def test_server_error_preserves_operation_id(self):
        def handler(request):
            return httpx.Response(500, json={"message": "后端失败", "code": "BACKEND_ERROR", "effect": "unknown"})
        client = self.client(handler)
        with self.assertRaises(RemoteFactorError) as error:
            client.call("db", {"resource_id": "r", "config_revision": "v"}, {"kind": "database"}, "deleteTable", {"table_name": "daily"}, mutation=True)
        self.assertEqual(error.exception.operation_id, client.last_operation_id)


if __name__ == "__main__":
    unittest.main()

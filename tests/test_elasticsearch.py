# -*- coding: utf-8 -*-
"""测试 Elasticsearch 基本连接和读写功能"""
import datetime as dt
import json
import os
import unittest

from elasticsearch import Elasticsearch


class TestElasticsearch(unittest.TestCase):
    """Elasticsearch 连接和读写测试"""

    @classmethod
    def setUpClass(cls):
        config_path = os.path.expanduser("~/QuantStudioConfig/ElasticSearchDBConfig.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        connect_args = config["ConnectArgs"]
        # 转换为 elasticsearch 9.x 格式
        host = connect_args.get("host", "localhost")
        port = connect_args.get("port", 9200)
        hosts = f"http://{host}:{port}"
        # 去掉 http_auth 中的 null
        kwargs = {"hosts": hosts}
        auth = connect_args.get("http_auth")
        if auth and auth != [None, None]:
            kwargs["basic_auth"] = (auth[0], auth[1])
        cls.ES = Elasticsearch(**kwargs)
        cls.INDEX_NAME = "qs_test_connection"

    def setUp(self):
        # 每个测试前清理索引
        if self.ES.indices.exists(index=self.INDEX_NAME):
            self.ES.indices.delete(index=self.INDEX_NAME)

    @classmethod
    def tearDownClass(cls):
        if cls.ES.indices.exists(index=cls.INDEX_NAME):
            cls.ES.indices.delete(index=cls.INDEX_NAME)
        cls.ES.close()

    # ==================== 连接测试 ====================

    def test_ping(self):
        """测试连接是否可达"""
        self.assertTrue(self.ES.ping())

    def test_info(self):
        """测试获取集群信息"""
        info = self.ES.info()
        self.assertIn("cluster_name", info)
        self.assertIn("version", info)
        print(f"\n集群: {info['cluster_name']}, 版本: {info['version']['number']}")

    # ==================== 索引操作 ====================

    def test_create_and_delete_index(self):
        """测试创建和删除索引"""
        index = "qs_test_temp"
        try:
            self.ES.indices.create(index=index, mappings={
                "properties": {
                    "name": {"type": "keyword"},
                    "value": {"type": "float"},
                }
            })
            self.assertTrue(self.ES.indices.exists(index=index))
        finally:
            self.ES.indices.delete(index=index)
            self.assertFalse(self.ES.indices.exists(index=index))

    # ==================== 文档读写 ====================

    def test_index_and_get_document(self):
        """测试写入和读取单个文档"""
        doc = {
            "code": "000001.SZ",
            "datetime": "2024-01-01T00:00:00",
            "close": 10.5,
            "volume": 1000000,
        }
        resp = self.ES.index(index=self.INDEX_NAME, document=doc, refresh="true")
        self.assertEqual(resp["result"], "created")

        # 读取
        get_resp = self.ES.get(index=self.INDEX_NAME, id=resp["_id"])
        self.assertEqual(get_resp["_source"]["code"], "000001.SZ")
        self.assertAlmostEqual(get_resp["_source"]["close"], 10.5)

    def test_bulk_write_and_search(self):
        """测试批量写入和搜索"""
        # 创建索引，指定 code 为 keyword 类型
        self.ES.indices.create(index=self.INDEX_NAME, mappings={
            "properties": {
                "code": {"type": "keyword"},
                "datetime": {"type": "date"},
                "close": {"type": "float"},
            }
        })
        docs = [
            {"_index": self.INDEX_NAME, "_source": {"code": "000001.SZ", "datetime": "2024-01-01T00:00:00", "close": 10.5}},
            {"_index": self.INDEX_NAME, "_source": {"code": "000001.SZ", "datetime": "2024-01-02T00:00:00", "close": 10.8}},
            {"_index": self.INDEX_NAME, "_source": {"code": "000002.SZ", "datetime": "2024-01-01T00:00:00", "close": 20.1}},
            {"_index": self.INDEX_NAME, "_source": {"code": "000002.SZ", "datetime": "2024-01-02T00:00:00", "close": 19.5}},
        ]
        from elasticsearch import helpers
        success, _ = helpers.bulk(self.ES, docs)
        self.assertEqual(success, 4)
        self.ES.indices.refresh(index=self.INDEX_NAME)

        # 搜索所有文档
        result = self.ES.search(index=self.INDEX_NAME, query={"match_all": {}})
        self.assertEqual(result["hits"]["total"]["value"], 4)

        # 按条件搜索
        result = self.ES.search(index=self.INDEX_NAME, query={
            "term": {"code": "000001.SZ"}
        })
        self.assertEqual(result["hits"]["total"]["value"], 2)

    def test_update_document(self):
        """测试更新文档"""
        doc = {"code": "000001.SZ", "close": 10.5}
        resp = self.ES.index(index=self.INDEX_NAME, document=doc, refresh="true")
        doc_id = resp["_id"]

        # 更新
        self.ES.update(index=self.INDEX_NAME, id=doc_id, doc={"close": 11.0}, refresh="true")
        get_resp = self.ES.get(index=self.INDEX_NAME, id=doc_id)
        self.assertAlmostEqual(get_resp["_source"]["close"], 11.0)

    def test_delete_document(self):
        """测试删除文档"""
        doc = {"code": "000001.SZ", "close": 10.5}
        resp = self.ES.index(index=self.INDEX_NAME, document=doc, refresh="true")
        doc_id = resp["_id"]

        self.ES.delete(index=self.INDEX_NAME, id=doc_id, refresh="true")
        self.assertFalse(self.ES.exists(index=self.INDEX_NAME, id=doc_id))

    def test_delete_by_query(self):
        """测试按条件删除"""
        # 创建索引，指定 code 为 keyword 类型
        self.ES.indices.create(index=self.INDEX_NAME, mappings={
            "properties": {
                "code": {"type": "keyword"},
                "value": {"type": "float"},
            }
        })
        docs = [
            {"_index": self.INDEX_NAME, "_source": {"code": "000001.SZ", "value": 1.0}},
            {"_index": self.INDEX_NAME, "_source": {"code": "000002.SZ", "value": 2.0}},
            {"_index": self.INDEX_NAME, "_source": {"code": "000001.SZ", "value": 3.0}},
        ]
        from elasticsearch import helpers
        helpers.bulk(self.ES, docs)
        self.ES.indices.refresh(index=self.INDEX_NAME)

        # 删除 code=000001.SZ 的文档
        self.ES.delete_by_query(index=self.INDEX_NAME, query={
            "term": {"code": "000001.SZ"}
        })
        self.ES.indices.refresh(index=self.INDEX_NAME)

        result = self.ES.search(index=self.INDEX_NAME, query={"match_all": {}})
        self.assertEqual(result["hits"]["total"]["value"], 1)
        self.assertEqual(result["hits"]["hits"][0]["_source"]["code"], "000002.SZ")


if __name__ == "__main__":
    unittest.main()

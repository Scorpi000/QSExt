# -*- coding: utf-8 -*-
"""向量语义检索测试。

测试覆盖：
  - EmbeddingService 编码和格式转换
  - Repository 层：入库自动写入 embedding、向量检索
  - Retriever 层：search_by_embedding、search_similar_accepted、get_similar_failures

运行方式：
    # 仅运行单元测试（不需要数据库和 Ollama）
    pytest tests/test_retriever_embedding.py -v -k "not integration"

    # 运行全部测试（需要 PostgreSQL + Ollama）
    pytest tests/test_retriever_embedding.py -v

环境要求：
    - QSExt/config/.env 中配置 POSTGRESQL_KDB_DSN_DEV
    - Ollama 服务运行中（bge-m3 模型可用）
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dotenv import load_dotenv

from QSExt import __QS_MainPath__

load_dotenv(__QS_MainPath__ + "/config/.env")

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    Experience,
    Decision,
    ExperienceTrack,
    ExperienceType,
)
from QSExt.LLMFactor.mining_log.embedding import EmbeddingService


# ============================================================
# EmbeddingService 单元测试（不需要 Ollama）
# ============================================================


class TestEmbeddingServiceFormat:
    """EmbeddingService 格式转换测试（不调用远程服务）。"""

    def test_to_db_format(self):
        """to_db_format 应输出 pgvector 兼容的字符串。"""
        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "bge-m3"
        svc._timeout = 30
        svc._base_url = "http://localhost"

        vec = np.array([0.1, 0.2, -0.3], dtype=np.float32)
        result = svc.to_db_format(vec)
        assert result.startswith("[")
        assert result.endswith("]")
        assert "0.1" in result
        assert "-0.3" in result

    def test_to_db_format_precision(self):
        """to_db_format 应保留 8 位小数精度。"""
        svc = EmbeddingService.__new__(EmbeddingService)
        svc._model = "bge-m3"
        svc._timeout = 30
        svc._base_url = "http://localhost"

        vec = np.array([0.123456789], dtype=np.float32)
        result = svc.to_db_format(vec)
        # 应保留 8 位
        assert "0.12345679" in result  # float32 四舍五入


class TestEmbeddingServiceEncode:
    """EmbeddingService 编码测试（mock 远程调用）。"""

    @patch("requests.post")
    def test_encode_success(self, mock_post):
        """正常编码应返回正确维度的向量。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": [0.1] * 1024}
        mock_post.return_value = mock_resp

        svc = EmbeddingService(base_url="http://localhost:11434", model="bge-m3")
        vec = svc.encode("测试文本")
        assert vec.shape == (1024,)
        assert vec.dtype == np.float32

    @patch("requests.post")
    def test_encode_empty_text(self, mock_post):
        """空文本应返回零向量，不调用远程服务。"""
        svc = EmbeddingService(base_url="http://localhost:11434", model="bge-m3")
        vec = svc.encode("   ")
        assert vec.shape == (1024,)
        assert np.allclose(vec, 0)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_encode_remote_error(self, mock_post):
        """远程服务出错应返回零向量。"""
        mock_post.side_effect = Exception("连接失败")
        svc = EmbeddingService(base_url="http://localhost:11434", model="bge-m3")
        vec = svc.encode("测试")
        assert vec.shape == (1024,)
        assert np.allclose(vec, 0)

    @patch("requests.post")
    def test_encode_wrong_dim(self, mock_post):
        """返回维度不匹配时应自动填充/截断。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": [0.5] * 512}  # 维度不对
        mock_post.return_value = mock_resp

        svc = EmbeddingService(base_url="http://localhost:11434", model="bge-m3")
        vec = svc.encode("测试")
        assert vec.shape == (1024,)
        # 前 512 维应为 0.5，其余为 0
        assert np.isclose(vec[0], 0.5)
        assert np.isclose(vec[511], 0.5)
        assert np.isclose(vec[512], 0.0)

    @patch("requests.post")
    def test_encode_batch(self, mock_post):
        """批量编码应返回 (N, dim) 矩阵。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"embedding": [0.1] * 1024}
        mock_post.return_value = mock_resp

        svc = EmbeddingService(base_url="http://localhost:11434", model="bge-m3")
        vecs = svc.encode_batch(["文本1", "文本2", "文本3"])
        assert vecs.shape == (3, 1024)


# ============================================================
# 模型层 embedding 测试
# ============================================================


class TestModelEmbedding:
    """测试模型的 embedding_str 字段。"""

    def test_mining_run_embedding_in_db_row(self):
        """MiningRun.to_db_row 有 embedding_str 时应包含 embedding 字段。"""
        run = MiningRun(id="FM_test", embedding_str="[0.1,0.2,0.3]")
        row = run.to_db_row()
        assert "embedding" in row
        assert row["embedding"] == "[0.1,0.2,0.3]"

    def test_mining_run_no_embedding_in_db_row(self):
        """MiningRun.to_db_row 无 embedding_str 时不应包含 embedding 字段。"""
        run = MiningRun(id="FM_test")
        row = run.to_db_row()
        assert "embedding" not in row

    def test_experience_embedding_in_db_row(self):
        """Experience.to_db_row 有 embedding_str 时应包含 embedding 字段。"""
        exp = Experience(id="EXP_test", embedding_str="[0.1,0.2,0.3]")
        row = exp.to_db_row()
        assert "embedding" in row
        assert row["embedding"] == "[0.1,0.2,0.3]"

    def test_experience_no_embedding_in_db_row(self):
        """Experience.to_db_row 无 embedding_str 时不应包含 embedding 字段。"""
        exp = Experience(id="EXP_test")
        row = exp.to_db_row()
        assert "embedding" not in row


# ============================================================
# 集成测试（需要 PostgreSQL + Ollama）
# ============================================================


@pytest.fixture(scope="module")
def db():
    """创建数据库连接。"""
    from QSExt.LLMFactor.mining_log.db import MiningLogDB

    dsn = os.getenv("POSTGRESQL_KDB_DSN_DEV")
    if not dsn:
        pytest.skip("未配置 POSTGRESQL_KDB_DSN_DEV，跳过集成测试")

    db = MiningLogDB(dsn=dsn)
    db.init_tables()
    yield db


@pytest.fixture(scope="module")
def embedding_service():
    """创建 EmbeddingService 实例（需要 Ollama 运行）。"""
    from QSExt.LLMFactor.mining_log.embedding import EmbeddingService

    svc = EmbeddingService()
    # 测试 Ollama 是否可用
    vec = svc.encode("连接测试")
    if np.allclose(vec, 0):
        pytest.skip("Ollama 服务不可用，跳过 embedding 集成测试")
    return svc


@pytest.fixture(scope="module")
def repo(db, embedding_service):
    """创建带 EmbeddingService 的 Repository。"""
    from QSExt.LLMFactor.mining_log.repository import MiningLogRepository

    return MiningLogRepository(db, embedding_service=embedding_service)


@pytest.fixture(scope="module")
def retriever(repo, embedding_service):
    """创建 Retriever 实例。"""
    from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever

    return MiningLogRetriever(repo, embedding_service=embedding_service)


@pytest.mark.integration
class TestInsertWithEmbedding:
    """入库自动写入 embedding 测试。"""

    RUN_ID = "FM_EMB_TEST_001"
    EXP_ID = "EXP_EMB_TEST_001"

    def test_insert_run_auto_embedding(self, repo):
        """insert_run 应自动为 content 生成 embedding。"""
        run = MiningRun(
            id=self.RUN_ID,
            content="日内动量因子：基于开盘价和收盘价的日内收益分解",
            tags=["测试", "动量", "embedding"],
            metadata={
                "factor_name": "test_emb_momentum",
                "direction_tag": "动量/日内方向预测",
                "status": "completed",
                "decision": "accepted",
                "rankic_mean": 0.045,
            },
        )
        result_id = repo.insert_run(run)
        assert result_id == self.RUN_ID

        # 验证 embedding 已写入
        with repo.conn.cursor() as cur:
            cur.execute(
                "SELECT embedding FROM mining_log WHERE id = %s",
                (self.RUN_ID,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] is not None  # embedding 不为空

    def test_insert_experience_auto_embedding(self, repo):
        """insert_experience 应自动为 content 生成 embedding。"""
        exp = Experience(
            id=self.EXP_ID,
            content="隔夜日内收益分解：将日收益率拆分为隔夜跳空和日内趋势两个独立信号",
            tags=["测试", "逻辑组件"],
            metadata={
                "track": ExperienceTrack.SUCCESS.value,
                "type": ExperienceType.LOGIC_COMPONENT.value,
                "name": "隔夜日内分解",
                "quality_score": 0.85,
                "direction_tag": "动量/日内方向预测",
            },
        )
        result_id = repo.insert_experience(exp)
        assert result_id == self.EXP_ID

        # 验证 embedding 已写入
        with repo.conn.cursor() as cur:
            cur.execute(
                "SELECT embedding FROM mining_experience WHERE id = %s",
                (self.EXP_ID,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] is not None


@pytest.mark.integration
class TestVectorSearch:
    """向量语义检索测试。"""

    def test_search_mining_log_by_embedding(self, repo, embedding_service):
        """在 mining_log 中按向量检索。"""
        vec = embedding_service.encode("动量因子 日内收益")
        vec_str = embedding_service.to_db_format(vec)
        results = repo.search_mining_log_by_embedding(vec_str, top_k=5, score_threshold=0.0)
        assert isinstance(results, list)
        for run, score in results:
            assert isinstance(run, MiningRun)
            assert 0.0 <= score <= 1.0

    def test_search_experience_by_embedding(self, repo, embedding_service):
        """在 mining_experience 中按向量检索。"""
        vec = embedding_service.encode("收益分解 隔夜")
        vec_str = embedding_service.to_db_format(vec)
        results = repo.search_experience_by_embedding(vec_str, top_k=5, score_threshold=0.0)
        assert isinstance(results, list)
        for exp, score in results:
            assert isinstance(exp, Experience)
            assert 0.0 <= score <= 1.0

    def test_search_experience_by_embedding_with_track(self, repo, embedding_service):
        """按 track 过滤语义检索。"""
        vec = embedding_service.encode("失败经验")
        vec_str = embedding_service.to_db_format(vec)
        results = repo.search_experience_by_embedding(
            vec_str, top_k=5, score_threshold=0.0, track="success",
        )
        for exp, score in results:
            assert exp.metadata.get("track") == "success"

    def test_search_by_embedding_threshold(self, repo, embedding_service):
        """高阈值应过滤掉低相似度结果。"""
        vec = embedding_service.encode("完全无关的查询 xyzabc")
        vec_str = embedding_service.to_db_format(vec)
        # 阈值 0.99 应几乎无结果
        results = repo.search_mining_log_by_embedding(
            vec_str, top_k=10, score_threshold=0.99,
        )
        # 结果应该很少或为空
        assert len(results) <= 1


@pytest.mark.integration
class TestRetrieverEmbedding:
    """Retriever 语义检索接口测试。"""

    def test_search_by_embedding_log(self, retriever):
        """search_by_embedding 搜索 mining_log 表。"""
        results = retriever.search_by_embedding(
            "日内动量 方向预测", table="mining_log", top_k=5, score_threshold=0.0,
        )
        assert isinstance(results, list)
        if results:
            from QSExt.LLMFactor.mining_log.retriever import RunSummary

            result, score = results[0]
            assert isinstance(result, RunSummary)
            assert 0.0 <= score <= 1.0

    def test_search_by_embedding_experience(self, retriever):
        """search_by_embedding 搜索 mining_experience 表。"""
        results = retriever.search_by_embedding(
            "收益分解", table="mining_experience", top_k=5, score_threshold=0.0,
        )
        assert isinstance(results, list)
        if results:
            from QSExt.LLMFactor.mining_log.retriever import ExperienceComponent

            result, score = results[0]
            assert isinstance(result, ExperienceComponent)

    def test_search_similar_accepted(self, retriever):
        """search_similar_accepted 应仅返回 accepted 记录。"""
        results = retriever.search_similar_accepted(
            "动量因子", top_k=3, score_threshold=0.0,
        )
        assert isinstance(results, list)
        for result, score in results:
            assert result.decision == Decision.ACCEPTED.value

    def test_get_similar_failures(self, retriever):
        """get_similar_failures 应返回失败经验。"""
        results = retriever.get_similar_failures(
            "IC 很低的因子", top_k=3, score_threshold=0.0,
        )
        assert isinstance(results, list)

    def test_search_by_embedding_no_service(self, db):
        """无 EmbeddingService 时应返回空列表。"""
        from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
        from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever

        repo = MiningLogRepository(db)  # 无 embedding_service
        retriever = MiningLogRetriever(repo)
        results = retriever.search_by_embedding("测试查询")
        assert results == []


@pytest.mark.integration
class TestBackfillEmbedding:
    """backfill_embeddings 补写测试。"""

    def test_backfill_mining_log(self, repo):
        """为缺少 embedding 的 mining_log 记录补写。"""
        count = repo.backfill_embeddings(table="mining_log", batch_size=10)
        assert count >= 0

    def test_backfill_mining_experience(self, repo):
        """为缺少 embedding 的 mining_experience 记录补写。"""
        count = repo.backfill_embeddings(table="mining_experience", batch_size=10)
        assert count >= 0

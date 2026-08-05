# -*- coding: utf-8 -*-
"""挖掘日志库测试。

测试覆盖：
  - 模型层：MiningRun / Experience 的创建、序列化、反序列化
  - 数据库层：连接管理、表初始化（需要真实 PostgreSQL 连接）
  - Repository 层：CRUD 操作
  - Retriever 层：检索接口

运行方式：
    # 仅运行模型测试（不需要数据库）
    pytest tests/test_mining_log.py -v -k "not integration"

    # 运行全部测试（需要 PostgreSQL 连接）
    pytest tests/test_mining_log.py -v

环境要求：
    - QSExt/config/.env 中配置 POSTGRESQL_KDB_DSN_DEV
    - Ollama 服务运行中（embedding 测试需要）
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from dotenv import load_dotenv

from QSExt import __QS_MainPath__

load_dotenv(__QS_MainPath__ + "/config/.env")

from QSExt.LLMFactor.mining_log.models import (
    MiningRun,
    Experience,
    RunStatus,
    Decision,
    ExperienceTrack,
    ExperienceType,
    FailureType,
    VerificationStatus,
)


# ============================================================
# 模型层测试（不需要数据库）
# ============================================================


class TestMiningRunModel:
    """MiningRun 数据模型测试。"""

    def test_create_default(self):
        """默认创建 MiningRun，字段应有合理默认值。"""
        run = MiningRun()
        assert run.id == ""
        assert run.source == "factor_mining_system"
        assert run.doc_type == "mining_log"
        assert run.content == ""
        assert run.tags == []
        assert run.metadata == {}
        assert run.created_at is None

    def test_create_with_fields(self):
        """指定字段创建 MiningRun。"""
        run = MiningRun(
            id="FM_20260706_001",
            content="测试因子",
            tags=["动量", "日内"],
            metadata={"factor_name": "test_factor", "rankic_mean": 0.05},
        )
        assert run.id == "FM_20260706_001"
        assert run.content == "测试因子"
        assert "动量" in run.tags
        assert run.metadata["factor_name"] == "test_factor"
        assert run.metadata["rankic_mean"] == 0.05

    def test_meta_property(self):
        """meta 属性应返回 metadata 的引用。"""
        run = MiningRun()
        run.metadata["key"] = "value"
        assert run.meta["key"] == "value"
        assert run.meta is run.metadata

    def test_to_db_row(self):
        """to_db_row 应正确序列化为数据库行格式。"""
        now = datetime(2026, 7, 6, 10, 0, 0)
        run = MiningRun(
            id="FM_20260706_001",
            content="测试内容",
            tags=["tag1"],
            metadata={"status": "completed"},
            created_at=now,
        )
        row = run.to_db_row()

        assert row["id"] == "FM_20260706_001"
        assert row["source"] == "factor_mining_system"
        assert row["doc_type"] == "mining_log"
        assert row["content"] == "测试内容"
        assert row["tags"] == ["tag1"]
        assert row["created_at"] == now

        # metadata 应被序列化为 JSON 字符串
        assert isinstance(row["metadata"], str)
        parsed = json.loads(row["metadata"])
        assert parsed["status"] == "completed"

    def test_to_db_row_with_embedding(self):
        """有 embedding_str 时，to_db_row 应包含 embedding 字段。"""
        run = MiningRun(id="FM_test", embedding_str="[0.1, 0.2, 0.3]")
        row = run.to_db_row()
        assert "embedding" in row
        assert row["embedding"] == "[0.1, 0.2, 0.3]"

    def test_to_db_row_without_embedding(self):
        """无 embedding_str 时，to_db_row 不应包含 embedding 字段。"""
        run = MiningRun(id="FM_test")
        row = run.to_db_row()
        assert "embedding" not in row

    def test_from_db_row_with_dict_metadata(self):
        """从 metadata 为 dict 的数据库行构造 MiningRun。"""
        row = {
            "id": "FM_20260706_002",
            "source": "factor_mining_system",
            "source_path": "",
            "doc_type": "mining_log",
            "content": "测试",
            "tags": ["a"],
            "metadata": {"factor_name": "pe_ttm"},
            "created_at": datetime(2026, 7, 6),
        }
        run = MiningRun.from_db_row(row)
        assert run.id == "FM_20260706_002"
        assert run.metadata["factor_name"] == "pe_ttm"

    def test_from_db_row_with_json_metadata(self):
        """从 metadata 为 JSON 字符串的数据库行构造 MiningRun。"""
        row = {
            "id": "FM_20260706_003",
            "metadata": '{"factor_name": "momentum"}',
            "tags": [],
        }
        run = MiningRun.from_db_row(row)
        assert run.metadata["factor_name"] == "momentum"

    def test_from_db_row_empty(self):
        """从空行构造 MiningRun 应使用默认值。"""
        run = MiningRun.from_db_row({})
        assert run.id == ""
        assert run.source == "factor_mining_system"
        assert run.metadata == {}

    def test_roundtrip(self):
        """to_db_row → from_db_row 往返应保持数据一致。"""
        original = MiningRun(
            id="FM_roundtrip",
            content="往返测试",
            tags=["t1", "t2"],
            metadata={"rankic_mean": 0.045, "status": "completed"},
        )
        row = original.to_db_row()
        restored = MiningRun.from_db_row(row)

        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.tags == original.tags
        assert restored.metadata["rankic_mean"] == original.metadata["rankic_mean"]
        assert restored.metadata["status"] == original.metadata["status"]


class TestExperienceModel:
    """Experience 数据模型测试。"""

    def test_create_default(self):
        """默认创建 Experience。"""
        exp = Experience()
        assert exp.id == ""
        assert exp.doc_type == "mining_experience"
        assert exp.metadata == {}

    def test_create_with_fields(self):
        """指定字段创建 Experience。"""
        exp = Experience(
            id="EXP_20260706_001",
            content="成功经验：隔夜日内分解",
            tags=["动量", "逻辑组件"],
            metadata={
                "track": "success",
                "type": "logic_component",
                "name": "隔夜日内分解",
                "quality_score": 0.85,
            },
        )
        assert exp.id == "EXP_20260706_001"
        assert exp.metadata["track"] == "success"
        assert exp.metadata["quality_score"] == 0.85

    def test_to_db_row(self):
        """to_db_row 应正确序列化。"""
        exp = Experience(
            id="EXP_test",
            content="经验内容",
            metadata={"track": "failure"},
        )
        row = exp.to_db_row()
        assert row["doc_type"] == "mining_experience"
        assert isinstance(row["metadata"], str)
        assert json.loads(row["metadata"])["track"] == "failure"

    def test_from_db_row(self):
        """from_db_row 应正确反序列化。"""
        row = {
            "id": "EXP_001",
            "metadata": '{"track": "success", "quality_score": 0.9}',
            "tags": [],
        }
        exp = Experience.from_db_row(row)
        assert exp.metadata["track"] == "success"
        assert exp.metadata["quality_score"] == 0.9


class TestEnums:
    """枚举类型测试。"""

    def test_run_status_values(self):
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.IN_DEVELOPMENT.value == "in_development"
        assert RunStatus.EVALUATING.value == "evaluating"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"

    def test_decision_values(self):
        assert Decision.ACCEPTED.value == "accepted"
        assert Decision.REFINING.value == "refining"
        assert Decision.REJECTED.value == "rejected"

    def test_experience_track_values(self):
        assert ExperienceTrack.SUCCESS.value == "success"
        assert ExperienceTrack.FAILURE.value == "failure"

    def test_failure_type_values(self):
        assert FailureType.LOW_IC.value == "low_ic"
        assert FailureType.DATA_LEAKAGE.value == "data_leakage"

    def test_verification_status_values(self):
        assert VerificationStatus.PENDING.value == "pending"
        assert VerificationStatus.VERIFIED.value == "verified"
        assert VerificationStatus.DEPRECATED.value == "deprecated"

    def test_enum_str_compat(self):
        """枚举值应兼容 str 比较。"""
        assert RunStatus.COMPLETED == "completed"
        assert Decision.ACCEPTED == "accepted"


# ============================================================
# 集成测试（需要数据库连接）
# ============================================================


@pytest.fixture(scope="module")
def db():
    """创建数据库连接，模块级别共享。"""
    from QSExt.LLMFactor.mining_log.db import MiningLogDB

    dsn = os.getenv("POSTGRESQL_KDB_DSN_DEV")
    if not dsn:
        pytest.skip("未配置 POSTGRESQL_KDB_DSN_DEV，跳过集成测试")

    db = MiningLogDB(dsn=dsn)
    db.init_tables()
    yield db


@pytest.fixture(scope="module")
def repo(db):
    """创建 Repository 实例。"""
    from QSExt.LLMFactor.mining_log.repository import MiningLogRepository

    return MiningLogRepository(db)


@pytest.fixture(scope="module")
def retriever(repo):
    """创建 Retriever 实例。"""
    from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever

    return MiningLogRetriever(repo)


@pytest.mark.integration
class TestDatabaseInit:
    """数据库初始化测试。"""

    def test_connect(self, db):
        """应能成功连接数据库。"""
        conn = db.connect()
        assert conn is not None
        assert not conn.closed

    def test_init_tables_idempotent(self, db):
        """重复调用 init_tables 不应报错。"""
        db.init_tables()  # 已在 fixture 中调用，再次调用应幂等


@pytest.mark.integration
class TestRepositoryRun:
    """Repository MiningRun CRUD 测试。"""

    RUN_ID = "FM_TEST_20260706_001"

    def test_insert_run(self, repo):
        """插入一条运行记录。"""
        run = MiningRun(
            id=self.RUN_ID,
            content="测试因子：日内动量",
            tags=["测试", "动量"],
            metadata={
                "factor_name": "test_intraday_momentum",
                "category": "动量",
                "direction_tag": "动量/日内方向预测",
                "status": RunStatus.COMPLETED.value,
                "rankic_mean": 0.042,
                "composite_score": 0.65,
                "decision": Decision.ACCEPTED.value,
            },
        )
        result_id = repo.insert_run(run)
        assert result_id == self.RUN_ID

    def test_get_run(self, repo):
        """按 ID 查询运行记录。"""
        run = repo.get_run(self.RUN_ID)
        assert run is not None
        assert run.id == self.RUN_ID
        assert run.metadata["factor_name"] == "test_intraday_momentum"
        assert run.metadata["rankic_mean"] == 0.042

    def test_get_run_not_found(self, repo):
        """查询不存在的记录应返回 None。"""
        run = repo.get_run("FM_NONEXISTENT")
        assert run is None

    def test_update_status(self, repo):
        """更新运行状态。"""
        repo.update_status(self.RUN_ID, RunStatus.EVALUATING)
        run = repo.get_run(self.RUN_ID)
        assert run.metadata["status"] == RunStatus.EVALUATING.value

    def test_update_eval_results(self, repo):
        """批量更新评测字段。"""
        repo.update_eval_results(
            self.RUN_ID,
            rankic_mean=0.048,
            rankicir=0.75,
            incremental_ic_t=2.5,
        )
        run = repo.get_run(self.RUN_ID)
        assert run.metadata["rankic_mean"] == 0.048
        assert run.metadata["rankicir"] == 0.75
        assert run.metadata["incremental_ic_t"] == 2.5

    def test_set_decision(self, repo):
        """设置入库决策。"""
        repo.set_decision(self.RUN_ID, Decision.ACCEPTED, "增量 IC 显著")
        run = repo.get_run(self.RUN_ID)
        assert run.metadata["decision"] == Decision.ACCEPTED.value
        assert run.metadata["decision_reason"] == "增量 IC 显著"

    def test_list_runs_by_status(self, repo):
        """按状态过滤运行记录。"""
        runs = repo.list_runs(status=RunStatus.EVALUATING, limit=10)
        assert any(r.id == self.RUN_ID for r in runs)

    def test_list_runs_by_decision(self, repo):
        """按决策过滤运行记录。"""
        runs = repo.list_runs(decision=Decision.ACCEPTED, limit=10)
        assert any(r.id == self.RUN_ID for r in runs)

    def test_list_runs_by_category(self, repo):
        """按类别过滤运行记录。"""
        runs = repo.list_runs(category="动量", limit=10)
        assert any(r.id == self.RUN_ID for r in runs)

    def test_search_by_tags(self, repo):
        """按标签搜索运行记录。"""
        runs = repo.search_by_tags(["测试", "动量"])
        assert any(r.id == self.RUN_ID for r in runs)

    def test_get_runs_by_direction(self, repo):
        """按方向标签查询运行记录。"""
        runs = repo.get_runs_by_direction("动量/日内方向预测")
        assert any(r.id == self.RUN_ID for r in runs)

    def test_upsert(self, repo):
        """重复插入应更新而非报错（ON CONFLICT upsert）。"""
        run = MiningRun(
            id=self.RUN_ID,
            content="更新后的内容",
            tags=["测试", "动量", "更新"],
            metadata={"factor_name": "test_intraday_momentum_v2"},
        )
        repo.insert_run(run)
        updated = repo.get_run(self.RUN_ID)
        assert updated.content == "更新后的内容"
        assert "更新" in updated.tags


@pytest.mark.integration
class TestRepositoryExperience:
    """Repository Experience CRUD 测试。"""

    EXP_ID = "EXP_TEST_20260706_001"

    def test_insert_success_experience(self, repo):
        """插入一条成功经验。"""
        exp = Experience(
            id=self.EXP_ID,
            content="隔夜日内分解逻辑组件",
            tags=["动量", "逻辑组件"],
            metadata={
                "track": ExperienceTrack.SUCCESS.value,
                "type": ExperienceType.LOGIC_COMPONENT.value,
                "name": "隔夜日内分解",
                "description": "将日内动量分解为隔夜和日内两部分",
                "quality_score": 0.85,
                "verification_status": VerificationStatus.VERIFIED.value,
                "code_snippet": "# 隔夜收益\novernight = open / close.shift(1) - 1",
                "direction_tag": "动量/日内方向预测",
            },
        )
        result_id = repo.insert_experience(exp)
        assert result_id == self.EXP_ID

    def test_get_experience(self, repo):
        """按 ID 查询经验记录。"""
        exp = repo.get_experience(self.EXP_ID)
        assert exp is not None
        assert exp.metadata["track"] == ExperienceTrack.SUCCESS.value
        assert exp.metadata["quality_score"] == 0.85

    def test_get_success_experiences(self, repo):
        """获取成功经验列表。"""
        exps = repo.get_success_experiences(min_quality=0.8)
        assert any(e.id == self.EXP_ID for e in exps)

    def test_increment_usage(self, repo):
        """增加经验使用次数。"""
        repo.increment_usage(self.EXP_ID)
        exp = repo.get_experience(self.EXP_ID)
        assert exp.metadata.get("usage_count", 0) >= 1

    def test_deprecate_experience(self, repo):
        """标记经验为废弃。"""
        # 先创建一个用于废弃的经验
        dep_id = "EXP_TEST_DEPRECATED"
        exp = Experience(
            id=dep_id,
            content="将被废弃的经验",
            metadata={
                "track": ExperienceTrack.SUCCESS.value,
                "verification_status": VerificationStatus.PENDING.value,
            },
        )
        repo.insert_experience(exp)

        repo.deprecate_experience(dep_id, "EXP_NEW_VERSION")
        updated = repo.get_experience(dep_id)
        assert updated.metadata["verification_status"] == VerificationStatus.DEPRECATED.value
        assert updated.metadata["deprecated_by"] == "EXP_NEW_VERSION"


@pytest.mark.integration
class TestRepositoryEvolution:
    """演化链测试。"""

    def test_parent_child_relationship(self, repo):
        """测试 parent_run_id 关联的父子关系。"""
        parent_id = "FM_EVOLUTION_PARENT"
        child_id = "FM_EVOLUTION_CHILD"

        # 插入父记录
        parent = MiningRun(
            id=parent_id,
            content="原始假设",
            metadata={"factor_name": "evolution_test", "status": "completed"},
        )
        repo.insert_run(parent)

        # 插入子记录
        child = MiningRun(
            id=child_id,
            content="精炼版本",
            metadata={
                "factor_name": "evolution_test",
                "parent_run_id": parent_id,
                "status": "completed",
            },
        )
        repo.insert_run(child)

        # 查询子记录
        children = repo.get_children(parent_id)
        assert len(children) >= 1
        assert any(c.id == child_id for c in children)


@pytest.mark.integration
class TestRetriever:
    """Retriever 检索接口测试。"""

    def test_search_by_direction(self, retriever):
        """按方向搜索历史记录。"""
        results = retriever.search_by_direction("动量", top_k=5)
        assert isinstance(results, list)
        # 结果应为 RunSummary 类型
        if results:
            from QSExt.LLMFactor.mining_log.retriever import RunSummary

            assert isinstance(results[0], RunSummary)

    def test_get_direction_coverage(self, retriever):
        """获取方向覆盖率统计。"""
        coverage = retriever.get_direction_coverage()
        assert isinstance(coverage, dict)
        # 如果有数据，值应为 DirectionStats
        if coverage:
            from QSExt.LLMFactor.mining_log.retriever import DirectionStats

            stats = next(iter(coverage.values()))
            assert isinstance(stats, DirectionStats)
            assert stats.attempts >= 0
            assert stats.successes >= 0

    def test_get_successful_patterns(self, retriever):
        """获取成功经验组件。"""
        patterns = retriever.get_successful_patterns(min_quality=0.5)
        assert isinstance(patterns, list)
        if patterns:
            from QSExt.LLMFactor.mining_log.retriever import ExperienceComponent

            assert isinstance(patterns[0], ExperienceComponent)

    def test_get_top_factors(self, retriever):
        """获取排行前列的入库因子。"""
        top = retriever.get_top_factors(metric="rankic_mean", limit=5)
        assert isinstance(top, list)
        # 结果应按 rankic_mean 降序
        if len(top) >= 2:
            scores = [r.rankic_mean for r in top if r.rankic_mean is not None]
            assert scores == sorted(scores, reverse=True)

    def test_get_evolution_tree(self, retriever):
        """获取演化树。"""
        tree = retriever.get_evolution_tree("FM_NONEXISTENT")
        assert tree == {}  # 不存在的记录应返回空字典


@pytest.mark.integration
class TestExperienceRefiner:
    """ExperienceRefiner 经验提炼测试。"""

    def test_refine_accepted_run(self, repo):
        """对 accepted 运行记录进行经验提炼。"""
        from QSExt.LLMFactor.mining_log.experience_refiner import (
            ExperienceRefiner,
        )

        refiner = ExperienceRefiner(repo)

        run = MiningRun(
            id="FM_REFINE_TEST",
            content="提炼测试",
            metadata={
                "status": RunStatus.COMPLETED.value,
                "decision": Decision.ACCEPTED.value,
                "factor_name": "refine_test_factor",
                "direction_tag": "测试/提炼",
                "rankic_mean": 0.05,
            },
        )
        # 使用 NoOpReviewer，不依赖 LLM
        experiences = refiner.refine(run)
        assert isinstance(experiences, list)

    def test_refine_rejected_run(self, repo):
        """对 rejected 运行记录进行失败经验提炼。"""
        from QSExt.LLMFactor.mining_log.experience_refiner import (
            ExperienceRefiner,
        )

        refiner = ExperienceRefiner(repo)

        run = MiningRun(
            id="FM_REFINE_REJECTED",
            content="失败提炼测试",
            metadata={
                "status": RunStatus.COMPLETED.value,
                "decision": Decision.REJECTED.value,
                "factor_name": "refine_rejected_factor",
                "direction_tag": "测试/失败提炼",
                "rankic_mean": 0.005,
            },
        )
        experiences = refiner.refine(run)
        assert isinstance(experiences, list)


# ============================================================
# 辅助函数测试
# ============================================================


class TestExtractCodeComponents:
    """extract_code_components 代码拆分测试。"""

    def test_split_by_comment_delimiters(self):
        """按注释分隔符拆分代码块。"""
        from QSExt.LLMFactor.mining_log.experience_refiner import (
            extract_code_components,
        )

        code = """# ---- 隔夜收益计算 ----
overnight = open / close.shift(1) - 1

# ---- 日内收益计算 ----
intraday = close / open - 1

# ---- 合成 ----
factor = overnight + intraday
"""
        components = extract_code_components(code)
        assert len(components) >= 2
        # 每个组件应有名称和代码
        for comp in components:
            assert "name" in comp
            assert "code" in comp

    def test_empty_code(self):
        """空代码应返回空列表。"""
        from QSExt.LLMFactor.mining_log.experience_refiner import (
            extract_code_components,
        )

        components = extract_code_components("")
        assert components == []

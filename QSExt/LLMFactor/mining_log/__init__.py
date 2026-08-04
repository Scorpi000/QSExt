# -*- coding: utf-8 -*-
"""挖掘日志库 (Mining Log) — 因子挖掘系统的长期记忆模块。

提供：
  - models:    数据模型定义 (MiningRun, Experience)
  - db:        数据库连接管理 + DDL
  - repository: CRUD 操作
  - writer:    挖掘日志写入器 (MiningLogWriter)
  - validator: 日志完整性校验
  - retriever:  假设生成阶段检索接口 (MiningLogRetriever)
  - experience_refiner: 经验提炼 (三层过滤)

用法示例:
    from QSExt.LLMFactor.mining_log.db import MiningLogDB
    from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
    from QSExt.LLMFactor.mining_log.writer import MiningLogWriter
    from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever

    db = MiningLogDB()
    db.init_tables()  # 首次使用：创建表和索引（幂等）

    repo = MiningLogRepository(db)
    writer = MiningLogWriter(repo)
    retriever = MiningLogRetriever(repo)

    # 查询某个方向的历史
    results = retriever.search_by_direction("动量因子", top_k=10)
"""
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
from QSExt.LLMFactor.mining_log.db import MiningLogDB
from QSExt.LLMFactor.mining_log.repository import MiningLogRepository
from QSExt.LLMFactor.mining_log.writer import MiningLogWriter
from QSExt.LLMFactor.mining_log.retriever import MiningLogRetriever
from QSExt.LLMFactor.mining_log.experience_refiner import (
    ExperienceRefiner,
    extract_code_components,
)
from QSExt.LLMFactor.mining_log.embedding import EmbeddingService
from QSExt.LLMFactor.mining_log.llm_reviewer import LLMReviewer
from QSExt.LLMFactor.mining_log.llm_client import create_llm

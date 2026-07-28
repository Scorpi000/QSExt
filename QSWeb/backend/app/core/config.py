"""
应用配置

从环境变量或 .env 文件加载配置
"""

import os
from typing import List


class Settings:
    """应用配置"""

    # 应用配置
    APP_NAME: str = "QSWeb"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # CORS 配置
    CORS_ORIGINS: List[str] = [
        "http://localhost:23000",
        "http://127.0.0.1:23000",
    ]

    # PostgreSQL 配置（可选）
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/qsweb"

    # QuantStudio 配置
    QS_CONFIG_PATH: str = os.path.expanduser("~/QuantStudioConfig")


settings = Settings()

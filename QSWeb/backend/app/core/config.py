"""
应用配置

从环境变量或 .env 文件加载配置
"""

import json
import os
from typing import List, Optional


# QSWeb 所在目录（即仓库根目录，比 backend/app/core 高 5 级）
_qsweb_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    ))))
)


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

    @property
    def factor_def(self) -> dict:
        """从 QSWebConfig.json 加载 factor_def 配置段"""
        config_path = os.path.join(self.QS_CONFIG_PATH, "QSWebConfig.json")
        if not os.path.exists(config_path):
            return self._default_factor_def()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            fd = config.get("factor_def", {})
            defaults = self._default_factor_def()
            return {**defaults, **fd}
        except Exception:
            return self._default_factor_def()

    @staticmethod
    def _default_factor_def() -> dict:
        return {
            "scripts_dir": os.path.expanduser("~/FactorDef/Scripts"),
            "settings_path": None,
            "skill_dir": None,
            "claude": {
                "repo_root": _qsweb_root,
                "mode": "cli",
                "session_persist_wait_sec": 10,
                "skills": ["develop-factor"],
                "permission_mode": "acceptEdits",
                "max_budget_usd": 1.0,
                "allowed_tools": [
                    "mcp__jy_base_doc__*", "mcp__qs-registry__*",
                    "Read", "Write", "Bash",
                ],
                "env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"},
                "mcp_servers": {},
                "system_prompt": (
                    "使用 develop-factor 技能，根据以下需求创建因子定义脚本：\n\n"
                    "{user_prompt}\n\n"
                    "请遵循 develop-factor 技能的所有步骤：\n"
                    "1. 理解需求并澄清不明确的部分\n"
                    "2. 通过 jy_base_doc 工具验证数据表和字段\n"
                    "3. 生成符合 FactorDef 框架规范的因子定义脚本\n"
                    "4. 将脚本保存到 {scripts_dir} 目录下\n\n"
                    "脚本必须包含 __FACTOR_META__ 和 defFactor(fdi) -> List[Factor]。\n"
                    "如果用户需求不明确，先使用 AskUserQuestion 工具询问缺失的关键信息。"
                ),
            },
        }


settings = Settings()

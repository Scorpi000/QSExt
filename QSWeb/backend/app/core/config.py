"""
应用配置

从 QSWebConfig.yaml 加载 Web 级配置，并结合统一 RuntimeSettings。
"""

import os
from functools import lru_cache
from typing import List, Optional

import yaml


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
	QS_CONFIG_PATH: str = os.path.join(
		os.path.expanduser("~/QuantStudioConfig"), "QSWebConfig.yaml"
	)

	# 统一运行时配置路径
	RUNTIME_SETTINGS_PATH: str = os.path.join(
		os.path.expanduser("~/QuantStudioConfig"), "settings.py"
	)

	# ============================================================
	# 统一运行时配置 (从 settings.py 加载)
	# ============================================================

	@property
	@lru_cache(maxsize=1)
	def runtime_settings(self):
		"""加载统一运行时配置 (RuntimeSettings 实例)。

		优先从 QSWebConfig.yaml 中 runtime_settings 字段读取路径，
		否则使用默认的 ~/QuantStudioConfig/settings.py。
		"""
		config_path = None
		if os.path.exists(self.QS_CONFIG_PATH):
			try:
				with open(self.QS_CONFIG_PATH, "r", encoding="utf-8") as f:
					yaml_config = yaml.safe_load(f)
				config_path = yaml_config.get("runtime_settings")
			except Exception:
				pass

		if not config_path:
			config_path = self.RUNTIME_SETTINGS_PATH

		from QSExt.RuntimeConfig.config import RuntimeSettings

		path = os.path.expanduser(config_path)
		if os.path.isfile(path):
			return RuntimeSettings.from_module(path)
		return RuntimeSettings()

	@property
	def factor_def(self) -> dict:
		"""FactorDef 配置：合并 RuntimeSettings + ai_workbench contexts.factor。

		返回 QSWeb 所需的值：scripts_dir, skill_dir, claude 配置。
		"""
		aw = self.ai_workbench
		factor_ctx = aw.get("contexts", {}).get("factor", {})
		general_ctx = aw.get("contexts", {}).get("general", {})
		merged = {**general_ctx, **factor_ctx}
		return {
			"scripts_dir": (
				factor_ctx.get("scripts_dir")
				or os.path.expanduser("~/FactorDef/Scripts")
			),
			"skill_dir": factor_ctx.get("skill_dir"),
			"claude": {
				"repo_root": merged.get("repo_root", _qsweb_root),
				"mode": aw.get("mode", "cli"),
				"session_persist_wait_sec": 10,
				"skills": merged.get("skills", []),
				"permission_mode": merged.get("permission_mode", "acceptEdits"),
				"max_budget_usd": merged.get("max_budget_usd", 1.0),
				"allowed_tools": merged.get("tools", []),
				"env": merged.get("env", {}),
				"mcp_servers": merged.get("mcp_servers", {}),
				"system_prompt": merged.get("system_prompt", ""),
			},
		}

	@property
	def strategy_def(self) -> dict:
		"""StrategyDef 配置：合并 RuntimeSettings + QSWebConfig.yaml。

		scripts_dir 从 YAML strategy_def 读取或使用默认值。
		"""
		sd_config = {}
		if os.path.exists(self.QS_CONFIG_PATH):
			try:
				with open(self.QS_CONFIG_PATH, "r", encoding="utf-8") as f:
					sd_config = yaml.safe_load(f).get("strategy_def", {})
			except Exception:
				pass

		return {
			"scripts_dir": (
				sd_config.get("scripts_dir")
				or os.path.expanduser("~/StrategyDef/Scripts")
			),
			"default_id_type": sd_config.get("default_id_type", "A股"),
		}

	# ============================================================
	# 全局配置（已从 QSWebConfig.yaml global 节迁入 RuntimeSettings）
	# ============================================================

	@property
	def global_config(self) -> dict:
		"""从统一 RuntimeSettings 读取全局配置。"""
		rs = self.runtime_settings
		return {
			"cache_dir": rs.cache_dir or os.path.expanduser("~/QSCache"),
			"use_temp_cache": rs.use_temp_cache,
			"engine": rs.engine,
		}

	# ============================================================
	# AI Workbench
	# ============================================================

	@property
	def ai_workbench(self) -> dict:
		"""从 QSWebConfig.yaml 加载 ai_workbench 配置段"""
		if not os.path.exists(self.QS_CONFIG_PATH):
			return self._default_ai_workbench()
		try:
			with open(self.QS_CONFIG_PATH, "r", encoding="utf-8") as f:
				config = yaml.safe_load(f)
			aw = config.get("ai_workbench", {})
			defaults = self._default_ai_workbench()

			# 合并 contexts：用户配置覆盖默认
			default_contexts = defaults.get("contexts", {})
			user_contexts = aw.get("contexts", {})
			merged_contexts = {}
			for key in set(list(default_contexts.keys()) + list(user_contexts.keys())):
				base = default_contexts.get(key, {})
				overlay = user_contexts.get(key, {})
				merged_contexts[key] = {**base, **overlay}

			return {
				"mode": aw.get("mode", defaults.get("mode", "cli")),
				"default_context": aw.get("default_context", defaults["default_context"]),
				"route_context_map": aw.get("route_context_map", defaults["route_context_map"]),
				"contexts": merged_contexts,
				"sessions_dir": aw.get("sessions_dir", defaults["sessions_dir"]),
			}
		except Exception:
			return self._default_ai_workbench()

	@staticmethod
	def _default_ai_workbench() -> dict:
		"""ai_workbench 默认配置"""
		return {
			"mode": "cli",
			"default_context": "general",
			"sessions_dir": os.path.expanduser("~/.qsweb/ai_sessions"),
			"route_context_map": {
				"/factor": "factor",
				"/backtest": "backtest",
				"/risk": "risk",
				"/portfolio": "portfolio",
			},
			"contexts": {
				"general": {
					"description": "通用 AI 助手",
					"placeholder": "描述你想做的事情...",
					"system_prompt": "你是一个集成在 QSWeb 量化平台中的 AI 助手。请用中文回答用户问题，提供简洁、准确的回答。",
					"skills": [],
					"tools": ["mcp__jy_base_doc__*", "mcp__qs-registry__*", "Read", "Bash"],
					"mcp_servers": {},
					"max_budget_usd": 1.0,
					"permission_mode": "acceptEdits",
					"allowed_actions": [],
					"env": {},
				},
				"factor": {
					"description": "因子开发助手",
					"placeholder": "描述你想要的因子，例如：创建一个 20 日动量因子...",
					"system_prompt": (
						"使用 generate-factor-def-code 技能创建因子定义脚本。\n"
						"请遵循以下步骤：\n"
						"1. 理解需求并澄清不明确的部分\n"
						"2. 通过 jy_base_doc 工具验证数据表和字段\n"
						"3. 生成符合 FactorDef 框架规范的因子定义脚本\n"
						"4. 将脚本保存到正确的目录下\n"
						"\n"
						"脚本必须包含 __FACTOR_META__ 和 defFactor(fdi) -> List[Factor]。\n"
						"如果用户需求不明确，先使用 AskUserQuestion 工具询问缺失的关键信息。\n"
						"\n"
						"当你完成脚本生成后，请以 action_card 格式输出结果：\n"
						'{ "type": "action_card", "data": { "kind": "save_script", '
						'"title": "因子脚本已生成", "summary": {"TargetTable": "因子表名", '
						'"IDType": "A股", "has_def_factor": true}, '
						'"actions": [{"key": "save", "label": "保存脚本", "style": "primary"}, '
						'{"key": "discard", "label": "放弃", "style": "default"}], '
						'"payload": {"code": "<完整脚本代码>", "filename": "<建议的文件名>"} } }'
					),
					"skills": ["generate-factor-def-code"],
					"tools": [
						"mcp__jy_base_doc__*", "mcp__qs-registry__*",
						"Read", "Write", "Bash",
					],
					"mcp_servers": {},
					"max_budget_usd": 1.0,
					"permission_mode": "acceptEdits",
					"allowed_actions": ["save", "discard"],
					"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"},
					"scripts_dir": os.path.expanduser("~/FactorDef/Scripts"),
				},
			},
		}

	# ============================================================
	# 因子挖掘
	# ============================================================

	@staticmethod
	def _default_mining() -> dict:
		"""mining 默认配置"""
		return {
			"workspace": os.path.expanduser("~/MiningWorkspace"),
			"frameworks": {
				"gp": {
					"population_size": 20,
					"n_generations": 20,
				},
				"llm_factor": {
					"mode": "skill",
					"max_rounds": 1,
					"max_hours": 8.0,
					"max_turns_hypothesis": 50,
					"max_turns_development": 80,
				},
			},
		}

	@property
	def mining(self) -> dict:
		"""从 QSWebConfig.yaml 加载 mining 配置节"""
		defaults = self._default_mining()
		if not os.path.exists(self.QS_CONFIG_PATH):
			return defaults
		try:
			with open(self.QS_CONFIG_PATH, "r", encoding="utf-8") as f:
				config = yaml.safe_load(f)
			user_mining = config.get("mining", {})
			result = {
				"workspace": user_mining.get("workspace", defaults["workspace"]),
				"frameworks": user_mining.get("frameworks", defaults["frameworks"]),
			}
			if "default_eval" in user_mining:
				result["default_eval"] = user_mining["default_eval"]
			return result
		except Exception:
			return defaults


settings = Settings()

"""
全局配置服务

读写 QSWebConfig.yaml 中的 global 节。
"""

import os
import tempfile
from typing import Tuple, List
from ruamel.yaml import YAML

from app.core.config import settings

QS_CONFIG_PATH = settings.QS_CONFIG_PATH

_ruamel = YAML()
_ruamel.preserve_quotes = True


def get_global_config() -> dict:
    """读取全局配置（从 Settings.global_config 读取，已含默认值合并）"""
    return settings.global_config


def resolve_engine() -> Tuple[type, List[str], str]:
    """根据全局配置解析引擎类、PIDList 和缓存目录。

    Returns:
        (EngineClass, PIDList, cache_dir)
        - EngineClass: CalcEngine.Engine 或 ParallelEngine.ParallelEngine
        - PIDList: 进程 ID 列表, 默认 ["0"]
        - cache_dir: 缓存目录绝对路径
    """
    config = settings.global_config
    engine_cfg = config.get("engine", {})
    engine_type = engine_cfg.get("type", "CalcEngine")
    engine_params = engine_cfg.get("params", {})

    if config.get("use_temp_cache", False):
        cache_dir = os.path.join(tempfile.gettempdir(), "QSCache")
    else:
        cache_dir = os.path.expanduser(config.get("cache_dir", "~/QSCache"))

    n_workers = int(engine_params.get("n_workers", 1))
    if n_workers < 1:
        n_workers = 1

    if engine_type == "ParallelEngine":
        from QuantStudio.Core.ParallelEngine import ParallelEngine as EngineClass
        pid_list = [str(i) for i in range(max(n_workers, 1))]
    else:
        from QuantStudio.Core.CalcEngine import Engine as EngineClass
        pid_list = ["0"]

    return EngineClass, pid_list, cache_dir


def set_global_config(data: dict):
    """
    写入全局配置到 QSWebConfig.yaml。

    Args:
        data: 完整的全局配置字典。
              示例: {"cache_dir": "D:/Data/QSCache", "engine": {"type": "ParallelEngine", "params": {"n_workers": 4}}}
    """
    if os.path.exists(QS_CONFIG_PATH):
        with open(QS_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = _ruamel.load(f)
    else:
        cfg = _ruamel.load("{}")

    cfg.setdefault("global", {})
    if "cache_dir" in data:
        cfg["global"]["cache_dir"] = data["cache_dir"]
    if "use_temp_cache" in data:
        cfg["global"]["use_temp_cache"] = data["use_temp_cache"]
    if "engine" in data:
        cfg["global"]["engine"] = data["engine"]

    os.makedirs(os.path.dirname(QS_CONFIG_PATH), exist_ok=True)
    with open(QS_CONFIG_PATH, "w", encoding="utf-8") as f:
        _ruamel.dump(cfg, f)

    # 确保缓存目录实际存在
    cache_dir = data.get("cache_dir", "")
    if cache_dir:
        os.makedirs(os.path.expanduser(cache_dir), exist_ok=True)

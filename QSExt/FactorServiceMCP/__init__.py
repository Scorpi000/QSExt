"""只通过 FactorService 发现和读取因子数据的独立 MCP 服务。"""

from .config import MCPConfig
from .service import FactorDataService

__all__ = ["MCPConfig", "FactorDataService"]

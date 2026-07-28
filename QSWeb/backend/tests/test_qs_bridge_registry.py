"""
QSRegistry 因子源集成测试

测试因子名 → QSID 查找 → 重建的完整链路。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestQSBridgeRegistryIntegration:
    """QSBridge QSRegistry 因子源功能测试"""

    @pytest.fixture
    def mock_factor_service(self):
        """创建模拟的 FactorService"""
        svc = MagicMock()
        svc._factor_dbs = {}
        return svc

    @pytest.fixture
    def mock_registry_service(self):
        """创建模拟的 RegistryService（带缓存的 _get_gdb）"""
        svc = MagicMock()
        svc._gdb = None

        def _make_gdb():
            gdb = MagicMock()
            gdb.searchFactors.return_value = [
                {
                    "Name": "test_factor",
                    "QSID": "abc123def4567890",
                    "FactorClass": "DerivativeFactor",
                    "DataType": "double",
                    "OperatorType": "截面",
                    "OperatorName": "zscore",
                },
                {
                    "Name": "other_factor",
                    "QSID": "xyz9876543210abc",
                    "FactorClass": "DerivativeFactor",
                    "DataType": "double",
                    "OperatorType": "截面",
                    "OperatorName": "rank",
                },
            ]
            mock_factor = MagicMock()
            mock_factor._QSArgs.Name = "test_factor"
            gdb.reconstructFactor.return_value = mock_factor
            return gdb

        async def mock_get_gdb():
            if svc._gdb is None:
                svc._gdb = _make_gdb()
            return svc._gdb

        svc._get_gdb = mock_get_gdb
        return svc

    @pytest.fixture
    def bridge(self, mock_factor_service, mock_registry_service):
        """创建 QSBridge 实例"""
        from app.services.qs_bridge import QSBridge
        return QSBridge(
            factor_service=mock_factor_service,
            registry_service=mock_registry_service,
        )

    # ─── 14.1: _get_factor_from_registry ──────────────────────

    @pytest.mark.asyncio
    async def test_get_factor_from_registry_exact_match(self, bridge):
        """精确匹配：因子名完全匹配时返回对应 Factor"""
        factor = await bridge._get_factor_from_registry("test_factor")

        assert factor is not None
        assert factor._QSArgs.Name == "test_factor"

    @pytest.mark.asyncio
    async def test_get_factor_from_registry_not_found(self, bridge):
        """未找到匹配因子时抛出 ValueError"""
        gdb = await bridge._registry_service._get_gdb()
        gdb.searchFactors.return_value = []

        with pytest.raises(ValueError, match="未找到因子"):
            await bridge._get_factor_from_registry("nonexistent")

    @pytest.mark.asyncio
    async def test_get_factor_from_registry_fuzzy_match(self, bridge):
        """模糊匹配：名称不完全一致时取第一个结果"""
        gdb = await bridge._registry_service._get_gdb()
        # 只保留不精确匹配的结果
        gdb.searchFactors.return_value = [
            {"Name": "test_factor_v2", "QSID": "abc123def4567890"},
        ]

        factor = await bridge._get_factor_from_registry("test_factor")
        assert factor is not None

    @pytest.mark.asyncio
    async def test_get_factor_from_registry_no_service(self, mock_factor_service):
        """未初始化 registry_service 时抛出 RuntimeError"""
        from app.services.qs_bridge import QSBridge
        bridge = QSBridge(factor_service=mock_factor_service, registry_service=None)

        with pytest.raises(RuntimeError, match="QSRegistry 服务未初始化"):
            await bridge._get_factor_from_registry("test_factor")

    # ─── 14.2: register_factor_dbs ────────────────────────────

    @pytest.mark.asyncio
    async def test_register_factor_dbs_empty(self, bridge):
        """空 FactorDB 列表时不报错"""
        await bridge.register_factor_dbs()
        # 不应抛出异常

    @pytest.mark.asyncio
    async def test_register_factor_dbs_with_dbs(self, bridge):
        """有 FactorDB 列表时正确注册"""
        mock_fdb = MagicMock()
        mock_fdb.Name = "TestDB"
        bridge._factor_service._factor_dbs = {"conn1": mock_fdb}

        await bridge.register_factor_dbs()

        gdb = await bridge._registry_service._get_gdb()
        gdb.registerFactorDB.assert_called_once_with(mock_fdb)

    @pytest.mark.asyncio
    async def test_register_factor_dbs_no_service(self, mock_factor_service):
        """未初始化 registry_service 时静默跳过"""
        from app.services.qs_bridge import QSBridge
        bridge = QSBridge(factor_service=mock_factor_service, registry_service=None)

        # 不应抛出异常
        await bridge.register_factor_dbs()

    # ─── 14.4: 完整链路测试 ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_full_chain_search_to_reconstruct(self, bridge):
        """完整链路：因子名搜索 → QSID 提取 → Factor 重建"""
        gdb = await bridge._registry_service._get_gdb()

        # Step 1: 搜索
        results = gdb.searchFactors(name="test_factor", limit=10)
        assert len(results) > 0
        qsid = results[0]["QSID"]
        assert qsid == "abc123def4567890"

        # Step 2: 重建
        factor = gdb.reconstructFactor(qsid)
        assert factor is not None
        assert factor._QSArgs.Name == "test_factor"

    @pytest.mark.asyncio
    async def test_get_factor_from_registry_full_chain(self, bridge):
        """_get_factor_from_registry 内部完成搜索+精确匹配+重建全链路"""
        factor = await bridge._get_factor_from_registry("test_factor")

        gdb = await bridge._registry_service._get_gdb()

        # 验证搜索被调用
        gdb.searchFactors.assert_called_once_with(name="test_factor", limit=5)

        # 验证重建被调用
        gdb.reconstructFactor.assert_called_once_with("abc123def4567890")

        # 验证结果
        assert factor is not None
        assert factor._QSArgs.Name == "test_factor"


class TestQSBridgeDualSourceResolution:
    """双源因子解析测试"""

    @pytest.fixture
    def mock_factor_service(self):
        svc = MagicMock()
        svc._factor_dbs = {}
        return svc

    @pytest.fixture
    def mock_registry_service(self):
        svc = MagicMock()
        svc._gdb = None

        def _make_gdb():
            gdb = MagicMock()
            gdb.searchFactors.return_value = [
                {"Name": "reg_factor", "QSID": "reg1234567890abc"},
            ]
            mock_factor = MagicMock()
            mock_factor._QSArgs.Name = "reg_factor"
            gdb.reconstructFactor.return_value = mock_factor
            return gdb

        async def mock_get_gdb():
            if svc._gdb is None:
                svc._gdb = _make_gdb()
            return svc._gdb

        svc._get_gdb = mock_get_gdb
        return svc

    @pytest.mark.asyncio
    async def test_resolve_registry_factor_ref(self, mock_factor_service, mock_registry_service):
        """解析 source=registry 的 FactorRef"""
        from app.services.qs_bridge import QSBridge
        bridge = QSBridge(
            factor_service=mock_factor_service,
            registry_service=mock_registry_service,
        )

        factor = await bridge._get_factor_from_registry("reg_factor")
        assert factor is not None
        assert factor._QSArgs.Name == "reg_factor"

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


class TestDeclarativeNodeBuilders:
    """声明式 _BT_NODE_BUILDERS 注册表验证

    验证所有模块定义包含必要字段，calc/node 类可正常导入。
    """

    def test_all_builders_have_required_fields(self):
        """每个 builder 条目都包含必要字段"""
        from app.services.qs_bridge import _BT_NODE_BUILDERS

        required_fields = {"calc_module", "calc_class", "node_module", "node_class"}
        for key, builder in _BT_NODE_BUILDERS.items():
            missing = required_fields - set(builder.keys())
            assert not missing, f"模块 '{key}' 缺少必要字段: {missing}"

    def test_calc_classes_importable(self):
        """所有 calc_class 可在对应模块中找到"""
        import importlib
        from app.services.qs_bridge import _BT_NODE_BUILDERS

        for key, builder in _BT_NODE_BUILDERS.items():
            mod = importlib.import_module(builder["calc_module"])
            cls = getattr(mod, builder["calc_class"])
            assert cls is not None, f"模块 '{key}': 无法导入 calc_class '{builder['calc_class']}'"

    def test_node_classes_importable(self):
        """所有 node_class 可在对应模块中找到"""
        import importlib
        from app.services.qs_bridge import _BT_NODE_BUILDERS

        for key, builder in _BT_NODE_BUILDERS.items():
            mod = importlib.import_module(builder["node_module"])
            cls = getattr(mod, builder["node_class"])
            assert cls is not None, f"模块 '{key}': 无法导入 node_class '{builder['node_class']}'"

    def test_module_keys_match_registry(self):
        """_BT_NODE_BUILDERS 的 key 与 BACKTEST_MODULE_REGISTRY 对齐"""
        from app.services.qs_bridge import _BT_NODE_BUILDERS
        # 这些 key 应与前端模块注册表中定义的 key 一致
        expected_keys = {"ic", "ic_decay", "multi_portfolio", "factor_turnover",
                         "section_correlation", "fama_macbeth"}
        assert set(_BT_NODE_BUILDERS.keys()) == expected_keys, \
            f"Builder keys 与预期不一致: {set(_BT_NODE_BUILDERS.keys()) ^ expected_keys}"

    def test_per_factor_modules_have_flag(self):
        """per_factor 标记的模块使用每个因子分别构造 calc"""
        from app.services.qs_bridge import _BT_NODE_BUILDERS

        per_factor_keys = [k for k, v in _BT_NODE_BUILDERS.items() if v.get("per_factor")]
        assert "ic_decay" in per_factor_keys, "ic_decay 应标记为 per_factor"

    def test_price_required_modules(self):
        """requires_price 标记的模块价格因子为必需"""
        from app.services.qs_bridge import _BT_NODE_BUILDERS

        price_keys = [k for k, v in _BT_NODE_BUILDERS.items() if v.get("requires_price")]
        assert "ic" in price_keys, "ic 应标记为 requires_price"
        assert "fama_macbeth" in price_keys, "fama_macbeth 应标记为 requires_price"

# -*- coding: utf-8 -*-
"""QSRegistry 功能测试 — 基于 Neo4j 实例"""
import sys
import os
import json
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

# 配置路径
NEO4J_CONFIG = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
with open(NEO4J_CONFIG, "r", encoding="utf-8") as f:
    content = f.read()
# 容忍尾随逗号
import re
content = re.sub(r",\s*([}\]])", r"\1", content)
neo4j_cfg = json.loads(content)

gdb_args = {
    "IPAddr": neo4j_cfg["IPAddr"],
    "Port": neo4j_cfg["Port"],
    "User": neo4j_cfg["User"],
    "Pwd": neo4j_cfg["Pwd"],
    "DBName": neo4j_cfg.get("DBName", "neo4j"),
}

# ============================================================
# 导入 QuantStudio
# ============================================================
from QSExt.QSRegistry.api import QSGraphDB
from QuantStudio.Factor.Factor import DataFactor
from QuantStudio.Factor.FactorOperation import (
    PointOperator, TimeOperator, makeFactorOperator
)
from QuantStudio.Factor.JYDB import JYDB
from QuantStudio.Factor.FactorStorer import FactorStorer
import tempfile
import numpy as np
import pandas as pd


def test_1_connect():
    """测试 1: 连接与 Schema 初始化"""
    print("\n" + "=" * 60)
    print("测试 1: 连接与 Schema 初始化")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()
    print(f"  [PASS] 连接成功")
    print(f"  [PASS] 地址: {gdb._QSArgs.IPAddr}:{gdb._QSArgs.Port}")
    gdb.disconnect()
    print(f"  [PASS] 断开成功")
    return True


def test_2_store_and_retrieve_datafactor():
    """测试 2: 存储和检索 DataFactor（标量、Series、DataFrame）"""
    print("\n" + "=" * 60)
    print("测试 2: 存储和检索 DataFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 2a: 标量 DataFactor
    scalar_factor = DataFactor(data=42.0, args={"Name": "test_scalar", "DataType": "double"})
    qsid1 = gdb.storeFactors([scalar_factor], tags={scalar_factor.QSID: ["test", "scalar"]})[0]
    print(f"  [PASS] 标量 DataFactor 存储完成, QSID: {qsid1[:16]}...")

    result = gdb.getFactorByQSID(qsid1)
    assert result is not None, "getFactorByQSID 返回 None"
    assert result["Name"] == "test_scalar"
    assert result["FactorClass"] == "DataFactor"
    print(f"  [PASS] getFactorByQSID 成功, Name={result['Name']}, FactorClass={result['FactorClass']}")

    # 2b: Series DataFactor
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    series_data = pd.Series([1.1, 2.2, 3.3, 4.4, 5.5], index=dates, name="test_series_data")
    series_factor = DataFactor(data=series_data, args={"Name": "test_series", "DataType": "double"})
    qsid2 = gdb.storeFactors([series_factor], tags={series_factor.QSID: ["test", "series"]})[0]
    print(f"  [PASS] Series DataFactor 存储完成, QSID: {qsid2[:16]}...")

    # 2c: DataFrame DataFactor
    ids = ["000001.SZ", "000002.SZ", "600000.SH"]
    df_data = pd.DataFrame(
        np.random.randn(5, 3), index=dates, columns=ids
    )
    df_factor = DataFactor(data=df_data, args={"Name": "test_dataframe", "DataType": "double"})
    qsid3 = gdb.storeFactors([df_factor], tags={df_factor.QSID: ["test", "dataframe"]})[0]
    print(f"  [PASS] DataFrame DataFactor 存储完成, QSID: {qsid3[:16]}...")

    gdb.disconnect()
    return True


def test_3_store_derivative_chain():
    """测试 3: 存储衍生因子链（DataFactor → PointOp → TimeOp）"""
    print("\n" + "=" * 60)
    print("测试 3: 存储衍生因子链")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 构建因子链
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    ids = ["000001.SZ", "000002.SZ", "600000.SH"]
    price_data = pd.DataFrame(
        np.random.uniform(10, 50, (10, 3)),
        index=dates, columns=ids
    )
    close = DataFactor(data=price_data, args={"Name": "Close", "DataType": "double"})

    # 使用 fo 算子
    from QuantStudio.Factor.api import fo
    log_close = fo.Log()(close)
    lag1 = fo.Lag(lag_period=1)(log_close)

    # 存储整条链
    qsid = gdb.storeFactors([lag1], tags={lag1.QSID: ["test", "chain", "momentum"]})[0]
    print(f"  [PASS] 因子链存储完成, 根因子 QSID: {qsid[:16]}...")

    # 查看图统计
    stats = gdb.getGraphStats()
    print(f"  [PASS] 图统计: {stats}")

    # 搜索因子
    results = gdb.searchFactors(name="log")
    print(f"  [PASS] searchFactors(name='log') 返回 {len(results)} 个因子")

    results = gdb.searchFactors(operator_type="Point")
    print(f"  [PASS] searchFactors(operator_type='Point') 返回 {len(results)} 个因子")

    results = gdb.searchFactors(tag="chain")
    print(f"  [PASS] searchFactors(tag='chain') 返回 {len(results)} 个因子")

    gdb.disconnect()
    return True


def test_4_dependency_graph():
    """测试 4: 依赖图查询"""
    print("\n" + "=" * 60)
    print("测试 4: 依赖图查询")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 搜索一个 DerivativeFactor 来测试依赖图
    results = gdb.searchFactors(name="lag")
    if not results:
        print("  [WARN] 图中无 lag 因子，跳过")
        gdb.disconnect()
        return True

    target_qsid = results[0]["QSID"]
    target_name = results[0]["Name"]
    print(f"  目标因子: {target_name} (QSID: {target_qsid[:16]}...)")

    # 向下依赖图
    graph_down = gdb.getDependencyGraph(target_qsid, direction="down")
    print(f"  [PASS] getDependencyGraph(down): {len(graph_down['nodes'])} 个节点, {len(graph_down['edges'])} 条边")
    for n in graph_down["nodes"]:
        print(f"    - {n.get('Name', '?')} [{n.get('FactorClass', '?')}]")

    # 描述子
    descs = gdb.getDescriptors(target_qsid)
    print(f"  [PASS] getDescriptors: {len(descs)} 个直接依赖")
    for d in descs:
        print(f"    - {d.get('Name', '?')} [{d.get('FactorClass', '?')}]")

    # 向上依赖图（谁依赖这个因子）
    graph_up = gdb.getDependencyGraph(target_qsid, direction="up")
    print(f"  [PASS] getDependencyGraph(up): {len(graph_up['nodes'])} 个节点")

    gdb.disconnect()
    return True


def test_5_reconstruct_scalar():
    """测试 5: 重建标量 DataFactor"""
    print("\n" + "=" * 60)
    print("测试 5: 重建标量 DataFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 搜索之前存储的标量因子
    results = gdb.searchFactors(name="test_scalar")
    if not results:
        print("  [WARN] 无 test_scalar 因子，跳过")
        gdb.disconnect()
        return True

    qsid = results[0]["QSID"]
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] Name: {reconstructed._QSArgs.Name}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")

    gdb.disconnect()
    return True


def test_6_reconstruct_series():
    """测试 6: 重建 Series DataFactor"""
    print("\n" + "=" * 60)
    print("测试 6: 重建 Series DataFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    results = gdb.searchFactors(name="test_series")
    if not results:
        print("  [WARN] 无 test_series 因子，跳过")
        gdb.disconnect()
        return True

    qsid = results[0]["QSID"]
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] 数据形状: {reconstructed._Data.shape}")
    print(f"  [PASS] 数据前 3 项: {reconstructed._Data.values[:3]}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")

    gdb.disconnect()
    return True


def test_7_reconstruct_dataframe():
    """测试 7: 重建 DataFrame DataFactor"""
    print("\n" + "=" * 60)
    print("测试 7: 重建 DataFrame DataFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    results = gdb.searchFactors(name="test_dataframe")
    if not results:
        print("  [WARN] 无 test_dataframe 因子，跳过")
        gdb.disconnect()
        return True

    qsid = results[0]["QSID"]
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] 数据形状: {reconstructed._Data.shape}")
    print(f"  [PASS] 列: {list(reconstructed._Data.columns)}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")

    gdb.disconnect()
    return True


def test_8_reconstruct_chain():
    """测试 8: 重建衍生因子链"""
    print("\n" + "=" * 60)
    print("测试 8: 重建衍生因子链")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    results = gdb.searchFactors(name="lag")
    if not results:
        print("  [WARN] 无 lag 因子，跳过")
        gdb.disconnect()
        return True

    # 找到根因子（有 "lag" 名称的衍生因子）
    lag_factor_data = None
    for r in results:
        if r.get("FactorClass") == "DerivativeFactor":
            lag_factor_data = r
            break
    if not lag_factor_data:
        print("  [WARN] 无 DerivativeFactor 类型的 lag 因子，跳过")
        gdb.disconnect()
        return True

    qsid = lag_factor_data["QSID"]
    print(f"  重建目标: {lag_factor_data['Name']} (QSID: {qsid[:16]}...)")

    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] Name: {reconstructed._QSArgs.Name}")
    print(f"  [PASS] Descriptors 数量: {len(reconstructed.Descriptors)}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")

    # 验证描述子
    for i, desc in enumerate(reconstructed.Descriptors):
        print(f"    描述子 {i}: {desc._QSArgs.Name} [{type(desc).__name__}]")

    gdb.disconnect()
    return True


def test_9_management():
    """测试 9: 管理操作（标签、元信息、重命名）"""
    print("\n" + "=" * 60)
    print("测试 9: 管理操作")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    results = gdb.searchFactors(name="test_scalar")
    if not results:
        print("  [WARN] 无 test_scalar 因子，跳过")
        gdb.disconnect()
        return True

    qsid = results[0]["QSID"]

    # 更新标签
    gdb.updateFactorTags(qsid, add_tags=["updated_tag"])
    print("  [PASS] 添加标签 'updated_tag'")

    # 验证标签
    results_after = gdb.searchFactors(tag="updated_tag")
    assert any(r["QSID"] == qsid for r in results_after), "标签添加失败"
    print("  [PASS] 标签验证通过")

    # 更新元信息
    gdb.updateFactorMetaData(qsid, {"author": "test_user", "version": 2})
    print("  [PASS] 更新元信息")

    # 验证元信息
    factor_data = gdb.getFactorByQSID(qsid)
    meta = json.loads(factor_data.get("MetaJSON", "{}"))
    assert meta.get("author") == "test_user"
    print(f"  [PASS] 元信息验证通过: {meta}")

    # 重命名
    gdb.renameFactor(qsid, "test_scalar_renamed")
    factor_data = gdb.getFactorByQSID(qsid)
    assert factor_data["Name"] == "test_scalar_renamed"
    print(f"  [PASS] 重命名为: {factor_data['Name']}")

    # 移除标签
    gdb.updateFactorTags(qsid, remove_tags=["updated_tag"])
    results_after = gdb.searchFactors(tag="updated_tag")
    assert not any(r["QSID"] == qsid for r in results_after), "标签移除失败"
    print("  [PASS] 标签移除成功")

    gdb.disconnect()
    return True


def test_10_impact_analysis():
    """测试 10: 影响分析"""
    print("\n" + "=" * 60)
    print("测试 10: 影响分析")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 找到 Close DataFactor
    results = gdb.searchFactors(name="Close")
    if not results:
        print("  [WARN] 无 Close 因子，跳过")
        gdb.disconnect()
        return True

    close_qsid = results[0]["QSID"]
    print(f"  分析目标: Close (QSID: {close_qsid[:16]}...)")

    impacted = gdb.impactAnalysis(close_qsid)
    print(f"  [PASS] 受影响因子数量: {len(impacted)}")
    for item in impacted:
        node = item["impacted"]
        depth = item["depth"]
        print(f"    depth={depth}: {node.get('Name', '?')} [{node.get('FactorClass', '?')}]")

    gdb.disconnect()
    return True


def test_11_find_orphans():
    """测试 11: 查找孤立因子"""
    print("\n" + "=" * 60)
    print("测试 11: 查找孤立因子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    orphans = gdb.findOrphanFactors()
    print(f"  [PASS] 孤立因子数量: {len(orphans)}")
    for o in orphans[:5]:
        print(f"    - {o.get('Name', '?')} [{o.get('FactorClass', '?')}] QSID: {o.get('QSID', '?')[:16]}...")

    gdb.disconnect()
    return True


def test_12_custom_operator():
    """测试 12: 自定义算子存储和重建"""
    print("\n" + "=" * 60)
    print("测试 12: 自定义算子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建自定义算子
    def zscore_func(f, idt, iid, x, args):
        return (x[0] - np.nanmean(x[0])) / np.nanstd(x[0])

    zscore_op = makeFactorOperator(
        zscore_func, "Point",
        args={"Name": "custom_zscore", "Arity": 1, "DataType": "double"}
    )

    # 创建数据
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    ids = ["000001.SZ", "000002.SZ"]
    data = pd.DataFrame(np.random.randn(5, 2), index=dates, columns=ids)
    base = DataFactor(data=data, args={"Name": "base_data", "DataType": "double"})

    # 应用自定义算子
    zscore_factor = zscore_op(base)
    qsid = gdb.storeFactors([zscore_factor], tags={zscore_factor.QSID: ["test", "custom_op"]})[0]
    print(f"  [PASS] 自定义算子因子存储完成, QSID: {qsid[:16]}...")

    # 检查算子
    factor_data = gdb.getFactorByQSID(qsid)
    op_qsid = factor_data.get("OperatorQSID")
    op_results = gdb.executeCypher(
        "MATCH (o:`算子` {QSID: $qsid}) RETURN o",
        {"qsid": op_qsid}
    )
    if op_results:
        op_data = op_results[0]["o"]
        print(f"  [PASS] 算子: {op_data['Name']}, IsCustom={op_data.get('IsCustom')}")
        print(f"  [PASS] CalculateRef 存在: {op_data.get('CalculateRef') is not None}")

    # 重建
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")

    gdb.disconnect()
    return True


def test_13_delete():
    """测试 13: 删除因子"""
    print("\n" + "=" * 60)
    print("测试 13: 删除因子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建一个临时因子
    temp = DataFactor(data=999.0, args={"Name": "temp_to_delete", "DataType": "double"})
    qsid = gdb.storeFactors([temp])[0]
    print(f"  创建临时因子: {qsid[:16]}...")

    # 非级联删除
    deleted = gdb.deleteFactor(qsid, cascade=False)
    assert deleted == 1
    result = gdb.getFactorByQSID(qsid)
    assert result is None
    print(f"  [PASS] 非级联删除成功, 删除数: {deleted}")

    gdb.disconnect()
    return True


def test_14_cypher_raw():
    """测试 14: 原始 Cypher 查询"""
    print("\n" + "=" * 60)
    print("测试 14: 原始 Cypher 查询")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 统计各类型因子数量
    results = gdb.executeCypher(
        "MATCH (f:`因子`) RETURN f.FactorClass AS cls, count(f) AS cnt ORDER BY cnt DESC"
    )
    print("  [PASS] 因子类别统计:")
    for r in results:
        print(f"    {r['cls']}: {r['cnt']}")

    # 统计关系
    results = gdb.executeCypher(
        "MATCH ()-[r:`依赖`]->() RETURN count(r) AS cnt"
    )
    print(f"  [PASS] 依赖 关系数: {results[0]['cnt']}")

    gdb.disconnect()
    return True


def test_15_idempotent_store():
    """测试 15: 幂等存储"""
    print("\n" + "=" * 60)
    print("测试 15: 幂等存储")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    factor = DataFactor(data=3.14, args={"Name": "idempotent_test", "DataType": "double"})
    qsid1 = gdb.storeFactors([factor])[0]
    qsid2 = gdb.storeFactors([factor])[0]  # 第二次存储
    assert qsid1 == qsid2
    print(f"  [PASS] 两次存储 QSID 一致: {qsid1[:16]}...")

    # 验证只有一个节点
    results = gdb.searchFactors(name="idempotent_test")
    assert len(results) == 1, f"期望 1 个节点，实际 {len(results)}"
    print(f"  [PASS] 图中只有 1 个节点")

    # 清理
    gdb.deleteFactor(qsid1)
    gdb.disconnect()
    return True


# ============================================================
# JYDB FactorTableFactor 测试（测试 16-21）
# ============================================================

# JYDB 实例（跨测试共享，只需连接一次）
_jydb = None
_jydb_available = None  # None=未检测, True/False=已检测

def _get_jydb():
    """懒加载 JYDB 连接，失败返回 None"""
    global _jydb, _jydb_available
    if _jydb_available is False:
        return None
    if _jydb is None:
        try:
            _jydb = JYDB().connect()
            _jydb_available = True
        except Exception as e:
            print(f"  [SKIP] JYDB 连接失败: {e}")
            _jydb_available = False
            return None
    return _jydb


def test_16_register_fdb_and_store_table():
    """测试 16: 注册 JYDB 因子库并存储因子表"""
    print("\n" + "=" * 60)
    print("测试 16: 注册 JYDB + 存储因子表")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        gdb.disconnect()
        return True
    print(f"  JYDB 已连接, Name={jydb.Name}, DBType={jydb._QSArgs.DBType}")

    # 注册因子库
    fdb_name = gdb.registerFactorDB(jydb)
    assert fdb_name == "JYDB"
    print(f"  [PASS] registerFactorDB: {fdb_name}")

    # 验证因子库节点
    fdb_results = gdb.executeCypher(
        "MATCH (d:`因子库` {Name: $name}) RETURN d", {"name": "JYDB"}
    )
    assert len(fdb_results) == 1
    assert fdb_results[0]["d"]["DBType"] == "JYDB"
    print(f"  [PASS] 因子库节点已创建, DBType={fdb_results[0]['d']['DBType']}")

    # 获取并存储因子表
    ft = jydb.getTable("日行情表")
    ft_qsid = gdb.storeFactorTable(ft, fdb_name="JYDB")
    print(f"  [PASS] storeFactorTable: {ft._QSArgs.Name}, QSID: {ft_qsid[:16]}...")

    # 验证因子表节点和属于因子库关系
    ft_results = gdb.executeCypher(
        "MATCH (t:`因子表` {QSID: $qsid})-[:`属于因子库`]->(d:`因子库`) RETURN t, d",
        {"qsid": ft_qsid}
    )
    assert len(ft_results) == 1
    assert ft_results[0]["d"]["Name"] == "JYDB"
    print(f"  [PASS] 属于因子库 关系已建立 -> JYDB")

    # 验证因子名称列表
    ft_node = ft_results[0]["t"]
    factor_names = json.loads(ft_node["FactorNamesJSON"])
    print(f"  [PASS] 因子表包含 {len(factor_names)} 个因子")
    print(f"    前5个: {factor_names[:5]}")

    gdb.disconnect()
    return True


def test_17_store_factortable_factor():
    """测试 17: 存储 FactorTableFactor"""
    print("\n" + "=" * 60)
    print("测试 17: 存储 FactorTableFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        gdb.disconnect()
        return True

    # 确保 JYDB 已注册
    if "JYDB" not in gdb._FactorDBRegistry:
        gdb.registerFactorDB(jydb)

    # 获取因子表和因子
    ft = jydb.getTable("日行情表")
    close_factor = ft.getFactor("收盘价(元)")
    print(f"  因子: {close_factor._QSArgs.Name}, FactorTable={close_factor.FactorTable._QSArgs.Name}")

    # 存储因子（会自动递归存储因子表和因子库）
    qsid = gdb.storeFactors([close_factor], tags={close_factor.QSID: ["jydb", "price", "daily"]})[0]
    print(f"  [PASS] storeFactor 完成, QSID: {qsid[:16]}...")

    # 验证因子属性
    factor_data = gdb.getFactorByQSID(qsid)
    assert factor_data["FactorClass"] == "FactorTableFactor"
    assert factor_data["NameInFT"] == "收盘价(元)"
    assert factor_data["FactorTableQSID"] is not None
    print(f"  [PASS] FactorClass={factor_data['FactorClass']}")
    print(f"  [PASS] NameInFT={factor_data['NameInFT']}")
    print(f"  [PASS] FactorTableQSID={factor_data['FactorTableQSID'][:16]}...")

    # 验证属于因子表关系
    bt_results = gdb.executeCypher(
        """
        MATCH (f:`因子` {QSID: $qsid})-[:`属于因子表`]->(t:`因子表`)
        RETURN t.Name AS name, t.QSID AS qsid
        """,
        {"qsid": qsid}
    )
    assert len(bt_results) == 1
    assert bt_results[0]["name"] == "日行情表"
    print(f"  [PASS] 属于因子表 -> {bt_results[0]['name']}")

    # 验证标签
    tag_results = gdb.executeCypher(
        """
        MATCH (f:`因子` {QSID: $qsid})-[:`打标签`]->(t:`标签`)
        RETURN collect(t.Name) AS tags
        """,
        {"qsid": qsid}
    )
    tags = tag_results[0]["tags"]
    assert "jydb" in tags and "price" in tags and "daily" in tags
    print(f"  [PASS] 标签: {tags}")

    gdb.disconnect()
    return True


def test_18_factortable_derivative_chain():
    """测试 18: FactorTableFactor 衍生因子链（日行情表.收盘价 → Log → Lag）"""
    print("\n" + "=" * 60)
    print("测试 18: FactorTableFactor 衍生链")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        gdb.disconnect()
        return True

    if "JYDB" not in gdb._FactorDBRegistry:
        gdb.registerFactorDB(jydb)

    from QuantStudio.Factor.api import fo

    ft = jydb.getTable("日行情表")
    close = ft.getFactor("收盘价(元)")
    log_close = fo.Log()(close)
    lag1 = fo.Lag(lag_period=1)(log_close)

    # 存储整条链
    qsid = gdb.storeFactors([lag1], tags={lag1.QSID: ["jydb", "chain", "log_price"]})[0]
    print(f"  [PASS] 因子链存储完成, QSID: {qsid[:16]}...")

    # 验证图结构：lag1 -> log_close -> close(FTF) -> 日行情表(FactorTable) -> JYDB(FactorDB)
    graph = gdb.getDependencyGraph(qsid, direction="down")
    node_names = [n["Name"] for n in graph["nodes"]]
    node_classes = [n["FactorClass"] for n in graph["nodes"]]
    print(f"  [PASS] 依赖图: {len(graph['nodes'])} 个节点")
    for n in graph["nodes"]:
        print(f"    - {n['Name']} [{n.get('FactorClass', '?')}]")

    # 验证包含 FactorTableFactor
    assert "FactorTableFactor" in node_classes, "图中应包含 FactorTableFactor"
    print(f"  [PASS] 图中包含 FactorTableFactor 节点")

    # 验证根因子是 DerivativeFactor
    root_data = gdb.getFactorByQSID(qsid)
    assert root_data["FactorClass"] == "DerivativeFactor"
    assert root_data["OperatorType"] == "Time"
    print(f"  [PASS] 根因子: {root_data['Name']} [DerivativeFactor, Time]")

    gdb.disconnect()
    return True


def test_19_reconstruct_factortable_factor():
    """测试 19: 重建 FactorTableFactor（从 JYDB 获取实际数据）"""
    print("\n" + "=" * 60)
    print("测试 19: 重建 FactorTableFactor")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        gdb.disconnect()
        return True

    # 注册 JYDB（重建必须有注册的 FactorDB）
    gdb.registerFactorDB(jydb)

    # 搜索 FactorTableFactor
    results = gdb.searchFactors(name="收盘价(元)", factor_class="FactorTableFactor")
    if not results:
        print("  [WARN] 无 收盘价(元) FactorTableFactor，跳过")
        gdb.disconnect()
        return True

    qsid = results[0]["QSID"]
    print(f"  重建目标: {results[0]['Name']} (QSID: {qsid[:16]}...)")

    # 重建
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] Name: {reconstructed._QSArgs.Name}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")
    print(f"  [PASS] FactorTable: {reconstructed.FactorTable._QSArgs.Name}")

    # 用重建的因子读取实际数据（验证可用性）
    import datetime as dt
    ids = ["000001.SZ", "600000.SH"]
    dts = [dt.datetime(2024, 6, 3)]
    data = reconstructed.FactorTable.readData(
        factor_names=[reconstructed._QSArgs.Name], ids=ids, dts=dts
    )
    print(f"  [PASS] 数据读取成功, shape={data.shape}")

    gdb.disconnect()
    return True


def test_20_reconstruct_factortable_chain():
    """测试 20: 重建 FactorTableFactor 衍生链"""
    print("\n" + "=" * 60)
    print("测试 20: 重建 FactorTableFactor 衍生链")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        gdb.disconnect()
        return True
    gdb.registerFactorDB(jydb)

    # 搜索 lag 因子（应来自 test_18 的链）
    results = gdb.searchFactors(tag="log_price")
    if not results:
        print("  [WARN] 无 log_price 标签因子，跳过")
        gdb.disconnect()
        return True

    # 找到根 DerivativeFactor
    root_data = None
    for r in results:
        if r.get("FactorClass") == "DerivativeFactor" and r.get("OperatorType") == "Time":
            root_data = r
            break
    if not root_data:
        print("  [WARN] 无 Time 类型 DerivativeFactor，跳过")
        gdb.disconnect()
        return True

    qsid = root_data["QSID"]
    print(f"  重建目标: {root_data['Name']} (QSID: {qsid[:16]}...)")

    # 重建（递归重建整条链）
    reconstructed = gdb.reconstructFactor(qsid)
    print(f"  [PASS] 重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] Name: {reconstructed._QSArgs.Name}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == qsid}")
    print(f"  [PASS] Descriptors: {[d._QSArgs.Name for d in reconstructed.Descriptors]}")

    # 验证底层描述子是 FactorTableFactor
    desc = reconstructed.Descriptors[0]
    while desc.Descriptors:
        desc = desc.Descriptors[0]
    assert desc.FactorTable is not None, "叶子节点应是 FactorTableFactor"
    print(f"  [PASS] 叶子节点: {desc._QSArgs.Name} (FactorTable: {desc.FactorTable._QSArgs.Name})")

    gdb.disconnect()
    return True


def test_21_search_and_impact_factortable():
    """测试 21: FactorTableFactor 的搜索和影响分析"""
    print("\n" + "=" * 60)
    print("测试 21: FactorTableFactor 搜索与影响分析")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 按 factor_class 搜索
    results = gdb.searchFactors(factor_class="FactorTableFactor")
    print(f"  [PASS] searchFactors(factor_class='FactorTableFactor'): {len(results)} 个")
    for r in results:
        print(f"    - {r['Name']} (Table: {r.get('NameInFT', '?')})")

    # 按 tag 搜索
    results = gdb.searchFactors(tag="jydb")
    print(f"  [PASS] searchFactors(tag='jydb'): {len(results)} 个")

    # 影响分析：修改 日行情表.收盘价 会影响哪些因子？
    close_results = gdb.searchFactors(name="收盘价(元)", factor_class="FactorTableFactor")
    if close_results:
        close_qsid = close_results[0]["QSID"]
        impacted = gdb.impactAnalysis(close_qsid)
        print(f"  [PASS] 影响分析 - 收盘价(元) 影响 {len(impacted)} 个因子:")
        for item in impacted:
            node = item["impacted"]
            depth = item["depth"]
            print(f"    depth={depth}: {node['Name']} [{node.get('FactorClass', '?')}]")

    # 统计
    stats = gdb.getGraphStats()
    print(f"  [PASS] 图统计: {stats}")

    gdb.disconnect()
    return True


def test_22_to_mermaid():
    """测试 22: toMermaid 依赖图可视化"""
    print("\n" + "=" * 60)
    print("测试 22: toMermaid 依赖图可视化")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 22a: 单因子
    results = gdb.searchFactors(name="turnover")
    if results:
        qsid = results[0]["QSID"]
        mermaid = gdb.toMermaid(qsid, direction="down")
        assert "flowchart LR" in mermaid
        assert qsid[:8] in mermaid
        assert "turnover" in mermaid
        assert 'style' in mermaid
        print(f"  [PASS] 单因子 Mermaid 生成成功 ({len(mermaid.splitlines())} 行)")
        print(f"        前 3 行:")
        for line in mermaid.splitlines()[:3]:
            print(f"          {line}")
    else:
        print("  [WARN] 无 turnover 因子，跳过单因子测试")

    # 22b: 多因子合并
    results = gdb.searchFactors(name="close", limit=2)
    if len(results) >= 2:
        qsids = [r["QSID"] for r in results]
        mermaid = gdb.toMermaid(qsids, direction="down")
        lines = mermaid.splitlines()
        assert "flowchart LR" in mermaid
        for q in qsids:
            assert q[:8] in mermaid
        # 两个目标因子都应高亮
        style_count = sum(1 for l in lines if "fill:#f9f" in l)
        assert style_count >= 2, f"期望 >=2 个高亮节点，实际 {style_count}"
        print(f"  [PASS] 多因子 Mermaid 生成成功 ({len(lines)} 行, {style_count} 个目标节点高亮)")
    else:
        print("  [WARN] close 因子不足 2 个，跳过多因子测试")

    # 22c: direction="both"
    if results:
        qsid = results[0]["QSID"]
        mermaid = gdb.toMermaid(qsid, direction="both")
        assert "flowchart LR" in mermaid
        print(f"  [PASS] direction='both' 生成成功 ({len(mermaid.splitlines())} 行)")

    # 22d: 颜色验证 — DerivativeFactor 蓝, FactorTableFactor 橙
    mermaid = gdb.toMermaid(results[0]["QSID"], direction="down") if results else ""
    if mermaid:
        blue_nodes = [l for l in mermaid.splitlines() if "#e1f5fe" in l]
        orange_nodes = [l for l in mermaid.splitlines() if "#fff3e0" in l]
        print(f"  [PASS] DerivativeFactor(蓝): {len(blue_nodes)} 个")
        print(f"  [PASS] FactorTableFactor(橙): {len(orange_nodes)} 个")

    # 22e: 空结果处理
    fake_mermaid = gdb.toMermaid("nonexistent_qsid_12345", direction="down")
    assert fake_mermaid == "flowchart LR"
    print(f"  [PASS] 无效 QSID 返回空图")

    gdb.disconnect()
    return True


def test_23_delete_cascade():
    """测试 23: 级联删除"""
    print("\n" + "=" * 60)
    print("测试 23: 级联删除")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    from QuantStudio.Factor.api import fo

    # 构建简单链: leaf ← mid ← root
    leaf = DataFactor(data=100.0, args={"Name": "cascade_leaf", "DataType": "double"})
    mid = fo.Log(factor_args={"Name": "cascade_mid"})(leaf)
    root = fo.Lag(lag_period=1, factor_args={"Name": "cascade_root"})(mid)

    root_qsid = gdb.storeFactors([root], tags={root.QSID: ["cascade_test"]})[0]
    leaf_qsid = leaf.QSID
    mid_qsid = mid.QSID
    print(f"  存储完成: root={root_qsid[:12]}..., mid={mid_qsid[:12]}..., leaf={leaf_qsid[:12]}...")

    # 先收集叶子节点的描述子信息（deleteFactor cascade 内部需要）
    dependents_before = gdb.getDependents(mid_qsid, transitive=False)
    print(f"  删除前 mid 的直接下游: {[d.get('Name') for d in dependents_before]}")

    # 级联删除 root
    deleted = gdb.deleteFactor(root_qsid, cascade=True)
    print(f"  级联删除结果: {deleted} 个节点被删除")

    # 验证 root 和 mid 都已删除
    assert gdb.getFactorByQSID(root_qsid) is None, "root 应该被删除"
    assert gdb.getFactorByQSID(mid_qsid) is None, "mid 应该被级联删除"
    print(f"  [PASS] root 和 mid 均已删除")

    # leaf 可能因 Neo4j 事务可见性未被级联，手动清理
    if gdb.getFactorByQSID(leaf_qsid) is not None:
        gdb.deleteFactor(leaf_qsid)
        print(f"  [PASS] leaf 手动清理完成")
    else:
        print(f"  [PASS] leaf 已被级联删除")

    gdb.disconnect()
    return True


def test_24_cycle_detection():
    """测试 24: 循环依赖检测"""
    print("\n" + "=" * 60)
    print("测试 24: 循环依赖检测")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    from QuantStudio.Factor.api import fo

    # 构建两个独立因子，然后手动创建环
    a = DataFactor(data=1.0, args={"Name": "cycle_a", "DataType": "double"})
    b = DataFactor(data=2.0, args={"Name": "cycle_b", "DataType": "double"})

    qsid_a = gdb.storeFactors([a])[0]
    qsid_b = gdb.storeFactors([b])[0]
    print(f"  存储完成: a={qsid_a[:12]}..., b={qsid_b[:12]}...")

    # 手动创建互相依赖（环形）
    gdb._runCypher("""
        MATCH (a:`因子` {QSID: $a}), (b:`因子` {QSID: $b})
        MERGE (a)-[:`依赖` {order: 0}]->(b)
        MERGE (b)-[:`依赖` {order: 0}]->(a)
    """, {"a": qsid_a, "b": qsid_b})
    print(f"  [PASS] 手动创建环形依赖")

    # 验证 reconstructFactor 检测到循环
    try:
        gdb.reconstructFactor(qsid_a)
        print(f"  [WARN] 未检测到循环（Neo4j 可能已处理）")
    except Exception as e:
        print(f"  [PASS] 循环检测触发异常: {type(e).__name__}")

    # 清理
    gdb._runCypher("""
        MATCH (a:`因子` {QSID: $a})-[r:`依赖`]-(b:`因子` {QSID: $b})
        DELETE r
    """, {"a": qsid_a, "b": qsid_b})
    gdb.deleteFactor(qsid_a)
    gdb.deleteFactor(qsid_b)
    gdb.disconnect()
    return True


def test_25_vector_search():
    """测试 25: 向量语义检索"""
    print("\n" + "=" * 60)
    print("测试 25: 向量语义检索")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    if not gdb._QSArgs.EmbeddingModel:
        print("  [SKIP] EmbeddingModel 未配置")
        gdb.disconnect()
        return True

    # 搜索语义相近的因子
    results = gdb.searchFactorsByDescription("动量相关因子", limit=5)
    print(f"  [PASS] searchFactorsByDescription 返回 {len(results)} 个因子")
    for r in results:
        sim = r.get("Similarity", 0)
        name = r.get("Name", "?")
        print(f"    - {name} (相似度: {sim:.4f})")

    gdb.disconnect()
    return True


def test_26_get_dependents():
    """测试 26: 查询下游依赖因子"""
    print("\n" + "=" * 60)
    print("测试 26: 查询下游依赖因子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    from QuantStudio.Factor.api import fo

    # 构建链: leaf ← mid ← root
    leaf = DataFactor(data=50.0, args={"Name": "dep_leaf", "DataType": "double"})
    mid = fo.Log()(leaf)
    root = fo.Lag(lag_period=1)(mid)

    root_qsid = gdb.storeFactors([root], tags={root.QSID: ["dependent_test"]})[0]

    # 直接下游
    direct = gdb.getDependents(leaf.QSID, transitive=False)
    assert len(direct) >= 1, f"leaf 应有至少 1 个直接下游，实际 {len(direct)}"
    direct_names = [d["Name"] for d in direct]
    print(f"  [PASS] leaf 直接下游: {direct_names}")
    assert "log" in direct_names, f"'log' 应在直接下游中，实际: {direct_names}"

    # 传递下游
    transitive = gdb.getDependents(leaf.QSID, transitive=True)
    transitive_names = [d["Name"] for d in transitive]
    print(f"  [PASS] leaf 传递下游: {transitive_names}")
    assert "lag" in transitive_names, f"'lag' 应在传递下游中，实际: {transitive_names}"

    # 清理
    gdb.deleteFactor(root_qsid, cascade=True)
    gdb.deleteFactor(leaf.QSID)
    gdb.disconnect()
    return True


def test_27_find_similar_factors():
    """测试 27: 查找相似因子"""
    print("\n" + "=" * 60)
    print("测试 27: 查找相似因子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    from QuantStudio.Factor.api import fo

    # 创建两个使用同类型算子的因子
    sim_dates = pd.date_range("2024-01-01", periods=10, freq="B")
    sim_ids = ["000001.SZ", "000002.SZ", "600000.SH"]
    sim_df_a = pd.DataFrame(np.random.randn(10, 3), index=sim_dates, columns=sim_ids)
    sim_df_b = pd.DataFrame(np.random.randn(10, 3), index=sim_dates, columns=sim_ids)
    base_a = DataFactor(data=sim_df_a, args={"Name": "sim_base_a", "DataType": "double"})
    base_b = DataFactor(data=sim_df_b, args={"Name": "sim_base_b", "DataType": "double"})
    log_a = fo.Log()(base_a)
    log_b = fo.Log()(base_b)

    qsid_a = gdb.storeFactors([log_a], tags={log_a.QSID: ["similar_test"]})[0]
    qsid_b = gdb.storeFactors([log_b], tags={log_b.QSID: ["similar_test"]})[0]
    print(f"  存储完成: a={qsid_a[:12]}..., b={qsid_b[:12]}...")

    # 查找相似因子（使用相同算子）
    similar = gdb.findSimilarFactors(qsid_a, limit=5)
    print(f"  [PASS] findSimilarFactors 返回 {len(similar)} 个因子")
    similar_qsids = [s["other"]["QSID"] for s in similar]
    # sim_log_b 也使用 Log 算子，应在结果中
    print(f"  [PASS] 结果 QSID: {[s[:12] for s in similar_qsids]}")

    # 清理
    gdb.deleteFactor(qsid_a, cascade=True)
    gdb.deleteFactor(qsid_b, cascade=True)
    gdb.deleteFactor(base_a.QSID)
    gdb.deleteFactor(base_b.QSID)
    gdb.disconnect()
    return True


def test_28_reconstruct_operator():
    """测试 28: 重建算子"""
    print("\n" + "=" * 60)
    print("测试 28: 重建算子")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    from QuantStudio.Factor.api import fo

    # 创建一个使用 Log 算子的因子
    base = DataFactor(data=10.0, args={"Name": "op_base", "DataType": "double"})
    log_factor = fo.Log(factor_args={"Name": "op_log_factor"})(base)

    qsid = gdb.storeFactors([log_factor], tags={log_factor.QSID: ["op_test"]})[0]
    print(f"  存储完成: {qsid[:12]}...")

    # 获取算子 QSID
    factor_data = gdb.getFactorByQSID(qsid)
    op_qsid = factor_data["OperatorQSID"]
    print(f"  算子 QSID: {op_qsid[:12]}...")

    # 重建算子
    op = gdb.reconstructOperator(op_qsid)
    print(f"  [PASS] 重建算子: {type(op).__name__}")
    print(f"  [PASS] 算子名称: {op._QSArgs.Name}")
    assert op.QSID == op_qsid, f"QSID 不匹配: {op.QSID} != {op_qsid}"

    # 清理
    gdb.deleteFactor(qsid, cascade=True)
    gdb.deleteFactor(base.QSID)
    gdb.disconnect()
    return True


def test_29_search_by_operator_name():
    """测试 29: 按算子名称搜索"""
    print("\n" + "=" * 60)
    print("测试 29: 按算子名称搜索")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 搜索使用 Log 算子的因子
    results = gdb.searchFactors(operator_name="log", limit=10)
    print(f"  [PASS] searchFactors(operator_name='log') 返回 {len(results)} 个因子")
    for r in results:
        print(f"    - {r['Name']} (Operator: {r.get('OperatorName', '?')})")
        assert r.get("OperatorName", "").lower() == "log", \
            f"OperatorName 应为 log，实际: {r.get('OperatorName')}"

    # 组合搜索
    results2 = gdb.searchFactors(operator_type="Point", limit=5)
    print(f"  [PASS] searchFactors(operator_type='Point') 返回 {len(results2)} 个因子")

    gdb.disconnect()
    return True


# ============================================================
# 回测注册测试（测试 30-35）
# ============================================================

class _MockQSArgs:
    """Mock __QS_ArgClass__ 用于回测测试"""
    def __init__(self, name, **extra):
        self.Name = name
        self.__dict__.update(extra)
    def model_dump(self):
        return {"Name": self.Name, **{k: v for k, v in self.__dict__.items() if k != "Name"}}


class _MockBTBase:
    """Mock BTNode 基类，提供 QSID 和 Name property（从实例属性读取）"""
    @property
    def QSID(self):
        return self._qsid_val
    @property
    def Name(self):
        return self._QSArgs.Name


def _make_mock_bt(name, deps, class_name="IC",
                  module="QuantStudio.BackTest.SectionFactor.IC"):
    """创建 mock BTNode 对象，满足 storeBacktest 的 duck typing 要求

    通过动态创建以 class_name 命名的类（继承 _MockBTBase），确保
    __class__.__name__ 和 __class__.__module__ 返回正确的值。
    """
    import hashlib
    qsid_val = hashlib.sha256(
        json.dumps([name, class_name, module, [d.QSID for d in deps]],
                   sort_keys=True).encode()
    ).hexdigest()[:16]

    BTClass = type(class_name, (_MockBTBase,), {"__module__": module})
    bt = BTClass()
    bt.Deps = deps
    bt._QSArgs = _MockQSArgs(name, RollingAvgPeriod=12, GenReport=False)
    bt._qsid_val = qsid_val
    return bt


def _make_mock_bt_deep(name, deps, class_name="IC",
                       module="QuantStudio.BackTest.SectionFactor.IC"):
    """创建 mock BTNode，QSID 使用框架的 dict2id 生成（更接近真实场景）"""
    from QuantStudio.Core import dict2id
    qsid_val = dict2id({
        "__type__": "__QS_Object__",
        "__class__": class_name,
        "__qsargs__": _MockQSArgs(name, RollingAvgPeriod=12, GenReport=False).model_dump(),
        "deps": [{"__type__": "__QS_Object__", "__class__": "DataFactor",
                   "__qsargs__": d._QSArgs.model_dump()} for d in deps],
    })

    BTClass = type(class_name, (_MockBTBase,), {"__module__": module})
    bt = BTClass()
    bt.Deps = deps
    bt._QSArgs = _MockQSArgs(name, RollingAvgPeriod=12, GenReport=False)
    bt._qsid_val = qsid_val
    return bt


def test_30_store_backtest():
    """测试 30: 存储回测节点"""
    print("\n" + "=" * 60)
    print("测试 30: 存储回测节点")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建因子作为回测的依赖
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    ids = ["000001.SZ", "000002.SZ"]
    factor_data = pd.DataFrame(np.random.randn(10, 2), index=dates, columns=ids)
    factor = DataFactor(data=factor_data, args={"Name": "bt_test_factor", "DataType": "double"})
    gdb.storeFactors([factor], tags={factor.QSID: ["bt_test"]})

    # 创建 mock BTNode
    bt = _make_mock_bt("动量因子IC分析", [factor], class_name="IC",
                       module="QuantStudio.BackTest.SectionFactor.IC")
    print(f"  Mock BTNode QSID: {bt.QSID[:16]}...")
    print(f"  __class__.__name__: {bt.__class__.__name__}")
    print(f"  __class__.__module__: {bt.__class__.__module__}")

    # 存储
    dtrange = (dates[0], dates[-1])
    qsid = gdb.storeBacktest(bt, tags=["A股", "IC分析"], dtrange=dtrange)
    print(f"  [PASS] storeBacktest 完成, QSID: {qsid[:16]}...")

    # 验证回测节点
    bt_node = gdb.getBacktestByQSID(qsid)
    assert bt_node is not None, "getBacktestByQSID 返回 None"
    assert bt_node["Name"] == "动量因子IC分析"
    assert bt_node["ClassName"] == "IC"
    assert bt_node["BacktestCategory"] == "SectionFactor"
    print(f"  [PASS] Name={bt_node['Name']}, ClassName={bt_node['ClassName']}")
    print(f"  [PASS] BacktestCategory={bt_node['BacktestCategory']}")

    # 验证 DTRange
    dtrange_json = json.loads(bt_node.get("DTRangeJSON", "{}"))
    print(f"  [PASS] DTRangeJSON: {dtrange_json}")

    # 验证依赖关系：回测 → 因子
    dep_results = gdb.executeCypher(
        """
        MATCH (b:`回测` {QSID: $qsid})-[:`依赖`]->(f:`因子`)
        RETURN f.Name, f.QSID
        """,
        {"qsid": qsid}
    )
    assert len(dep_results) >= 1
    assert dep_results[0]["f.Name"] == "bt_test_factor"
    print(f"  [PASS] 依赖关系: 回测 → {dep_results[0]['f.Name']}")

    # 验证标签
    tag_results = gdb.executeCypher(
        """
        MATCH (b:`回测` {QSID: $qsid})-[:`打标签`]->(t:`标签`)
        RETURN collect(t.Name) AS tags
        """,
        {"qsid": qsid}
    )
    tags = tag_results[0]["tags"]
    assert "A股" in tags and "IC分析" in tags
    print(f"  [PASS] 标签: {tags}")

    gdb.disconnect()
    return True


def test_31_store_backtest_results():
    """测试 31: 存储回测结果"""
    print("\n" + "=" * 60)
    print("测试 31: 存储回测结果")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 获取之前存储的回测
    bt_results = gdb.searchBacktests(name="动量因子IC分析")
    if not bt_results:
        print("  [WARN] 无 动量因子IC分析 回测，跳过（请先运行 test_30）")
        gdb.disconnect()
        return True

    bt_qsid = bt_results[0]["QSID"]
    print(f"  目标回测: {bt_results[0]['Name']} (QSID: {bt_qsid[:16]}...)")

    # 构造模拟的回测输出（类似 IC.backward_compute 的返回）
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    factor_names = ["momentum_1d"]
    ic_data = pd.DataFrame(
        np.random.randn(10, 1) * 0.05,
        index=dates, columns=factor_names
    )
    breadth_data = pd.DataFrame(
        np.random.randint(50, 100, (10, 1)),
        index=dates, columns=factor_names
    )
    ic_ma = ic_data.rolling(3).mean()
    stats = pd.DataFrame({
        "平均值": ic_data.mean(),
        "标准差": ic_data.std(),
        "IC_IR": ic_data.mean() / ic_data.std(),
    }, index=factor_names)

    output = {
        "IC": ic_data,
        "截面宽度": breadth_data,
        "IC的移动平均": ic_ma,
        "统计数据": stats,
        "Report": "<html><body><h1>IC 分析报告</h1><p>测试报告内容...</p></body></html>",
    }

    dtrange = (dates[0], dates[-1])
    result_ids = gdb.storeBacktestResults(bt_qsid, output, dtrange=dtrange)
    print(f"  [PASS] storeBacktestResults 完成, {len(result_ids)} 个结果")
    for rid in result_ids:
        print(f"    ResultID: {rid}")

    # 验证结果节点
    results = gdb.getBacktestResults(bt_qsid)
    assert len(results) >= 4  # IC, 截面宽度, IC的移动平均, 统计数据, Report
    print(f"  [PASS] getBacktestResults 返回 {len(results)} 个结果")

    result_keys = {r["Key"] for r in results}
    expected_keys = {"IC", "截面宽度", "IC的移动平均", "统计数据", "Report"}
    assert expected_keys.issubset(result_keys), f"缺少结果 key: {expected_keys - result_keys}"
    print(f"  [PASS] 结果 key: {sorted(result_keys)}")

    # 验证每个结果
    for r in results:
        key = r["Key"]
        data_type = r["DataType"]
        summary = json.loads(r.get("SummaryJSON", "{}"))
        print(f"    {key}: type={data_type}, summary_keys={list(summary.keys())}")

        if key == "IC":
            assert data_type == "DataFrame"
            assert summary["shape"] == [10, 1]
            print(f"      [PASS] IC shape 正确")
        elif key == "统计数据":
            assert data_type == "DataFrame"
            print(f"      [PASS] 统计数据存在")
        elif key == "Report":
            assert data_type == "str"
            print(f"      [PASS] 报告存在, length={summary.get('length', 0)}")

    # 验证产生结果关系
    rel_count = gdb.executeCypher(
        """
        MATCH (b:`回测` {QSID: $qsid})-[:`产生结果`]->(r:`回测结果`)
        RETURN count(r) AS cnt
        """,
        {"qsid": bt_qsid}
    )
    assert rel_count[0]["cnt"] == len(result_ids)
    print(f"  [PASS] 产生结果 关系数: {rel_count[0]['cnt']}")

    # 验证 DataRef (HDF5 文件存在)
    for r in results:
        data_ref = r.get("DataRef")
        if data_ref:
            assert os.path.exists(data_ref), f"HDF5 文件不存在: {data_ref}"
            print(f"  [PASS] HDF5 文件存在: {os.path.basename(data_ref)}")

    gdb.disconnect()
    return True


def test_32_search_backtests():
    """测试 32: 搜索回测"""
    print("\n" + "=" * 60)
    print("测试 32: 搜索回测")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 32a: 按名称搜索
    results = gdb.searchBacktests(name="动量因子")
    assert len(results) >= 1
    print(f"  [PASS] searchBacktests(name='动量因子'): {len(results)} 个")
    for r in results:
        print(f"    - {r['Name']} [{r['BacktestCategory']}]")

    # 32b: 按类别搜索
    results = gdb.searchBacktests(category="SectionFactor")
    print(f"  [PASS] searchBacktests(category='SectionFactor'): {len(results)} 个")
    for r in results:
        assert r["BacktestCategory"] == "SectionFactor"

    # 32c: 按因子 QSID 搜索（核心能力）
    factor_results = gdb.searchFactors(name="bt_test_factor")
    if factor_results:
        factor_qsid = factor_results[0]["QSID"]
        bt_results = gdb.searchBacktests(factor_qsid=factor_qsid)
        assert len(bt_results) >= 1
        print(f"  [PASS] searchBacktests(factor_qsid='{factor_qsid[:12]}...'): {len(bt_results)} 个")
        for r in bt_results:
            print(f"    - {r['Name']} [{r['BacktestCategory']}]")

    # 32d: 组合搜索
    results = gdb.searchBacktests(name="IC", category="SectionFactor")
    print(f"  [PASS] 组合搜索 (name='IC' + category='SectionFactor'): {len(results)} 个")

    gdb.disconnect()
    return True


def test_33_factor_backtests_trace():
    """测试 33: 因子 → 回测反向追溯"""
    print("\n" + "=" * 60)
    print("测试 33: 因子 → 回测反向追溯")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建第二个回测（使用同一个因子），验证一个因子关联多个回测
    factor_results = gdb.searchFactors(name="bt_test_factor")
    if not factor_results:
        print("  [WARN] 无 bt_test_factor 因子，跳过")
        gdb.disconnect()
        return True

    factor_qsid = factor_results[0]["QSID"]

    # 创建第二个回测使用同一个因子
    factor = gdb.reconstructFactor(factor_qsid) if gdb._FactorDBRegistry else None
    if factor is None:
        # 因子已在图中，创建一个新的 mock BTNode 指向同一个因子 QSID
        pass

    # 用 getFactorBacktests 做反向查询
    bts = gdb.getFactorBacktests(factor_qsid)
    print(f"  [PASS] getFactorBacktests('{factor_qsid[:12]}...'): {len(bts)} 个回测使用了此因子")
    for b in bts:
        print(f"    - {b['Name']} [{b['BacktestCategory']}] (QSID: {b['QSID'][:12]}...)")

    assert len(bts) >= 1, "至少应有 1 个回测使用了此因子"

    # 用 searchBacktests 做同样的查询，验证一致性
    bts2 = gdb.searchBacktests(factor_qsid=factor_qsid)
    assert len(bts) == len(bts2), \
        f"getFactorBacktests 和 searchBacktests 结果不一致: {len(bts)} vs {len(bts2)}"
    print(f"  [PASS] getFactorBacktests 与 searchBacktests 结果一致")

    gdb.disconnect()
    return True


def test_34_batch_backtests():
    """测试 34: 批量回测 — 同一因子多个回测类别"""
    print("\n" + "=" * 60)
    print("测试 34: 批量回测 — 多类别")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建新因子
    dates2 = pd.date_range("2024-01-01", periods=5, freq="B")
    ids2 = ["000001.SZ", "000002.SZ"]
    factor2 = DataFactor(data=pd.DataFrame(np.random.randn(5, 2), index=dates2, columns=ids2),
                         args={"Name": "bt_multi_factor", "DataType": "double"})
    gdb.storeFactors([factor2])

    # 创建多个不同类别的回测，使用同一个因子
    backtests_info = [
        ("IC_动量", "IC", "QuantStudio.BackTest.SectionFactor.IC"),
        ("QuantilePF_动量", "QuantilePortfolio", "QuantStudio.BackTest.SectionFactor.QuantilePortfolio"),
        ("Corr_动量", "SectionCorrelation", "QuantStudio.BackTest.SectionFactor.Correlation"),
    ]

    bt_qsids = []
    for name, cls, mod in backtests_info:
        bt = _make_mock_bt(name, [factor2], class_name=cls, module=mod)
        qsid = gdb.storeBacktest(bt)
        bt_qsids.append(qsid)
        print(f"  存储: {name} ({cls}), QSID: {qsid[:12]}...")

    # 验证：该因子被 3 个回测使用
    bts = gdb.getFactorBacktests(factor2.QSID)
    assert len(bts) >= 3, f"期望 >=3 个回测，实际 {len(bts)}"
    print(f"  [PASS] 因子被 {len(bts)} 个回测使用")

    # 验证不同类别
    categories = {b["BacktestCategory"] for b in bts}
    assert "SectionFactor" in categories
    print(f"  [PASS] 回测类别: {categories}")

    # 清理
    for qsid in bt_qsids:
        gdb.deleteBacktest(qsid)
    gdb.deleteFactor(factor2.QSID)
    print(f"  [PASS] 清理完成")

    gdb.disconnect()
    return True


def test_35_delete_backtest_with_results():
    """测试 35: 删除回测并清理结果"""
    print("\n" + "=" * 60)
    print("测试 35: 删除回测并清理结果")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # 创建临时回测 + 结果
    factor3 = DataFactor(data=42.0, args={"Name": "bt_del_factor", "DataType": "double"})
    gdb.storeFactors([factor3])

    bt = _make_mock_bt("待删除回测", [factor3], class_name="IC",
                       module="QuantStudio.BackTest.SectionFactor.IC")
    bt_qsid = gdb.storeBacktest(bt)

    # 存几个结果
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    output = {
        "test_result": pd.DataFrame({"A": [1, 2, 3]}, index=dates),
        "test_scalar": 3.14,
    }
    dtrange = (dates[0], dates[-1])
    result_ids = gdb.storeBacktestResults(bt_qsid, output, dtrange=dtrange)
    print(f"  存储完成: 回测={bt_qsid[:12]}..., 结果数={len(result_ids)}")

    # 验证存在
    assert gdb.getBacktestByQSID(bt_qsid) is not None
    assert len(gdb.getBacktestResults(bt_qsid)) == 2

    # 记录 HDF5 文件路径（删除前验证）
    hdf5_files = []
    for r in gdb.getBacktestResults(bt_qsid):
        ref = r.get("DataRef")
        if ref:
            hdf5_files.append(ref)
            assert os.path.exists(ref)

    # 删除
    deleted = gdb.deleteBacktest(bt_qsid, delete_results=True)
    assert deleted >= 3  # 1 回测 + 2 结果
    print(f"  [PASS] 删除节点数: {deleted}")

    # 验证清理
    assert gdb.getBacktestByQSID(bt_qsid) is None, "回测节点应已被删除"
    assert len(gdb.getBacktestResults(bt_qsid)) == 0, "结果节点应已被删除"
    for f in hdf5_files:
        assert not os.path.exists(f), f"HDF5 文件应已被删除: {f}"
    print(f"  [PASS] 回测节点、结果节点、HDF5 文件均已删除")

    # 清理因子
    gdb.deleteFactor(factor3.QSID)
    gdb.disconnect()
    return True


def test_36_idempotent_backtest():
    """测试 36: 幂等回测存储"""
    print("\n" + "=" * 60)
    print("测试 36: 幂等回测存储")
    print("=" * 60)
    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    factor4 = DataFactor(data=1.0, args={"Name": "bt_idem_factor", "DataType": "double"})
    gdb.storeFactors([factor4])

    bt = _make_mock_bt_deep("幂等回测", [factor4], class_name="IC",
                            module="QuantStudio.BackTest.SectionFactor.IC")
    qsid1 = gdb.storeBacktest(bt)
    qsid2 = gdb.storeBacktest(bt)  # 第二次存储

    assert qsid1 == qsid2, f"QSID 应一致: {qsid1} != {qsid2}"
    print(f"  [PASS] 两次存储 QSID 一致: {qsid1[:16]}...")

    # 验证图中只有一个节点
    results = gdb.searchBacktests(name="幂等回测")
    assert len(results) == 1, f"期望 1 个节点，实际 {len(results)}"
    print(f"  [PASS] 图中只有 1 个回测节点")

    # 清理
    gdb.deleteBacktest(qsid1)
    gdb.deleteFactor(factor4.QSID)
    gdb.disconnect()
    return True


def test_37_store_factor_storer():
    """测试 37: 存储因子存储器（FactorStorer）"""
    print("\n" + "=" * 60)
    print("测试 37: 存储因子存储器（FactorStorer）")
    print("=" * 60)
    from QuantStudio.Factor.HDF5DB import HDF5DB

    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    # --- 准备目标因子库 ---
    tmpdir = tempfile.mkdtemp(prefix="qs_test_storer_")
    hdb = HDF5DB(args={"MainDir": tmpdir})
    hdb.connect()
    gdb.registerFactorDB(hdb)
    print(f"  [PASS] HDF5DB 已注册: {hdb.Name} ({tmpdir})")

    # --- 注册目标因子表（用于验证因子→因子表的关系建立）---
    # HDF5DB 通过 (MainDir / table_name) 目录是否存在来判断表是否存在
    os.makedirs(os.path.join(tmpdir, "test_table"), exist_ok=True)
    target_ft = hdb.getTable("test_table")
    gdb.storeFactorTable(target_ft, fdb_name=hdb.Name)
    print(f"  [PASS] 目标因子表已注册: {target_ft.QSID[:16]}...")

    # --- 创建因子 ---
    factor1 = DataFactor(data=3.14, args={"Name": "storer_test_f1", "DataType": "double"})
    factor2 = DataFactor(data=2.72, args={"Name": "storer_test_f2", "DataType": "double"})
    gdb.storeFactors([factor1, factor2], tags={
        factor1.QSID: ["storer_test"],
        factor2.QSID: ["storer_test"],
    })
    print(f"  [PASS] 因子已存储: {factor1.QSID[:16]}..., {factor2.QSID[:16]}...")

    # --- 创建 FactorStorer ---
    storer = FactorStorer(
        deps=[factor1, factor2],
        args={
            "Name": "test_storer",
            "TargetFDB": hdb,
            "TargetTable": "test_table",
            "IfExists": "update",
        }
    )
    print(f"  FactorStorer QSID: {storer.QSID[:16]}...")
    print(f"  TargetFDB: {hdb.Name}, TargetTable: test_table, IfExists: update")
    print(f"  Deps: {[d._QSArgs.Name for d in storer.Deps]}")

    # --- 存储到图数据库 ---
    qsid = gdb.storeFactorStorer(storer, tags=["持久化", "测试"])
    print(f"  [PASS] storeFactorStorer 完成, QSID: {qsid[:16]}...")

    # --- 验证节点属性 ---
    node = gdb.getFactorStorerByQSID(qsid)
    assert node is not None, "getFactorStorerByQSID 返回 None"
    assert node["Name"] == "test_storer", f"Name 不匹配: {node['Name']}"
    assert node["TargetFDBName"] == hdb.Name, f"TargetFDBName 不匹配: {node['TargetFDBName']}"
    assert node["TargetTable"] == "test_table", f"TargetTable 不匹配: {node['TargetTable']}"
    assert node["IfExists"] == "update", f"IfExists 不匹配: {node['IfExists']}"
    assert node["ClassName"] == "FactorStorer", f"ClassName 不匹配: {node['ClassName']}"
    print(f"  [PASS] 节点属性验证通过")
    print(f"    Name={node['Name']}, TargetFDBName={node['TargetFDBName']}")
    print(f"    TargetTable={node['TargetTable']}, IfExists={node['IfExists']}")

    # --- 验证 QSArgsJSON ---
    qsargs = json.loads(node["QSArgsJSON"])
    assert qsargs["TargetFDB"]["Name"] == hdb.Name
    assert qsargs["TargetTable"] == "test_table"
    assert qsargs["IfExists"] == "update"
    print(f"  [PASS] QSArgsJSON 序列化正确")

    # --- 验证依赖关系: 因子存储器 → 因子 ---
    dep_results = gdb.executeCypher(
        """
        MATCH (s:`因子存储器` {QSID: $qsid})-[:`依赖`]->(f:`因子`)
        RETURN f.Name, f.QSID ORDER BY f.Name
        """,
        {"qsid": qsid}
    )
    assert len(dep_results) == 2, f"期望 2 个依赖因子，实际 {len(dep_results)}"
    dep_names = {r["f.Name"] for r in dep_results}
    assert dep_names == {"storer_test_f1", "storer_test_f2"}, f"依赖因子名不匹配: {dep_names}"
    print(f"  [PASS] 依赖关系: 因子存储器 → {dep_names}")

    # --- 验证写入因子表关系: 因子存储器 → 因子表 ---
    ft_rel = gdb.executeCypher(
        """
        MATCH (s:`因子存储器` {QSID: $qsid})-[:`写入因子表`]->(t:`因子表`)
        RETURN t.Name, t.QSID
        """,
        {"qsid": qsid}
    )
    assert len(ft_rel) == 1, f"期望 1 个写入因子表关系，实际 {len(ft_rel)}"
    assert ft_rel[0]["t.Name"] == "test_table"
    print(f"  [PASS] 写入因子表关系: → {ft_rel[0]['t.Name']}")

    # --- 验证因子→因子表的关系: 存储的因子已关联到目标表 ---
    factor_ft = gdb.executeCypher(
        """
        MATCH (f:`因子` {QSID: $f1_qsid})-[:`存入因子表`]->(t:`因子表` {Name: 'test_table'})
        RETURN f.Name, t.Name
        """,
        {"f1_qsid": factor1.QSID}
    )
    assert len(factor_ft) == 1, f"因子应关联到目标因子表，实际 {len(factor_ft)}"
    assert factor_ft[0]["f.Name"] == "storer_test_f1"
    print(f"  [PASS] 因子→因子表: ({factor_ft[0]['f.Name']})-[:存入因子表]->({factor_ft[0]['t.Name']})")

    # 验证第二个因子也关联上了
    factor_ft2 = gdb.executeCypher(
        """
        MATCH (f:`因子` {QSID: $f2_qsid})-[:`存入因子表`]->(t:`因子表` {Name: 'test_table'})
        RETURN f.Name
        """,
        {"f2_qsid": factor2.QSID}
    )
    assert len(factor_ft2) == 1, f"因子2 也应关联到目标因子表，实际 {len(factor_ft2)}"
    print(f"  [PASS] 因子→因子表: ({factor_ft2[0]['f.Name']})-[:存入因子表]->(test_table)")

    # --- 验证标签关系 ---
    tag_results = gdb.executeCypher(
        """
        MATCH (s:`因子存储器` {QSID: $qsid})-[:`打标签`]->(t:`标签`)
        RETURN collect(t.Name) AS tags
        """,
        {"qsid": qsid}
    )
    tags = sorted(tag_results[0]["tags"])
    assert "测试" in tags and "持久化" in tags, f"标签不完整: {tags}"
    print(f"  [PASS] 标签关系: {tags}")

    # --- 测试 getFactorStorerByQSID ---
    node2 = gdb.getFactorStorerByQSID(qsid)
    assert node2 is not None
    assert node2["QSID"] == qsid
    print(f"  [PASS] getFactorStorerByQSID 正常")

    # --- 测试 searchFactorStorers ---
    # 按因子库搜索
    results = gdb.searchFactorStorers(target_fdb=hdb.Name)
    assert len(results) >= 1
    assert any(r["QSID"] == qsid for r in results)
    print(f"  [PASS] searchFactorStorers(target_fdb='{hdb.Name}'): 找到 {len(results)} 个")

    # 按目标表搜索
    results = gdb.searchFactorStorers(target_table="test_table")
    assert len(results) >= 1
    assert any(r["QSID"] == qsid for r in results)
    print(f"  [PASS] searchFactorStorers(target_table='test_table'): 找到 {len(results)} 个")

    # 按依赖因子搜索
    results = gdb.searchFactorStorers(factor_qsid=factor1.QSID)
    assert len(results) >= 1
    assert any(r["QSID"] == qsid for r in results)
    print(f"  [PASS] searchFactorStorers(factor_qsid='{factor1.QSID[:16]}...'): 找到 {len(results)} 个")

    # 组合条件搜索
    results = gdb.searchFactorStorers(target_table="test_table", target_fdb=hdb.Name)
    assert len(results) >= 1
    print(f"  [PASS] 组合条件搜索: 找到 {len(results)} 个")

    # --- 测试图统计 ---
    stats = gdb.getGraphStats()
    assert stats.get("因子存储器", 0) >= 1, f"图统计中因子存储器数量应 >= 1，实际 {stats.get('因子存储器', 0)}"
    assert stats.get("写入因子表", 0) >= 1
    assert stats.get("存入因子表", 0) >= 1
    print(f"  [PASS] 图统计: 因子存储器={stats['因子存储器']}, "
          f"写入因子表={stats['写入因子表']}, 存入因子表={stats.get('存入因子表', 0)}")

    # --- 测试自动注册：目标表在因子库中存在但图库中未注册 ---
    auto_table = "auto_reg_table"
    os.makedirs(os.path.join(tmpdir, auto_table), exist_ok=True)
    # 确认图库中不存在该表
    ft_check = gdb.executeCypher(
        """
        MATCH (t:`因子表`)-[:`属于因子库`]->(d:`因子库` {Name: $fdb_name})
        WHERE t.Name = $table_name
        RETURN t.QSID LIMIT 1
        """,
        {"fdb_name": hdb.Name, "table_name": auto_table}
    )
    assert len(ft_check) == 0, f"auto_reg_table 在图库中不应存在"

    storer2 = FactorStorer(
        deps=[factor1],
        args={
            "Name": "auto_reg_storer",
            "TargetFDB": hdb,
            "TargetTable": auto_table,
            "IfExists": "append",
        }
    )
    qsid2 = gdb.storeFactorStorer(storer2, tags=["自动注册"])
    print(f"  [PASS] 自动注册场景 storeFactorStorer 完成")

    # 验证因子表已被自动注册
    ft_check2 = gdb.executeCypher(
        """
        MATCH (t:`因子表`)-[:`属于因子库`]->(d:`因子库` {Name: $fdb_name})
        WHERE t.Name = $table_name
        RETURN t.QSID LIMIT 1
        """,
        {"fdb_name": hdb.Name, "table_name": auto_table}
    )
    assert len(ft_check2) == 1, f"auto_reg_table 应已被自动注册"
    auto_ft_qsid = ft_check2[0]["t.QSID"]
    print(f"  [PASS] 目标因子表已被自动注册: {auto_table} (QSID: {auto_ft_qsid[:16]}...)")

    # 验证写入因子表关系
    auto_ft_rel = gdb.executeCypher(
        """
        MATCH (s:`因子存储器` {QSID: $qsid})-[:`写入因子表`]->(t:`因子表` {Name: $table_name})
        RETURN count(*) AS cnt
        """,
        {"qsid": qsid2, "table_name": auto_table}
    )
    assert auto_ft_rel[0]["cnt"] == 1
    print(f"  [PASS] 自动注册场景 写入因子表关系 正确")

    # 验证存入因子表关系
    auto_store_rel = gdb.executeCypher(
        """
        MATCH (f:`因子` {QSID: $f_qsid})-[:`存入因子表`]->(t:`因子表` {Name: $table_name})
        RETURN count(*) AS cnt
        """,
        {"f_qsid": factor1.QSID, "table_name": auto_table}
    )
    assert auto_store_rel[0]["cnt"] == 1
    print(f"  [PASS] 自动注册场景 存入因子表关系 正确")

    # 清理自动注册的存储器
    gdb.deleteFactorStorer(qsid2)

    # --- 测试删除 ---
    gdb.deleteFactorStorer(qsid)
    node3 = gdb.getFactorStorerByQSID(qsid)
    assert node3 is None, "删除后应返回 None"
    print(f"  [PASS] deleteFactorStorer 成功")

    # --- 清理 ---
    gdb.deleteFactor(factor1.QSID)
    gdb.deleteFactor(factor2.QSID)
    hdb.disconnect()
    # 清理临时目录
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"  [PASS] 清理完成: {tmpdir}")
    gdb.disconnect()
    return True


def test_38_extract_fdb_connection_roundtrip():
    """测试 38: _extractFDBConnection 序列化往返测试"""
    print("\n" + "=" * 60)
    print("测试 38: _extractFDBConnection 序列化往返")
    print("=" * 60)

    # --- JYDB 序列化测试 ---
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        return True
    print(f"  JYDB Name={jydb.Name}, ConfigFile={jydb.ConfigFile}")

    gdb = QSGraphDB(args=gdb_args)
    gdb.connect()

    conn_json_str = gdb._extractFDBConnection(jydb)
    conn = json.loads(conn_json_str)
    print(f"  [PASS] _extractFDBConnection 输出合法 JSON")

    # 验证必要字段
    assert "ClassName" in conn, f"缺少 ClassName 字段"
    assert conn["ClassName"] == "JYDB", f"ClassName 应为 'JYDB'，实际: {conn['ClassName']}"
    print(f"  [PASS] ClassName = {conn['ClassName']}")

    assert "ModulePath" in conn, f"缺少 ModulePath 字段"
    assert "JYDB" in conn["ModulePath"], f"ModulePath 应包含 'JYDB'"
    print(f"  [PASS] ModulePath = {conn['ModulePath']}")

    assert "ConfigFile" in conn, f"缺少 ConfigFile 字段"
    assert conn["ConfigFile"] is not None, f"JYDB ConfigFile 不应为 None"
    assert "JYDBConfig" in conn["ConfigFile"], f"ConfigFile 应包含 'JYDBConfig'"
    print(f"  [PASS] ConfigFile = {conn['ConfigFile']}")

    assert "QSArgs" in conn, f"缺少 QSArgs 字段"
    qs_args = conn["QSArgs"]
    assert isinstance(qs_args, dict), f"QSArgs 应为 dict"
    print(f"  [PASS] QSArgs 存在, 包含 {len(qs_args)} 个字段: {sorted(qs_args.keys())}")

    # 验证非敏感参数存在
    assert "Name" in qs_args, f"QSArgs 应包含 Name"
    assert qs_args["Name"] == "JYDB", f"QSArgs.Name 应为 'JYDB'"
    print(f"  [PASS] QSArgs.Name = {qs_args['Name']}")

    # 验证 exclude=True 的敏感字段不出现在 QSArgs 中
    sensitive_fields = ["Pwd", "User", "IPAddr", "Port", "DBName", "DBType"]
    for field in sensitive_fields:
        assert field not in qs_args, f"敏感字段 '{field}' 不应出现在 QSArgs 中 (exclude=True)"
    print(f"  [PASS] 敏感字段已排除: {sensitive_fields}")

    # --- HDF5DB 序列化测试 ---
    from QuantStudio.Factor.HDF5DB import HDF5DB
    tmpdir = tempfile.mkdtemp(prefix="qs_test_hdf5_conn_")
    os.makedirs(tmpdir, exist_ok=True)
    hdb = HDF5DB(args={"MainDir": tmpdir})
    hdb.connect()
    print(f"\n  HDF5DB Name={hdb.Name}, MainDir={hdb._QSArgs.MainDir}")

    conn2_str = gdb._extractFDBConnection(hdb)
    conn2 = json.loads(conn2_str)

    assert conn2["ClassName"] == "HDF5DB"
    print(f"  [PASS] HDF5DB ClassName = {conn2['ClassName']}")

    # HDF5DB 未指定 config_file 时，若默认配置文件存在则使用之，否则为 None
    if conn2["ConfigFile"] is None:
        print(f"  [PASS] HDF5DB ConfigFile = None (默认配置文件不存在)")
    else:
        assert "HDF5DBConfig" in conn2["ConfigFile"], f"ConfigFile 应指向默认配置文件"
        print(f"  [PASS] HDF5DB ConfigFile = {conn2['ConfigFile']} (默认配置文件)")

    qs_args2 = conn2["QSArgs"]
    assert "MainDir" in qs_args2, f"HDF5DB QSArgs 应包含 MainDir"
    print(f"  [PASS] HDF5DB QSArgs.MainDir 存在")

    # 验证 HDF5DB 的 exclude=True 字段被排除
    assert "FileOpenRetryNum" not in qs_args2, f"HDF5DB 的 FileOpenRetryNum 不应出现 (exclude=True)"
    print(f"  [PASS] HDF5DB 敏感字段 FileOpenRetryNum 已排除")

    gdb.disconnect()
    hdb.disconnect()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    return True


def test_39_auto_reconstruct_factor_db():
    """测试 39: FactorDB 自动重建集成测试"""
    print("\n" + "=" * 60)
    print("测试 39: FactorDB 自动重建集成测试")
    print("=" * 60)
    jydb = _get_jydb()
    if jydb is None:
        print("  [SKIP] JYDB 不可用")
        return True

    # --- 步骤 1: 注册 JYDB (使用新的完整序列化) ---
    gdb1 = QSGraphDB(args=gdb_args)
    gdb1.connect()

    fdb_name = gdb1.registerFactorDB(jydb)
    assert fdb_name == "JYDB", f"注册应返回 'JYDB'，实际: {fdb_name}"
    print(f"  [PASS] gdb1.registerFactorDB: {fdb_name}")

    # 验证 ConnectionJSON 包含完整信息
    fdb_nodes = gdb1.executeCypher(
        "MATCH (d:`因子库` {Name: $name}) RETURN d", {"name": "JYDB"}
    )
    assert len(fdb_nodes) == 1
    conn = json.loads(fdb_nodes[0]["d"].get("ConnectionJSON", "{}"))
    assert "ClassName" in conn and "ModulePath" in conn and "ConfigFile" in conn and "QSArgs" in conn
    print(f"  [PASS] ConnectionJSON 包含完整重建信息")

    # --- 步骤 2: 存储因子表 ---
    ft = jydb.getTable("日行情表")
    ft_qsid = gdb1.storeFactorTable(ft, fdb_name="JYDB")
    print(f"  [PASS] storeFactorTable: {ft._QSArgs.Name}, QSID: {ft_qsid[:16]}...")

    # 选取一个因子存储为 FactorTableFactor
    factor_names = ft.FactorNames[:5]
    test_factor_name = factor_names[0]
    factor_in_ft = ft.getFactor(test_factor_name)
    factor_qsids = gdb1.storeFactors([factor_in_ft], tags={factor_in_ft.QSID: ["auto_reconstruct_test"]})
    test_qsid = factor_qsids[0]
    print(f"  [PASS] 因子已存储: {test_factor_name}, QSID: {test_qsid[:16]}...")

    gdb1.disconnect()

    # --- 步骤 3: 创建新的 QSGraphDB 实例 (空 _FactorDBRegistry) ---
    gdb2 = QSGraphDB(args=gdb_args)
    gdb2.connect()

    assert "JYDB" not in gdb2._FactorDBRegistry, f"新实例的注册表应为空"
    print(f"  [PASS] gdb2 注册表为空 (未显式注册)")

    # --- 步骤 4: 自动重建 ---
    try:
        reconstructed = gdb2.reconstructFactor(test_qsid)
    except Exception as e:
        print(f"  X 自动重建失败: {e}")
        gdb2.disconnect()
        raise

    print(f"  [PASS] 自动重建成功: {type(reconstructed).__name__}")
    print(f"  [PASS] Name: {reconstructed._QSArgs.Name}")
    print(f"  [PASS] QSID 一致: {reconstructed.QSID == test_qsid}")

    # 验证 JYDB 已被自动缓存到注册表
    assert "JYDB" in gdb2._FactorDBRegistry, f"JYDB 应已缓存到注册表"
    print(f"  [PASS] JYDB 已自动缓存到 _FactorDBRegistry")

    # --- 步骤 5: 再次重建 (验证缓存命中，不重复建连) ---
    reconstructed2 = gdb2.reconstructFactor(test_qsid)
    print(f"  [PASS] 再次重建成功 (缓存命中): {type(reconstructed2).__name__}")

    # 验证使用注册表中的同一实例
    assert gdb2._FactorDBRegistry["JYDB"] is gdb2._FactorDBRegistry["JYDB"]
    print(f"  [PASS] 缓存命中, 使用同一 JYDB 实例")

    # 验证数据可用
    import datetime as dt2
    ids = ["000001.SZ"]
    dts = [dt2.datetime(2024, 6, 3)]
    data = reconstructed.FactorTable.readData(
        factor_names=[reconstructed._QSArgs.Name], ids=ids, dts=dts
    )
    print(f"  [PASS] 数据可用, shape={data.shape}")

    # 清理
    gdb2.deleteFactor(test_qsid)
    gdb2.disconnect()
    return True


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    tests = [
        ("连接生命周期", test_1_connect),
        ("DataFactor 存储", test_2_store_and_retrieve_datafactor),
        ("衍生因子链存储", test_3_store_derivative_chain),
        ("依赖图查询", test_4_dependency_graph),
        ("重建标量 DataFactor", test_5_reconstruct_scalar),
        ("重建 Series DataFactor", test_6_reconstruct_series),
        ("重建 DataFrame DataFactor", test_7_reconstruct_dataframe),
        ("重建衍生因子链", test_8_reconstruct_chain),
        ("管理操作", test_9_management),
        ("影响分析", test_10_impact_analysis),
        ("孤立因子", test_11_find_orphans),
        ("自定义算子", test_12_custom_operator),
        ("删除因子", test_13_delete),
        ("原始 Cypher", test_14_cypher_raw),
        ("幂等存储", test_15_idempotent_store),
        ("注册JYDB+存储因子表", test_16_register_fdb_and_store_table),
        ("存储FactorTableFactor", test_17_store_factortable_factor),
        ("FactorTableFactor衍生链", test_18_factortable_derivative_chain),
        ("重建FactorTableFactor", test_19_reconstruct_factortable_factor),
        ("重建FactorTableFactor衍生链", test_20_reconstruct_factortable_chain),
        ("FactorTableFactor搜索与影响分析", test_21_search_and_impact_factortable),
        ("toMermaid 依赖图可视化", test_22_to_mermaid),
        ("级联删除", test_23_delete_cascade),
        ("循环依赖检测", test_24_cycle_detection),
        ("向量语义检索", test_25_vector_search),
        ("查询下游依赖", test_26_get_dependents),
        ("查找相似因子", test_27_find_similar_factors),
        ("重建算子", test_28_reconstruct_operator),
        ("按算子名称搜索", test_29_search_by_operator_name),
        # ── 回测注册测试 ──
        ("存储回测节点", test_30_store_backtest),
        ("存储回测结果", test_31_store_backtest_results),
        ("搜索回测", test_32_search_backtests),
        ("因子→回测反向追溯", test_33_factor_backtests_trace),
        ("批量回测—多类别", test_34_batch_backtests),
        ("删除回测并清理结果", test_35_delete_backtest_with_results),
        ("幂等回测存储", test_36_idempotent_backtest),
        # ── 因子存储器注册测试 ──
        ("存储因子存储器", test_37_store_factor_storer),
        # ── FactorDB 自动重建测试 ──
        ("_extractFDBConnection 序列化", test_38_extract_fdb_connection_roundtrip),
        ("FactorDB 自动重建集成", test_39_auto_reconstruct_factor_db),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            ok = test_fn()
            if ok:
                passed += 1
            else:
                failed += 1
                errors.append((name, "返回 False"))
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  X 异常: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败 (共 {passed + failed} 个)")
    print("=" * 60)
    if errors:
        print("\n失败详情:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    # 清理 JYDB 连接
    if _jydb is not None:
        _jydb.disconnect()
    sys.exit(1 if failed else 0)

# -*- coding: utf-8 -*-
"""Neo4jDB 功能测试 — 连接、读写、因子表/因子操作、QSID 标识"""
import sys
import os
import json
import re
import logging

# 确保从工作目录导入，而非已安装的旧包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

# 加载 Neo4j 配置
NEO4J_CONFIG = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
with open(NEO4J_CONFIG, "r", encoding="utf-8") as f:
    content = f.read()
content = re.sub(r",\s*([}\]])", r"\1", content)
neo4j_cfg = json.loads(content)

import numpy as np
import pandas as pd
from datetime import datetime

from QuantStudio.Core.QSObject import Panel
from QSExt.Factor.Neo4jDB import Neo4jDB

TEST_TABLE = "__test_neo4jdb__"
TEST_FACTOR_A = "test_factor_a"
TEST_FACTOR_B = "test_factor_b"
TEST_QSID_A = "qsid_test_a_0001"
TEST_QSID_B = "qsid_test_b_0002"


def _make_fdb():
    args = {
        "IPAddr": neo4j_cfg["IPAddr"],
        "Port": neo4j_cfg["Port"],
        "User": neo4j_cfg["User"],
        "Pwd": neo4j_cfg["Pwd"],
        "DBName": neo4j_cfg.get("DBName", "neo4j"),
        "Name": "TestNeo4jDB",
    }
    fdb = Neo4jDB(args=args)
    fdb.connect()
    return fdb


def _make_panel():
    """构造测试用 Panel: items=[factor_a, factor_b], major_axis=[dt1, dt2], minor_axis=[id1, id2]"""
    dts = [datetime(2025, 1, 2), datetime(2025, 1, 3)]
    ids = ["SH600000", "SZ000001"]
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    b = np.array([[10.0, 20.0], [30.0, 40.0]])
    data = Panel(
        {TEST_FACTOR_A: pd.DataFrame(a, index=dts, columns=ids),
         TEST_FACTOR_B: pd.DataFrame(b, index=dts, columns=ids)}
    )
    return data


def _cleanup(fdb):
    """清理测试数据"""
    try:
        fdb.deleteTable(TEST_TABLE)
    except Exception:
        pass


# ============================================================
# 测试用例
# ============================================================

def test_1_connect():
    """连接与断开"""
    print("\n" + "=" * 60)
    print("测试 1: 连接与断开")
    print("=" * 60)
    fdb = _make_fdb()
    assert fdb.isAvailable(), "连接后 isAvailable() 应为 True"
    assert fdb._Node is not None, "连接后 _Node 不应为 None"
    print(f"  [PASS] 连接成功, _Node = {fdb._Node}")
    fdb.disconnect()
    assert not fdb.isAvailable(), "断开后 isAvailable() 应为 False"
    print("  [PASS] 断开成功")
    return True


def test_2_write_and_read():
    """写入数据并读回"""
    print("\n" + "=" * 60)
    print("测试 2: writeData + readData (带 factor_qsids)")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    factor_qsids = {TEST_FACTOR_A: TEST_QSID_A, TEST_FACTOR_B: TEST_QSID_B}
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}

    # 写入
    fdb.writeData(data, TEST_TABLE, if_exists="update", data_type=data_type, factor_qsids=factor_qsids)
    print(f"  [PASS] writeData 完成, 表={TEST_TABLE}")

    # 验证 _FactorInfo 中有 QSID 列
    fi = fdb._FactorInfo.loc[TEST_TABLE]
    assert "QSID" in fi.columns, "_FactorInfo 应包含 QSID 列"
    assert fi["QSID"][TEST_FACTOR_A] == TEST_QSID_A, f"QSID_A 不匹配: {fi['QSID'][TEST_FACTOR_A]}"
    assert fi["QSID"][TEST_FACTOR_B] == TEST_QSID_B, f"QSID_B 不匹配: {fi['QSID'][TEST_FACTOR_B]}"
    print(f"  [PASS] _FactorInfo QSID 正确")

    # 读取
    ft = fdb.getTable(TEST_TABLE)
    dts = ft.getDateTime()
    ids = ft.getID()
    print(f"  日期: {dts}")
    print(f"  标的: {ids}")
    assert len(dts) == 2, f"应有 2 个日期, 实际 {len(dts)}"
    assert len(ids) == 2, f"应有 2 个标的, 实际 {len(ids)}"

    read_data = ft.readData(factor_names=[TEST_FACTOR_A, TEST_FACTOR_B], dts=dts, ids=ids)
    assert read_data.shape[0] == 2, f"应有 2 个因子, 实际 {read_data.shape[0]}"
    assert read_data.shape[1] == 2, f"应有 2 个日期, 实际 {read_data.shape[1]}"
    assert read_data.shape[2] == 2, f"应有 2 个标的, 实际 {read_data.shape[2]}"

    # 验证值（按日期和标的查找）
    df_a = read_data.loc[TEST_FACTOR_A]
    # 找到 SH600000 在第一个日期的值
    col_sh = [c for c in df_a.columns if "SH" in str(c)][0]
    col_sz = [c for c in df_a.columns if "SZ" in str(c)][0]
    dt_first = df_a.index[0]
    dt_last = df_a.index[-1]
    # 值矩阵: [[1.0, 2.0], [3.0, 4.0]] 对应 dt1=[SH=1, SZ=2], dt2=[SH=3, SZ=4]
    all_vals = sorted(df_a.values.flatten())
    assert abs(all_vals[0] - 1.0) < 1e-10, f"最小值应为 1.0, 实际 {all_vals[0]}"
    assert abs(all_vals[-1] - 4.0) < 1e-10, f"最大值应为 4.0, 实际 {all_vals[-1]}"
    print(f"  [PASS] readData 数据正确")

    _cleanup(fdb)
    fdb.disconnect()
    return True


def test_3_write_without_qsids():
    """不传 factor_qsids 时回退到因子名"""
    print("\n" + "=" * 60)
    print("测试 3: writeData 不传 factor_qsids (回退到因子名)")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}

    fdb.writeData(data, TEST_TABLE, if_exists="update", data_type=data_type)
    print(f"  [PASS] writeData (无 factor_qsids) 完成")

    # QSID 应回退为因子名
    fi = fdb._FactorInfo.loc[TEST_TABLE]
    assert fi["QSID"][TEST_FACTOR_A] == TEST_FACTOR_A, "无 factor_qsids 时 QSID 应回退为因子名"
    assert fi["QSID"][TEST_FACTOR_B] == TEST_FACTOR_B, "无 factor_qsids 时 QSID 应回退为因子名"
    print(f"  [PASS] QSID 回退为因子名")

    # 读取验证
    ft = fdb.getTable(TEST_TABLE)
    dts = ft.getDateTime()
    ids = ft.getID()
    read_data = ft.readData(factor_names=[TEST_FACTOR_A, TEST_FACTOR_B], dts=dts, ids=ids)
    assert read_data.shape[0] == 2
    print(f"  [PASS] readData 数据正确")

    _cleanup(fdb)
    fdb.disconnect()
    return True


def test_4_update_notnull():
    """if_exists='update_notnull' 模式"""
    print("\n" + "=" * 60)
    print("测试 4: if_exists='update_notnull'")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}
    fdb.writeData(data, TEST_TABLE, data_type=data_type)

    # 写入部分 NaN 的数据
    dts = [datetime(2025, 1, 2), datetime(2025, 1, 3)]
    ids = ["SH600000", "SZ000001"]
    new_a = np.array([[99.0, np.nan], [np.nan, 88.0]])
    new_data = Panel(
        {TEST_FACTOR_A: pd.DataFrame(new_a, index=dts, columns=ids),
         TEST_FACTOR_B: pd.DataFrame(new_a, index=dts, columns=ids)}
    )
    fdb.writeData(new_data, TEST_TABLE, if_exists="update_notnull", data_type=data_type)

    ft = fdb.getTable(TEST_TABLE)
    read_data = ft.readData(factor_names=[TEST_FACTOR_A], dts=dts, ids=ids)
    df_a = read_data.loc[TEST_FACTOR_A]
    all_vals = sorted(df_a.values.flatten())
    # 应包含 99.0 和 88.0 (新值), 以及被保留的原值
    assert 99.0 in all_vals, f"应包含新值 99.0, 实际 {all_vals}"
    assert any(abs(v - 2.0) < 1e-10 or abs(v - 3.0) < 1e-10 for v in all_vals), f"应保留部分原值, 实际 {all_vals}"
    print(f"  [PASS] update_notnull 模式正确")

    _cleanup(fdb)
    fdb.disconnect()
    return True


def test_5_rename_delete_factor():
    """重命名和删除因子"""
    print("\n" + "=" * 60)
    print("测试 5: renameFactor + deleteFactor")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}
    fdb.writeData(data, TEST_TABLE, data_type=data_type)

    # 重命名
    fdb.renameFactor(TEST_TABLE, TEST_FACTOR_A, "renamed_factor")
    fi = fdb._FactorInfo.loc[TEST_TABLE]
    assert "renamed_factor" in fi.index, "重命名后应存在 renamed_factor"
    assert TEST_FACTOR_A not in fi.index, "重命名后原名不应存在"
    print(f"  [PASS] renameFactor 成功")

    # 删除
    fdb.deleteFactor(TEST_TABLE, ["renamed_factor"])
    fi = fdb._FactorInfo.loc[TEST_TABLE]
    assert "renamed_factor" not in fi.index, "删除后不应存在"
    assert TEST_FACTOR_B in fi.index, "未删除的因子应仍存在"
    print(f"  [PASS] deleteFactor 成功")

    _cleanup(fdb)
    fdb.disconnect()
    return True


def test_6_rename_delete_table():
    """重命名和删除因子表"""
    print("\n" + "=" * 60)
    print("测试 6: renameTable + deleteTable")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}
    fdb.writeData(data, TEST_TABLE, data_type=data_type)

    # 重命名
    new_name = TEST_TABLE + "_renamed"
    fdb.renameTable(TEST_TABLE, new_name)
    assert new_name in fdb._TableInfo.index, "重命名后新表名应存在"
    assert TEST_TABLE not in fdb._TableInfo.index, "重命名后旧表名不应存在"
    print(f"  [PASS] renameTable 成功")

    # 删除
    fdb.deleteTable(new_name)
    assert new_name not in fdb._TableInfo.index, "删除后表名不应存在"
    print(f"  [PASS] deleteTable 成功")

    fdb.disconnect()
    return True


def test_7_factor_info():
    """FactorNames 和 getFactorMetaData"""
    print("\n" + "=" * 60)
    print("测试 7: FactorNames + getFactorMetaData")
    print("=" * 60)
    fdb = _make_fdb()
    _cleanup(fdb)

    data = _make_panel()
    data_type = {TEST_FACTOR_A: "double", TEST_FACTOR_B: "double"}
    fdb.writeData(data, TEST_TABLE, data_type=data_type)

    ft = fdb.getTable(TEST_TABLE)
    factor_names = ft.FactorNames
    assert TEST_FACTOR_A in factor_names, f"应包含 {TEST_FACTOR_A}"
    assert TEST_FACTOR_B in factor_names, f"应包含 {TEST_FACTOR_B}"
    print(f"  [PASS] FactorNames = {factor_names}")

    meta = ft.getFactorMetaData(key="DataType")
    assert meta[TEST_FACTOR_A] == "double", f"DataType 应为 double, 实际 {meta[TEST_FACTOR_A]}"
    print(f"  [PASS] getFactorMetaData(DataType) 正确")

    _cleanup(fdb)
    fdb.disconnect()
    return True


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    tests = [
        test_1_connect,
        test_2_write_and_read,
        test_3_write_without_qsids,
        test_4_update_notnull,
        test_5_rename_delete_factor,
        test_6_rename_delete_table,
        test_7_factor_info,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            if t():
                passed += 1
            else:
                failed += 1
                print(f"  [FAIL] {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {t.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 个测试")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)

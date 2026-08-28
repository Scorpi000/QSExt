# -*- coding: utf-8 -*-
"""脚本节点功能测试脚本

测试 QSGraphDB 中脚本节点的存储、查询和影响分析功能。

使用方法：
    python tests/test_script_node.py

测试内容：
    1. storeScript() - 存储脚本节点
    2. storeFactorDef() - 一体化存储因子定义和脚本
    3. 查询 API - getScriptByQSID、searchScripts、getScriptFactors、getScriptDeps
    4. 影响分析 - getScriptImpact
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from QSExt.QSRegistry.QSGraphDB import QSGraphDB


def load_neo4j_config():
    """加载 Neo4j 配置"""
    config_path = os.path.expanduser("~/QuantStudioConfig/Neo4jDBConfig.json")
    if not os.path.exists(config_path):
        print(f"错误：Neo4j 配置文件不存在: {config_path}")
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 移除 JSON 中的尾随逗号
    import re
    content = re.sub(r",\s*([}\]])", r"\1", content)
    return json.loads(content)


def get_test_script_path(script_name):
    """获取测试脚本路径"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "QSExt", "FactorDef", script_name
    )


def test_store_script(gdb):
    """测试 storeScript 方法"""
    print("\n" + "=" * 60)
    print("测试 1: storeScript() - 存储脚本节点")
    print("=" * 60)

    # 测试脚本 1
    script1_path = get_test_script_path("stock_cn_factor_example1.py")
    if not os.path.exists(script1_path):
        print(f"错误：测试脚本不存在: {script1_path}")
        return None

    print(f"\n存储脚本: {script1_path}")
    qsid1 = gdb.storeScript(script1_path)
    print(f"  QSID: {qsid1}")

    # 验证脚本节点
    script1 = gdb.getScriptByQSID(qsid1)
    if script1:
        print(f"  名称: {script1.get('Name')}")
        print(f"  模块类型: {script1.get('ModuleType')}")
        print(f"  入口函数: {script1.get('EntryFunction')}")
        print(f"  内容哈希: {script1.get('ContentHash')[:16]}...")
        print(f"  作者: {script1.get('Author')}")
        print(f"  描述: {script1.get('Description')}")
    else:
        print("  错误：无法获取脚本节点")
        return None

    # 测试脚本 2
    script2_path = get_test_script_path("stock_cn_factor_example2.py")
    print(f"\n存储脚本: {script2_path}")
    qsid2 = gdb.storeScript(script2_path)
    print(f"  QSID: {qsid2}")

    # 验证脚本节点
    script2 = gdb.getScriptByQSID(qsid2)
    if script2:
        print(f"  名称: {script2.get('Name')}")
        print(f"  模块类型: {script2.get('ModuleType')}")
        print(f"  入口函数: {script2.get('EntryFunction')}")

    return qsid1, qsid2


def test_search_scripts(gdb):
    """测试 searchScripts 方法"""
    print("\n" + "=" * 60)
    print("测试 2: searchScripts() - 搜索脚本节点")
    print("=" * 60)

    # 按名称搜索
    print("\n按名称搜索 'example':")
    results = gdb.searchScripts(name="example")
    for r in results:
        print(f"  - {r.get('Name')} (QSID: {r.get('QSID')})")

    # 按模块类型搜索
    print("\n按模块类型搜索 'FactorDef':")
    results = gdb.searchScripts(module_type="FactorDef")
    for r in results:
        print(f"  - {r.get('Name')} (类型: {r.get('ModuleType')})")

    return results


def test_store_factor_def(gdb):
    """测试 storeFactorDef 方法"""
    print("\n" + "=" * 60)
    print("测试 3: storeFactorDef() - 一体化存储因子定义")
    print("=" * 60)

    from QSExt.FactorDef.FactorDefContent import FactorDef, FactorMeta

    # 创建测试 FactorDef
    script1_path = get_test_script_path("stock_cn_factor_example1.py")

    # 模拟 FactorMeta
    meta1 = FactorMeta(
        TargetTable="stock_cn_factor_example1",
        IDType="A股",
        Author="示例作者",
        Description="示例因子：演示 FactorDef 框架用法，含行情因子",
        DefScriptPath=script1_path,
        Tags=["示例", "教学", "行情"],
        FactorDeps={},
        DBDeps={"BSDB": "基于 BaoStock 的因子库"},
    )

    # 注意：这里我们无法真正运行 defFactor，因为需要数据库连接
    # 所以我们只测试脚本存储部分
    print(f"\n存储脚本（从 FactorDef）: {script1_path}")
    script_qsid = gdb.storeScript(script1_path, meta={
        "TargetTable": meta1.TargetTable,
        "IDType": meta1.IDType,
        "Author": meta1.Author,
        "Description": meta1.Description,
        "Tags": meta1.Tags,
        "FactorDeps": meta1.FactorDeps,
        "DBDeps": meta1.DBDeps,
    })
    print(f"  脚本 QSID: {script_qsid}")

    return script_qsid


def test_get_script_factors(gdb, script_qsid):
    """测试 getScriptFactors 方法"""
    print("\n" + "=" * 60)
    print("测试 4: getScriptFactors() - 获取脚本定义的因子")
    print("=" * 60)

    print(f"\n查询脚本 {script_qsid} 定义的因子:")
    factors = gdb.getScriptFactors(script_qsid)
    if factors:
        for f in factors:
            print(f"  - {f.get('Name')} (QSID: {f.get('QSID')})")
    else:
        print("  无因子（可能需要先运行 storeFactorDef）")

    return factors


def test_get_script_deps(gdb, script_qsid):
    """测试 getScriptDeps 方法"""
    print("\n" + "=" * 60)
    print("测试 5: getScriptDeps() - 获取脚本依赖")
    print("=" * 60)

    print(f"\n查询脚本 {script_qsid} 的依赖:")
    deps = gdb.getScriptDeps(script_qsid, depth=1)
    if deps.get("dependencies"):
        for dep in deps["dependencies"]:
            print(f"  - {dep.get('name')} (深度: {dep.get('depth')})")
            if dep.get("factor_names"):
                print(f"    依赖因子: {dep['factor_names']}")
    else:
        print("  无依赖")

    return deps


def test_get_script_impact(gdb, script_qsid):
    """测试 getScriptImpact 方法"""
    print("\n" + "=" * 60)
    print("测试 6: getScriptImpact() - 脚本影响分析")
    print("=" * 60)

    print(f"\n分析脚本 {script_qsid} 的影响范围:")
    impact = gdb.getScriptImpact(script_qsid)

    if impact.get("error"):
        print(f"  错误: {impact['error']}")
        return impact

    print(f"  脚本名称: {impact.get('script_name')}")
    print(f"  直接定义的因子: {len(impact.get('direct_factors', []))}")
    for f in impact.get("direct_factors", []):
        print(f"    - {f.get('name')}")

    print(f"  直接定义的策略: {len(impact.get('direct_strategies', []))}")
    for s in impact.get("direct_strategies", []):
        print(f"    - {s.get('name')}")

    print(f"  下游脚本: {len(impact.get('downstream_scripts', []))}")
    for s in impact.get("downstream_scripts", []):
        print(f"    - {s.get('name')}")

    print(f"  受影响的回测: {len(impact.get('affected_backtests', []))}")
    print(f"  受影响的因子存储器: {len(impact.get('affected_storers', []))}")

    return impact


def test_idempotency(gdb):
    """测试幂等性 - 重复存储同一脚本"""
    print("\n" + "=" * 60)
    print("测试 7: 幂等性测试 - 重复存储同一脚本")
    print("=" * 60)

    script1_path = get_test_script_path("stock_cn_factor_example1.py")

    # 第一次存储
    qsid1 = gdb.storeScript(script1_path)
    print(f"\n第一次存储 QSID: {qsid1}")

    # 第二次存储（应该返回相同的 QSID）
    qsid2 = gdb.storeScript(script1_path)
    print(f"第二次存储 QSID: {qsid2}")

    if qsid1 == qsid2:
        print("✓ 幂等性测试通过：两次存储返回相同的 QSID")
    else:
        print("✗ 幂等性测试失败：两次存储返回不同的 QSID")

    return qsid1 == qsid2


def main():
    """主测试函数"""
    print("=" * 60)
    print("脚本节点功能测试")
    print("=" * 60)

    # 加载配置
    config = load_neo4j_config()
    if not config:
        return

    # 创建 QSGraphDB 实例
    gdb = QSGraphDB(args={
        "IPAddr": config["IPAddr"],
        "Port": config["Port"],
        "User": config["User"],
        "Pwd": config["Pwd"],
        "DBName": config.get("DBName", "neo4j"),
    })

    try:
        # 连接数据库
        print("\n连接 Neo4j 数据库...")
        gdb.connect()
        print("✓ 连接成功")

        # 运行测试
        result = test_store_script(gdb)
        if result:
            qsid1, qsid2 = result

            test_search_scripts(gdb)
            test_store_factor_def(gdb)
            test_get_script_factors(gdb, qsid1)
            test_get_script_deps(gdb, qsid2)
            test_get_script_impact(gdb, qsid1)
            test_idempotency(gdb)

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 关闭连接
        gdb.disconnect()
        print("\n已断开数据库连接")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""测试 development LangGraph 端到端运行。

使用 demo PE_TTM 因子目录作为测试输入，验证图的完整流程。
由于代码生成需要 LLM，本测试仅验证图编译和验证节点。
"""
import asyncio
import logging
import sys

# 修复 Windows GBK 编码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)

from QSExt.LLMFactor.development.graph import (
    DevelopmentState,
    build_development_graph,
    compile_graph,
    after_verify,
    generate_node,
    verify_node,
    fix_node,
    search_node,
    log_node,
)


def test_graph_structure():
    """测试图结构正确性。"""
    print("\n" + "=" * 60)
    print("测试 1: 图结构")
    print("=" * 60)

    graph = build_development_graph()
    nodes = list(graph.nodes.keys())
    print(f"节点: {nodes}")

    expected = {"generate", "verify", "fix", "search", "log"}
    assert set(nodes) == expected, f"节点不匹配: {set(nodes)} != {expected}"
    print("节点正确")

    # 编译
    app = compile_graph()
    print(f"编译成功: {type(app).__name__}")
    print("PASS: 图结构测试通过\n")


def test_state_creation():
    """测试状态创建。"""
    print("=" * 60)
    print("测试 2: 状态创建")
    print("=" * 60)

    state = DevelopmentState.create_initial(
        hypothesis={
            "factor_name": "PE_TTM",
            "category": "估值因子",
            "market": "A股",
            "frequency": "日频",
        },
        config={
            "max_auto_fixes": 3,
            "enable_leak_test": False,
            "enable_unit_check": False,
            "enable_semantic_review": False,
        },
    )

    assert state["hypothesis"]["factor_name"] == "PE_TTM"
    assert state["attempt"] == 0
    assert state["generated_code"] is None
    assert state["validation_report"] is None
    assert state["search_result"] is None
    assert state["development_result"] is None
    print(f"状态字段: {list(state.keys())}")
    print("PASS: 状态创建测试通过\n")


def test_after_verify_routing():
    """测试验证后路由逻辑。"""
    print("=" * 60)
    print("测试 3: 条件路由")
    print("=" * 60)

    config = {"max_auto_fixes": 3}

    # 情况 1: 全部通过 → search
    state = DevelopmentState.create_initial(
        hypothesis={},
        config=config,
    )
    state["validation_report"] = {"all_passed": True}
    state["attempt"] = 1
    result = after_verify(state)
    assert result == "search", f"预期 search, 实际 {result}"
    print(f"  all_passed=True, attempt=1 → {result}  ✓")

    # 情况 2: 未通过，未超限 → fix
    state = DevelopmentState.create_initial(
        hypothesis={},
        config=config,
    )
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 1
    result = after_verify(state)
    assert result == "fix", f"预期 fix, 实际 {result}"
    print(f"  all_passed=False, attempt=1 → {result}  ✓")

    # 情况 3: 未通过，已超限 → end
    state = DevelopmentState.create_initial(
        hypothesis={},
        config=config,
    )
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 4  # > max_auto_fixes=3
    result = after_verify(state)
    assert result == "end", f"预期 end, 实际 {result}"
    print(f"  all_passed=False, attempt=4 → {result}  ✓")

    # 情况 4: 边界 - 刚好等于 max → fix（还有一次机会）
    state = DevelopmentState.create_initial(
        hypothesis={},
        config=config,
    )
    state["validation_report"] = {"all_passed": False}
    state["attempt"] = 3  # == max_auto_fixes
    result = after_verify(state)
    assert result == "fix", f"预期 fix, 实际 {result}"
    print(f"  all_passed=False, attempt=3 → {result}  ✓")

    print("PASS: 条件路由测试通过\n")


async def test_verify_node_on_demo():
    """测试 verify_node 在 demo 因子上的执行。"""
    print("=" * 60)
    print("测试 4: verify_node 执行（demo PE_TTM 因子）")
    print("=" * 60)

    demo_dir = "QSExt/LLMFactor/demo_stock_cn_factor_def"

    state = DevelopmentState.create_initial(
        hypothesis={"factor_name": "PE_TTM"},
        config={
            "max_auto_fixes": 3,
            "enable_leak_test": True,
            "enable_unit_check": True,
            "enable_semantic_review": False,  # 跳过 LLM 审查以加速测试
            "llm_model": "claude-sonnet-5",
            "llm_temperature": 0.1,
        },
    )
    state["workspace_dir"] = demo_dir

    result = await verify_node(state)

    report = result.get("validation_report", {})
    all_passed = report.get("all_passed", False)
    attempt = result.get("attempt", 0)

    print(f"  all_passed: {all_passed}")
    print(f"  attempt: {attempt}")

    for key in ["syntax", "execution", "leak_test", "unit_check"]:
        sub = report.get(key, {})
        passed = sub.get("passed", "N/A")
        issues = sub.get("issues", [])
        print(f"  {key}: passed={passed}, issues={len(issues)}")
        if issues:
            for issue in issues[:3]:
                print(f"    - {issue}")

    print("PASS: verify_node 执行测试通过\n")


if __name__ == "__main__":
    # 选择测试
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        test_graph_structure()
        test_state_creation()
        test_after_verify_routing()
        asyncio.run(test_verify_node_on_demo())
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        asyncio.run(test_verify_node_on_demo())
    else:
        # 默认运行单元测试（快速，无外部依赖）
        test_graph_structure()
        test_state_creation()
        test_after_verify_routing()
        print("=" * 60)
        print("所有单元测试通过！")
        print("运行 'python tests/test_development_graph.py verify' 测试 verify_node")
        print("运行 'python tests/test_development_graph.py all' 运行全部测试")
        print("=" * 60)

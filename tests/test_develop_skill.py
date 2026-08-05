# -*- coding: utf-8 -*-
"""测试使用 Claude Agent SDK 加载 development skill。

测试场景：
1. 使用 skills 参数加载 develop-factor skill
2. 传递假设文档路径作为参数
3. 捕获输出并保存到文件
"""
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 设置环境变量以使用 PowerShell
os.environ["CLAUDE_CODE_USE_POWERSHELL_TOOL"] = "1"

# 修复 Windows GBK 终端编码问题（emoji 等 Unicode 字符）
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from claude_agent_sdk import query, ClaudeAgentOptions
from QSExt import __QS_MainPath__

# 项目根目录
PROJECT_ROOT = Path(__QS_MainPath__).parent
MCP_CONFIG = PROJECT_ROOT / ".mcp.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
DEMO_HYPOTHESIS = PROJECT_ROOT / "QSExt" / "LLMFactor" / "demo_stock_cn_factor_def"

# 预授权的 MCP 工具列表（避免交互式权限确认）
ALLOWED_MCP_TOOLS = [
    # jy_base_doc
    "mcp__jy_base_doc__query_table",
    "mcp__jy_base_doc__search_table_list",
    "mcp__jy_base_doc__execute_sql",
    "mcp__jy_base_doc__query_qs_read_data_help",
    "mcp__jy_base_doc__query_qs_get_factor_help",
    # qs-registry
    "mcp__qs-registry__search_factors",
    "mcp__qs-registry__get_factor_info",
    "mcp__qs-registry__get_factor_code",
    # mining-log
    "mcp__mining-log__search_history",
    "mcp__mining-log__get_successful_components",
    "mcp__mining-log__get_failure_lessons",
    "mcp__mining-log__get_direction_coverage",
    # qswiki
    "mcp__qswiki__kb_search",
    "mcp__qswiki__kb_page",
    "mcp__qswiki__kb_ask",
    "mcp__qswiki__kb_list",
    "mcp__qswiki__kb_sources",
    # pdf_parser
    "mcp__pdf_parser__parse_pdf",
    "mcp__pdf_parser__parse_pdf_with_details",
]


async def test_develop_factor_skill():
    """测试 develop-factor skill 加载和执行。"""

    # 使用 demo 因子目录作为测试输入（模拟已有的假设文档）
    # 实际场景中应传入 Phase 1 输出的假设 YAML 路径
    prompt = (
        "请对 demo 因子目录 QSExt/LLMFactor/demo_stock_cn_factor_def 执行因子验证流程。"
        "这是一个 PE_TTM 因子，请运行语法检查和执行验证。"
        "使用 jy_base_doc 工具验证表名和字段名。"
        "输出验证结果汇总。"
    )

    options = ClaudeAgentOptions(
        cli_path=r"C:\Users\hst\.local\bin\claude.exe",
        # 加载 verify-factor 子 skill（单独测试验证步骤）
        skills=["verify-factor"],
        # MCP 配置
        mcp_servers=MCP_CONFIG,
        # 工作目录
        cwd=str(PROJECT_ROOT),
        # 自动权限 + 预授权 MCP 工具
        permission_mode="auto",
        allowed_tools=ALLOWED_MCP_TOOLS,
        # 限制轮次（测试用，避免过长）
        max_turns=30,
    )

    print("=" * 60)
    print("测试 verify-factor skill")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"Prompt: {prompt[:100]}...")
    print("=" * 60)

    # 收集输出
    output_messages = []

    async for message in query(prompt=prompt, options=options):
        msg_type = type(message).__name__

        if hasattr(message, "content"):
            content = message.content
            if isinstance(content, str):
                print(f"[{msg_type}] {content[:300]}")
                output_messages.append(content)
            elif isinstance(content, list):
                for block in content:
                    if hasattr(block, "text"):
                        print(f"[{msg_type}] {block.text[:300]}")
                        output_messages.append(block.text)

    # 保存输出
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = OUTPUT_DIR / f"develop_skill_test_{timestamp}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_messages))
    print(f"\n输出已保存: {output_file}")

    # 检查是否包含验证相关内容
    full_output = "\n".join(output_messages)
    has_validation = any(
        kw in full_output
        for kw in ["验证", "passed", "failed", "语法", "执行", "validation", "SyntaxReport"]
    )
    print(f"\n验证相关内容检测: {'通过' if has_validation else '未检测到'}")

    return output_messages


async def test_generate_factor_code_skill():
    """测试 generate-factor-code skill 加载。"""

    # 构造一个简化的假设文档 prompt
    prompt = (
        "请根据以下因子信息生成 QuantStudio 因子定义代码：\n"
        "- 因子名称: Test_Momentum_5D\n"
        "- 类别: 动量因子\n"
        "- 经济逻辑: 过去5个交易日的收益率作为短期动量信号\n"
        "- 计算步骤: 收盘价5日变化率\n"
        "- 数据需求: A股日频收盘价\n"
        "\n"
        "使用 jy_base_doc 工具查询真实的表名和字段名。"
        "输出 factor_def.py 代码、search_space.json 和 metadata.json。"
    )

    options = ClaudeAgentOptions(
        cli_path=r"C:\Users\hst\.local\bin\claude.exe",
        skills=["generate-factor-code"],
        mcp_servers=MCP_CONFIG,
        cwd=str(PROJECT_ROOT),
        permission_mode="auto",
        allowed_tools=ALLOWED_MCP_TOOLS,
        max_turns=25,
    )

    print("\n" + "=" * 60)
    print("测试 generate-factor-code skill")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 60)

    output_messages = []

    async for message in query(prompt=prompt, options=options):
        msg_type = type(message).__name__
        if hasattr(message, "content"):
            content = message.content
            if isinstance(content, str):
                print(f"[{msg_type}] {content[:300]}")
                output_messages.append(content)
            elif isinstance(content, list):
                for block in content:
                    if hasattr(block, "text"):
                        print(f"[{msg_type}] {block.text[:300]}")
                        output_messages.append(block.text)

    # 保存输出
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = OUTPUT_DIR / f"generate_skill_test_{timestamp}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_messages))
    print(f"\n输出已保存: {output_file}")

    # 尝试提取生成的代码
    full_output = "\n".join(output_messages)
    has_defactor = "defFactor" in full_output or "FACTOR_CODE" in full_output
    has_meta = "__FACTOR_META__" in full_output or "METADATA" in full_output
    print(f"因子代码检测: {'通过' if has_defactor else '未检测到'}")
    print(f"元数据检测: {'通过' if has_meta else '未检测到'}")

    # 提取代码块
    code_pattern = r"```python\s*\n(.*?)```"
    code_matches = re.findall(code_pattern, full_output, re.DOTALL)
    if code_matches:
        # 保存最长的代码块作为因子代码
        longest_code = max(code_matches, key=len)
        code_file = OUTPUT_DIR / f"generated_factor_{timestamp}.py"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(longest_code)
        print(f"生成的代码已保存: {code_file}")

    return output_messages


if __name__ == "__main__":
    # 选择要运行的测试
    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        asyncio.run(test_generate_factor_code_skill())
    elif len(sys.argv) > 1 and sys.argv[1] == "all":
        asyncio.run(test_verify_factor_skill())
        asyncio.run(test_generate_factor_code_skill())
    else:
        # 默认运行验证测试（资源消耗较小）
        asyncio.run(test_develop_factor_skill())

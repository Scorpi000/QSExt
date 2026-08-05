# -*- coding: utf-8 -*-
"""测试使用 Claude Agent SDK 加载 hypothesis skill。

测试场景：
1. 使用 skills 参数加载 skill
2. 传递参数给 skill
3. 捕获输出并保存到文件
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# 设置环境变量以使用 PowerShell
os.environ["CLAUDE_CODE_USE_POWERSHELL_TOOL"] = "1"

from claude_agent_sdk import query, ClaudeAgentOptions


async def test_hypothesis_skill():
    """测试 hypothesis skill 加载和执行。"""

    # 配置选项
    options = ClaudeAgentOptions(
        cli_path=r"C:\Users\lenovo\AppData\Local\Microsoft\WinGet\Links\claude.exe",
        # 加载 hypothesis skill
        skills=["hypothesis"],
        # 设置 MCP 配置
        mcp_servers=Path("D:/HST/QSExt/.mcp.json"),
        # 设置工作目录
        cwd="D:/HST/QSExt",
        # 设置权限模式为 auto，避免权限提示
        permission_mode="auto",
        # 设置最大轮次
        max_turns=50,
    )

    # prompt 内容
    prompt = "动量因子，A股，日频"

    print(f"开始执行 hypothesis skill...")
    print(f"Prompt: {prompt}")
    print("=" * 60)

    # 收集输出
    output_messages = []

    async for message in query(prompt=prompt, options=options):
        # 打印消息类型和内容
        msg_type = type(message).__name__

        if hasattr(message, 'content'):
            content = message.content
            if isinstance(content, str):
                print(f"[{msg_type}] {content[:200]}...")
                output_messages.append(content)
            elif isinstance(content, list):
                for block in content:
                    if hasattr(block, 'text'):
                        print(f"[{msg_type}] {block.text[:200]}...")
                        output_messages.append(block.text)

    # 保存输出
    output_dir = Path("D:/HST/QSExt/output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存完整输出
    output_file = output_dir / f"hypothesis_sdk_output_{timestamp}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_messages))
    print(f"\n输出已保存: {output_file}")

    # 尝试提取 YAML 内容
    full_output = "\n".join(output_messages)
    if "hypothesis_id" in full_output and "factor_name" in full_output:
        # 查找 YAML 内容
        import re
        yaml_pattern = r"```yaml\s*\n(.*?)\n```"
        yaml_matches = re.findall(yaml_pattern, full_output, re.DOTALL)

        if yaml_matches:
            yaml_content = yaml_matches[0]
        else:
            # 尝试从 hypothesis_id 开始提取
            lines = full_output.split("\n")
            yaml_lines = []
            in_yaml = False
            for line in lines:
                if "hypothesis_id:" in line:
                    in_yaml = True
                if in_yaml:
                    yaml_lines.append(line)
            yaml_content = "\n".join(yaml_lines)

        if yaml_content:
            yaml_file = output_dir / f"hypothesis_{timestamp}.yaml"
            with open(yaml_file, "w", encoding="utf-8") as f:
                f.write(yaml_content)
            print(f"假设文件已保存: {yaml_file}")


if __name__ == "__main__":
    asyncio.run(test_hypothesis_skill())

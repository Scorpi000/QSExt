# -*- coding: utf-8 -*-
import os
import re

from QSExt.Tools.HTML import TableHTMLParser


def html_table_to_markdown(html_table: str) -> str:
    """将HTML表格转换为Markdown表格"""
    parser = TableHTMLParser()
    parser.feed(html_table)
    rows = parser.get_rows()

    if not rows:
        return html_table

    # 计算最大列数
    max_cols = max(len(row) for row in rows)

    # 补齐每行的列数
    for row in rows:
        while len(row) < max_cols:
            row.append('')

    # 生成Markdown表格
    markdown_lines = []

    for i, row in enumerate(rows):
        # 转义特殊字符
        formatted_row = [cell.replace('|', '\\|').replace('\n', ' ') for cell in row]
        markdown_lines.append('| ' + ' | '.join(formatted_row) + ' |')

        # 在第一行后添加分隔符
        if i == 0:
            separator = '|' + '|'.join(['---'] * max_cols) + '|'
            markdown_lines.append(separator)

    return '\n'.join(markdown_lines)

def convert_all_html_table_to_markdown(content: str) -> str:
    """转换字符串中的HTML表格为Markdown格式

    Args:
        content: 输入的内容
    """

    # 匹配HTML表格（支持多行）
    table_pattern = re.compile(r'<table[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)

    def replace_table(match):
        html_table = match.group(0)
        try:
            markdown_table = html_table_to_markdown(html_table)
            return markdown_table
        except Exception as e:
            print(f"警告: 转换表格时出错: {e}")
            return html_table  # 出错时保留原HTML

    # 替换所有HTML表格
    new_content = table_pattern.sub(replace_table, content)
    return new_content

def remove_html_images(html_string: str) -> str:
    """
    从HTML字符串中删除所有图片标签
    支持 <img> 标签和 <image> 标签（SVG）
    """
    # 匹配 <img> 标签（包括自闭合和带结束标签的）
    # 匹配各种属性顺序和大小写
    pattern_img = r'<img\s+[^>]*?src=["\'][^"\']*["\'][^>]*?/?>'
    
    # 匹配 <image> 标签（SVG中的图片）
    pattern_image = r'<image\s+[^>]*?href=["\'][^"\']*["\'][^>]*?/?>'
    
    # 先移除 img 标签
    result = re.sub(pattern_img, '', html_string, flags=re.IGNORECASE)
    # 再移除 image 标签
    result = re.sub(pattern_image, '', result, flags=re.IGNORECASE)
    return result

def add_chapter(content, chapter_title, chapter_content, target_chapter=None, insert_at_start=False, level=1) -> str:
    """
    向 Markdown 文件添加章节的高级函数。
    
    Args:
        file_path (str): 文件路径。
        chapter_title (str): 新章节标题。
        chapter_content (str): 新章节内容。
        target_chapter (str): [可选] 目标章节标题。新章节将插入到此章节之后。
        insert_at_start (bool): [可选] 如果为 True，新章节将插入到文件最开头（第一个标题之前）。
        level (int): 新章节的标题级别 (1=#, 2=##)。
    """
    
    # 构建新章节的完整文本
    header_prefix = "#" * level
    # 确保内容前后有适当的换行
    new_section = f"\n\n{header_prefix} {chapter_title}\n\n{chapter_content}\n"

    final_content = ""

    # --- 逻辑分支 1: 插入到文章最前面 ---
    if insert_at_start:
        # 简单的策略：直接放在所有内容之前，或者第一个标题之前
        # 这里我们选择放在第一个标题之前，以保持文档结构整洁
        # 正则匹配第一个 # 标题
        first_header_pattern = r'(^#\s+.+$)'
        match = re.search(first_header_pattern, content, re.MULTILINE)
        
        if match:
            # 在第一个标题前插入
            insert_pos = match.start()
            final_content = content[:insert_pos] + new_section.strip() + "\n\n" + content[insert_pos:]
        else:
            # 如果没有找到标题，直接加在最前面
            final_content = new_section.strip() + "\n\n" + content
            
    # --- 逻辑分支 2: 插入到指定章节后面 ---
    elif target_chapter:
        # 我们需要转义标题中的特殊字符，以防正则报错
        # 同时匹配不同级别的标题 (例如用户输入 "简介"，我们要能匹配到 "## 简介")
        escaped_target = re.escape(target_chapter)
        
        # 正则解释：
        # ^ : 行首
        # (#{1,6}) : 捕获组1，匹配 1 到 6 个 #
        # \s+ : 匹配空格
        # {escaped_target} : 目标标题文本
        # \s* : 匹配标题后的可选空格
        # $ : 行尾
        pattern = rf'^(#+)\s+{escaped_target}\s*$'
        
        match = re.search(pattern, content, re.MULTILINE)
        
        if match:
            # 找到目标章节，获取其结束位置
            insert_pos = match.end()
            
            # 检查目标章节后面是否已经有换行符，避免格式错乱
            # 我们希望在插入新内容前有两个换行符（Markdown 标准段落分隔）
            prefix = ""
            if not content[insert_pos:insert_pos+2] == "\n\n":
                if content[insert_pos:insert_pos+1] == "\n":
                    prefix = "\n" # 已有1个，补1个
                else:
                    prefix = "\n\n" # 没有，补2个
            
            # 拼接：前文 + 目标章节结尾 + 换行符 + 新章节
            final_content = content[:insert_pos] + prefix + new_section + content[insert_pos:]
        else:
            print(f"⚠️ 警告: 未在文件中找到章节 '{target_chapter}'。操作取消。")
            return

    # --- 逻辑分支 3: 默认追加到末尾 ---
    else:
        if content.endswith('\n'):
            final_content = content + new_section
        else:
            final_content = content + "\n" + new_section

    return final_content

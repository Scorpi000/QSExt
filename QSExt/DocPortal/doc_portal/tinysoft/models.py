# -*- coding: utf-8 -*-
"""天软文档数据模型定义。

定义了文档节点树、文档内容、搜索结果等核心数据结构，使用 Pydantic v2 进行数据校验。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DocNode(BaseModel):
    """文档目录树中的一个节点。

    Attributes:
        id: 天软文档站中的文档 ID，对应 display.tsl?id=<id>
        name: 节点名称（函数名、章节名等）
        is_folder: 是否为目录节点（非叶子节点）
        children: 子节点列表
    """

    id: int
    name: str
    is_folder: bool = False
    children: list[DocNode] = Field(default_factory=list)


class DocContent(BaseModel):
    """一篇文档的完整内容。

    支持两种文档类型：
    1. 函数文档：summary/definition/parameters/examples/related
    2. 数据表文档：data_description/field_description/basic_info/update_log/code_examples

    Attributes:
        id: 文档 ID
        title: 文档标题
        breadcrumb: 面包屑导航路径（如 ["TSL函数", "系统相关函数", "数据类型函数"]）
        summary: 简述/描述文本（函数文档）或 数据说明（数据表文档）
        definition: 函数定义/语法
        parameters: 参数说明（Markdown 表格格式）或 字段说明（数据表文档）
        examples: 代码示例列表
        related: 相关文档列表 [{id, name}]
        raw_content: 原始内容文本（所有段落拼接）
        # 数据表文档特有字段
        data_description: 数据说明（数据表文档专用）
        field_description: 字段说明（数据表文档专用，包含字段ID、类型、名称、单位）
        basic_info: 基本概况（数据表文档专用，包含表ID、表名、提取方式）
        update_log: 更新日志（数据表文档专用）
        data_update_info: 数据更新情况（数据表文档专用）
        access_code: 访问代码（数据表文档专用）
    """

    id: int
    title: str
    breadcrumb: list[str] = Field(default_factory=list)
    summary: str = ""
    definition: str = ""
    parameters: str = ""
    examples: list[str] = Field(default_factory=list)
    related: list[dict[str, str | int]] = Field(default_factory=list)
    raw_content: str = ""
    # 数据表文档特有字段
    data_description: str = ""
    field_description: str = ""
    basic_info: str = ""
    update_log: str = ""
    data_update_info: str = ""
    access_code: str = ""


class SearchResultItem(BaseModel):
    """搜索结果中的一条记录。

    Attributes:
        id: 文档 ID
        title: 文档标题
        category: 所属板块
        breadcrumb: 面包屑导航
        snippet: 内容摘要片段
    """

    id: int
    title: str
    category: str = ""
    breadcrumb: list[str] = Field(default_factory=list)
    snippet: str = ""


class CategoryType:
    """文档板块类型常量。"""

    TSL = 1  # TSL 语言基础
    DOTNET = 242  # .NET 函数大全
    KB = 10002  # 知识库

    NAMES = {1: "tsl", 242: "dotnet", 10002: "kb"}
    TYPES = {"tsl": 1, "dotnet": 242, "kb": 10002, "all": None}

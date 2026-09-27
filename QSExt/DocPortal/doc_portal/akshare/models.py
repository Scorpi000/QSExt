# -*- coding: utf-8 -*-
"""AKShare 文档数据模型定义。

定义了接口条目、文档页面、接口详情等核心数据结构，使用 Pydantic v2 进行数据校验。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParamInfo(BaseModel):
    """接口参数信息（输入或输出）。

    Attributes:
        name: 参数名称
        type: 参数类型（如 str、int、float）
        description: 参数描述
    """

    name: str
    type: str = ""
    description: str = ""


class InterfaceDetail(BaseModel):
    """单个 AKShare 接口的详细信息。

    Attributes:
        name: 接口名，如 "stock_zh_a_hist"
        category: 所属类目，如 "stock"
        description: 接口描述
        target_url: 数据源地址
        limit_desc: 数据量限制说明
        module: 接口所在模块路径（仅 akshare API 可用时填充）
        input_params: 输入参数列表
        output_params: 输出参数列表
        example: 调用示例代码
        notes: 补充说明
        page_path: 所在文档页路径
        section: 所属小节标题
        documented: 是否在文档中已有收录
    """

    name: str
    category: str = ""
    description: str = ""
    target_url: str = ""
    limit_desc: str = ""
    module: str = ""
    input_params: list[ParamInfo] = Field(default_factory=list)
    output_params: list[ParamInfo] = Field(default_factory=list)
    example: str = ""
    notes: str = ""
    page_path: str = ""
    section: str = ""
    documented: bool = True


class AKShareCategory(BaseModel):
    """AKShare 数据字典中的一个类目条目。

    Attributes:
        name: 类目名称，如 "stock"
        display_name: 显示名称，如 "AKShare 股票数据"
        page_path: 文档页路径，如 "data/stock/stock.html"
        interface_count: 接口数量
    """

    name: str
    display_name: str = ""
    page_path: str = ""
    interface_count: int = 0


class SearchResultItem(BaseModel):
    """搜索结果中的一条记录。

    Attributes:
        name: 接口名
        category: 所属类目
        description: 接口描述
        score: 匹配分数
        documented: 是否在文档中收录
    """

    name: str
    category: str = ""
    description: str = ""
    score: float = 0.0
    documented: bool = True

# -*- coding: utf-8 -*-
"""
回测报告生成系统

提供基于 YAML 配置 + 组件库的回测报告生成框架。
每个"场景"包含一个 YAML 配置文件和 Python 脚本，定义回测模块组装和报告布局。
"""

from QSExt.ReportGenerator.node import ReportGeneratorNode

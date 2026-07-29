# report-center

## Purpose

QSWeb 报告中心模块，支持用户选择报告场景生成报告、浏览和预览已生成的报告，以及将报告关联到因子或回测后注册到 QSRegistry。

## Requirements

### Requirement: 报告生成

系统 SHALL 支持用户选择报告场景、配置参数并生成报告。

#### Scenario: 生成单因子分析报告
- **WHEN** 用户选择"单因子分析"场景，配置因子、日期范围和格式（HTML/Markdown）
- **THEN** 系统提交异步生成任务，完成后返回报告 ID

#### Scenario: 报告生成进度
- **WHEN** 报告生成任务执行中
- **THEN** 系统通过 WebSocket 推送生成进度

### Requirement: 报告浏览

系统 SHALL 支持用户浏览、搜索和预览已生成的报告。

#### Scenario: 查看报告列表
- **WHEN** 用户进入报告中心
- **THEN** 系统展示报告列表，支持按因子、场景、日期筛选

#### Scenario: 预览报告
- **WHEN** 用户点击某报告
- **THEN** 系统以内嵌 HTML 或 Markdown 渲染方式展示报告内容

#### Scenario: 下载报告
- **WHEN** 用户点击"下载"
- **THEN** 系统提供报告文件下载

### Requirement: 报告注册

系统 SHALL 支持用户将报告关联到因子或回测并注册到 QSRegistry。

#### Scenario: 注册报告到 QSRegistry
- **WHEN** 用户选择关联的因子和/或回测，点击注册
- **THEN** 系统通过 `register_report` MCP 工具将报告元数据写入 Neo4j 图数据库

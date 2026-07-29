# report-center (delta)

## MODIFIED Requirements

### Requirement: 报告生成

系统 SHALL 支持用户选择报告场景、从全局因子池选择因子、配置参数并生成报告。

#### Scenario: 生成单因子分析报告
- **WHEN** 用户选择"单因子分析"场景，从右侧因子池面板勾选因子，配置日期范围和格式（HTML/Markdown）
- **THEN** 系统从 store 的 selectedIds 读取已选因子构建 FactorRef[]，提交异步生成任务

#### Scenario: 报告生成进度
- **WHEN** 报告生成任务执行中
- **THEN** 系统通过轮询推送生成进度

## ADDED Requirements

### Requirement: 全局因子池集成

系统 SHALL 在报告中心页面通过 PoolRefPicker 从全局因子池选择价格/Mask/行业/权重因子，通过 FactorPoolPanel（右侧面板）勾选被测因子。

#### Scenario: 从池中选择报告因子
- **WHEN** 用户在右侧因子池面板勾选需要纳入报告的因子
- **THEN** 系统将 selectedIds 对应的因子转换为 FactorRef[] 用于报告生成请求

#### Scenario: 选择辅助因子
- **WHEN** 用户需要指定价格/Mask/行业/权重因子
- **THEN** PoolRefPicker 下拉展示池中所有因子供选择

#### Scenario: 池变更实时反映
- **WHEN** 在其他页面向池中添加或移除因子
- **THEN** 报告中心的因子选项自动同步更新

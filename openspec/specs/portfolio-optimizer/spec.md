# portfolio-optimizer

## Purpose

QSWeb 组合优化器模块，支持用户配置优化问题的目标函数和约束条件、提交求解请求，并查看权重分布和风险分解结果。

## Requirements

### Requirement: 优化配置

系统 SHALL 支持用户配置组合优化问题的目标函数和约束条件。

#### Scenario: 选择优化目标
- **WHEN** 用户选择目标类型（均值方差/风险预算/最大分散化）
- **THEN** 系统展示对应的参数配置表单（风险厌恶系数、风险预算向量等）

#### Scenario: 添加约束条件
- **WHEN** 用户点击"添加约束"，选择约束类型
- **THEN** 系统展示对应的约束参数编辑器（Box 约束/行业暴露/换手率/非零个数）

### Requirement: 优化求解

系统 SHALL 支持用户提交组合优化问题并获取求解结果。

#### Scenario: 求解组合优化
- **WHEN** 用户配置完目标和约束，点击"求解"
- **THEN** 系统调用 CVXPY 求解器，返回最优权重和求解状态

#### Scenario: 求解失败处理
- **WHEN** 优化问题无可行解或求解器报错
- **THEN** 系统返回错误信息和建议的约束调整方向

### Requirement: 全局因子池集成

系统 SHALL 在组合优化页面中通过 PoolFactorPicker 从全局因子池选择因子作为优化输入（预期收益、Mask、基准权重），PoolFactorPicker 从 Zustand store 读取因子列表。

#### Scenario: 从池中选择优化因子
- **WHEN** 用户在组合优化页面配置预期收益/Mask/基准权重
- **THEN** PoolFactorPicker 下拉框展示全局池中所有因子，用户选择后生成 FactorDataRef

#### Scenario: 池变更实时反映
- **WHEN** 在其他页面向池中添加新因子
- **THEN** 组合优化页面的 PoolFactorPicker 下拉选项自动包含新因子

### Requirement: 结果展示

系统 SHALL 支持用户查看优化结果的权重分布和风险分解。

#### Scenario: 查看权重分布
- **WHEN** 求解成功
- **THEN** 系统以柱状图/饼图展示 Top N 权重分布

#### Scenario: 查看风险分解
- **WHEN** 求解成功
- **THEN** 系统展示因子风险 vs 特异性风险的占比

#### Scenario: 导出权重
- **WHEN** 用户点击"导出权重 CSV"
- **THEN** 系统生成 CSV 文件供下载

#### Scenario: 注册到 QSRegistry
- **WHEN** 用户点击"注册到 QSRegistry"
- **THEN** 系统将优化配置和结果元数据写入 Neo4j 图数据库

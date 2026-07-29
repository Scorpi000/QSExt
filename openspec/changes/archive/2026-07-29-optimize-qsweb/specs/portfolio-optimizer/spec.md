# portfolio-optimizer (delta)

## ADDED Requirements

### Requirement: 全局因子池集成

系统 SHALL 在组合优化页面中通过 PoolFactorPicker 从全局因子池选择因子作为优化输入（预期收益、Mask、基准权重）。

#### Scenario: 从池中选择优化因子
- **WHEN** 用户在组合优化页面配置预期收益/Mask/基准权重
- **THEN** PoolFactorPicker 下拉框展示全局池中所有因子（FactorDB + QSRegistry），用户选择后生成 FactorDataRef

#### Scenario: 池变更实时反映
- **WHEN** 在其他页面向池中添加新因子
- **THEN** 组合优化页面的 PoolFactorPicker 下拉选项自动包含新因子

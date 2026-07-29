# backtest-studio (delta)

## MODIFIED Requirements

### Requirement: 因子选择

系统 SHALL 支持用户从全局因子池中选择因子用于回测。因子池位于 MainLayout 右侧滑出面板（hover 展开），FactorDiscover Drawer 由右侧面板触发。

#### Scenario: 从池中选择已添加的因子
- **WHEN** 用户在 ModulePicker 中为回测模块配置因子
- **THEN** ModulePicker 从全局因子池 Zustand store 读取因子列表，转换为 FactorRef 构建模块配置

#### Scenario: 添加新因子到池
- **WHEN** 用户需要池中不存在的因子
- **THEN** 用户从右侧因子池面板点击"添加"，打开 FactorDiscover Drawer，浏览 FactorDB 或搜索 QSRegistry 添加因子

#### Scenario: QSRegistry 因子重建用于回测
- **WHEN** 回测任务执行时遇到 source 为 "registry" 的因子
- **THEN** 系统通过 QSGraphDB.reconstructFactor(qsid) 重建完整 Factor 对象用于回测计算

#### Scenario: 池变更实时反映
- **WHEN** 在其他页面向池中添加或移除因子
- **THEN** 回测工作台的 ModulePicker 因子选项自动更新

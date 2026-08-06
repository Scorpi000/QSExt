# backtest-studio

## MODIFIED Requirements

### Requirement: 后续模块扩展

系统 SHALL 支持通过 `_BT_NODE_BUILDERS` 字典声明式添加更多回测模块，并支持通过策略回测路径（Strategy → `AccountReport`）执行自定义策略回测，策略回测结果使用统一的 `ResultNode` 树结构返回。

策略回测的 `QSBridge` 执行路径与模块化回测并列：策略回测使用 `defStrategy(sdi) → Strategy 实例 → AccountReport(strategy_factor)` 构建 BTNode，通过同一 `Engine.run()` 执行，输出同样序列化为 `ResultNode` 树。

#### Scenario: 添加新模块

- **WHEN** 在 `_BT_NODE_BUILDERS` 中注册新模块定义（calc_module/calc_class/node_module/node_class）
- **THEN** 前端模块列表和配置表单自动支持新模块，无需额外开发

#### Scenario: 执行策略回测

- **WHEN** 策略工作台提交策略回测请求
- **THEN** QSBridge 动态加载策略代码、调用 `defStrategy`、构造 `AccountReport`，通过引擎执行并返回 `ResultNode` 树，结果与模块化回测使用相同的数据结构

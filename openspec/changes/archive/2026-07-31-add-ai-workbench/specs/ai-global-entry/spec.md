# ai-global-entry

## Purpose

全局 AI 入口系统，提供 FAB 悬浮按钮、Ctrl+K 快捷键、侧边栏导航菜单项三种触发方式，用户可从 QSWeb 任意页面快速唤起 AI 助手 Drawer。入口自动感知当前路由以注入对应上下文。

## ADDED Requirements

### Requirement: FAB 悬浮按钮

系统 SHALL 在所有页面右下角显示 AI 助手 FAB 悬浮按钮。

#### Scenario: FAB 可见性

- **WHEN** 用户在 QSWeb 任意页面
- **THEN** 右下角固定位置显示圆形悬浮按钮，图标为机器人（RobotOutlined），颜色为主题色

#### Scenario: 点击 FAB

- **WHEN** 用户点击 FAB 按钮
- **THEN** 打开 `AiChatDrawer`，context 由当前路由 + `route_context_map` 推断

#### Scenario: FAB 不遮挡页面内容

- **WHEN** 因子池面板展开时
- **THEN** FAB 应位于因子池左侧（避免重叠），或临时向左偏移

### Requirement: Ctrl+K 快捷键

系统 SHALL 支持 `Ctrl+K`（macOS: `Cmd+K`）快捷键唤起 AI 助手。

#### Scenario: 快捷键触发

- **WHEN** 用户在 QSWeb 任意页面按下 `Ctrl+K` 或 `Cmd+K`
- **THEN** 打开 `AiChatDrawer`，context 由当前路由 + `route_context_map` 推断
- **WHEN** Drawer 已打开时按下快捷键
- **THEN** 关闭 Drawer（toggle 行为）

#### Scenario: 快捷键不干扰输入框

- **WHEN** 用户在输入框（input/textarea）内按下 `Ctrl+K`
- **THEN** 不触发 AI Drawer（避免与文本编辑快捷键冲突）

### Requirement: 侧边栏导航菜单项

系统 SHALL 在左侧导航栏新增 `/ai` 菜单项。

#### Scenario: 菜单项位置

- **WHEN** 用户查看左侧导航栏
- **THEN** 在现有菜单项下方显示"AI 工作台"菜单项（图标：RobotOutlined），位于"报告中心"之下

#### Scenario: 点击菜单项

- **WHEN** 用户点击"AI 工作台"菜单项
- **THEN** 导航到 `/ai` 独立页面

### Requirement: 路由感知上下文集

`AiChatDrawer` SHALL 在打开时根据当前路由自动注入对应 context。

#### Scenario: 路由匹配

- **WHEN** 用户在 `/factor` 路径打开 Drawer（通过 FAB 或快捷键）
- **THEN** Drawer 的 context 设为 `route_context_map["/factor"]`（即 `"factor"`），输入框占位文字为 context 配置的 `placeholder`

#### Scenario: 无匹配路由

- **WHEN** 当前路由不在 `route_context_map` 中（如 `/report`）
- **THEN** 使用 `default_context`（`"general"`）

#### Scenario: 页面按钮覆盖

- **WHEN** 用户通过页面内的"AI 助手"按钮打开（如回测页面可能有专属按钮）
- **THEN** 使用按钮显式指定的 context，覆盖路由自动推断

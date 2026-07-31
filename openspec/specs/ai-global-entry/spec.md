# ai-global-entry

## Purpose

全局 AI 入口系统，提供 FAB 悬浮按钮、Ctrl+K 快捷键、侧边栏导航菜单项三种触发方式，用户可从 QSWeb 任意页面快速唤起 AI 助手 Drawer。入口自动感知当前路由以注入对应上下文。

## Requirements

### Requirement: FAB 悬浮按钮

系统 SHALL 在所有页面右下角显示 AI 助手 FAB 悬浮按钮（RobotOutlined 图标，主题色），点击打开 `AiChatDrawer`，context 由当前路由 + `route_context_map` 推断。

### Requirement: Ctrl+K 快捷键

系统 SHALL 支持 `Ctrl+K`（macOS: `Cmd+K`）快捷键唤起 AI 助手。输入框内不触发，已打开时 toggle 关闭。在 `MainLayout` 中监听全局键盘事件。

### Requirement: 侧边栏导航菜单项

系统 SHALL 在左侧导航栏新增"AI 工作台"菜单项（RobotOutlined 图标，路由 `/ai`），位于"报告中心"之下。

### Requirement: 路由感知上下文

`AiChatDrawer` SHALL 在打开时根据当前路由自动注入对应 context。路由匹配 `route_context_map`，未匹配使用 `default_context`。页面按钮显式指定 context 时优先级高于路由推断。

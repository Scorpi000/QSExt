# ai-action-card

## Purpose

通用 action_card 消息协议，允许 AI 在生成结果后向前端推送结构化操作卡片。前端不感知业务语义，通过 `kind` 字段匹配渲染组件，通过 `onAction` 回调委托业务逻辑。协议为后端驱动，新增 action 类型无需改动前端代码。

## Requirements

### Requirement: action_card 消息协议

系统 SHALL 定义 `action_card` 类型的 WebSocket 消息协议。

#### Scenario: 消息结构

- **WHEN** AI 完成特定任务（如生成脚本、计算出结果）后发送 action_card
- **THEN** 消息 JSON 结构为：
  ```json
  {
    "type": "action_card",
    "data": {
      "kind": "string (如 save_script)",
      "title": "string (卡片标题)",
      "summary": "object (key-value 摘要信息)",
      "actions": [
        {
          "key": "string (操作标识)",
          "label": "string (按钮文字)",
          "style": "primary | default | danger"
        }
      ],
      "payload": "object (传给 onAction 的附带数据)"
    }
  }
  ```

#### Scenario: 动作按钮配置

- **WHEN** action_card 包含多个 `actions`
- **THEN** 按钮按顺序渲染，`style: "primary"` 为蓝色主题按钮，`style: "danger"` 为红色，`style: "default"` 为灰色

### Requirement: 前端通用渲染

`AiChatPanel` SHALL 通用渲染 action_card，不感知业务语义。

#### Scenario: 渲染 action_card

- **WHEN** 收到 `type: "action_card"` 消息
- **THEN** 渲染绿色边框卡片，显示 `title`（粗体）、`summary` 的 key-value 列表、操作按钮行

#### Scenario: 操作按钮点击

- **WHEN** 用户点击 action 按钮
- **THEN** 调用 `onAction(action.key, card.payload)` prop，按钮进入 loading 状态
- **WHEN** `onAction` resolve（成功）
- **THEN** 按钮恢复，卡片上方显示"✓ 操作成功"
- **WHEN** `onAction` reject（失败）
- **THEN** 按钮恢复，卡片上方显示"✗ {error.message}"
- **WHEN** 用户点击 `style: "default"` 的按钮（通常为"放弃"）
- **THEN** 卡片整体折叠/隐藏

### Requirement: onAction 回调协议

`onAction` prop SHALL 接收通用回调签名。

#### Scenario: 回调签名

- **WHEN** 调用方使用 `AiChatPanel`
- **THEN** `onAction` 类型为 `(key: string, payload: any) => Promise<{success: boolean, message?: string}>`

#### Scenario: Action 路由

- **WHEN** factor 场景中 `key` 为 `"save"`
- **THEN** 调用方匹配 `key === "save"`，调用 `POST /api/factors/import` 保存脚本
- **WHEN** `key` 为 `"discard"`
- **THEN** 调用方直接 resolve `{success: true}`，前端自动隐藏卡片

### Requirement: action_card 生成方式

后端 SHALL 通过 system_prompt 指导 Claude 何时发送 action_card。在 `format_message()`（SDK）或 `_parse_cli_message()`（CLI）中，`_extract_action_card()` 从 text block 提取 JSON，`_strip_action_card()` 从文本中移除。支持紧凑单行和嵌套多行两种 JSON 格式。

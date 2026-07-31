/**
 * AiFactorAssistant - AI 因子助手 Chat 面板
 *
 * 通过 WebSocket 与后端 AI 服务通信（基于 ClaudeSDKClient 双向交互），
 * 流式展示 Claude 的思考过程和生成的因子脚本。
 * 支持多轮对话：发送初始需求 → 追问 → 中断。
 * 生成完成后自动调用导入管道获取元信息预览，提供保存/注册/编辑操作。
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Drawer,
  Input,
  Button,
  Space,
  Tag,
  Collapse,
  message,
  Spin,
  Typography,
  Alert,
  Empty,
  Badge,
} from 'antd'
import {
  SendOutlined,
  ReloadOutlined,
  RobotOutlined,
  UserOutlined,
  ToolOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { AiChatClient } from '../../services/ai'
import type { AiMessage, AiBlock } from '../../services/ai'
import { importFactor } from '../../services/import'
import type { ImportResult } from '../../services/import'

const { TextArea } = Input
const { Text } = Typography

interface ChatMessage {
  role: 'user' | 'ai'
  content: string
  blocks?: AiBlock[]
  thinking?: string  // Claude 的思考过程
  isToolCall?: boolean
  isError?: boolean
  isCode?: boolean
}

interface AiFactorAssistantProps {
  open: boolean
  onClose: () => void
}

/** Claude 运行状态 */
type RunState = 'idle' | 'running' | 'interrupted' | 'done'

function AiFactorAssistant({ open, onClose }: AiFactorAssistantProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [runState, setRunState] = useState<RunState>('idle')
  const [generatedCode, setGeneratedCode] = useState<string | null>(null)
  const [generatedFilename, setGeneratedFilename] = useState('factor.py')
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importing, setImporting] = useState(false)

  const clientRef = useRef<AiChatClient | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }, [])

  // 初始化 WebSocket 客户端和消息处理
  useEffect(() => {
    const client = new AiChatClient()
    clientRef.current = client

    client.onMessage((msg: AiMessage) => {
      switch (msg.type) {
        case 'assistant': {
          const blocks = msg.data?.blocks || []
          const textBlocks = blocks.filter((b) => b.kind === 'text')
          const thinkingBlocks = blocks.filter((b) => b.kind === 'thinking')
          const toolBlocks = blocks.filter((b) => b.kind === 'tool_use' || b.kind === 'tool_result')
          const content = textBlocks.map((b) => b.content).join('\n')
          const thinking = thinkingBlocks.map((b) => b.content).join('\n')

          if (content || thinking) {
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              // 检测是否为代码
              const isCode = content.includes('__FACTOR_META__') || content.includes('defFactor')
              if (isCode) {
                const codeMatch = content.match(/```python\n?([\s\S]*?)```/)
                if (codeMatch) {
                  setGeneratedCode(codeMatch[1])
                } else {
                  setGeneratedCode(content)
                }
                setGeneratedFilename('factor.py')
              }

              if (last && last.role === 'ai' && !last.isToolCall && !last.isCode) {
                return [...prev.slice(0, -1), {
                  ...last,
                  content: last.content + content,
                  thinking: (last.thinking || '') + thinking,
                  isCode: last.isCode || isCode,
                }]
              }
              return [...prev, { role: 'ai', content, thinking, isCode }]
            })
          }

          if (toolBlocks.length > 0) {
            for (const tb of toolBlocks) {
              if (tb.kind === 'tool_use') {
                setMessages((prev) => [
                  ...prev,
                  {
                    role: 'ai',
                    content: `调用工具: ${tb.tool_name}`,
                    isToolCall: true,
                    blocks: [tb],
                  },
                ])
              } else if (tb.kind === 'tool_result') {
                setMessages((prev) => [
                  ...prev,
                  {
                    role: 'ai',
                    content: typeof tb.content === 'string' ? tb.content : JSON.stringify(tb.content),
                    isToolCall: true,
                    blocks: [tb],
                  },
                ])
              }
            }
          }
          scrollToBottom()
          break
        }

        case 'stream':
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            const content = msg.data?.content || ''
            if (last && last.role === 'ai' && !last.isToolCall && !last.isCode) {
              return [...prev.slice(0, -1), { ...last, content: last.content + content }]
            }
            return [...prev, { role: 'ai', content }]
          })
          scrollToBottom()
          break

        case 'result': {
          const isError = msg.data?.is_error || false
          if (isError) {
            setMessages((prev) => [
              ...prev,
              { role: 'ai', content: `❌ ${msg.data?.content || '未知错误'}`, isError: true },
            ])
          }
          setRunState('done')
          scrollToBottom()
          break
        }

        case 'error':
          setMessages((prev) => [
            ...prev,
            {
              role: 'ai',
              content: `❌ ${msg.data?.message || '未知错误'}`,
              isError: true,
            },
          ])
          setRunState('done')
          scrollToBottom()
          break

        case 'interrupted':
          setMessages((prev) => [
            ...prev,
            { role: 'ai', content: '⏸ 已中断', isError: false },
          ])
          setRunState('interrupted')
          scrollToBottom()
          break

        case 'done':
          setRunState('done')
          break
      }
    })

    return () => {
      client.disconnect()
    }
  }, [])

  // 发送初始需求（启动 Claude 会话）
  const handleSend = async () => {
    if (!input.trim()) return
    const client = clientRef.current
    if (!client) {
      message.error('WebSocket 未初始化')
      return
    }

    const userInput = input
    setMessages((prev) => [...prev, { role: 'user', content: userInput }])
    setInput('')
    setRunState('running')
    setGeneratedCode(null)
    setImportResult(null)

    try {
      // 新协议：start 包含连接 + 初始提示
      // 如果当前有活跃会话，先断开
      if (runState === 'running' || runState === 'interrupted') {
        client.disconnect()
        // 重新创建 client 和 handler（因为 disconnect 后 ws 关闭）
        const newClient = new AiChatClient()
        clientRef.current = newClient
        newClient.onMessage(client['handlers']?.[0] ? (() => {}) : (() => {})) // handled by effect
        // 直接用当前 client 的 start
      }
      await client.start(userInput)
    } catch (err: any) {
      message.error(`连接失败: ${err.message}`)
      setRunState('idle')
    }
  }

  // 发送后续消息
  const handleSendFollowup = () => {
    if (!input.trim()) return
    const client = clientRef.current
    if (!client) return

    setMessages((prev) => [...prev, { role: 'user', content: input }])
    const userInput = input
    setInput('')
    setRunState('running')

    try {
      client.sendQuery(userInput)
    } catch (err: any) {
      message.error(`发送失败: ${err.message}`)
      setRunState('idle')
    }
  }

  // 中断 Claude
  const handleInterrupt = () => {
    const client = clientRef.current
    if (!client) return
    client.interrupt()
  }

  // 新建会话
  const handleNewSession = () => {
    const client = clientRef.current
    if (client) {
      client.disconnect()
    }
    setMessages([])
    setGeneratedCode(null)
    setImportResult(null)
    setRunState('idle')
  }

  // AI 生成完成后：自动预览导入
  useEffect(() => {
    if (!generatedCode || runState !== 'done') return
    const previewImport = async () => {
      try {
        const result = await importFactor(generatedCode, generatedFilename)
        setImportResult(result as unknown as ImportResult)
      } catch {
        // 预览失败不阻断
      }
    }
    previewImport()
  }, [generatedCode, runState])

  // 确认导入
  const handleConfirmImport = async () => {
    if (!generatedCode) return
    setImporting(true)
    try {
      const result = await importFactor(generatedCode, generatedFilename)
      const data = result as unknown as ImportResult
      if (data.success) {
        message.success(`脚本已保存: ${data.saved_path}`)
      }
    } catch (err: any) {
      message.error(err?.response?.data?.message || err?.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // 渲染单条消息
  const renderMessage = (msg: ChatMessage, idx: number) => {
    const isUser = msg.role === 'user'
    return (
      <div
        key={idx}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: isUser ? 'flex-end' : 'flex-start',
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
          {isUser ? (
            <>
              <span style={{ fontSize: 12, color: '#888' }}>你</span>
              <UserOutlined style={{ fontSize: 12, color: '#888' }} />
            </>
          ) : (
            <>
              <RobotOutlined style={{ fontSize: 12, color: '#52c41a' }} />
              <span style={{ fontSize: 12, color: '#52c41a' }}>AI 助手</span>
            </>
          )}
        </div>

        {msg.isToolCall ? (
          <div
            style={{
              maxWidth: '90%',
              padding: '6px 10px',
              borderRadius: 8,
              background: '#f6ffed',
              border: '1px solid #b7eb8f',
              fontSize: 12,
            }}
          >
            <ToolOutlined style={{ marginRight: 4 }} />
            {msg.blocks?.[0]?.kind === 'tool_use' ? (
              <span>
                正在调用: <Tag style={{ fontSize: 11 }}>{msg.blocks[0].tool_name}</Tag>
              </span>
            ) : (
              <Text ellipsis={{ tooltip: msg.content }} style={{ fontSize: 12, maxWidth: 400 }}>
                {msg.content}
              </Text>
            )}
          </div>
        ) : msg.isCode ? (
          <div style={{ maxWidth: '95%' }}>
            <pre
              style={{
                background: '#1e1e1e',
                color: '#d4d4d4',
                padding: 12,
                borderRadius: 8,
                fontSize: 11,
                overflow: 'auto',
                maxHeight: 400,
              }}
            >
              <code>{msg.content}</code>
            </pre>
          </div>
        ) : (
          <div
            style={{
              maxWidth: '90%',
              padding: '8px 12px',
              borderRadius: 8,
              background: isUser ? '#e6f7ff' : msg.isError ? '#fff2f0' : '#f5f5f5',
              border: isUser ? '1px solid #91d5ff' : msg.isError ? '1px solid #ffccc7' : '1px solid #d9d9d9',
              fontSize: 13,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {/* 思考过程 — 折叠显示 */}
            {msg.thinking && (
              <Collapse
                size="small"
                ghost
                items={[{
                  key: 'thinking',
                  label: <span style={{ fontSize: 11, color: '#888' }}>💭 思考过程</span>,
                  children: <pre style={{ fontSize: 11, color: '#888', whiteSpace: 'pre-wrap', margin: 0, maxHeight: 200, overflow: 'auto' }}>{msg.thinking}</pre>,
                }]}
                style={{ marginBottom: msg.content ? 6 : 0, background: 'transparent' }}
              />
            )}
            {msg.content}
          </div>
        )}
      </div>
    )
  }

  const isActive = runState === 'running'

  return (
    <Drawer
      title={
        <Space>
          <RobotOutlined />
          <span>AI 因子助手</span>
          {isActive && (
            <Badge status="processing" text="运行中" style={{ fontSize: 11 }} />
          )}
          {runState === 'interrupted' && (
            <Badge status="warning" text="已中断" style={{ fontSize: 11 }} />
          )}
          {runState === 'done' && (
            <Badge status="success" text="已完成" style={{ fontSize: 11 }} />
          )}
        </Space>
      }
      open={open}
      onClose={() => {
        // 关闭面板时断开 Claude
        if (isActive) {
          clientRef.current?.interrupt()
        }
        clientRef.current?.disconnect()
        setRunState('idle')
        onClose()
      }}
      width={520}
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={handleNewSession}>
          新建会话
        </Button>
      }
    >
      {/* 消息列表 */}
      <div style={{ height: 'calc(100vh - 350px)', overflow: 'auto', marginBottom: 12 }}>
        {messages.length === 0 ? (
          <Empty
            description="描述你想要的因子，AI 将帮你创建"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 60 }}
          />
        ) : (
          messages.map((msg, idx) => renderMessage(msg, idx))
        )}
        {isActive && (
          <div style={{ textAlign: 'center', padding: 8 }}>
            <Spin size="small" /> <span style={{ fontSize: 12, color: '#888' }}>AI 正在思考...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 代码生成后的操作区 */}
      {generatedCode && runState === 'done' && (
        <div style={{ marginBottom: 12 }}>
          <Alert
            type="success"
            message="因子脚本已生成"
            description={
              <div>
                {importResult && importResult.success && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ marginBottom: 4 }}>
                      <Text strong style={{ fontSize: 12 }}>元信息:</Text>
                    </div>
                    {importResult.meta?.TargetTable && (
                      <Tag>{importResult.meta.TargetTable}</Tag>
                    )}
                    {importResult.meta?.IDType && (
                      <Tag color="blue">{importResult.meta.IDType}</Tag>
                    )}
                    {importResult.has_def_factor && (
                      <Tag color="green">defFactor ✓</Tag>
                    )}
                    {importResult.warnings.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {importResult.warnings.map((w, i) => (
                          <div key={i} style={{ fontSize: 11, color: '#faad14' }}>⚠ {w}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            }
            style={{ marginBottom: 8 }}
          />
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckCircleOutlined />}
              loading={importing}
              onClick={handleConfirmImport}
            >
              保存脚本
            </Button>
            <Button
              size="small"
              icon={<CloseCircleOutlined />}
              onClick={() => {
                setGeneratedCode(null)
                setImportResult(null)
              }}
            >
              放弃
            </Button>
          </Space>
        </div>
      )}

      {/* 输入区 */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <TextArea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              if (runState === 'idle') {
                handleSend()
              } else {
                handleSendFollowup()
              }
            }
          }}
          placeholder={
            isActive
              ? '输入后续消息追问 Claude...'
              : '描述你想要的因子，例如：创建一个 20 日动量因子，A 股，基于日收益率计算...'
          }
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 8, justifyContent: 'flex-end' }}>
          {isActive && (
            <Button
              danger
              icon={<StopOutlined />}
              onClick={handleInterrupt}
            >
              停止
            </Button>
          )}
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={runState === 'idle' ? handleSend : handleSendFollowup}
            disabled={!input.trim()}
          >
            {runState === 'idle' ? '发送' : '追问'}
          </Button>
        </div>
      </div>
    </Drawer>
  )
}

export default AiFactorAssistant

/**
 * AiFactorAssistant - AI 因子助手 Chat 面板
 *
 * 通过 WebSocket 与后端 AI 服务通信，流式展示 Claude 的思考过程和生成的因子脚本。
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
} from 'antd'
import {
  SendOutlined,
  ReloadOutlined,
  RobotOutlined,
  UserOutlined,
  ToolOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import { AiChatClient } from '../../services/ai'
import type { AiMessage, AiBlock } from '../../services/ai'
import { importFactor } from '../../services/import'
import type { ImportResult } from '../../services/import'

const { TextArea } = Input
const { Text, Paragraph } = Typography

interface ChatMessage {
  role: 'user' | 'ai'
  content: string
  blocks?: AiBlock[]
  isThinking?: boolean
  isToolCall?: boolean
  isError?: boolean
  isCode?: boolean
}

interface AiFactorAssistantProps {
  open: boolean
  onClose: () => void
}

function AiFactorAssistant({ open, onClose }: AiFactorAssistantProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
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

  // 初始化 WebSocket
  useEffect(() => {
    const client = new AiChatClient()
    clientRef.current = client

    client.onMessage((msg: AiMessage) => {
      switch (msg.type) {
        case 'assistant': {
          const blocks = msg.data?.blocks || []
          const textBlocks = blocks.filter((b) => b.kind === 'text')
          const toolBlocks = blocks.filter((b) => b.kind === 'tool_use' || b.kind === 'tool_result')
          const content = textBlocks.map((b) => b.content).join('\n')

          if (content) {
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              // 检测是否为代码（包含 __FACTOR_META__ 或 defFactor）
              const isCode = content.includes('__FACTOR_META__') || content.includes('defFactor')
              if (isCode) {
                // 提取代码部分
                const codeMatch = content.match(/```python\n?([\s\S]*?)```/)
                if (codeMatch) {
                  setGeneratedCode(codeMatch[1])
                } else {
                  setGeneratedCode(content)
                }
                setGeneratedFilename('factor.py')
              }

              if (last && last.role === 'ai' && !last.isToolCall && !last.isCode) {
                return [...prev.slice(0, -1), { ...last, content: last.content + content, isCode: last.isCode || isCode }]
              }
              return [...prev, { role: 'ai', content, isCode }]
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
          const content = msg.data?.content || ''
          const isError = msg.data?.is_error || false
          setMessages((prev) => [
            ...prev,
            { role: 'ai', content: isError ? `❌ ${content}` : content, isError },
          ])
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
          setSending(false)
          scrollToBottom()
          break

        case 'done':
          setSending(false)
          break
      }
    })

    return () => {
      client.disconnect()
    }
  }, [])

  // 发送消息
  const handleSend = async () => {
    if (!input.trim()) return
    const client = clientRef.current
    if (!client) {
      message.error('WebSocket 未初始化')
      return
    }

    setMessages((prev) => [...prev, { role: 'user', content: input }])
    const userInput = input
    setInput('')
    setSending(true)
    setGeneratedCode(null)
    setImportResult(null)

    try {
      await client.connect()
      client.send(userInput)
    } catch (err: any) {
      message.error(`连接失败: ${err.message}`)
      setSending(false)
    }
  }

  // 新建会话
  const handleNewSession = () => {
    setMessages([])
    setGeneratedCode(null)
    setImportResult(null)
  }

  // AI 生成完成后：自动预览导入
  useEffect(() => {
    if (!generatedCode || sending) return
    const previewImport = async () => {
      try {
        const result = await importFactor(generatedCode, generatedFilename)
        setImportResult(result as unknown as ImportResult)
      } catch {
        // 预览失败不阻断
      }
    }
    previewImport()
  }, [generatedCode, sending])

  // 确认导入（含注册）
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
            {msg.content}
          </div>
        )}
      </div>
    )
  }

  return (
    <Drawer
      title={
        <Space>
          <RobotOutlined />
          <span>AI 因子助手</span>
        </Space>
      }
      open={open}
      onClose={onClose}
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
        {sending && (
          <div style={{ textAlign: 'center', padding: 8 }}>
            <Spin size="small" /> <span style={{ fontSize: 12, color: '#888' }}>AI 正在思考...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 代码生成后的操作区 */}
      {generatedCode && !sending && (
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
              handleSend()
            }
          }}
          placeholder="描述你想要的因子，例如：创建一个 20 日动量因子，A 股，基于日收益率计算..."
          disabled={sending}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={sending}
          disabled={!input.trim()}
          style={{ marginTop: 8, float: 'right' }}
        >
          发送
        </Button>
      </div>
    </Drawer>
  )
}

export default AiFactorAssistant

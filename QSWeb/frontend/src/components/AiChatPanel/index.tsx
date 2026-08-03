/**
 * AiChatPanel - 通用 AI 聊天面板
 *
 * 纯通用组件，不包含任何业务逻辑。通过 props 注入 context、placeholder、
 * action handlers 等差异化行为。被 AiChatDrawer、AiWorkbench 页面、
 * AiFactorAssistant 复用。
 *
 * 支持消息类型:
 *   - user / assistant (Markdown)
 *   - thinking (可折叠思考过程)
 *   - tool_use / tool_result (工具调用卡片)
 *   - stream (流式增量追加)
 *   - action_card (结构化操作卡片)
 *   - data_block (富媒体数据块)
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Input,
  Button,
  Space,
  Tag,
  Collapse,
  message,
  Spin,
  Typography,
  Empty,
  Badge,
  Radio,
  Checkbox,
} from 'antd'
import {
  SendOutlined,
  ReloadOutlined,
  RobotOutlined,
  UserOutlined,
  ToolOutlined,
  StopOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { AiChatClient } from '../../services/ai'
import type { AiMessage, AiBlock, ActionCardData, DataBlockData } from '../../services/ai'

const { TextArea } = Input
const { Text } = Typography

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: 'user' | 'ai'
  content: string
  blocks?: AiBlock[]
  thinking?: string
  isToolCall?: boolean
  isError?: boolean
  isStreaming?: boolean
}

export interface ActionHandlerResult {
  success: boolean
  message?: string
}

export interface AiChatPanelProps {
  /** AI 上下文标识（传给后端） */
  context: string
  /** 输入框占位文字 */
  placeholder?: string
  /** 标题栏右侧额外内容 */
  headerExtra?: React.ReactNode
  /** 预设初始消息（恢复会话时使用） */
  initialMessages?: ChatMessage[]
  /** action_card 按钮回调 */
  onAction?: (key: string, payload: any) => Promise<ActionHandlerResult>
  /** 会话 ID（恢复会话时使用） */
  sessionId?: string
  /** 新会话创建回调 */
  onNewSession?: () => void
}

/** Claude 运行状态 */
type RunState = 'idle' | 'running' | 'interrupted' | 'done'

// ---------------------------------------------------------------------------
// ActionCard 子组件
// ---------------------------------------------------------------------------

interface ActionCardProps {
  data: ActionCardData
  onAction?: (key: string, payload: any) => Promise<ActionHandlerResult>
}

function ActionCard({ data, onAction }: ActionCardProps) {
  const [loadingKey, setLoadingKey] = useState<string | null>(null)
  const [result, setResult] = useState<{ success: boolean; message?: string } | null>(null)
  const [collapsed, setCollapsed] = useState(false)

  const handleClick = async (action: ActionCardData['actions'][0]) => {
    if (!onAction) return
    setLoadingKey(action.key)
    try {
      const res = await onAction(action.key, data.payload)
      setResult(res)
      if (action.style === 'default') {
        setCollapsed(true)
      }
    } catch (err: any) {
      setResult({ success: false, message: err?.message || '操作失败' })
    } finally {
      setLoadingKey(null)
    }
  }

  if (collapsed) return null

  return (
    <div
      style={{
        border: '1px solid #b7eb8f',
        borderRadius: 8,
        padding: 12,
        background: '#f6ffed',
        marginBottom: 8,
      }}
    >
      {result && (
        <div
          style={{
            marginBottom: 8,
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 12,
            background: result.success ? '#f6ffed' : '#fff2f0',
            color: result.success ? '#52c41a' : '#ff4d4f',
          }}
        >
          {result.success ? '✓ 操作成功' : `✗ ${result.message}`}
          {result.success && result.message && `: ${result.message}`}
        </div>
      )}
      <div style={{ fontWeight: 500, marginBottom: 8 }}>{data.title}</div>
      {data.summary && Object.keys(data.summary).length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {Object.entries(data.summary).map(([key, value]) => (
            <Tag key={key} style={{ marginBottom: 4 }}>
              {key}: {String(value)}
            </Tag>
          ))}
        </div>
      )}
      <Space>
        {data.actions.map((action) => {
          const typeMap: Record<string, any> = {
            primary: 'primary',
            danger: 'danger',
            default: 'default',
          }
          return (
            <Button
              key={action.key}
              type={typeMap[action.style] || 'default'}
              size="small"
              loading={loadingKey === action.key}
              danger={action.style === 'danger'}
              onClick={() => handleClick(action)}
            >
              {action.label}
            </Button>
          )
        })}
      </Space>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DataBlock 子组件
// ---------------------------------------------------------------------------

interface DataBlockProps {
  data: DataBlockData
}

function DataBlock({ data }: DataBlockProps) {
  // 根据 kind 选择合适的渲染器
  switch (data.kind) {
    case 'table':
    case 'factor_table':
      return (
        <div
          style={{
            border: '1px solid #d9d9d9',
            borderRadius: 8,
            padding: 12,
            background: '#fafafa',
            marginBottom: 8,
            overflow: 'auto',
            maxHeight: 300,
          }}
        >
          <Text type="secondary" style={{ fontSize: 11, marginBottom: 8, display: 'block' }}>
            📊 数据表
          </Text>
          <pre style={{ fontSize: 11, margin: 0, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(data.payload, null, 2)}
          </pre>
        </div>
      )
    case 'chart':
      return (
        <div
          style={{
            border: '1px solid #d9d9d9',
            borderRadius: 8,
            padding: 12,
            background: '#fafafa',
            marginBottom: 8,
          }}
        >
          <Text type="secondary" style={{ fontSize: 11 }}>
            📈 图表 (Plotly 渲染预留)
          </Text>
        </div>
      )
    case 'dag':
      return (
        <div
          style={{
            border: '1px solid #d9d9d9',
            borderRadius: 8,
            padding: 12,
            background: '#fafafa',
            marginBottom: 8,
          }}
        >
          <Text type="secondary" style={{ fontSize: 11 }}>
            🔗 DAG 依赖图
          </Text>
        </div>
      )
    default:
      return (
        <div
          style={{
            border: '1px solid #d9d9d9',
            borderRadius: 8,
            padding: 12,
            background: '#fafafa',
            marginBottom: 8,
            overflow: 'auto',
            maxHeight: 300,
          }}
        >
          <Text type="secondary" style={{ fontSize: 11, marginBottom: 4, display: 'block' }}>
            📦 {data.kind}
          </Text>
          <pre style={{ fontSize: 11, margin: 0, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(data.payload, null, 2)}
          </pre>
        </div>
      )
  }
}

// ---------------------------------------------------------------------------
// AskUserQuestion 子组件
// ---------------------------------------------------------------------------

interface AskUserPanelProps {
  questions: Array<{
    question: string
    header: string
    options: Array<{ label: string; description: string }>
    multiSelect: boolean
  }>
  onSubmit: (answers: Record<string, string | string[]>) => void
  clientRef: React.MutableRefObject<AiChatClient | null>
}

function AskUserPanel({ questions, onSubmit, clientRef }: AskUserPanelProps) {
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({})
  const [submitted, setSubmitted] = useState(false)

  const handleSingleSelect = (question: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [question]: value }))
  }

  const handleMultiSelect = (question: string, value: string, checked: boolean) => {
    setAnswers((prev) => {
      const current = (prev[question] as string[]) || []
      return {
        ...prev,
        [question]: checked
          ? [...current, value]
          : current.filter((v) => v !== value),
      }
    })
  }

  const handleSubmit = () => {
    if (submitted) return
    // 为未回答的单选问题填充默认值
    const final: Record<string, string | string[]> = {}
    for (const q of questions) {
      const ans = answers[q.question]
      if (ans !== undefined) {
        final[q.question] = ans
      } else if (q.multiSelect) {
        final[q.question] = []
      } else if (q.options.length > 0) {
        final[q.question] = q.options[0].label
      }
    }
    setSubmitted(true)
    // 通过 clientRef 直接发送答案
    clientRef.current?.sendAnswer(final)
    onSubmit(final)
  }

  return (
    <div
      style={{
        border: '1px solid #91d5ff',
        borderRadius: 8,
        padding: 16,
        background: '#e6f7ff',
        marginBottom: 8,
        maxWidth: '90%',
      }}
    >
      <div style={{ fontWeight: 500, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
        <QuestionCircleOutlined style={{ color: '#1677ff' }} />
        <span>Claude 想确认几个问题</span>
      </div>
      {questions.map((q, qi) => (
        <div
          key={qi}
          style={{
            marginBottom: qi < questions.length - 1 ? 16 : 12,
            padding: 12,
            background: '#fff',
            borderRadius: 6,
            border: '1px solid #d9d9d9',
          }}
        >
          <div style={{ fontWeight: 500, marginBottom: 4 }}>
            <Tag color="blue" style={{ marginRight: 8 }}>{q.header}</Tag>
            {q.question}
          </div>
          {q.multiSelect ? (
            <Checkbox.Group
              options={q.options.map((o) => ({
                label: `${o.label} — ${o.description}`,
                value: o.label,
              }))}
              onChange={(values) => setAnswers((prev) => ({ ...prev, [q.question]: values }))}
              style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
            />
          ) : (
            <Radio.Group
              options={q.options.map((o) => ({
                label: `${o.label} — ${o.description}`,
                value: o.label,
              }))}
              onChange={(e) => handleSingleSelect(q.question, e.target.value)}
              value={(answers[q.question] as string) || q.options[0]?.label}
              style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
            />
          )}
        </div>
      ))}
      <Button
        type="primary"
        onClick={handleSubmit}
        disabled={submitted}
      >
        {submitted ? '已提交' : '提交'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SlashCommandPalette 子组件
// ---------------------------------------------------------------------------

interface SlashCommandPaletteProps {
  commands: string[]
  filterPrefix: string
  visible: boolean
  selectedIndex: number
  onSelect: (command: string) => void
}

function SlashCommandPalette({
  commands,
  filterPrefix,
  visible,
  selectedIndex,
  onSelect,
}: SlashCommandPaletteProps) {
  const filtered = commands.filter((cmd) =>
    cmd.toLowerCase().startsWith(filterPrefix.toLowerCase())
  )

  if (!visible || filtered.length === 0) return null

  return (
    <div
      className="slash-command-palette"
      style={{
        position: 'absolute',
        bottom: '100%',
        left: 0,
        right: 0,
        marginBottom: 4,
        background: '#fff',
        border: '1px solid #d9d9d9',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        maxHeight: 200,
        overflow: 'auto',
        zIndex: 1000,
      }}
    >
      {filtered.map((cmd, idx) => (
        <div
          key={cmd}
          onMouseDown={(e) => {
            e.preventDefault()
            onSelect(cmd)
          }}
          style={{
            padding: '6px 12px',
            cursor: 'pointer',
            background: idx === selectedIndex ? '#e6f7ff' : 'transparent',
            fontSize: 13,
          }}
        >
          <span style={{ fontWeight: 500, color: '#1677ff' }}>/{cmd}</span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

function AiChatPanel({
  context,
  placeholder = '描述你想做的事情...',
  headerExtra,
  initialMessages,
  onAction,
  sessionId: _sessionId,
  onNewSession,
}: AiChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages || [])
  const [input, setInput] = useState('')
  const [runState, setRunState] = useState<RunState>('idle')
  const [slashCommands, setSlashCommands] = useState<string[]>([
    'compact', 'clear', 'context', 'usage',
  ])
  const [slashActive, setSlashActive] = useState(false)
  const [slashPrefix, setSlashPrefix] = useState('')
  const [slashStartIdx, setSlashStartIdx] = useState(-1)
  const [slashSelectedIdx, setSlashSelectedIdx] = useState(0)

  const textareaRef = useRef<any>(null)

  const clientRef = useRef<AiChatClient | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }, [])

  // Slash 命令检测：判断光标前最近的 `/` 是否触发命令面板
  const scanSlashTrigger = useCallback(
    (value: string, cursorPos: number) => {
      const before = value.slice(0, cursorPos)
      const slashIdx = before.lastIndexOf('/')
      if (slashIdx === -1) return { active: false, prefix: '', startIdx: -1 }
      // `/` 必须在行首或空格后
      if (slashIdx > 0 && before[slashIdx - 1] !== ' ') {
        return { active: false, prefix: '', startIdx: -1 }
      }
      const prefix = before.slice(slashIdx + 1)
      return { active: true, prefix, startIdx: slashIdx }
    },
    []
  )

  // 选择 slash 命令后替换输入文本
  const handleSelectSlashCommand = useCallback(
    (cmd: string) => {
      const before = input.slice(0, slashStartIdx)
      const afterSlash = input.slice(slashStartIdx + 1 + slashPrefix.length)
      const newValue = before + '/' + cmd + ' ' + afterSlash
      setInput(newValue)
      setSlashActive(false)
      // 恢复焦点并将光标放在命令后
      const cursorTarget = before.length + cmd.length + 2 // after "/cmd "
      setTimeout(() => {
        const el = textareaRef.current?.resizableTextArea?.textArea
        if (el) {
          el.focus()
          el.setSelectionRange(cursorTarget, cursorTarget)
        }
      }, 0)
    },
    [input, slashStartIdx, slashPrefix]
  )

  // 点击面板外部关闭
  useEffect(() => {
    if (!slashActive) return
    const handleClick = (e: MouseEvent) => {
      const palette = document.querySelector('.slash-command-palette')
      if (palette && !palette.contains(e.target as Node)) {
        setSlashActive(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [slashActive])

  // initialMessages 变化时同步到 messages（支持会话恢复）
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages)
      setRunState('done')
    }
  }, [initialMessages])

  // initialMessages 加载后滚动到底部
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      scrollToBottom()
    }
  }, [initialMessages, scrollToBottom])

  // 初始化 WebSocket 客户端和消息处理
  useEffect(() => {
    const client = new AiChatClient()
    clientRef.current = client

    client.onMessage((msg: AiMessage) => {
      switch (msg.type) {
        case 'init': {
          const cmds = msg.data?.slash_commands
          if (Array.isArray(cmds)) {
            setSlashCommands(cmds)
          }
          break
        }

        case 'assistant': {
          const blocks = msg.data?.blocks || []
          const textBlocks = blocks.filter((b) => b.kind === 'text')
          const thinkingBlocks = blocks.filter((b) => b.kind === 'thinking')
          const toolBlocks = blocks.filter(
            (b) => b.kind === 'tool_use' || b.kind === 'tool_result'
          )
          const content = textBlocks.map((b) => b.content).join('\n')
          const thinking = thinkingBlocks.map((b) => b.content).join('\n')

          if (content || thinking) {
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last && last.role === 'ai' && last.isStreaming) {
                return [
                  ...prev.slice(0, -1),
                  {
                    ...last,
                    content: last.content + content,
                    thinking: (last.thinking || '') + thinking,
                    isStreaming: true,
                  },
                ]
              }
              return [
                ...prev,
                { role: 'ai', content, thinking, isStreaming: true },
              ]
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
                    content:
                      typeof tb.content === 'string'
                        ? tb.content
                        : JSON.stringify(tb.content),
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
            if (last && last.role === 'ai' && last.isStreaming) {
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + content },
              ]
            }
            return [
              ...prev,
              { role: 'ai', content, isStreaming: true },
            ]
          })
          scrollToBottom()
          break

        case 'action_card': {
          // 将 action_card 渲染为特殊消息
          // 数据在顶层 data 中
          const cardData = msg.data || msg
          setMessages((prev) => [
            ...prev,
            {
              role: 'ai',
              content: '',
              blocks: [{ kind: 'text', content: '' }],
            },
          ])
          // 用自定义属性标记此消息需要特殊渲染
          // 存储 action_card 数据到最近一条 ai 消息的扩展字段
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (!last) return prev
            ;(last as any).actionCard = cardData
            return [...prev]
          })
          scrollToBottom()
          break
        }

        case 'data_block': {
          const blockData = msg.data || msg
          setMessages((prev) => [
            ...prev,
            {
              role: 'ai',
              content: '',
              blocks: [{ kind: 'text', content: '' }],
              isToolCall: false,
            },
          ])
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (!last) return prev
            ;(last as any).dataBlock = blockData
            return [...prev]
          })
          scrollToBottom()
          break
        }

        case 'ask_user': {
          const questions = msg.data?.questions || []
          setMessages((prev) => [
            ...prev,
            { role: 'ai', content: '', blocks: [] },
          ])
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (!last) return prev
            ;(last as any).askUser = {
              questions,
              onSubmit: (_answers: Record<string, string | string[]>) => {},
            }
            return [...prev]
          })
          scrollToBottom()
          break
        }

        case 'result': {
          const isError = msg.data?.is_error || false
          if (isError) {
            setMessages((prev) => [
              ...prev,
              {
                role: 'ai',
                content: `❌ ${msg.data?.content || '未知错误'}`,
                isError: true,
              },
            ])
          }
          // 标记之前流式消息为完成
          setMessages((prev) =>
            prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
          )
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
          setMessages((prev) =>
            prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
          )
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
          setMessages((prev) =>
            prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
          )
          setRunState('done')
          break
      }
    })

    return () => {
      client.disconnect()
    }
  }, [])

  // 发送初始需求
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

    try {
      await client.start(userInput, context)
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

  // 中断
  const handleInterrupt = () => {
    clientRef.current?.interrupt()
  }

  // 新建会话
  const handleNewSession = () => {
    clientRef.current?.disconnect()
    setMessages([])
    setRunState('idle')
    onNewSession?.()
  }

  // 渲染代码块（Markdown 中的 ``` 块）
  const renderContent = (content: string) => {
    if (!content) return null
    // 简易 Markdown 代码块渲染
    const parts = content.split(/(```\w*\n[\s\S]*?```)/g)
    return parts.map((part, i) => {
      const codeMatch = part.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeMatch) {
        const lang = codeMatch[1] || 'text'
        const code = codeMatch[2]
        return (
          <div key={i} style={{ margin: '8px 0' }}>
            <div
              style={{
                background: '#1e1e1e',
                color: '#d4d4d4',
                padding: '4px 8px',
                borderRadius: '4px 4px 0 0',
                fontSize: 10,
                display: 'inline-block',
              }}
            >
              {lang}
            </div>
            <pre
              style={{
                background: '#1e1e1e',
                color: '#d4d4d4',
                padding: 12,
                borderRadius: '0 0 8px 8px',
                fontSize: 11,
                overflow: 'auto',
                maxHeight: 400,
                margin: 0,
              }}
            >
              <code>{code}</code>
            </pre>
          </div>
        )
      }
      return (
        <span key={i} style={{ whiteSpace: 'pre-wrap' }}>
          {part}
        </span>
      )
    })
  }

  // 渲染单条消息
  const renderMessage = (
    msg: ChatMessage & {
      actionCard?: ActionCardData
      dataBlock?: DataBlockData
      askUser?: { questions: any[]; onSubmit: (answers: Record<string, string | string[]>) => void }
    },
    idx: number
  ) => {
    const isUser = msg.role === 'user'

    // ask_user 渲染
    if (msg.askUser) {
      return (
        <div
          key={idx}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
            <RobotOutlined style={{ fontSize: 12, color: '#52c41a' }} />
            <span style={{ fontSize: 12, color: '#52c41a' }}>AI 助手</span>
          </div>
          <AskUserPanel
            questions={msg.askUser.questions}
            onSubmit={msg.askUser.onSubmit}
            clientRef={clientRef}
          />
        </div>
      )
    }

    // action_card 渲染
    if (msg.actionCard) {
      return (
        <div
          key={idx}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
            <RobotOutlined style={{ fontSize: 12, color: '#52c41a' }} />
            <span style={{ fontSize: 12, color: '#52c41a' }}>AI 助手</span>
          </div>
          <ActionCard data={msg.actionCard} onAction={onAction} />
        </div>
      )
    }

    // data_block 渲染
    if (msg.dataBlock) {
      return (
        <div
          key={idx}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
            <RobotOutlined style={{ fontSize: 12, color: '#52c41a' }} />
            <span style={{ fontSize: 12, color: '#52c41a' }}>AI 助手</span>
          </div>
          <DataBlock data={msg.dataBlock} />
        </div>
      )
    }

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
              <Text
                ellipsis={{ tooltip: msg.content }}
                style={{ fontSize: 12, maxWidth: 400 }}
              >
                {msg.content}
              </Text>
            )}
          </div>
        ) : (
          <div
            style={{
              maxWidth: '90%',
              padding: '8px 12px',
              borderRadius: 8,
              background: isUser
                ? '#e6f7ff'
                : msg.isError
                ? '#fff2f0'
                : '#f5f5f5',
              border: isUser
                ? '1px solid #91d5ff'
                : msg.isError
                ? '1px solid #ffccc7'
                : '1px solid #d9d9d9',
              fontSize: 13,
              wordBreak: 'break-word',
            }}
          >
            {/* 思考过程 */}
            {msg.thinking && (
              <Collapse
                size="small"
                ghost
                items={[
                  {
                    key: 'thinking',
                    label: (
                      <span style={{ fontSize: 11, color: '#888' }}>
                        💭 思考过程
                      </span>
                    ),
                    children: (
                      <pre
                        style={{
                          fontSize: 11,
                          color: '#888',
                          whiteSpace: 'pre-wrap',
                          margin: 0,
                          maxHeight: 200,
                          overflow: 'auto',
                        }}
                      >
                        {msg.thinking}
                      </pre>
                    ),
                  },
                ]}
                style={{
                  marginBottom: msg.content ? 6 : 0,
                  background: 'transparent',
                }}
              />
            )}
            {renderContent(msg.content)}
          </div>
        )}
      </div>
    )
  }

  const isActive = runState === 'running'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 标题栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
          flexShrink: 0,
        }}
      >
        <Space>
          <RobotOutlined />
          <span style={{ fontWeight: 500 }}>AI 助手</span>
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
        <Space>
          {headerExtra}
          <Button size="small" icon={<ReloadOutlined />} onClick={handleNewSession}>
            新建会话
          </Button>
        </Space>
      </div>

      {/* 消息列表 */}
      <div style={{ flex: 1, overflow: 'auto', marginBottom: 12 }}>
        {messages.length === 0 ? (
          <Empty
            description={placeholder}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 60 }}
          />
        ) : (
          messages.map((msg, idx) => renderMessage(msg as any, idx))
        )}
        {isActive && (
          <div style={{ textAlign: 'center', padding: 8 }}>
            <Spin size="small" />{' '}
            <span style={{ fontSize: 12, color: '#888' }}>AI 正在思考...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, flexShrink: 0, position: 'relative' }}>
        <SlashCommandPalette
          commands={slashCommands}
          filterPrefix={slashPrefix}
          visible={slashActive}
          selectedIndex={slashSelectedIdx}
          onSelect={handleSelectSlashCommand}
        />
        <TextArea
          ref={textareaRef}
          rows={3}
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            const result = scanSlashTrigger(
              e.target.value,
              (e.target as HTMLTextAreaElement).selectionStart || 0
            )
            setSlashActive(result.active)
            setSlashPrefix(result.prefix)
            setSlashStartIdx(result.startIdx)
            if (result.active) setSlashSelectedIdx(0)
          }}
          onKeyDown={(e) => {
            if (!slashActive) return
            const filtered = slashCommands.filter((c) =>
              c.toLowerCase().startsWith(slashPrefix.toLowerCase())
            )
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setSlashSelectedIdx((prev) =>
                Math.min(prev + 1, filtered.length - 1)
              )
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setSlashSelectedIdx((prev) => Math.max(prev - 1, 0))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              e.stopPropagation()
              const cmd = filtered[slashSelectedIdx]
              if (cmd) handleSelectSlashCommand(cmd)
            } else if (e.key === 'Escape') {
              e.preventDefault()
              setSlashActive(false)
            } else if (e.key === 'Tab') {
              e.preventDefault()
              // 计算所有匹配命令的最长公共前缀
              let common = filtered.length > 0 ? filtered[0] : ''
              for (let i = 1; i < filtered.length; i++) {
                while (!filtered[i].toLowerCase().startsWith(common.toLowerCase())) {
                  common = common.slice(0, -1)
                  if (!common) break
                }
                if (!common) break
              }
              // 公共前缀比当前输入长 → 补全到公共前缀
              if (common.length > slashPrefix.length) {
                const before = input.slice(0, slashStartIdx)
                const afterSlash = input.slice(slashStartIdx + 1 + slashPrefix.length)
                const newValue = before + '/' + common + afterSlash
                setInput(newValue)
                setSlashPrefix(common)
                setSlashSelectedIdx(0)
                // 光标定位到补全内容末尾
                const cursorPos = slashStartIdx + 1 + common.length
                setTimeout(() => {
                  const el = textareaRef.current?.resizableTextArea?.textArea
                  if (el) {
                    el.focus()
                    el.setSelectionRange(cursorPos, cursorPos)
                  }
                }, 0)
              } else if (filtered.length > 0) {
                // 公共前缀已达上限，循环切换选中命令
                setSlashSelectedIdx((prev) =>
                  (prev + 1) % filtered.length
                )
              }
            }
          }}
          onPressEnter={(e) => {
            if (slashActive) return
            if (!e.shiftKey) {
              e.preventDefault()
              if (runState === 'idle') {
                handleSend()
              } else {
                handleSendFollowup()
              }
            }
          }}
          placeholder={isActive ? '输入后续消息追问...' : placeholder}
        />
        <div
          style={{
            display: 'flex',
            gap: 8,
            marginTop: 8,
            justifyContent: 'flex-end',
          }}
        >
          {isActive && (
            <Button danger icon={<StopOutlined />} onClick={handleInterrupt}>
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
    </div>
  )
}

export default AiChatPanel
export { ActionCard, DataBlock }

/**
 * AiWorkbench - 独立 AI 工作台页面 (/ai)
 *
 * 布局：左侧会话列表 + 右侧全屏 AiChatPanel。
 * 支持会话管理（新建/切换/删除）、上下文选择、会话恢复。
 */

import { useState, useEffect, useCallback } from 'react'
import { Layout, Select, Button } from 'antd'
import { RobotOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import AiChatPanel from '../../components/AiChatPanel'
import SessionList from '../../components/SessionList'
import { listContexts, getSession } from '../../services/session'
import type { ContextInfo, SessionMeta } from '../../services/session'
import type { ActionHandlerResult } from '../../components/AiChatPanel'
import type { ChatMessage } from '../../components/AiChatPanel'

const { Sider, Content } = Layout

function AiWorkbench() {
  const [contexts, setContexts] = useState<ContextInfo[]>([])
  const [currentContext, setCurrentContext] = useState('general')
  const [activeSession, setActiveSession] = useState<SessionMeta | null>(null)
  const [initialMessages, setInitialMessages] = useState<ChatMessage[] | undefined>()
  const [refreshKey, setRefreshKey] = useState(0)
  const [collapsed, setCollapsed] = useState(true)

  // 加载可用的 context 列表
  useEffect(() => {
    listContexts()
      .then((data) => {
        setContexts(data.contexts || [])
        setCurrentContext(data.default_context || 'general')
      })
      .catch(() => {
        setContexts([{ key: 'general', description: '通用', placeholder: '描述你想做的事情...' }])
      })
  }, [])

  // 选择会话 → 加载消息历史
  const handleSelectSession = useCallback(async (session: SessionMeta) => {
    setActiveSession(session)
    setCurrentContext(session.context || 'general')
    try {
      const data = await getSession(session.id)
      // 转换后端消息格式为前端 ChatMessage 格式
      const msgs = (data.messages || []).map((msg: any) => {
        const blocks: any[] = msg.data?.blocks || []
        const isUser = msg.type === 'user'
        // AI 消息的文本在 blocks 中提取
        const content = msg.data?.content
          || blocks.filter((b: any) => b.kind === 'text').map((b: any) => b.content).join('\n')
        const thinking = blocks.filter((b: any) => b.kind === 'thinking').map((b: any) => b.content).join('\n') || undefined
        const isToolCall = blocks.some((b: any) => b.kind === 'tool_use' || b.kind === 'tool_result')
        return {
          role: isUser ? 'user' as const : 'ai' as const,
          content,
          blocks,
          thinking,
          isToolCall,
          isError: msg.data?.is_error || false,
          isStreaming: false,
        }
      })
      setInitialMessages(msgs)
    } catch {
      setInitialMessages([])
    }
  }, [])

  // 新建会话（延迟刷新等 fire-and-forget 的 save_message 写完索引）
  const handleNewSession = useCallback(() => {
    setActiveSession(null)
    setInitialMessages(undefined)
    setTimeout(() => setRefreshKey((k) => k + 1), 500)
  }, [])

  // 上下文选择器变更
  const handleContextChange = (value: string) => {
    setCurrentContext(value)
  }

  // action_card 回调
  const handleAction = async (key: string, _payload: any): Promise<ActionHandlerResult> => {
    // /ai 页面的通用 action 处理（可扩展）
    return { success: true }
  }

  const selectedPlaceholder = contexts.find((c) => c.key === currentContext)?.placeholder

  return (
    <Layout style={{ height: 'calc(100vh - 160px)', background: '#fff' }}>
      <Sider
        width={collapsed ? 0 : 280}
        style={{
          background: '#fafafa',
          borderRight: collapsed ? 'none' : '1px solid #f0f0f0',
          overflow: 'hidden',
          transition: 'width 0.2s',
        }}
      >
        {!collapsed && (
          <SessionList
            onSelect={handleSelectSession}
            activeSessionId={activeSession?.id}
            refreshKey={refreshKey}
          />
        )}
      </Sider>
      <Content style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column' }}>
        {/* 上下文选择器 */}
        <div
          style={{
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexShrink: 0,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? '展开会话列表' : '折叠会话列表'}
          />
          <RobotOutlined />
          <Select
            value={currentContext}
            onChange={handleContextChange}
            style={{ width: 160 }}
            size="small"
            options={contexts.map((ctx) => ({
              value: ctx.key,
              label: `${ctx.description} (${ctx.key})`,
            }))}
          />
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          <AiChatPanel
            context={currentContext}
            placeholder={selectedPlaceholder}
            initialMessages={initialMessages}
            onAction={handleAction}
            sessionId={activeSession?.id}
            onNewSession={handleNewSession}
          />
        </div>
      </Content>
    </Layout>
  )
}

export default AiWorkbench

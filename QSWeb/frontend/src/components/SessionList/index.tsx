/**
 * SessionList - AI 会话历史列表
 *
 * 展示所有历史会话，支持选中、新建、删除操作。
 * 列表项显示：标题、context 标签、更新时间、消息数量。
 */

import { useState, useEffect, useCallback } from 'react'
import { List, Button, Tag, Popconfirm, message, Typography, Input } from 'antd'
import { DeleteOutlined, MessageOutlined, EditOutlined } from '@ant-design/icons'
import { listSessions, deleteSession, renameSession } from '../../services/session'
import type { SessionMeta } from '../../services/session'

const { Text } = Typography

interface SessionListProps {
  onSelect: (session: SessionMeta) => void
  activeSessionId?: string
  refreshKey?: number  // 外部控制刷新
}

function SessionList({ onSelect, activeSessionId, refreshKey }: SessionListProps) {
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const loadSessions = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listSessions()
      setSessions(data)
    } catch {
      message.error('加载会话列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions, refreshKey])

  const handleRename = async (sessionId: string) => {
    if (!editTitle.trim()) {
      setEditingId(null)
      return
    }
    try {
      await renameSession(sessionId, editTitle.trim())
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: editTitle.trim() } : s))
      )
      message.success('已重命名')
    } catch {
      message.error('重命名失败')
    }
    setEditingId(null)
  }

  const handleDelete = async (sessionId: string) => {
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      message.success('已删除会话')
    } catch {
      message.error('删除失败')
    }
  }

  const contextColorMap: Record<string, string> = {
    general: 'default',
    factor: 'blue',
    backtest: 'green',
    risk: 'orange',
    portfolio: 'purple',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #f0f0f0',
          flexShrink: 0,
        }}
      >
        <Text strong style={{ fontSize: 14 }}>
          会话列表
        </Text>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <List
          loading={loading}
          dataSource={sessions}
          locale={{ emptyText: '暂无历史会话' }}
          renderItem={(item) => (
            <List.Item
              onClick={() => onSelect(item)}
              style={{
                padding: '10px 16px',
                cursor: 'pointer',
                background: activeSessionId === item.id ? '#e6f7ff' : undefined,
                borderLeft:
                  activeSessionId === item.id
                    ? '3px solid #1677ff'
                    : '3px solid transparent',
              }}
              extra={
                <Popconfirm
                  title="确定删除此会话？"
                  onConfirm={(e) => {
                    e?.stopPropagation()
                    handleDelete(item.id)
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              }
            >
              <List.Item.Meta
                avatar={
                  <MessageOutlined
                    style={{
                      fontSize: 16,
                      color:
                        activeSessionId === item.id ? '#1677ff' : '#999',
                    }}
                  />
                }
                title={
                  editingId === item.id ? (
                    <Input
                      size="small"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onPressEnter={() => handleRename(item.id)}
                      onBlur={() => handleRename(item.id)}
                      autoFocus
                      style={{ width: 160 }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Text
                        ellipsis
                        onDoubleClick={(e) => {
                          e.stopPropagation()
                          setEditingId(item.id)
                          setEditTitle(item.title || '新会话')
                        }}
                        style={{
                          maxWidth: 140,
                          fontWeight: activeSessionId === item.id ? 500 : undefined,
                          cursor: 'pointer',
                        }}
                        title="双击重命名"
                      >
                        {item.title || '新会话'}
                      </Text>
                      <EditOutlined
                        style={{ fontSize: 10, color: '#bbb', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditingId(item.id)
                          setEditTitle(item.title || '新会话')
                        }}
                      />
                      <Tag
                        color={contextColorMap[item.context] || 'default'}
                        style={{ fontSize: 10, lineHeight: '16px' }}
                      >
                        {item.context}
                      </Tag>
                    </div>
                  )
                }
                description={
                  <div style={{ fontSize: 11, color: '#999' }}>
                    <span>{item.message_count} 条消息</span>
                    <span style={{ marginLeft: 8 }}>{item.updated_at?.slice(0, 16)}</span>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </div>
    </div>
  )
}

export default SessionList

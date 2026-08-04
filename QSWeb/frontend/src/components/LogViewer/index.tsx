/**
 * LogViewer — 实时日志查看器
 *
 * 终端风格（黑底绿字），自动滚到底部（手动上滚时暂停），
 * 关键词搜索/高亮，运行中每 2s 轮询增量日志。
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Input, Tag, Empty } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { getRunLog, type RunLogResponse } from '../../services/mining'

interface LogViewerProps {
  taskId: string
  runId: string
  isRunning: boolean
}

function LogViewer({ taskId, runId, isRunning }: LogViewerProps) {
  const [lines, setLines] = useState<string[]>([])
  const [eof, setEof] = useState(false)
  const [status, setStatus] = useState<string>('unknown')
  const [searchTerm, setSearchTerm] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const autoScrollRef = useRef(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const offsetRef = useRef(0)          // ref 追踪 offset，避免 fetchLog 被频繁重建
  const fetchingRef = useRef(false)    // 防止并发请求

  // 检测用户是否手动上滚
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const { scrollTop, scrollHeight, clientHeight } = el
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 50
  }, [])

  // 自动滚到底部
  const scrollToBottom = useCallback(() => {
    if (!autoScrollRef.current) return
    const el = containerRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [])

  // 拉取日志（fetchLog 只依赖 taskId/runId，offset 走 ref 避免重建）
  const fetchLog = useCallback(async () => {
    if (fetchingRef.current) return // 防止并发
    fetchingRef.current = true
    try {
      const data = (await getRunLog(taskId, runId, offsetRef.current, 500)) as unknown as RunLogResponse
      if (data.lines && data.lines.length > 0) {
        setLines((prev) => [...prev, ...data.lines])
      }
      offsetRef.current = data.next_offset
      setEof(data.eof)
      setStatus(data.status)
    } catch {
      // 轮询失败静默
    } finally {
      fetchingRef.current = false
    }
  }, [taskId, runId])

  // taskId/runId 切换时重置并加载
  useEffect(() => {
    setLines([])
    offsetRef.current = 0
    setEof(false)
    setStatus('unknown')
    fetchLog()
  }, [fetchLog])

  // 滚动到底部
  useEffect(() => {
    scrollToBottom()
  }, [lines.length, scrollToBottom])

  // 轮询（fetchLog 稳定不重建，timer 也稳定）
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    if (eof || status === 'completed' || status === 'failed') {
      return
    }

    timerRef.current = setInterval(fetchLog, 2000)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [eof, status, fetchLog])

  // 过滤和搜索高亮
  const filteredLines = searchTerm
    ? lines.filter((line) => line.toLowerCase().includes(searchTerm.toLowerCase()))
    : lines

  const highlightText = (text: string, term: string) => {
    if (!term) return text
    const parts = text.split(new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
    return parts.map((part, i) =>
      part.toLowerCase() === term.toLowerCase()
        ? <mark key={i} style={{ background: '#ff0', color: '#000', padding: '0 2px' }}>{part}</mark>
        : part
    )
  }

  const statusTag = () => {
    if (status === 'completed') return <Tag color="success">已完成</Tag>
    if (status === 'failed') return <Tag color="error">失败</Tag>
    if (status === 'running') return <Tag color="processing">运行中</Tag>
    return null
  }

  return (
    <div>
      {/* 工具栏 */}
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索关键词…"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ width: 260 }}
          allowClear
          size="small"
        />
        {statusTag()}
        {!isRunning && status !== 'running' && eof && (
          <span style={{ fontSize: 12, color: '#999' }}>进程已结束</span>
        )}
        <span style={{ fontSize: 12, color: '#999' }}>
          {lines.length} 行
        </span>
      </div>

      {/* 日志内容 */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          height: 460,
          background: '#1e1e1e',
          color: '#4ec9b0',
          fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
          fontSize: 12,
          lineHeight: '20px',
          padding: '8px 12px',
          borderRadius: 6,
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {filteredLines.length === 0 && !isRunning && status !== 'running' ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无日志"
            style={{ marginTop: 60 }}
          />
        ) : filteredLines.length === 0 ? (
          <div style={{ color: '#666' }}>等待日志输出…</div>
        ) : (
          filteredLines.map((line, i) => (
            <div key={i}>{highlightText(line, searchTerm)}</div>
          ))
        )}
      </div>
    </div>
  )
}

export default LogViewer

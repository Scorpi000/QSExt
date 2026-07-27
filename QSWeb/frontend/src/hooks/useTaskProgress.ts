/**
 * useTaskProgress Hook
 *
 * 通过 WebSocket 连接后端，实时获取异步任务进度。
 */

import { useState, useEffect, useRef, useCallback } from 'react'

export interface TaskProgress {
  task_id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  progress_message: string
  error?: string
  created_at?: string
  started_at?: string
  completed_at?: string
}

interface UseTaskProgressOptions {
  /** 轮询模式：不使用 WebSocket，改用 HTTP 轮询（毫秒间隔） */
  pollingInterval?: number
  /** WebSocket 连接 URL 前缀 */
  wsBaseUrl?: string
}

function getWsBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

/**
 * 订阅异步任务进度
 *
 * @param taskId - 任务 ID，为 null 时不连接
 * @param options - 配置选项
 * @returns { task, isConnected, error }
 */
export function useTaskProgress(
  taskId: string | null,
  options: UseTaskProgressOptions = {}
) {
  const { pollingInterval, wsBaseUrl = getWsBaseUrl() } = options
  const [task, setTask] = useState<TaskProgress | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 连接回调（提取为 ref 以避免闭包问题）
  const connectWs = useCallback(
    (id: string) => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }

      const url = `${wsBaseUrl}/ws/tasks/${id}`
      try {
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          setIsConnected(true)
          setError(null)
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data !== 'pong') {
              setTask(data as TaskProgress)
            }
          } catch {
            // 非 JSON 消息忽略
          }
        }

        ws.onerror = () => {
          setError('WebSocket 连接失败')
          setIsConnected(false)
        }

        ws.onclose = () => {
          setIsConnected(false)
          // 任务未完成时自动重连（最多重连一次）
          setTask((prev) => {
            if (prev && prev.status !== 'completed' && prev.status !== 'failed') {
              reconnectTimerRef.current = setTimeout(() => {
                connectWs(id)
              }, 3000)
            }
            return prev
          })
        }
      } catch {
        setError('WebSocket 连接失败，使用轮询模式')
      }
    },
    [wsBaseUrl]
  )

  // 轮询回调
  const fetchProgress = useCallback(
    async (id: string) => {
      try {
        const resp = await fetch(`/api/backtest/tasks/${id}`)
        if (resp.ok) {
          const data = await resp.json()
          setTask(data as TaskProgress)
        }
      } catch {
        // 轮询失败静默处理
      }
    },
    []
  )

  useEffect(() => {
    if (!taskId) {
      setTask(null)
      setIsConnected(false)
      return
    }

    if (pollingInterval) {
      // 轮询模式
      fetchProgress(taskId)
      const timer = setInterval(() => fetchProgress(taskId), pollingInterval)
      return () => clearInterval(timer)
    }

    // WebSocket 模式
    connectWs(taskId)

    // 心跳
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 15000)

    return () => {
      clearInterval(heartbeat)
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [taskId, pollingInterval, connectWs, fetchProgress])

  return { task, isConnected, error }
}

export default useTaskProgress

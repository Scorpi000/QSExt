/**
 * AI 因子助手 WebSocket 客户端
 *
 * 连接到后端 /ws/ai/chat，基于 ClaudeSDKClient 的双向交互协议。
 *
 * 协议:
 *   start(prompt)      → {"action": "start", "prompt": "..."}
 *   sendQuery(prompt)  → {"action": "query", "prompt": "..."}
 *   interrupt()        → {"action": "interrupt"}
 *   disconnect()       → {"action": "disconnect"}
 */

export type AiMessageType =
  | 'system'
  | 'assistant'
  | 'user'
  | 'tool_use'
  | 'tool_result'
  | 'result'
  | 'stream'
  | 'error'
  | 'done'
  | 'interrupted'

export interface AiBlock {
  kind: 'text' | 'tool_use' | 'tool_result' | 'thinking'
  content?: string
  tool_name?: string
  tool_input?: Record<string, any>
  id?: string
  tool_use_id?: string
}

export interface AiMessage {
  type: AiMessageType
  data?: {
    content?: string
    blocks?: AiBlock[]
    message?: string
    is_error?: boolean
    raw?: string
  }
}

type MessageHandler = (msg: AiMessage) => void

export class AiChatClient {
  private ws: WebSocket | null = null
  private handlers: MessageHandler[] = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private url: string
  private _isConnected = false
  private pendingStart: { prompt: string } | null = null

  constructor(url: string = 'ws://localhost:28000/ws/ai/chat') {
    this.url = url
  }

  get isConnected() {
    return this._isConnected
  }

  /** 建立 WebSocket 连接 */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve()
        return
      }

      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this._isConnected = true
        // 如果有待发送的 start，在连接建立后立即发送
        if (this.pendingStart) {
          this.ws!.send(JSON.stringify({
            action: 'start',
            prompt: this.pendingStart.prompt,
          }))
          this.pendingStart = null
        }
        resolve()
      }

      this.ws.onmessage = (event) => {
        try {
          const msg: AiMessage = JSON.parse(event.data)
          this.handlers.forEach((h) => h(msg))
        } catch {
          // ignore parse errors
        }
      }

      this.ws.onerror = () => {
        this._isConnected = false
        if (this.ws?.readyState !== WebSocket.OPEN) {
          reject(new Error('WebSocket 连接失败'))
        }
      }

      this.ws.onclose = () => {
        this._isConnected = false
      }
    })
  }

  /** 启动 Claude 会话并发送初始需求 */
  async start(prompt: string): Promise<void> {
    await this.connect()
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'start', prompt }))
    } else {
      // 如果还没连上，暂存等待 onopen 发送
      this.pendingStart = { prompt }
    }
  }

  /** 发送后续消息 */
  sendQuery(prompt: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接')
    }
    this.ws.send(JSON.stringify({ action: 'query', prompt }))
  }

  /** 中断 Claude 当前操作 */
  interrupt(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'interrupt' }))
    }
  }

  /** 注册消息回调，返回取消注册函数 */
  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  /** 断开连接并通知后端清理 Claude 进程 */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ action: 'disconnect' }))
        } catch {
          // ignore
        }
      }
      this.ws.close()
      this.ws = null
    }
    this._isConnected = false
    this.pendingStart = null
  }
}

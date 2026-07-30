/**
 * AI 因子助手 WebSocket 客户端
 *
 * 连接到后端 /ws/ai/chat，流式收发消息。
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
  | 'stopped'

export interface AiBlock {
  kind: 'text' | 'tool_use' | 'tool_result'
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

  constructor(url: string = 'ws://localhost:28000/ws/ai/chat') {
    this.url = url
  }

  get isConnected() {
    return this._isConnected
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve()
        return
      }

      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this._isConnected = true
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

  send(prompt: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接')
    }
    this.ws.send(JSON.stringify({ prompt }))
  }

  stop(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'stop' }))
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this._isConnected = false
  }
}

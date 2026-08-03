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
  | 'init'
  | 'assistant'
  | 'user'
  | 'tool_use'
  | 'tool_result'
  | 'result'
  | 'stream'
  | 'error'
  | 'done'
  | 'interrupted'
  | 'action_card'
  | 'data_block'
  | 'ask_user'

export interface ActionCardAction {
  key: string
  label: string
  style: 'primary' | 'default' | 'danger'
}

export interface ActionCardData {
  kind: string
  title: string
  summary?: Record<string, any>
  actions: ActionCardAction[]
  payload?: any
}

export interface DataBlockData {
  kind: string  // 'factor_table' | 'chart' | 'dag' | 'risk_heatmap' | etc.
  payload: any
}

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
    // action_card / data_block 类型时直接使用顶层字段
    kind?: string
    title?: string
    summary?: Record<string, any>
    actions?: ActionCardAction[]
    payload?: any
  }
}

type MessageHandler = (msg: AiMessage) => void

export class AiChatClient {
  private ws: WebSocket | null = null
  private handlers: MessageHandler[] = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private url: string
  private _isConnected = false
  private pendingStart: { prompt: string; context?: string } | null = null

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
            context: this.pendingStart.context || 'general',
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

      this.ws.onclose = (event) => {
        this._isConnected = false
        // 非正常关闭时通知 handlers
        if (event.code !== 1000 && event.code !== 1005) {
          const closedMsg: AiMessage = {
            type: 'error',
            data: { message: `WebSocket 连接已断开 (code=${event.code})` },
          }
          this.handlers.forEach((h) => h(closedMsg))
        }
      }
    })
  }

  /** 启动 Claude 会话并发送初始需求 */
  async start(prompt: string, context: string = 'general'): Promise<void> {
    await this.connect()
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'start', prompt, context }))
    } else {
      // 连接后瞬间断开：重连一次
      if (this.ws && this.ws.readyState > WebSocket.OPEN) {
        // CLOSING(2) 或 CLOSED(3)
        this.ws = null
        await this.connect()
      }
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'start', prompt, context }))
      } else {
        throw new Error('WebSocket 连接失败，请重试')
      }
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

  /** 回答 AskUserQuestion */
  sendAnswer(answers: Record<string, string | string[]>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接')
    }
    this.ws.send(JSON.stringify({ action: 'answer', answers }))
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

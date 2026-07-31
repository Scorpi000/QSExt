/**
 * AI 会话管理 API 客户端
 */

import api from './api'

export interface SessionMeta {
  id: string
  title: string
  context: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface SessionData {
  id: string
  context: string
  messages: any[]
  created_at: string
  updated_at: string
}

export interface ContextInfo {
  key: string
  description: string
  placeholder: string
}

export interface ContextsResponse {
  contexts: ContextInfo[]
  default_context: string
  route_context_map: Record<string, string>
}

/** 获取可用 AI context 列表 */
export async function listContexts(): Promise<ContextsResponse> {
  return api.get('/ai/contexts') as unknown as Promise<ContextsResponse>
}

/** 列出所有会话 */
export async function listSessions(): Promise<SessionMeta[]> {
  const data = await api.get('/ai/sessions') as unknown as { sessions: SessionMeta[] }
  return data.sessions || []
}

/** 获取单个会话详情 */
export async function getSession(sessionId: string): Promise<SessionData> {
  return api.get(`/ai/sessions/${sessionId}`) as unknown as Promise<SessionData>
}

/** 删除会话 */
export async function deleteSession(sessionId: string): Promise<void> {
  return api.delete(`/ai/sessions/${sessionId}`)
}

/** 重命名会话 */
export async function renameSession(sessionId: string, title: string): Promise<void> {
  return api.put(`/ai/sessions/${sessionId}/title`, { title })
}

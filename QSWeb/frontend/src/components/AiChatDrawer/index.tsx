/**
 * AiChatDrawer - 全局 AI 助手 Drawer
 *
 * 包装 AiChatPanel，从当前路由自动推断 context。
 * 被 FAB、Ctrl+K 和页面内"AI 助手"按钮复用。
 *
 * 使用方式:
 *   <AiChatDrawer open={open} onClose={handleClose} />
 *   <AiChatDrawer open={open} onClose={handleClose} explicitContext="factor" />
 */

import { useEffect, useState } from 'react'
import { Drawer } from 'antd'
import { useLocation } from 'react-router-dom'
import AiChatPanel from '../AiChatPanel'
import type { ActionHandlerResult } from '../AiChatPanel'
import { listContexts } from '../../services/session'
import type { ContextsResponse } from '../../services/session'

interface AiChatDrawerProps {
  open: boolean
  onClose: () => void
  /** 显式指定 context（优先级高于路由推断） */
  explicitContext?: string
  /** action_card 回调 */
  onAction?: (key: string, payload: any) => Promise<ActionHandlerResult>
}

function AiChatDrawer({ open, onClose, explicitContext, onAction }: AiChatDrawerProps) {
  const location = useLocation()
  const [configs, setConfigs] = useState<ContextsResponse | null>(null)

  // 加载 context 配置
  useEffect(() => {
    if (open) {
      listContexts().then(setConfigs).catch(() => setConfigs(null))
    }
  }, [open])

  // 推断 context
  const resolvedContext = (() => {
    if (explicitContext) return explicitContext
    if (!configs) return 'general'

    const routeMap = configs.route_context_map || {}
    // 匹配最长的路由前缀
    const match = Object.entries(routeMap)
      .filter(([route]) => location.pathname.startsWith(route))
      .sort((a, b) => b[0].length - a[0].length)
    return match.length > 0 ? match[0][1] : configs.default_context || 'general'
  })()

  // 获取对应 context 的 placeholder
  const placeholder = (() => {
    if (!configs) return undefined
    const ctx = configs.contexts.find((c) => c.key === resolvedContext)
    return ctx?.placeholder || undefined
  })()

  return (
    <Drawer
      title={null}
      open={open}
      onClose={onClose}
      width={520}
      styles={{ body: { padding: '16px' } }}
    >
      <AiChatPanel
        context={resolvedContext}
        placeholder={placeholder}
        onAction={onAction}
      />
    </Drawer>
  )
}

export default AiChatDrawer

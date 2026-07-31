/**
 * AiFactorAssistant - AI 因子助手 Chat 面板（薄包装）
 *
 * 已合并到通用 AiChatPanel + AiChatDrawer 架构。
 * 此组件保留为兼容层，内部使用 AiChatDrawer + context="factor"。
 *
 * @deprecated 新代码请直接使用 AiChatDrawer 并指定 explicitContext="factor"
 */

import { message } from 'antd'
import AiChatDrawer from '../AiChatDrawer'
import { importFactor } from '../../services/import'
import type { ActionHandlerResult } from '../AiChatPanel'

interface AiFactorAssistantProps {
  open: boolean
  onClose: () => void
}

function AiFactorAssistant({ open, onClose }: AiFactorAssistantProps) {
  return (
    <AiChatDrawer
      open={open}
      onClose={onClose}
      explicitContext="factor"
      onAction={async (key, payload): Promise<ActionHandlerResult> => {
        if (key === 'save') {
          const code = payload?.code || ''
          const filename = payload?.filename || 'factor.py'
          if (!code) return { success: false, message: '脚本内容为空' }
          try {
            const result = await importFactor(code, filename) as any
            if (result.success) {
              message.success(`脚本已保存: ${result.saved_path}`)
              return { success: true, message: `已保存到 ${result.saved_path}` }
            }
            return { success: false, message: '导入失败' }
          } catch (err: any) {
            return {
              success: false,
              message: err?.response?.data?.message || err?.message || '导入失败',
            }
          }
        }
        return { success: true }
      }}
    />
  )
}

export default AiFactorAssistant

/**
 * 全局配置 API
 */

import api from './api'

// ─── 类型定义 ─────────────────────────────────────────────────

export interface EngineConfig {
  type: 'CalcEngine' | 'ParallelEngine'
  params: Record<string, any>
}

export interface GlobalConfig {
  cache_dir: string
  use_temp_cache: boolean
  engine: EngineConfig
}

// ─── API 调用 ─────────────────────────────────────────────────

/** GET /api/config */
export const getGlobalConfig = () => {
  return api.get<GlobalConfig>('/config')
}

/** PUT /api/config */
export const updateGlobalConfig = (config: GlobalConfig) => {
  return api.put<{ message: string; config: GlobalConfig }>('/config', config)
}

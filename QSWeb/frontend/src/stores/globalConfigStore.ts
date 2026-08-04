/**
 * 全局配置 Zustand Store
 *
 * 跨页面共享的全局配置状态。
 * - GlobalConfigPanel：写入（saveConfig）
 * - BacktestStudio / MiningStudio：只读（config?.cache_dir, config?.engine）
 * - MainLayout：启动时调用 fetchConfig() 初始化
 */

import { create } from 'zustand'
import type { GlobalConfig } from '../services/globalConfig'
import { getGlobalConfig, updateGlobalConfig } from '../services/globalConfig'

interface GlobalConfigState {
  /** 当前全局配置（null = 尚未加载或加载失败） */
  config: GlobalConfig | null
  /** 是否正在加载 */
  loading: boolean
  /** 错误信息（null = 无错误） */
  error: string | null

  /** 从后端拉取配置 */
  fetchConfig: () => Promise<void>
  /** 保存配置到后端并更新本地状态 */
  saveConfig: (config: GlobalConfig) => Promise<void>
  /** 重置为初始状态 */
  reset: () => void
}

const initialState = {
  config: null,
  loading: false,
  error: null,
}

export const useGlobalConfigStore = create<GlobalConfigState>((set) => ({
  ...initialState,

  fetchConfig: async () => {
    set({ loading: true, error: null })
    try {
      const data = (await getGlobalConfig()) as unknown as GlobalConfig
      set({ config: data, loading: false })
    } catch (e: any) {
      set({
        error: e?.response?.data?.detail || e?.message || '加载全局配置失败',
        loading: false,
      })
    }
  },

  saveConfig: async (config: GlobalConfig) => {
    set({ loading: true, error: null })
    try {
      const resp = (await updateGlobalConfig(config)) as unknown as {
        message: string
        config: GlobalConfig
      }
      set({ config: resp.config, loading: false })
    } catch (e: any) {
      set({
        error: e?.response?.data?.detail || e?.message || '保存全局配置失败',
        loading: false,
      })
    }
  },

  reset: () => set({ ...initialState }),
}))

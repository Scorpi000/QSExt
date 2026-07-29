/**
 * 全局因子池 Zustand Store
 *
 * 跨页面共享的因子池状态管理。
 * 所有页面读写同一个池子实例，增删操作在所有页面间即时同步。
 */

import { create } from 'zustand'
import type { PoolItem } from '../types/pool'

interface FactorPoolState {
  /** 池中因子列表 */
  items: PoolItem[]
  /** 当前选中的因子 ID 集合 */
  selectedIds: Set<string>

  // 操作
  addItems: (newItems: PoolItem[]) => void
  removeItem: (id: string) => void
  toggleSelect: (id: string) => void
  selectAll: () => void
  clearSelection: () => void
  setItems: (items: PoolItem[]) => void
  clear: () => void
}

export const useFactorPoolStore = create<FactorPoolState>((set, get) => ({
  items: [],
  selectedIds: new Set<string>(),

  addItems: (newItems) => {
    const existing = get().items
    const existingIds = new Set(existing.map((i) => i.id))
    const toAdd = newItems.filter((item) => !existingIds.has(item.id))
    if (toAdd.length === 0) return
    set({ items: [...existing, ...toAdd] })
  },

  removeItem: (id) => {
    const items = get().items.filter((item) => item.id !== id)
    const selectedIds = new Set(get().selectedIds)
    selectedIds.delete(id)
    set({ items, selectedIds })
  },

  toggleSelect: (id) => {
    const selectedIds = new Set(get().selectedIds)
    if (selectedIds.has(id)) {
      selectedIds.delete(id)
    } else {
      selectedIds.add(id)
    }
    set({ selectedIds })
  },

  selectAll: () => {
    const ids = get().items.map((item) => item.id)
    set({ selectedIds: new Set(ids) })
  },

  clearSelection: () => {
    set({ selectedIds: new Set() })
  },

  setItems: (items) => {
    set({ items, selectedIds: new Set() })
  },

  clear: () => {
    set({ items: [], selectedIds: new Set() })
  },
}))

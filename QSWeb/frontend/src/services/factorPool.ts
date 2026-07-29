/**
 * 全局因子池 API
 */

import api from './api'
import type { PoolItem, FactorStats } from '../types/pool'

/** 添加因子到池（后端 resolve + 缓存） */
export const addToPool = (items: Partial<PoolItem>[]) => {
  return api.post<{ items: Array<{ item: PoolItem; resolved: boolean }> }>(
    '/pool/factors',
    items
  )
}

/** 获取因子统计信息 */
export const getFactorStats = (item: Partial<PoolItem>) => {
  return api.post<FactorStats>('/pool/factors/stats', item)
}

/** 保存因子池到图数据库 */
export const savePool = (name: string, items: PoolItem[]) => {
  return api.post('/pool/save', items, { params: { name } })
}

/** 从图数据库加载因子池 */
export const loadPool = (name: string) => {
  return api.get<{ name: string; items: PoolItem[] }>(`/pool/load/${name}`)
}

/** 列出已保存的因子池 */
export const listPools = () => {
  return api.get<Array<{ Name: string; CreatedAt: string; FactorCount: number }>>('/pool/list')
}

/** 删除已保存的因子池 */
export const deletePool = (name: string) => {
  return api.delete(`/pool/${name}`)
}

/** 清理因子池（删除因子库后调用） */
export const cleanupPool = (
  poolItems: PoolItem[],
  connId?: string,
  affectedQsids?: string[]
) => {
  return api.post<{ items: PoolItem[] }>(
    '/pool/cleanup',
    { pool_items: poolItems, affected_qsids: affectedQsids },
    { params: connId ? { conn_id: connId } : {} }
  )
}

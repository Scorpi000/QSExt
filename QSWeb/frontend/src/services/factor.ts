/**
 * 因子数据 API
 */

import api from './api'

export interface FactorTable {
  name: string
  db_name: string
  conn_id: string
  factor_count?: number
  description?: string
}

export interface FactorInfo {
  name: string
  table_name: string
  db_name: string
  conn_id: string
  description?: string
  data_type?: string
  last_date?: string
  id_count?: number
}

export interface FactorData {
  data: Record<string, any>
  columns: string[]
  index: string[]
  total_rows: number
  total_columns: number
}

export interface FactorStats {
  id_count: number
  dt_count: number
  first_id: string | null
  last_id: string | null
  first_dt: string | null
  last_dt: string | null
}

// 重连因子库
export const reconnectFactorDB = (connId: string) => {
  return api.post(`/factors/${connId}/reconnect`)
}

// 获取因子表列表
export const getTables = (connId: string) => {
  return api.get<FactorTable[]>(`/factors/${connId}/tables`)
}

// 获取因子列表
export const getFactors = (connId: string, tableName: string) => {
  return api.get<FactorInfo[]>(`/factors/${connId}/tables/${tableName}/factors`)
}

// 获取因子数据
export const getFactorData = (
  connId: string,
  tableName: string,
  factorName: string,
  params?: {
    start_date?: string
    end_date?: string
    limit?: number
  }
) => {
  return api.get<FactorData>(
    `/factors/${connId}/tables/${tableName}/factors/${factorName}/data`,
    { params }
  )
}

// 获取因子统计信息
export const getFactorStats = (
  connId: string,
  tableName: string,
  factorName: string
) => {
  return api.get<FactorStats>(
    `/factors/${connId}/tables/${tableName}/factors/${factorName}/stats`
  )
}

// 获取多个因子数据
export const getMultiFactorData = (
  connId: string,
  tableName: string,
  data: {
    factor_names: string[]
    start_date?: string
    end_date?: string
    ids?: string[]
    limit?: number
  }
) => {
  return api.post<FactorData>(
    `/factors/${connId}/tables/${tableName}/data`,
    data
  )
}

// 获取因子元数据
export const getFactorMetadata = (
  connId: string,
  tableName: string,
  factorName: string
) => {
  return api.get<Record<string, any>>(
    `/factors/${connId}/tables/${tableName}/factors/${factorName}/metadata`
  )
}

// 获取因子表元数据
export const getTableMetadata = (
  connId: string,
  tableName: string
) => {
  return api.get<Record<string, any>>(
    `/factors/${connId}/tables/${tableName}/metadata`
  )
}

// ---------- 表管理 ----------

// 重命名因子表
export const renameTable = (
  connId: string,
  tableName: string,
  newName: string
) => {
  return api.put(`/factors/${connId}/tables/${tableName}/rename`, { new_name: newName })
}

// 批量删除因子表
export const deleteTables = (
  connId: string,
  tableNames: string[]
) => {
  return api.delete(`/factors/${connId}/tables`, { data: { table_names: tableNames } })
}

// 更新因子表元数据
export const updateTableMetadata = (
  connId: string,
  tableName: string,
  metadata: Record<string, any>
) => {
  return api.put(`/factors/${connId}/tables/${tableName}/metadata`, { metadata })
}

// ---------- 因子管理 ----------

// 重命名因子
export const renameFactor = (
  connId: string,
  tableName: string,
  oldName: string,
  newName: string
) => {
  return api.put(
    `/factors/${connId}/tables/${tableName}/factors/${oldName}/rename`,
    { new_name: newName }
  )
}

// 批量删除因子
export const deleteFactors = (
  connId: string,
  tableName: string,
  factorNames: string[]
) => {
  return api.delete(
    `/factors/${connId}/tables/${tableName}/factors`,
    { data: { factor_names: factorNames } }
  )
}

// 更新因子元数据
export const updateFactorMetadata = (
  connId: string,
  tableName: string,
  factorName: string,
  metadata: Record<string, any>
) => {
  return api.put(
    `/factors/${connId}/tables/${tableName}/factors/${factorName}/metadata`,
    { metadata }
  )
}

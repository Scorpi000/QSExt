/**
 * 连接管理 API
 */

import api from './api'

export interface Connection {
  /** QSID 唯一标识（替代旧 UUID id） */
  qsid: string
  name: string
  db_type: string
  description?: string
  args: Record<string, any>
  status: string
  source?: string
  created_at?: string
  updated_at?: string
}

/** 影响分析结果 */
export interface ImpactFactor {
  QSID: string
  Name: string
  FactorTableName?: string
}

export interface ImpactAnalysis {
  factor_db: Record<string, any> | null
  direct_factors: ImpactFactor[]
  indirect_factors: ImpactFactor[]
  factor_tables: Array<{ QSID: string; Name: string }>
  total_affected_factors: number
}

export interface ConnectionCreate {
  name: string
  db_type: string
  description?: string
  args: Record<string, any>
}

export interface ConnectionUpdate {
  name?: string
  description?: string
  args?: Record<string, any>
}

export interface ConnectionTestResult {
  success: boolean
  message: string
  detail?: Record<string, any>
}

// 支持的数据库类型
export const DB_TYPES = [
  { value: 'HDF5DB', label: 'HDF5 数据库', icon: '📁', writable: true },
  { value: 'SQLDB', label: '关系数据库 (SQL)', icon: '🗃️', writable: true },
  { value: 'JYDB', label: '聚源数据库 (JYDB)', icon: '📊', writable: false },
  { value: 'ClickHouseDB', label: 'ClickHouse', icon: '⚡', writable: true },
  { value: 'MongoDB', label: 'MongoDB', icon: '🍃', writable: true },
  { value: 'Neo4jDB', label: 'Neo4j 图数据库', icon: '🔗', writable: true },
]

/** 判断数据库类型是否支持写入操作 */
export function isWritableDB(dbType: string): boolean {
  const def = DB_TYPES.find((d) => d.value === dbType)
  return def?.writable ?? true
}

// 获取所有连接
export const getConnections = () => {
  return api.get<Connection[]>('/connections/')
}

// 获取单个连接
export const getConnection = (qsid: string) => {
  return api.get<Connection>(`/connections/${qsid}`)
}

// 创建连接
export const createConnection = (data: ConnectionCreate) => {
  return api.post<Connection>('/connections/', data)
}

// 更新连接
export const updateConnection = (qsid: string, data: ConnectionUpdate) => {
  return api.put<Record<string, any>>(`/connections/${qsid}`, data)
}

// 删除连接（preview mode，返回影响范围）
export const deleteConnectionPreview = (qsid: string) => {
  return api.delete<{ action: string; impact: ImpactAnalysis }>(`/connections/${qsid}`)
}

// 确认删除连接（级联删除）
export const deleteConnectionConfirm = (qsid: string) => {
  return api.delete(`/connections/${qsid}?confirm=true`)
}

// 获取删除影响范围
export const getImpact = (qsid: string) => {
  return api.get<ImpactAnalysis>(`/connections/${qsid}/impact`)
}

// 测试连接（按 QSID）
export const testConnection = (qsid: string) => {
  return api.post<ConnectionTestResult>(`/connections/${qsid}/test`)
}

// 测试连接（直接传参）
export const testConnectionDirect = (dbType: string, args: Record<string, any>) => {
  return api.post<ConnectionTestResult>(
    `/connections/test?db_type=${encodeURIComponent(dbType)}&args_json=${encodeURIComponent(JSON.stringify(args))}`
  )
}

// 健康检查
export const checkHealth = () => {
  return api.get<{ status: string; message: string }>('/connections/health')
}

/**
 * 连接管理 API
 */

import api from './api'

export interface Connection {
  id: string
  name: string
  db_type: string
  description?: string
  args: Record<string, any>
  status: string
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
export const getConnection = (id: string) => {
  return api.get<Connection>(`/connections/${id}`)
}

// 创建连接
export const createConnection = (data: ConnectionCreate) => {
  return api.post<Connection>('/connections/', data)
}

// 更新连接
export const updateConnection = (id: string, data: ConnectionUpdate) => {
  return api.put<Connection>(`/connections/${id}`, data)
}

// 删除连接
export const deleteConnection = (id: string) => {
  return api.delete(`/connections/${id}`)
}

// 测试连接
export const testConnection = (id: string) => {
  return api.post<ConnectionTestResult>(`/connections/${id}/test`)
}

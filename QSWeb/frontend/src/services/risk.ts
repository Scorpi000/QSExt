/**
 * 风险管理 API
 */

import api from './api'

export interface RiskDBInfo {
  id: string
  name: string
  db_type: string
  description: string
  connected: boolean
}

export interface RiskTableInfo {
  name: string
  is_factor_rt: boolean
  factor_count: number
  dt_count: number
  first_dt: string | null
  last_dt: string | null
}

export interface MatrixData {
  dt: string
  ids: string[]
  data: [number, number, number][]  // [row, col, value]
}

export interface FactorDecompositionData {
  dt: string
  factors: string[]
  factor_count: number
  factor_cov: MatrixData
  specific_risk: {
    ids: string[]
    values: (number | null)[]
  }
}

// 支持的风险库类型
export const RISK_DB_TYPES = [
  { value: 'HDF5RDB', label: 'HDF5 风险库 (RiskDB)', icon: '📁', desc: '基于 HDF5 文件的协方差矩阵风险库 (.hdf5)' },
  { value: 'HDF5FRDB', label: 'HDF5 多因子风险库 (FactorRDB)', icon: '📊', desc: '基于 HDF5 文件的多因子风险库，含因子协方差/特异性风险 (.h5)' },
]

// —— 风险库 CRUD ——

export const getRiskDatabases = () => {
  return api.get<RiskDBInfo[]>('/risk/databases')
}

export const getRiskDatabase = (dbId: string) => {
  return api.get<RiskDBInfo>(`/risk/databases/${dbId}`)
}

export const createRiskDatabase = (data: {
  name: string
  db_type: string
  args: Record<string, any>
  description?: string
}) => {
  return api.post<RiskDBInfo>('/risk/databases', data)
}

export const updateRiskDatabase = (
  dbId: string,
  data: { name?: string; args?: Record<string, any>; description?: string }
) => {
  return api.put<RiskDBInfo>(`/risk/databases/${dbId}`, data)
}

export const deleteRiskDatabase = (dbId: string) => {
  return api.delete(`/risk/databases/${dbId}`)
}

export const testRiskDatabase = (dbId: string) => {
  return api.post<{ success: boolean; message: string }>(`/risk/databases/${dbId}/test`)
}

// —— 风险表浏览 ——

export const getRiskTables = (dbId: string) => {
  return api.get<RiskTableInfo[]>(`/risk/databases/${dbId}/tables`)
}

// —— 风险矩阵 ——

export const getCovariance = (dbId: string, tableName: string, dt: string, limit = 100) => {
  return api.get<MatrixData>(`/risk/tables/${dbId}/${tableName}/covariance`, {
    params: { dt, limit },
  })
}

export const getCorrelation = (dbId: string, tableName: string, dt: string, limit = 100) => {
  return api.get<MatrixData>(`/risk/tables/${dbId}/${tableName}/correlation`, {
    params: { dt, limit },
  })
}

export const getFactorDecomposition = (dbId: string, tableName: string, dt: string, limit = 100) => {
  return api.get<FactorDecompositionData>(
    `/risk/tables/${dbId}/${tableName}/factor-decomposition`,
    { params: { dt, limit } }
  )
}

export const getTableDates = (dbId: string, tableName: string) => {
  return api.get<string[]>(`/risk/tables/${dbId}/${tableName}/dates`)
}

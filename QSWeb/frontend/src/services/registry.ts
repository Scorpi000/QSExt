/**
 * QSRegistry API
 */

import api from './api'

export interface FactorSearchResult {
  name: string
  qsid: string
  factor_class: string
  data_type: string
  operator_type: string
  operator_name: string
  similarity?: number
}

export interface FactorDetail {
  name: string
  qsid: string
  factor_class: string
  data_type: string
  module_path: string
  description: string
  operator_name: string
  operator_type: string
  operator_qsid: string
  descriptors: { name: string; qsid: string }[]
  dependents: { name: string; qsid: string }[]
  dependency_depth: number
  tags: string[]
}

export interface DAGData {
  root_qsid: string
  nodes: DAGNode[]
  edges: DAGEdge[]
}

export interface DAGNode {
  qsid: string
  name: string
  factor_class: string
  operator_type: string
  data_type: string
  x?: number
  y?: number
}

export interface DAGEdge {
  source: string
  target: string
  order: number
}

export interface OperatorInfo {
  name: string
  qsid: string
  operator_type: string
  class_name: string
  module_path: string
  data_type: string
  arity: number | null
  description: string
}

// 关键词搜索
export const searchFactors = (q: string, limit = 20) => {
  return api.get<FactorSearchResult[]>('/factors/search', { params: { q, limit } })
}

// 语义搜索
export const semanticSearch = (q: string, limit = 20) => {
  return api.get<FactorSearchResult[]>('/factors/search/semantic', { params: { q, limit } })
}

// 获取因子详情
export const getFactorDetail = (qsid: string) => {
  return api.get<FactorDetail>(`/factors/${qsid}`)
}

// 获取因子 DAG
export const getFactorDAG = (qsid: string) => {
  return api.get<DAGData>(`/factors/${qsid}/dag`)
}

// 获取算子列表
export const getOperators = (operatorType?: string) => {
  return api.get<OperatorInfo[]>('/operators', { params: { operator_type: operatorType } })
}

// 获取 QSArgs JSON Schema
export const getArgsSchema = (className: string) => {
  return api.get<Record<string, any>>(`/args/${className}/schema`)
}

// 创建衍生因子
export const createDerivativeFactor = (params: {
  name: string
  operator_qsid: string
  descriptor_qsids: string
  factor_args_json?: string
}) => {
  return api.post('/factors/derivative', null, { params })
}

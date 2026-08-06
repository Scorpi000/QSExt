/**
 * 策略工作台 API
 */

import api from './api'

// ─── 类型定义 ─────────────────────────────────────────────────

export interface OperatorConfig {
  SignalType: string
  InitCash: number
  ShortAllowed: boolean
}

export interface StrategyMeta {
  Name: string
  QSID?: string
  TargetTable: string
  IDType: string
  OperatorConfig: OperatorConfig
  FactorDeps: Record<string, string[]>
  StrategyDeps: Record<string, Record<string, string>>
  DBDeps: Record<string, string>
  ModelArgs: Record<string, string>
  Author: string
  Description: string
  Tags: string[]
  MaxLookBack: number
  DefScriptPath: string
}

export interface StrategySearchResult {
  QSID: string
  Name: string
  TargetTable: string
  IDType: string
  Author: string
  Description: string
  Tags: string[]
  DefScriptPath: string
  UpdatedAt?: string
  Similarity?: number
}

export interface StrategyImportPreviewResponse {
  valid: boolean
  meta?: StrategyMeta
  errors: string[]
  warnings: string[]
}

export interface FactorRef {
  name: string
  source: 'db' | 'registry'
  conn_id?: string
  table_name?: string
}

export interface StrategyBacktestRequest {
  code?: string
  strategy_qsid?: string
  factor_refs: FactorRef[]
  model_args: Record<string, any>
  operator_config?: OperatorConfig
  start_date: string
  end_date: string
  dt_mode: 'natural' | 'trading'
  descriptor_ids?: string[]
}

export interface StrategyBacktestResult {
  task_id: string
}

export interface ResultNode {
  key: string
  label: string
  type: 'branch' | 'series' | 'dataframe' | 'scalar'
  children?: ResultNode[]
  data?: any
}

export interface AvailableFactor {
  name: string
  source: string
  conn_id?: string
  table_name?: string
  qsid?: string
  description?: string
}

export interface StrategyDeleteResponse {
  qsid: string
  deleted: boolean
  file_deleted: boolean
}

// ─── API 调用 ─────────────────────────────────────────────────

/** 预览策略元信息（仅验证） */
export const previewStrategyImport = (code: string, filename?: string) => {
  return api.post<StrategyImportPreviewResponse>('/strategy/import/preview', { code, filename })
}

/** 导入策略（验证 + 保存 + 注册） */
export const importStrategy = (code: string, filename?: string) => {
  return api.post<{ valid: boolean; meta?: any; filepath: string; register_task_id: string }>(
    '/strategy/import', { code, filename }
  )
}

/** 搜索策略 */
export const searchStrategies = (params: {
  q?: string
  tag?: string
  factor_qsid?: string
  limit?: number
}) => {
  return api.get<StrategySearchResult[]>('/strategy/search', { params })
}

/** 获取策略详情 */
export const getStrategyDetail = (qsid: string) => {
  return api.get<Record<string, any>>(`/strategy/${qsid}`)
}

/** 获取策略源代码 */
export const getStrategyCode = (qsid: string) => {
  return api.get<{ qsid: string; code: string }>(`/strategy/${qsid}/code`)
}

/** 删除策略 */
export const deleteStrategy = (qsid: string, keepFile: boolean = true) => {
  return api.delete<StrategyDeleteResponse>(`/strategy/${qsid}`, { params: { keep_file: keepFile } })
}

/** 提交策略回测 */
export const submitStrategyBacktest = (request: StrategyBacktestRequest) => {
  return api.post<StrategyBacktestResult>('/strategy/backtest', request)
}

/** 获取策略回测结果 */
export const getStrategyBacktestResult = (taskId: string) => {
  return api.get<ResultNode>(`/strategy/backtest/${taskId}/result`)
}

/** 获取策略模板（新建策略时使用） */
export const getStrategyTemplate = () => {
  return api.get<{ code: string }>('/strategy/template')
}

/** 获取可用因子列表 */
export const getAvailableFactors = () => {
  return api.get<AvailableFactor[]>('/strategy/factors/available')
}

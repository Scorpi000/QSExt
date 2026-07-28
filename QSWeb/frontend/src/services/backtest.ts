/**
 * 回测工作台 API
 */

import api from './api'

// ─── 模块注册表 ───────────────────────────────────────────────

export interface ParamDef {
  name: string
  type: 'int' | 'float' | 'str' | 'bool' | 'select' | 'multiselect_ids' | 'multiselect_factor'
  label: string
  default?: any
  options?: string[]
  required: boolean
  description?: string
}

export interface ModuleInfo {
  key: string
  name: string
  category: string
  description: string
  params: ParamDef[]
  requires_price: boolean
  requires_descriptor_ids: boolean
}

// ─── 因子引用 ─────────────────────────────────────────────────

export interface FactorRef {
  source: 'db' | 'registry'
  name: string
  conn_id?: string
  table_name?: string
}

export interface PriceRef {
  conn_id: string
  table_name: string
  factor_name: string
}

// ─── 运行配置 ─────────────────────────────────────────────────

export interface ModuleRunConfig {
  module_key: string
  instance_label: string
  factor_refs: FactorRef[]
  params: Record<string, any>
  price_ref?: PriceRef | null
  descriptor_source?: string | null
  descriptor_ids?: string[] | null
}

export interface BacktestRunRequest {
  module_configs: ModuleRunConfig[]
  start_date: string
  end_date: string
  dt_mode: 'natural' | 'trading'
  rebalance_dts?: string[]
}

// ─── 结果树 ───────────────────────────────────────────────────

export interface ResultNode {
  key: string
  label: string
  type: 'branch' | 'series' | 'dataframe' | 'scalar'
  children?: ResultNode[]
  data?: any
}

// ─── API 调用 ─────────────────────────────────────────────────

export interface SectionIdSource {
  name: string
  method: string
}

/** 获取回测全局配置 */
export const getBacktestConfig = () => {
  return api.get<{ trading_day_available: boolean; section_id_sources: string[] }>('/backtest/config')
}

/** 获取截面 ID 源列表 */
export const getSectionIdSources = () => {
  return api.get<SectionIdSource[]>('/backtest/section-id-sources')
}

/** 获取所有回测模块 */
export const getBacktestModules = () => {
  return api.get<ModuleInfo[]>('/backtest/modules')
}

/** 获取单个模块详情 */
export const getBacktestModule = (key: string) => {
  return api.get<ModuleInfo>(`/backtest/modules/${key}`)
}

/** 提交回测运行 */
export const submitBacktestRun = (request: BacktestRunRequest) => {
  return api.post<{ task_id: string }>('/backtest/run', request)
}

/** 获取回测结果 */
export const getBacktestResult = (taskId: string) => {
  return api.get<ResultNode>(`/backtest/tasks/${taskId}/result`)
}

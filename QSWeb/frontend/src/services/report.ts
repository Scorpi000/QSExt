/**
 * 报告中心 API
 */

import api from './api'

// ─── 类型定义 ─────────────────────────────────────────────────

export interface FactorRef {
  conn_id: string
  table_name: string
  factor_name: string
}

export interface PriceRef {
  conn_id: string
  table_name: string
  factor_name: string
}

export interface ReportModuleConfig {
  ic?: boolean | Record<string, any>
  ic_decay?: boolean | Record<string, any>
  quantile_portfolio?: boolean | Record<string, any>
  factor_turnover?: boolean | Record<string, any>
}

export interface ReportGenerateRequest {
  scenario: string
  name: string
  factor_refs: FactorRef[]
  price_ref?: PriceRef | null
  mask_ref?: FactorRef | null
  cat_data_ref?: FactorRef | null
  weight_ref?: FactorRef | null
  start_date: string
  end_date: string
  output_formats: string[]
  modules: ReportModuleConfig
  descriptor_ids?: string[] | null
  rebalance_dts?: string[] | null
}

export interface ReportScenario {
  key: string
  name: string
  description: string
  output_formats: string[]
  module_options: string[]
}

export interface ReportInfo {
  id: string
  name: string
  scenario: string
  factor_names: string[]
  formats: string[]
  registered: boolean
  created_at: string
  start_date: string
  end_date: string
}

export interface TaskStatus {
  task_id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  progress_message: string
  error?: string
}

// ─── API 调用 ─────────────────────────────────────────────────

export const listScenarios = () => {
  return api.get<ReportScenario[]>('/reports/scenarios')
}

export const generateReport = (data: ReportGenerateRequest) => {
  return api.post<{ task_id: string }>('/reports/generate', data)
}

export const getTask = (taskId: string) => {
  return api.get<TaskStatus>('/reports/tasks/' + taskId)
}

export const getTaskResult = (taskId: string) => {
  return api.get<{
    report_id: string
    name: string
    factor_names: string[]
    formats: string[]
  }>('/reports/tasks/' + taskId + '/result')
}

export const listReports = (params?: { scenario?: string; factor_name?: string }) => {
  return api.get<ReportInfo[]>('/reports', { params })
}

export const getReport = (reportId: string) => {
  return api.get<ReportInfo>('/reports/' + reportId)
}

export const getReportContent = (reportId: string, fmt: string = 'html') => {
  return api.get<Record<string, string>>('/reports/' + reportId + '/content', { params: { fmt } })
}

export const deleteReport = (reportId: string) => {
  return api.delete('/reports/' + reportId)
}

export const registerReport = (
  reportId: string,
  data: { factor_qsids?: string[]; bt_qsid?: string }
) => {
  return api.post<{ message: string; report_ids: Record<string, string> }>(
    '/reports/' + reportId + '/register',
    data
  )
}

// ─── 配置 ─────────────────────────────────────────────────

export const getReportConfig = () => {
  return api.get<{ output_dir: string }>('/reports/config')
}

export const updateReportConfig = (output_dir: string) => {
  return api.put<{ output_dir: string; message: string }>('/reports/config', { output_dir })
}

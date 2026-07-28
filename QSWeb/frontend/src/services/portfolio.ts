/**
 * 组合优化 API
 */

import api from './api'

// ─── 类型定义 ─────────────────────────────────────────────────

export interface ObjectiveConfig {
  type: 'mean_variance' | 'risk_budget' | 'max_diversification'
  risk_aversion?: number
  expected_return_coef?: number
  risk_budget?: number[] | null
}

export interface FactorDataRef {
  conn_id: string
  table_name: string
  factor_name: string
  dt?: string | null
}

export interface ConstraintDef {
  type: 'box' | 'industry_exposure' | 'turnover' | 'cardinality' | 'budget'
  [key: string]: any
}

export interface OptimizeRequest {
  name: string
  solver: string
  objective: ObjectiveConfig
  constraints: ConstraintDef[]
  optim_options: Record<string, any>
  risk_db_id?: string | null
  risk_table_name?: string | null
  risk_dt?: string | null
  cov_matrix?: number[][] | null
  asset_ids?: string[] | null
  expected_return?: number[] | null
  expected_return_ref?: FactorDataRef | null
  initial_weights?: number[] | null
  benchmark_weights?: number[] | null
  benchmark_ref?: FactorDataRef | null
  mask_ref?: FactorDataRef | null
}

export interface RiskContribution {
  asset: string
  pct: number
  weight: number
}

export interface RiskDecomposition {
  portfolio_volatility: number
  portfolio_variance: number
  risk_contributions: RiskContribution[]
}

export interface OptimizeResponse {
  solution_id: string
  name: string
  status: 'optimal' | 'infeasible' | 'unbounded' | 'error'
  message: string
  solver_name: string
  solve_time: number
  weights: number[]
  asset_ids: string[]
  risk_decomposition: RiskDecomposition | null
}

// ─── 目标类型选项 ─────────────────────────────────────────────

export const OBJECTIVE_TYPES = [
  { value: 'mean_variance', label: '均值方差', desc: '最大化风险调整后收益：α·r - λ·w\'Σw' },
  { value: 'risk_budget', label: '风险预算', desc: '按预设预算分配风险（等风险平价 / 自定义）' },
  { value: 'max_diversification', label: '最大分散化', desc: '最大化分散化比率，降低集中风险' },
] as const

// ─── 约束类型选项 ─────────────────────────────────────────────

export const CONSTRAINT_TYPES = [
  { value: 'budget', label: '预算约束', desc: '限制总权重范围（如满仓=100%）' },
  { value: 'box', label: 'Box 约束', desc: '限制个股权重上下限' },
  { value: 'turnover', label: '换手率约束', desc: '限制总换手/买入/卖出比例' },
  { value: 'cardinality', label: '基数约束', desc: '限制最大持仓数量' },
] as const

// ─── 求解器选项 ─────────────────────────────────────────────

export interface SolverInfo {
  key: string
  label: string
  desc: string
}

// ─── API 调用 ─────────────────────────────────────────────────

export const getDefaultOptimOptions = (solver: string) => {
  return api.get<Record<string, any>>('/portfolio/optim-options', { params: { solver } })
}

export const listSolvers = () => {
  return api.get<SolverInfo[]>('/portfolio/solvers')
}

export const runOptimization = (data: OptimizeRequest) => {
  return api.post<OptimizeResponse>('/portfolio/optimize', data)
}

export const getSolution = (solutionId: string) => {
  return api.get<OptimizeResponse>(`/portfolio/solutions/${solutionId}`)
}

export const getWeightsCsvUrl = (solutionId: string) => {
  return `/api/portfolio/solutions/${solutionId}/weights`
}

// ─── 任务保存/加载 ─────────────────────────────────────────────

export interface SavedTaskInfo {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export interface SavedTask {
  id: string
  name: string
  config: OptimizeRequest
  created_at: string
  updated_at: string
}

export const listTasks = () => {
  return api.get<SavedTaskInfo[]>('/portfolio/tasks')
}

export const getTask = (taskId: string) => {
  return api.get<SavedTask>('/portfolio/tasks/' + taskId)
}

export const saveTask = (name: string, config: OptimizeRequest) => {
  return api.post<{ id: string; name: string; message: string }>('/portfolio/tasks', { name, config })
}

export const deleteTask = (taskId: string) => {
  return api.delete('/portfolio/tasks/' + taskId)
}

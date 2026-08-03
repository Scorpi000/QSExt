/**
 * 因子挖掘 API
 */

import api from './api'

// ─── 类型定义 ─────────────────────────────────────────────────

export interface TerminalFactorRef {
  conn_id: string
  table_name: string
  factor_name: string
}

export interface PriceRef {
  conn_id: string
  table_name: string
  factor_name: string
}

export interface EvalModuleConfig {
  module: string
  instance_label?: string
  params: Record<string, any>
  price_ref?: PriceRef | null
  section_mode?: 'auto' | 'source' | 'custom'
  section_source?: string | null
  section_ids?: string[] | null
}

export interface EvalConfig {
  modules: EvalModuleConfig[]
  transform: string
  sign: 'greater' | 'less'
}

export interface GPRunConfig {
  operators: string[]
  terminal_factors: TerminalFactorRef[]
  seed_factors: TerminalFactorRef[]
  population_size: number
  n_generations: number
  tournament_size: number
  init_depth: [number, number]
  init_method: 'grow' | 'full' | 'half and half'
  const_range: [number, number] | null
  p_crossover: number
  p_subtree_mutation: number
  p_hoist_mutation: number
  p_point_mutation: number
  p_point_replace: number
  parsimony_coefficient: number
  start_date?: string | null
  end_date?: string | null
  dt_mode?: 'natural' | 'trading'
  section_id_source?: string
  descriptor_ids?: string[]
  eval: EvalConfig
}

export interface FrameworkInfo {
  key: string
  name: string
  description: string
  config_schema: Record<string, any>
}

export interface MiningTaskSummary {
  task_id: string
  name: string
  framework: string
  status: string
  current_run: number
  created_at: string
}

export interface RunSummary {
  run_id: string
  status: string
  n_generations: number
  started_at: string | null
  completed_at: string | null
  error?: string | null
}

export interface MiningTask {
  task_id: string
  name: string
  framework: string
  runs: RunSummary[]
  created_at: string
}

export interface HallOfFameEntry {
  rank: number
  fitness: number
  expression: string
}

export interface RunResult {
  run_id: string
  hall_of_fame: HallOfFameEntry[]
  fitness_history: {
    gen_best: number[]
    gen_avg: number[]
  }
  gen_start: number
  gen_end: number
}

export interface FactorTreeNode {
  id: string
  name: string
  type: 'operator' | 'terminal'
}

export interface FactorTreeEdge {
  source: string
  target: string
}

export interface FactorTreeDAG {
  nodes: FactorTreeNode[]
  edges: FactorTreeEdge[]
}

// ─── API 调用 ─────────────────────────────────────────────────

export const listFrameworks = () => {
  return api.get<FrameworkInfo[]>('/mining/frameworks')
}

export const getFrameworkConfig = (name: string) => {
  return api.get<Record<string, any>>(`/mining/frameworks/${name}/config`)
}

export const createTask = (data: { name: string; framework: string }) => {
  return api.post<MiningTask>('/mining/tasks', data)
}

export const listTasks = () => {
  return api.get<MiningTaskSummary[]>('/mining/tasks')
}

export const getTask = (taskId: string) => {
  return api.get<MiningTask>(`/mining/tasks/${taskId}`)
}

export const deleteTask = (taskId: string) => {
  return api.delete(`/mining/tasks/${taskId}`)
}

export const submitRun = (taskId: string, config: GPRunConfig) => {
  return api.post<{ run_id: string }>(`/mining/tasks/${taskId}/run`, { config })
}

export const continueMining = (taskId: string, config: GPRunConfig) => {
  return api.post<{ run_id: string }>(`/mining/tasks/${taskId}/continue`, { config })
}

export const getRunResult = (taskId: string, runId: string) => {
  return api.get<RunResult>(`/mining/tasks/${taskId}/runs/${runId}/result`)
}

export const getFactorTree = (taskId: string, index: number) => {
  return api.get<FactorTreeDAG>(`/mining/tasks/${taskId}/factor-tree/${index}`)
}

export const exportFactor = (taskId: string, targetDir?: string) => {
  return api.post<{ message: string; path: string }>(`/mining/tasks/${taskId}/export`, {
    target_dir: targetDir || null,
  })
}

export const importFactorsFromScript = (scriptPath: string) => {
  const form = new FormData()
  form.append('script_path', scriptPath)
  return api.post<{
    script: string
    terminal_count: number
    terminals: { conn_id: string; table_name: string; factor_name: string }[]
  }>('/mining/import-factors', form)
}

/**
 * 回测服务 API 调用
 */

import api from './api'

export interface ICAnalysisParams {
  conn_id: string
  table_name: string
  factor_name: string
  price_table_name?: string
  price_field?: string
  start_date?: string | null
  end_date?: string | null
  corr_method?: string
  lookback?: number
}

export interface ICAnalysisResult {
  ic_series: Array<{ date: string; ic: number }>
  ic_decay: Array<{ lag: number; autocorr: number }>
  summary: {
    mean_ic: number
    std_ic: number
    ir: number
    positive_ratio: number
    n_periods: number
    max_ic?: number
    min_ic?: number
  }
  factor_name: string
  corr_method: string
}

export interface QuantilePortfolioParams {
  conn_id: string
  table_name: string
  factor_name: string
  price_table_name?: string
  price_field?: string
  start_date?: string | null
  end_date?: string | null
  n_groups?: number
  rebalance_freq?: string
}

export interface QuantilePortfolioResult {
  nav_series: Array<{
    group: number
    label: string
    data: Array<{ date: string; nav: number }>
  }>
  long_short_nav: Array<{ date: string; nav: number }>
  summary: Record<string, { total_return: number; annual_return: number }>
  factor_name: string
  n_groups: number
}

export interface TurnoverParams {
  conn_id: string
  table_name: string
  factor_name: string
  start_date?: string | null
  end_date?: string | null
  top_pct?: number
  rebalance_freq?: string
}

export interface TurnoverResult {
  turnover_series: Array<{ date: string; turnover: number }>
  avg_turnover: number
  factor_name: string
}

export interface StrategyBacktestParams {
  conn_id: string
  table_name: string
  factor_name: string
  price_table_name?: string
  price_field?: string
  start_date?: string | null
  end_date?: string | null
  initial_capital?: number
  commission_rate?: number
  slippage?: number
  rebalance_freq?: string
  signal_direction?: string
  top_n?: number
}

export interface BacktestResultData {
  task_id: string
  nav_series: Array<{ date: string; nav: number }>
  daily_returns: Array<{ date: string; return: number }>
  trades: Array<{
    date: string
    code: string
    action: string
    shares: number
    price: number
  }>
  summary: {
    total_return: number
    annual_return: number
    annual_volatility: number
    max_drawdown: number
    sharpe_ratio: number
    win_rate: number
    n_trades: number
    info_ratio: number
  }
  params: Record<string, unknown>
}

export interface BacktestHistoryItem {
  task_id: string
  name: string
  factor_name: string
  params: Record<string, unknown>
  summary: BacktestResultData['summary'] | null
  created_at: string
}

export interface TaskStatusResponse {
  task_id: string
  name: string
  status: string
  progress: number
  progress_message: string
  error?: string
  result?: BacktestResultData
}

// ─── API ─────────────────────────────────────────────

/** 运行 IC 分析 */
export async function runICAnalysis(params: ICAnalysisParams): Promise<ICAnalysisResult> {
  return api.post('/backtest/ic-analysis', params) as Promise<ICAnalysisResult>
}

/** 运行分位数组合 */
export async function runQuantilePortfolio(params: QuantilePortfolioParams): Promise<QuantilePortfolioResult> {
  return api.post('/backtest/quantile-portfolio', params) as Promise<QuantilePortfolioResult>
}

/** 运行换手率分析 */
export async function runTurnover(params: TurnoverParams): Promise<TurnoverResult> {
  return api.post('/backtest/turnover', params) as Promise<TurnoverResult>
}

/** 提交策略回测（异步） */
export async function submitStrategyBacktest(params: StrategyBacktestParams): Promise<{ task_id: string }> {
  return api.post('/backtest/strategy/run', params) as Promise<{ task_id: string }>
}

/** 获取回测任务结果 */
export async function getBacktestResult(taskId: string): Promise<TaskStatusResponse> {
  return api.get(`/backtest/tasks/${taskId}/result`) as Promise<TaskStatusResponse>
}

/** 获取任务状态 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return api.get(`/backtest/tasks/${taskId}`) as Promise<TaskStatusResponse>
}

/** 获取回测历史 */
export async function getBacktestHistory(factorName?: string, limit = 20): Promise<{ total: number; items: BacktestHistoryItem[] }> {
  const params = { limit }
  if (factorName) Object.assign(params, { factor_name: factorName })
  return api.get('/backtest/history', { params }) as Promise<{ total: number; items: BacktestHistoryItem[] }>
}

/** 注册回测 */
export async function registerBacktest(taskId: string, name?: string, category?: string): Promise<{ message: string; qsid?: string }> {
  return api.post(`/backtest/${taskId}/register`, { name, category }) as Promise<{ message: string; qsid?: string }>
}

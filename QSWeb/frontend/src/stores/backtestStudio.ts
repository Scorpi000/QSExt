/**
 * 回测工作台状态管理
 */

import { create } from 'zustand'
import type {
  ICAnalysisResult,
  QuantilePortfolioResult,
  TurnoverResult,
  BacktestResultData,
  BacktestHistoryItem,
  StrategyBacktestParams,
} from '../services/backtest'

type AnalysisTab = 'ic' | 'quantile' | 'turnover' | 'strategy'

interface BacktestStudioState {
  // 配置
  connId: string
  tableName: string
  factorName: string
  analysisType: AnalysisTab

  // IC 分析
  icResult: ICAnalysisResult | null
  icLoading: boolean

  // 分位数组合
  quantileResult: QuantilePortfolioResult | null
  quantileLoading: boolean

  // 换手率
  turnoverResult: TurnoverResult | null
  turnoverLoading: boolean

  // 策略回测
  strategyParams: StrategyBacktestParams | null
  strategyTaskId: string | null
  strategyResult: BacktestResultData | null
  strategyLoading: boolean

  // 历史
  history: BacktestHistoryItem[]
  historyLoading: boolean
  compareIds: string[]

  // 操作
  setConnId: (id: string) => void
  setTableName: (name: string) => void
  setFactorName: (name: string) => void
  setAnalysisType: (t: AnalysisTab) => void
  setIcResult: (r: ICAnalysisResult | null) => void
  setIcLoading: (l: boolean) => void
  setQuantileResult: (r: QuantilePortfolioResult | null) => void
  setQuantileLoading: (l: boolean) => void
  setTurnoverResult: (r: TurnoverResult | null) => void
  setTurnoverLoading: (l: boolean) => void
  setStrategyParams: (p: StrategyBacktestParams | null) => void
  setStrategyTaskId: (id: string | null) => void
  setStrategyResult: (r: BacktestResultData | null) => void
  setStrategyLoading: (l: boolean) => void
  setHistory: (h: BacktestHistoryItem[]) => void
  setHistoryLoading: (l: boolean) => void
  toggleCompareId: (id: string) => void
  clearCompare: () => void
  reset: () => void
}

export const useBacktestStudioStore = create<BacktestStudioState>((set) => ({
  connId: '',
  tableName: '',
  factorName: '',
  analysisType: 'ic',

  icResult: null,
  icLoading: false,

  quantileResult: null,
  quantileLoading: false,

  turnoverResult: null,
  turnoverLoading: false,

  strategyParams: null,
  strategyTaskId: null,
  strategyResult: null,
  strategyLoading: false,

  history: [],
  historyLoading: false,
  compareIds: [],

  setConnId: (id) => set({ connId: id }),
  setTableName: (name) => set({ tableName: name }),
  setFactorName: (name) => set({ factorName: name }),
  setAnalysisType: (t) => set({ analysisType: t }),
  setIcResult: (r) => set({ icResult: r }),
  setIcLoading: (l) => set({ icLoading: l }),
  setQuantileResult: (r) => set({ quantileResult: r }),
  setQuantileLoading: (l) => set({ quantileLoading: l }),
  setTurnoverResult: (r) => set({ turnoverResult: r }),
  setTurnoverLoading: (l) => set({ turnoverLoading: l }),
  setStrategyParams: (p) => set({ strategyParams: p }),
  setStrategyTaskId: (id) => set({ strategyTaskId: id }),
  setStrategyResult: (r) => set({ strategyResult: r }),
  setStrategyLoading: (l) => set({ strategyLoading: l }),
  setHistory: (h) => set({ history: h }),
  setHistoryLoading: (l) => set({ historyLoading: l }),
  toggleCompareId: (id) =>
    set((s) => ({
      compareIds: s.compareIds.includes(id)
        ? s.compareIds.filter((i) => i !== id)
        : [...s.compareIds, id],
    })),
  clearCompare: () => set({ compareIds: [] }),
  reset: () =>
    set({
      icResult: null,
      quantileResult: null,
      turnoverResult: null,
      strategyResult: null,
      strategyTaskId: null,
    }),
}))

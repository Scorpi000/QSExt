/**
 * 因子工作台状态管理
 */

import { create } from 'zustand'
import type { FactorSearchResult, FactorDetail, DAGData, OperatorInfo } from '../services/registry'

interface FactorWorkbenchState {
  // 搜索
  searchQuery: string
  searchResults: FactorSearchResult[]
  searchMode: 'keyword' | 'semantic'
  searching: boolean

  // 当前选中因子
  selectedFactor: FactorDetail | null
  selectedQSID: string | null
  loadingDetail: boolean

  // DAG
  dagData: DAGData | null
  loadingDAG: boolean

  // 算子
  operators: OperatorInfo[]
  loadingOperators: boolean

  // 操作
  setSearchQuery: (q: string) => void
  setSearchResults: (results: FactorSearchResult[]) => void
  setSearchMode: (mode: 'keyword' | 'semantic') => void
  setSearching: (s: boolean) => void
  setSelectedFactor: (f: FactorDetail | null) => void
  setSelectedQSID: (qsid: string | null) => void
  setLoadingDetail: (l: boolean) => void
  setDagData: (d: DAGData | null) => void
  setLoadingDAG: (l: boolean) => void
  setOperators: (ops: OperatorInfo[]) => void
  setLoadingOperators: (l: boolean) => void
  reset: () => void
}

export const useFactorWorkbenchStore = create<FactorWorkbenchState>((set) => ({
  searchQuery: '',
  searchResults: [],
  searchMode: 'keyword',
  searching: false,

  selectedFactor: null,
  selectedQSID: null,
  loadingDetail: false,

  dagData: null,
  loadingDAG: false,

  operators: [],
  loadingOperators: false,

  setSearchQuery: (q) => set({ searchQuery: q }),
  setSearchResults: (results) => set({ searchResults: results }),
  setSearchMode: (mode) => set({ searchMode: mode }),
  setSearching: (s) => set({ searching: s }),
  setSelectedFactor: (f) => set({ selectedFactor: f }),
  setSelectedQSID: (qsid) => set({ selectedQSID: qsid }),
  setLoadingDetail: (l) => set({ loadingDetail: l }),
  setDagData: (d) => set({ dagData: d }),
  setLoadingDAG: (l) => set({ loadingDAG: l }),
  setOperators: (ops) => set({ operators: ops }),
  setLoadingOperators: (l) => set({ loadingOperators: l }),
  reset: () => set({
    searchQuery: '',
    searchResults: [],
    selectedFactor: null,
    selectedQSID: null,
    dagData: null,
  }),
}))

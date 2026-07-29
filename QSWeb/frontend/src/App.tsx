import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './components/Layout/MainLayout'
import Loading from './components/Loading/Loading'
import ErrorBoundary from './components/ErrorBoundary'

// 页面组件懒加载
const DataManager = lazy(() => import('./pages/DataManager'))
const FactorWorkbench = lazy(() => import('./pages/FactorWorkbench'))
const BacktestStudio = lazy(() => import('./pages/BacktestStudio'))
const RiskManager = lazy(() => import('./pages/RiskManager'))
const PortfolioOptimizer = lazy(() => import('./pages/PortfolioOptimizer'))
const ReportCenter = lazy(() => import('./pages/ReportCenter'))

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/data" replace />} />
          <Route
            path="data"
            element={
              <ErrorBoundary title="数据管理页面出错">
                <Suspense fallback={<Loading />}>
                  <DataManager />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="factor"
            element={
              <ErrorBoundary title="因子工作台页面出错">
                <Suspense fallback={<Loading />}>
                  <FactorWorkbench />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="backtest"
            element={
              <ErrorBoundary title="回测工作台页面出错">
                <Suspense fallback={<Loading />}>
                  <BacktestStudio />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="risk"
            element={
              <ErrorBoundary title="风险管理页面出错">
                <Suspense fallback={<Loading />}>
                  <RiskManager />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="portfolio"
            element={
              <ErrorBoundary title="组合优化页面出错">
                <Suspense fallback={<Loading />}>
                  <PortfolioOptimizer />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="report"
            element={
              <ErrorBoundary title="报告中心页面出错">
                <Suspense fallback={<Loading />}>
                  <ReportCenter />
                </Suspense>
              </ErrorBoundary>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

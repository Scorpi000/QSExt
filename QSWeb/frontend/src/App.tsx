import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './components/Layout/MainLayout'
import Loading from './components/Loading/Loading'

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
              <Suspense fallback={<Loading />}>
                <DataManager />
              </Suspense>
            }
          />
          <Route
            path="factor"
            element={
              <Suspense fallback={<Loading />}>
                <FactorWorkbench />
              </Suspense>
            }
          />
          <Route
            path="backtest"
            element={
              <Suspense fallback={<Loading />}>
                <BacktestStudio />
              </Suspense>
            }
          />
          <Route
            path="risk"
            element={
              <Suspense fallback={<Loading />}>
                <RiskManager />
              </Suspense>
            }
          />
          <Route
            path="portfolio"
            element={
              <Suspense fallback={<Loading />}>
                <PortfolioOptimizer />
              </Suspense>
            }
          />
          <Route
            path="report"
            element={
              <Suspense fallback={<Loading />}>
                <ReportCenter />
              </Suspense>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

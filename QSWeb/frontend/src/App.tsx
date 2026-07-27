import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './components/Layout/MainLayout'
import DataManager from './pages/DataManager'
import FactorWorkbench from './pages/FactorWorkbench'
import BacktestStudio from './pages/BacktestStudio'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/data" replace />} />
          <Route path="data" element={<DataManager />} />
          <Route path="factor" element={<FactorWorkbench />} />
          <Route path="backtest" element={<BacktestStudio />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

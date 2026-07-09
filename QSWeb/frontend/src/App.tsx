import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './components/Layout/MainLayout'
import DataManager from './pages/DataManager'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/data" replace />} />
          <Route path="data" element={<DataManager />} />
          {/* 后续添加更多路由 */}
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

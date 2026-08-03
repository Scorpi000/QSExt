import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 23000,
    host: '0.0.0.0',  // 允许局域网访问
    proxy: {
      '/api': {
        target: 'http://localhost:28000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            // 后端未就绪时返回 503 而非静默断开
            if (res && 'writeHead' in res) {
              const srvRes = res as any
              srvRes.writeHead(503, { 'Content-Type': 'application/json' })
              srvRes.end(JSON.stringify({
                code: 'BACKEND_NOT_READY',
                message: '后端服务未就绪，请稍后刷新重试',
              }))
            }
          })
        },
      },
    },
    allowedHosts: ['qsweb.cpolar.top'],
  },
})

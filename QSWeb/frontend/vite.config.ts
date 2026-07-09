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
      },
    },
  },
})

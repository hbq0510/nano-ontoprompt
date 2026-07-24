import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8765'
  return {
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(__dirname, './src') } },
    server: {
      host: true,
      port: 5173,
      proxy: { '/api': backendUrl }
    }
  }
})

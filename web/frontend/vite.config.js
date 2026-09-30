import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时：npm run dev → http://localhost:5173 ，/api 代理到 8787
// 生产时：npm run build → web/frontend/dist ，由 web/server.py 直接托管
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
})

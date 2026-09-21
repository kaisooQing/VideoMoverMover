import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8001',
      '/ws': { target: 'ws://127.0.0.1:8001', ws: true }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  }
})

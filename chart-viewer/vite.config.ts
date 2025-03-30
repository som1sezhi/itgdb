import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/static/',
  server: {
    host: true,
    origin: 'http://localhost:5173'
  },
  build: {
    manifest: 'manifest.json',
    outDir: resolve('./dist'),
    rollupOptions: {
      input: {
        'chart-viewer': resolve('./src/main.tsx')
      }
    }
  }
})

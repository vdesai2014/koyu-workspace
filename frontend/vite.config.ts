import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
      '/video': {
        target: 'http://localhost:9090',
        rewrite: (path) => path.replace(/^\/video/, ''),
      },
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true,
      },
    },
  },
})

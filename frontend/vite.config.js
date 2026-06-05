import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxar /api -> FastAPI på localhost:8000 så frontend kan köra på 5173
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

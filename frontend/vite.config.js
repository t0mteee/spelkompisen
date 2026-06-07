import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxar /api -> FastAPI på localhost:8000 så frontend kan köra på 5173.
// host:true + allowedHosts:true => nåbar från andra enheter (Tailscale/LAN).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

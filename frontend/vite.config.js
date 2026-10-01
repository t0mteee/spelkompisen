import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxar /api -> FastAPI på localhost:8002 så frontend kan köra på 5175.
// xfwd: X-Forwarded-For bär klientens adress till backend, så att svar i
// spel-ai-kompisens inkorg kan skiljas från anrop från servern själv.
// host:true + allowedHosts:true => nåbar från andra enheter (Tailscale/LAN).
// Portar: svs = 8000/5173, vm = 8001/5174, spelkompisen = 8002/5175.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: true,
    port: 5175,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8002', xfwd: true },
    },
  },
  // `vite preview` servar den BYGGDA bunten. Skillnaden är inte kosmetisk:
  // i dev dubbelkör React StrictMode varje effekt, så Oddset-vyn hämtar
  // matcher, powerrank, notiser och radar TVÅ gånger vid varje mount (mätt
  // 2026-08-10). Proxyn måste anges separat — `server.proxy` gäller inte här.
  preview: {
    host: true,
    allowedHosts: true,
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8002', xfwd: true },
    },
  },
})

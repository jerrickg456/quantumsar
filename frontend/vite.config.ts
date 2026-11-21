import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In dev, API calls are proxied to the FastAPI backend (uvicorn api.main:app --port 8000).
const API = process.env.QUANTUMSAR_API ?? 'http://localhost:8000'
const apiPaths = ['/segment', '/edges', '/benchmark', '/samples', '/solvers', '/health', '/cache-status', '/results']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: Object.fromEntries(apiPaths.map((p) => [p, API])) },
  build: { chunkSizeWarningLimit: 900 },
})

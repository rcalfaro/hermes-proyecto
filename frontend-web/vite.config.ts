import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// El backend FastAPI expone /api/*; en desarrollo se delega por proxy para
// evitar CORS y que lib/api.ts use rutas relativas (mismo contrato en prod).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});

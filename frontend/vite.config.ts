import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/v1/auth': { target: 'http://localhost:8001', changeOrigin: true },
      '/api/v1/orders': { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/products': { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/cart': { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/recommendations': { target: 'http://localhost:8003', changeOrigin: true },
      '/api/LogInteractionFunction': {
        target: 'http://localhost:7071',
        changeOrigin: true,
      },
    },
  },
});

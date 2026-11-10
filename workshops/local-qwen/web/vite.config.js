import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 18791,
    strictPort: true,
    proxy: {
      // Preserve Host and Origin together for the backend's same-origin check.
      '/api': { target: 'http://127.0.0.1:18790', changeOrigin: false },
    },
  },
});

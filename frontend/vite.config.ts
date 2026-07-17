import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy API calls to the FastAPI backend during local development.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 4100,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  preview: {
    port: 4100,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})

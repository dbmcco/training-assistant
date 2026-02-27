import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const configuredAllowedHosts = process.env.VITE_ALLOWED_HOSTS?.split(',')
  .map((host) => host.trim())
  .filter(Boolean)

const allowedHosts = configuredAllowedHosts && configuredAllowedHosts.length > 0
  ? configuredAllowedHosts
  : true

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 4100,
    allowedHosts,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4100,
    allowedHosts,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

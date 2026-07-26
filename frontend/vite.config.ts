import { copyFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const frontendDir = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'preserve-marketing-site',
      closeBundle() {
        copyFileSync(
          resolve(frontendDir, 'multiscribe-logo.png'),
          resolve(frontendDir, 'dist/multiscribe-logo.png'),
        )
        copyFileSync(
          resolve(frontendDir, 'multiscribe-logo.svg'),
          resolve(frontendDir, 'dist/multiscribe-logo.svg'),
        )
      },
    },
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: 'index.html',
        console: 'console.html',
        login: 'login.html',
        'daily-news': 'daily-news.html',
      },
    },
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

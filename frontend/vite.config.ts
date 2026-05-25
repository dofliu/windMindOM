/// <reference types="vitest/config" />
import path from 'path';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    // Load .env from project root (one level up from frontend/)
    const env = loadEnv(mode, path.resolve(__dirname, '..'), '');
    // Also load frontend-local .env
    const localEnv = loadEnv(mode, '.', '');

    const backendPort = env.BACKEND_PORT || '8100';
    const frontendPort = parseInt(env.VITE_PORT || '3100', 10);
    const backendUrl = `http://localhost:${backendPort}`;
    const wsUrl = `ws://localhost:${backendPort}`;

    return {
      server: {
        port: frontendPort,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: backendUrl,
            changeOrigin: true,
          },
          '/ws': {
            target: wsUrl,
            ws: true,
          },
        },
      },
      plugins: [react()],
      define: {
        'process.env.API_KEY': JSON.stringify(localEnv.GEMINI_API_KEY || env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(localEnv.GEMINI_API_KEY || env.GEMINI_API_KEY),
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      },
      // Vitest 設定：jsdom 環境 + 全域 API（describe/it/expect）+ jest-dom matcher。
      // 只收 frontend 自己的 *.test.ts(x)，排除 node_modules / dist。
      test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: ['./test/setup.ts'],
        include: ['**/*.{test,spec}.{ts,tsx}'],
        exclude: ['node_modules/**', 'dist/**'],
        css: false,
      },
    };
});

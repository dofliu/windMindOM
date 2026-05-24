/// <reference types="vitest/config" />
import path from 'path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Vitest 專用設定。與 vite.config.ts 分離，避免 build 設定與 test 設定互相干擾；
// vitest 會優先讀本檔。前端測試走 jsdom（hook 需要 document / WebSocket / timer）。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['**/*.test.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
    restoreMocks: true,
  },
});

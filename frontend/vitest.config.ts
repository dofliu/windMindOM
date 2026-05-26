/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// 獨立的 vitest 設定：刻意不併進 vite.config.ts，避免 test 設定影響
// production build（`vite build` 仍只讀 vite.config.ts）。
// 不開 globals — 各 test 檔顯式 `import { describe, it, expect } from 'vitest'`，
// 如此 tsconfig.json 不需加 `vitest/globals` types 也能通過 tsc --noEmit。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**'],
  },
});

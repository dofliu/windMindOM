/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// 固定 runner timezone 為 UTC，讓 `new Date(iso)` 的 parsing 在所有 CI runner 上一致。
// 元件層的時間顯示（statusUtils.fmtDateTime）一律強制 `timeZone: 'Asia/Taipei'`，
// 故顯示字串不受此影響；此處只是消除「runner 本地時區外洩進測試」的潛在 flaky 來源。
process.env.TZ = 'UTC';

// 獨立的 vitest 設定：刻意不併進 vite.config.ts，避免 test 設定影響
// production build（`vite build` 仍只讀 vite.config.ts）。
// 不開 globals — 各 test 檔顯式 `import { describe, it, expect } from 'vitest'`，
// 如此 tsconfig.json 不需加 `vitest/globals` types 也能通過 tsc --noEmit。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: false,
    // component render 測試啟用 @testing-library/jest-dom matcher
    // （toBeInTheDocument / toBeDisabled / toHaveTextContent…）。
    // setup 檔只 import matcher，對純 hook / util 測試無副作用。
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**'],
  },
});

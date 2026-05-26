import { defineConfig } from 'vitest/config';

// 前端測試設定（與 vite.config.ts 分離，避免污染 production build 設定）。
// 不掛 @vitejs/plugin-react：目前測試皆為 .ts hook 測試（無 JSX），esbuild 直接轉
// TS 即可；且 vitest 2.x 內嵌 vite 5、app 用 vite 6，掛 plugin 會引入兩份 vite 型別衝突。
// 未來若新增 .tsx 元件渲染測試，再評估升級 vitest 至支援 vite 6 的版本並掛回 react plugin。
// environment=jsdom 提供 WebSocket / DOMException / DOM API；globals=true 讓
// @testing-library/react 的 auto-cleanup（afterEach）生效。
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    // 每個 test 前自動 reset 所有 vi.fn()。注意 vi.restoreAllMocks() 只還原 spyOn，
    // 對 vi.mock() factory 產生的 vi.fn() 無效；故統一靠此設定清理，避免 mock 狀態洩漏。
    mockReset: true,
    include: ['**/*.test.{ts,tsx}'],
    css: false,
  },
});

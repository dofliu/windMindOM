/**
 * Vitest 全域 setup —— 由 `vitest.config.ts` 的 `setupFiles` 載入。
 *
 * 引入 `@testing-library/jest-dom/vitest` 的副作用：把 `toBeInTheDocument`、
 * `toHaveAttribute`、`toBeDisabled` 等 DOM matcher 擴充進 vitest 的 `expect`，
 * 同時觸發型別 augmentation（讓 `tsc --noEmit` 認得這些 matcher）。
 *
 * 注意：本檔只做測試環境設定，不會進 production bundle（`vite build` 只讀
 * `vite.config.ts`，不讀 `vitest.config.ts`）。
 */

import '@testing-library/jest-dom/vitest';

import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// `@testing-library/react` 的「每個 test 後自動 unmount」只有在 vitest `globals: true`
// 時才會自動掛 afterEach。本專案刻意維持 `globals: false`（見 vitest.config.ts），
// 故必須手動註冊 cleanup，否則跨 test 的 render 會殘留在 document 上，造成
// getByRole / getByText 命中多個元素而報「Found multiple elements」。
afterEach(() => {
  cleanup();
  // 防禦性清除：ThemeProvider 會讀寫 localStorage（key='wmom.theme'）、mockUsers 用
  // 'wmom_actor_id'。清掉避免某 test 切 theme / 設 actor 後污染後續 test 的初始狀態。
  localStorage.clear();
});

/**
 * Vitest 全域 setup — 啟用 @testing-library/jest-dom 的 DOM matcher。
 *
 * 載入後即可在 component render 測試使用 `toBeInTheDocument()` /
 * `toHaveTextContent()` / `toBeDisabled()` 等語意化斷言，比手動
 * `expect(el.textContent).toContain(...)` 可讀且失敗訊息更清楚。
 *
 * 由 `vitest.config.ts` 的 `test.setupFiles` 在每個測試檔前自動引入；
 * 純 hook / util 測試不依賴這些 matcher，但載入無副作用、成本可忽略。
 */

import '@testing-library/jest-dom/vitest';

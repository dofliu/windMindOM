/**
 * renderWithTheme —— 把元件包進 `<ThemeProvider>` 再 render 的共用 helper。
 *
 * 為什麼需要：`components/ui/*` 全部呼叫 `useTheme()`（取 palette `C`），
 * 若不套 provider 直接 render 會在 `useTheme` 內 throw
 * 「must be used inside <ThemeProvider>」。所有 component render 測試一律走此 helper，
 * 避免每個檔案重複包 provider。
 *
 * 預設用 light 主題（與 `ThemeProvider` 預設一致）；目前測試只驗 DOM 結構 /
 * 互動 / aria，不綁特定主題色，故不需要切 dark。
 */

import React from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import { ThemeProvider } from '../theme/ThemeProvider';

// 模組層級宣告（非每次呼叫重建）：避免 rerender 時 wrapper 參照變動造成 context re-mount。
const ThemeWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

/**
 * 包 ThemeProvider 後 render。
 *
 * @param ui - 待 render 的 React 元素
 * @param options - 透傳給 RTL `render` 的選項（container 等，少用）
 * @returns RTL 的 RenderResult（含 `rerender` / `unmount` / queries）
 *
 * 注意 spread 順序：`{ ...options, wrapper: ThemeWrapper }` —— wrapper 放最後，
 * 確保 ThemeProvider 永遠存在、不被呼叫端誤傳的 `options.wrapper` 靜默蓋掉
 * （否則元件在無 theme context 下 render 會在 useTheme throw）。
 */
export function renderWithTheme(ui: React.ReactElement, options?: RenderOptions): RenderResult {
  return render(ui, { ...options, wrapper: ThemeWrapper });
}

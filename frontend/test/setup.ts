/**
 * Vitest 全域 setup。
 *
 * - 註冊 @testing-library/jest-dom 的 matcher（toBeInTheDocument 等）給 vitest 的 expect。
 * - 每個 test 後自動 cleanup 已 render 的 React 樹，避免 test 間 DOM 殘留互相污染。
 */
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

/**
 * Vitest 全域 setup。
 *
 * 註冊 @testing-library/jest-dom 的 matcher（toBeInTheDocument 等）給 vitest 的 expect。
 *
 * 註：test DOM 的 teardown 不需手動處理 —— `globals: true` 下 afterEach 為全域，
 * @testing-library/react 16 會自動註冊 cleanup，每個 test 後清掉已 render 的 React 樹。
 */
import '@testing-library/jest-dom/vitest';

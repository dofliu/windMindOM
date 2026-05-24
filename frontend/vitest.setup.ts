import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// 每個 test 後卸載殘留的 React tree，避免 hook 測試互相污染。
afterEach(() => {
  cleanup();
});

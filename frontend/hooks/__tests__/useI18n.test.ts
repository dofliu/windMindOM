/**
 * useI18n — authFetch 稽核（WMOM-20260925-01）。
 *
 * mount 時 GET `/api/i18n/tags/all`（後端 `require_authenticated()`）先前是裸 fetch。
 * 本檔先前無測試覆蓋，補上已登入/未登入對照測試。全程 mock `fetch`，零真連線。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useI18n } from '../useI18n';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

const fetchMock = vi.fn();

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ json: async () => ({}) } as unknown as Response);
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearAuthToken();
});

describe('useI18n — authFetch 稽核（WMOM-20260925-01）', () => {
  it('已登入 → mount 時 GET /api/i18n/tags/all 帶 Authorization header', () => {
    setAuthToken('test-token-i18n');
    renderHook(() => useI18n());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBe(
      'Bearer test-token-i18n',
    );
  });

  it('未登入 → mount 時 GET 不帶 Authorization header（過渡期行為不變）', () => {
    renderHook(() => useI18n());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBeUndefined();
  });
});

/**
 * authClient 單元測試（WMOM-20260716-05f）。
 *
 * 全程 mock `global.fetch` + 用 jsdom `window.localStorage`，零真連線、零新依賴
 * （與 mockUsers.test / knowledgeService.test 同精神：純邏輯層）。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  AUTH_TOKEN_STORAGE_KEY,
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  isLoggedIn,
  authHeaders,
  authFetch,
  authApi,
  onUnauthorized,
} from '../authClient';

const fetchMock = vi.fn();

function mockResp(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  window.localStorage.clear();
  onUnauthorized(null);
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('token 存取', () => {
  it('set / get / clear round-trip', () => {
    expect(getAuthToken()).toBeNull();
    expect(isLoggedIn()).toBe(false);

    setAuthToken('tok123');
    expect(getAuthToken()).toBe('tok123');
    expect(isLoggedIn()).toBe(true);
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('tok123');

    clearAuthToken();
    expect(getAuthToken()).toBeNull();
    expect(isLoggedIn()).toBe(false);
  });
});

describe('authHeaders', () => {
  it('有 token → Authorization header', () => {
    setAuthToken('abc');
    expect(authHeaders()).toEqual({ Authorization: 'Bearer abc' });
  });

  it('無 token → 空物件（過渡期未登入不帶）', () => {
    expect(authHeaders()).toEqual({});
  });
});

describe('authFetch', () => {
  it('有 token 時注入 Authorization，不覆蓋既有 Content-Type', async () => {
    setAuthToken('tok');
    fetchMock.mockResolvedValue(mockResp(200, { ok: true }));
    await authFetch('/api/x', { headers: { 'Content-Type': 'application/json' } });
    expect(fetchMock).toHaveBeenCalledWith('/api/x', {
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer tok' },
    });
  });

  it('無 token → 不帶 Authorization', async () => {
    fetchMock.mockResolvedValue(mockResp(200));
    await authFetch('/api/x');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('401 → 清 token + 觸發 onUnauthorized handler', async () => {
    setAuthToken('stale');
    const handler = vi.fn();
    onUnauthorized(handler);
    fetchMock.mockResolvedValue(mockResp(401));

    await authFetch('/api/x');

    expect(getAuthToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
  });

  it('非 401 → 不動 token、不觸發 handler', async () => {
    setAuthToken('good');
    const handler = vi.fn();
    onUnauthorized(handler);
    fetchMock.mockResolvedValue(mockResp(200));

    await authFetch('/api/x');

    expect(getAuthToken()).toBe('good');
    expect(handler).not.toHaveBeenCalled();
  });
});

describe('authApi.login', () => {
  it('成功 → 存 token + 回 actor（走原生 POST /api/auth/login）', async () => {
    fetchMock.mockResolvedValue(
      mockResp(200, {
        access_token: 'jwt-xyz',
        token_type: 'bearer',
        actor: { id: 'u1', name: 'Alice', role: 'employee' },
      }),
    );

    const actor = await authApi.login('alice', 'pw');

    expect(actor).toEqual({ id: 'u1', name: 'Alice', role: 'employee' });
    expect(getAuthToken()).toBe('jwt-xyz');
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/auth/login');
    expect((init as RequestInit).method).toBe('POST');
  });

  it('401 → throw（帶後端 detail）且不存 token', async () => {
    fetchMock.mockResolvedValue(mockResp(401, { detail: '帳號或密碼錯誤' }));
    await expect(authApi.login('x', 'y')).rejects.toThrow('帳號或密碼錯誤');
    expect(getAuthToken()).toBeNull();
  });

  it('login 的 401 不觸發 onUnauthorized（語意＝帳密錯，非 session 失效）', async () => {
    const handler = vi.fn();
    onUnauthorized(handler);
    fetchMock.mockResolvedValue(mockResp(401, { detail: 'bad' }));
    await expect(authApi.login('x', 'y')).rejects.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });
});

describe('authApi.me', () => {
  it('帶 token 查身分 → 回 actor', async () => {
    setAuthToken('tok');
    fetchMock.mockResolvedValue(mockResp(200, { id: 'u2', name: 'Bob', role: 'leader' }));

    const actor = await authApi.me();

    expect(actor).toEqual({ id: 'u2', name: 'Bob', role: 'leader' });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
  });
});

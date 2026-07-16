/**
 * authClient — 真登入的最底層 client（WMOM-20260716-05f，D1：localStorage token）。
 *
 * 純邏輯、無 React 依賴，職責：
 *  - token 存取（localStorage，key `wmom_auth_token`）
 *  - `authHeaders()`：有 token → `{ Authorization: 'Bearer <token>' }`，否則 `{}`
 *  - `authFetch()`：包 `fetch`，注入 auth header + 攔 401（清 token + 呼叫已註冊 handler）
 *  - `authApi.login` / `me`：打 `/api/auth/*`
 *
 * 非破壞（對應計畫 §1 P2）：`WMOM_AUTH_ENFORCE=false` 過渡期，未登入 → 無 token →
 * `authHeaders()` 空 → 行為同以往（後端仍收 body `actor_id`）。登入後才帶 token。
 * 401（cutover 後未登入 / token 失效）→ 清 token + 觸發 handler（AuthProvider 註冊為
 * 「導回登入頁」）。此模組**只管 client 行為**，UI 導向由 `onUnauthorized` 掛入。
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

/** localStorage key — 存 JWT access token。 */
export const AUTH_TOKEN_STORAGE_KEY = 'wmom_auth_token';

/** 與後端 `modules/auth/roles.py` 的 Role value 對齊。 */
export type AuthRole = 'employee' | 'leader' | 'supervisor' | 'treasury' | 'admin';

export interface AuthActor {
  id: string;
  name: string;
  role: AuthRole;
}

interface LoginResult {
  access_token: string;
  token_type: string;
  actor: AuthActor;
}

// ─── token 存取 ─────────────────────────────────────────────────────────────

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

/** 目前是否持有 token（≠ token 一定有效；有效性由後端驗）。 */
export function isLoggedIn(): boolean {
  return getAuthToken() !== null;
}

/** 有 token → Authorization header；否則空物件（過渡期未登入不帶）。 */
export function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ─── 401 handler 註冊（AuthProvider 掛：清 state + 導回登入頁）──────────────

type UnauthorizedHandler = () => void;
let _unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * 註冊 401 回呼（傳 null 取消）。`authFetch` 收到 401 時，先清 token 再呼叫此 handler。
 * 用於「session 失效 → 導回登入頁」；由 AuthProvider 於 mount 時掛入。
 */
export function onUnauthorized(handler: UnauthorizedHandler | null): void {
  _unauthorizedHandler = handler;
}

// ─── authFetch：所有業務 API 走此，統一帶 token + 攔 401 ──────────────────

/**
 * `fetch` 包裝：merge `authHeaders()`（不覆蓋既有 Content-Type / Accept），
 * 並在 401 時清 token + 觸發 `onUnauthorized` handler。回傳原始 `Response`
 * 讓 caller 既有的 `resp.ok` 錯誤處理照舊運作（不吞錯）。
 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const merged: RequestInit = {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...authHeaders(),
    },
  };
  const resp = await fetch(input, merged);
  if (resp.status === 401) {
    // token 失效 / cutover 後未登入 → 清 token 並通知 handler（導回登入）。
    clearAuthToken();
    _unauthorizedHandler?.();
  }
  return resp;
}

// ─── auth API（login / me）──────────────────────────────────────────────────

async function _readDetail(resp: Response): Promise<string | null> {
  try {
    const body = await resp.json();
    if (body && typeof body.detail === 'string') return body.detail;
  } catch {
    /* ignore parse error */
  }
  return null;
}

export const authApi = {
  /**
   * 帳密登入。成功 → 存 token 並回主體資訊；失敗 → throw（帶後端 detail 訊息）。
   *
   * 刻意走原生 `fetch`（非 `authFetch`）：登入的 401 語意是「帳密錯」，不該觸發
   * 「session 失效 → 導回登入」的 handler（我們本來就在登入頁）。
   */
  async login(username: string, password: string): Promise<AuthActor> {
    const resp = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const detail = await _readDetail(resp);
      throw new Error(detail ?? `登入失敗（HTTP ${resp.status}）`);
    }
    const data = (await resp.json()) as LoginResult;
    setAuthToken(data.access_token);
    return data.actor;
  },

  /** 查目前 token 對應的已驗證身分（有效 → actor；否則 throw）。 */
  async me(): Promise<AuthActor> {
    const resp = await authFetch(`${API_BASE}/api/auth/me`);
    if (!resp.ok) {
      throw new Error(`身分查詢失敗（HTTP ${resp.status}）`);
    }
    return (await resp.json()) as AuthActor;
  },
};

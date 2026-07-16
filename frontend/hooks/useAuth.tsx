/**
 * useAuth — 真登入 React Context（WMOM-20260716-05f-b）。
 *
 * 疊在 authClient（-05f-a）之上：持有目前登入者 `actor` + 登入頁 overlay 開關，
 * 並把「401 → 導回登入」handler 掛進 `authClient.onUnauthorized`。
 *
 * 過渡期（`WMOM_AUTH_ENFORCE=false`）：登入為 **opt-in** — 未登入 app 照跑
 * （走 mock `UserSwitcher` 的 body `actor_id`）。登入後 authClient 存 token、
 * `authFetch` 自動帶上；token 失效（401）→ 清 state + 彈登入頁。dev 的
 * `UserSwitcher` 保留（D6）。
 *
 * actor 持久化：登入者資訊（id/name/role）存 localStorage（key `wmom_auth_actor`），
 * 重整後還原顯示（僅在仍持有 token 時）。token 由 authClient 管；logout / 401 兩者同清。
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  authApi,
  clearAuthToken,
  getAuthToken,
  onUnauthorized,
  type AuthActor,
} from '../services/authClient';

const ACTOR_STORAGE_KEY = 'wmom_auth_actor';

function readStoredActor(): AuthActor | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(ACTOR_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthActor;
  } catch {
    return null;
  }
}

function writeStoredActor(actor: AuthActor | null): void {
  if (typeof window === 'undefined') return;
  if (actor === null) window.localStorage.removeItem(ACTOR_STORAGE_KEY);
  else window.localStorage.setItem(ACTOR_STORAGE_KEY, JSON.stringify(actor));
}

interface AuthContextValue {
  /** 目前登入者；`null` = 未登入（過渡期仍可操作，走 body actor_id）。 */
  actor: AuthActor | null;
  isAuthenticated: boolean;
  /** 是否顯示登入頁 overlay。 */
  loginOpen: boolean;
  /** true = 因 401 被導回（vs 使用者主動開登入）；影響 overlay 標題文案。 */
  sessionExpired: boolean;
  openLogin: () => void;
  closeLogin: () => void;
  /** 帳密登入；成功 set actor + 關 overlay，失敗 throw（caller 顯示錯誤）。 */
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // 初值：僅在仍持有 token 時還原 actor（避免 token 已清但殘留 actor 的不一致）。
  const [actor, setActor] = useState<AuthActor | null>(() =>
    getAuthToken() !== null ? readStoredActor() : null,
  );
  const [loginOpen, setLoginOpen] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  // 掛 401 handler：authFetch 收到 401 已清 token → 這裡清 actor state + 彈登入頁。
  useEffect(() => {
    onUnauthorized(() => {
      writeStoredActor(null);
      setActor(null);
      setSessionExpired(true);
      setLoginOpen(true);
    });
    return () => onUnauthorized(null);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const a = await authApi.login(username, password); // 失敗 throw（帶後端 detail）
    writeStoredActor(a);
    setActor(a);
    setSessionExpired(false);
    setLoginOpen(false);
  }, []);

  const logout = useCallback(() => {
    clearAuthToken();
    writeStoredActor(null);
    setActor(null);
    setSessionExpired(false);
  }, []);

  const openLogin = useCallback(() => {
    setSessionExpired(false);
    setLoginOpen(true);
  }, []);

  const closeLogin = useCallback(() => setLoginOpen(false), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      actor,
      isAuthenticated: actor !== null,
      loginOpen,
      sessionExpired,
      openLogin,
      closeLogin,
      login,
      logout,
    }),
    [actor, loginOpen, sessionExpired, openLogin, closeLogin, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * 取 auth state。必須在 `<AuthProvider>` 內呼叫。
 *
 * @throws Error 若沒有 AuthProvider 包裹（fail-fast）
 */
export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
};

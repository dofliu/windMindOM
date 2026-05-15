/**
 * useCurrentUser — React Context + hook 管「目前登入者」（mock login）。
 *
 * WMOM-20260510-01 Part B：取代 hardcoded `DEV_ACTOR_ID`，讓 demo 操作者
 * 可動態切換 4 個 fixture user 來扮不同 signoff 階級。
 *
 * 用法：
 *   - App 根包 `<UserProvider>...</UserProvider>`
 *   - 任何子元件 `const { currentUser, setCurrentUser } = useCurrentUser()`
 *   - 非 React 模組：`getCurrentActorId()` 同步讀 localStorage（見 mockUsers.ts）
 *
 * 持久化：透過 localStorage（key = `wmom_actor_id`）跨 session 保留選擇。
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  ACTOR_ID_STORAGE_KEY,
  DEFAULT_USER,
  MOCK_USERS,
  type MockUser,
  findMockUser,
} from '../services/mockUsers';

interface UserContextValue {
  /** 目前選的 user。永遠非 null（fallback DEFAULT_USER）。 */
  currentUser: MockUser;
  /** 切換 user。同步寫 localStorage。 */
  setCurrentUser: (user: MockUser) => void;
  /** 4 個 fixture user 列表（給 switcher render dropdown 用）。 */
  availableUsers: ReadonlyArray<MockUser>;
}

const UserContext = createContext<UserContextValue | null>(null);

/**
 * 從 localStorage 讀初始 user（找不到 fallback 到 DEFAULT_USER）。
 *
 * 包成函式給 `useState(initFn)` lazy 初始化用，避免 SSR / 第一次 render 時
 * window 不存在或 localStorage 空導致錯誤。
 */
const readInitialUser = (): MockUser => {
  if (typeof window === 'undefined') return DEFAULT_USER;
  const stored = window.localStorage.getItem(ACTOR_ID_STORAGE_KEY);
  return findMockUser(stored) ?? DEFAULT_USER;
};

interface UserProviderProps {
  children: React.ReactNode;
}

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [currentUser, setCurrentUserState] = useState<MockUser>(readInitialUser);

  const setCurrentUser = useCallback((user: MockUser) => {
    setCurrentUserState(user);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, user.id);
    }
  }, []);

  // 確保 localStorage 與 state 一致（例如初次 mount 但 localStorage 無值時）
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(ACTOR_ID_STORAGE_KEY);
    if (stored !== currentUser.id) {
      window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, currentUser.id);
    }
  }, [currentUser.id]);

  const value = useMemo<UserContextValue>(
    () => ({
      currentUser,
      setCurrentUser,
      availableUsers: MOCK_USERS,
    }),
    [currentUser, setCurrentUser],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};

/**
 * 取目前 user state。必須在 `<UserProvider>` 內呼叫。
 *
 * @throws Error 若沒有 UserProvider 包裹（fail-fast 比 silent fallback 好）
 */
export const useCurrentUser = (): UserContextValue => {
  const ctx = useContext(UserContext);
  if (!ctx) {
    throw new Error('useCurrentUser must be used within <UserProvider>');
  }
  return ctx;
};

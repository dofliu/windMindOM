/**
 * useSourceGate — 資料來源選擇 gate 的狀態機（WMOM-20260719-05，抽自 App.tsx 便於測試）。
 *
 * 後端開機 idle（不自動起來源）。本 hook 查 `/api/source/status` 決定是否顯示選擇頁，並提供
 * `selectMode` 啟動來源。抽成 hook 是因為這段（fetch status / 依 auth 重查 / select）是本功能
 * 風險最高、行為最複雜的邏輯，值得獨立測試（原本只有純呈現的 SourceSelectPage 有測）。
 *
 * 登出防呆：只在「取得登入」(false→true) 或初次掛載時重查；**登出**(true→false) 不重查——
 * 否則 enforce 下重查會 401，authClient 的 401 handler 會把「主動登出」誤標成 session 過期。
 */

import { useEffect, useRef, useState } from 'react';
import { authFetch } from '../services/authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

export type SourceMode = 'simulation' | 'live' | 'view';

/** 啟動來源的結果；`status` 供 UI 對 403（權限不足）等給明確回饋而非靜默。 */
export interface SelectResult {
  ok: boolean;
  status?: number;
}

export interface SourceGate {
  /** null＝尚未查得（載入中）；true＝已選來源；false＝未選（顯示選擇頁）。 */
  sourceActive: boolean | null;
  /** 啟動指定來源；成功時把 sourceActive 設 true。 */
  selectMode: (mode: SourceMode) => Promise<SelectResult>;
}

export function useSourceGate(isAuthenticated: boolean): SourceGate {
  const [sourceActive, setSourceActive] = useState<boolean | null>(null);
  const prevAuth = useRef(isAuthenticated);

  useEffect(() => {
    const wasAuth = prevAuth.current;
    prevAuth.current = isAuthenticated;
    // 登出不重查（見檔頭「登出防呆」）。
    if (wasAuth && !isAuthenticated) return;

    let cancelled = false;
    authFetch(`${API_BASE}/api/source/status`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!cancelled) setSourceActive(data ? !!data.active : false);
      })
      .catch(() => {
        if (!cancelled) setSourceActive(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const selectMode = async (mode: SourceMode): Promise<SelectResult> => {
    try {
      const res = await authFetch(`${API_BASE}/api/source/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (res.ok) {
        setSourceActive(true);
        return { ok: true };
      }
      // 非 ok：401（未登入）由 authClient 彈登入頁；403（如 live 需主管）由呼叫端顯示訊息。
      return { ok: false, status: res.status };
    } catch {
      return { ok: false }; // 網路錯誤
    }
  };

  return { sourceActive, selectMode };
}

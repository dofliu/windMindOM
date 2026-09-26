/**
 * useScenarioMountData — 情境掛載資料（PR C Phase 1，WMOM-20260926-03）。
 *
 * 給定 `scenarioId`，取該情境每台機組的最後一筆讀數（`GET /api/scenarios/{id}/turbines`），
 * 轉成與即時路徑相同的 `TurbineData` 形狀（重用 `useRealtimeData` 的 `apiToTurbineData`），
 * 讓 FarmOverview/TurbineDetail 可原封不動沿用既有畫面元件、不需另外維護一份轉換邏輯。
 *
 * 只在 `scenarioId` 變動時 fetch 一次——情境資料是凍結快照不會變（DEC-20260720-01 §「情境＝
 * 凍結資料集」），不像 `useRealtimeData` 需要 WS/輪詢保持更新；這正是「停用既有 WS 訂閱」的
 * 實作方式——本 hook 從不建立 WebSocket 或輪詢計時器。
 *
 * 刻意不呼叫 `/api/scenarios/{id}/farm-status`：`FarmOverview` 的風場層數字本來就是從
 * `turbines` prop 自行加總（既有 live 路徑亦從未呼叫 `/api/turbines/farm-status`，見
 * `FarmOverview.tsx` `HeroStats`），與新端點算出的數字理論上一致，多打一次 API 是純粹的
 * 重複往返，故不在此消費（該端點仍完整測試於後端，供未來需要獨立風場層查詢時使用）。
 */

import { useEffect, useState } from 'react';
import { authFetch } from '../services/authClient';
import { type TurbineData } from '../types';
import { apiToTurbineData, type ApiTurbineReading } from './useRealtimeData';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

export interface ScenarioMountData {
  turbines: TurbineData[];
  loading: boolean;
  /** 非 null 時代表 fetch 失敗（含情境已被刪除的 404）；`turbines` 會是空陣列。 */
  error: string | null;
}

export function useScenarioMountData(scenarioId: number | null): ScenarioMountData {
  const [turbines, setTurbines] = useState<TurbineData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (scenarioId === null) {
      setTurbines([]);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    authFetch(`${API_BASE}/api/scenarios/${scenarioId}/turbines`)
      .then(async res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return (await res.json()) as ApiTurbineReading[];
      })
      .then(data => {
        if (cancelled) return;
        setTurbines(data.map(apiToTurbineData));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTurbines([]);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  return { turbines, loading, error };
}

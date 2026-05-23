/**
 * useCostData — 4 個 cost endpoint 的 stateful hook。
 *
 * 每個 endpoint 對應一個 (data, loading, error, run) 組合：
 *   - data: 最新 response（null = 還沒跑過）
 *   - loading: 是否正在 fetch
 *   - error: 上次失敗的 error message（成功會清掉）
 *   - run(req): 觸發 fetch，更新上述 state
 *   - reset(): 清 data + error，並 abort in-flight fetch
 *
 * Race-condition 防護（WMOM-20260504-13）：
 *   - 每次 run 會 abort 上一次未完成的 fetch（React 18+ Strict Mode dev 雙 mount 安全）
 *   - reset 也會 abort，避免「先清視覺、慢 fetch 後回又把舊資料寫回」的 UX bug
 *   - 用戶快速切 dataset 也保證 last-write-wins
 *   - AbortError 不視為 user-facing error（不寫進 error state、不關 loading）
 *   - component unmount 時 abort 當前 in-flight fetch；unmount 後不會再有 setState
 *     （loading 留在 true 也無妨 — 組件已卸載；下次 mount 時 useState(false) 自然 reset）
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  costApi,
  type CostApiOptions,
  type CostForecastRequest,
  type CostForecastResponse,
  type LCOERequest,
  type LCOEResponse,
  type MonteCarloRequest,
  type MonteCarloResponse,
  type VarFluctRequest,
  type VarFluctResponse,
} from '../services/costService';

interface AsyncState<TData, TReq> {
  data: TData | null;
  loading: boolean;
  error: string | null;
  run: (req?: TReq) => Promise<void>;
  /** 清空 data + error，並 abort 任何 in-flight fetch（避免舊結果寫回新清空的 UI）。 */
  reset: () => void;
}

/**
 * 判斷一個 thrown error 是否來自 AbortController.abort()。
 *
 * 現代 runtime（瀏覽器 fetch、Node 18+ undici）統一在 abort 時拋
 * DOMException with `name === 'AbortError'`。`code === 20` 是更早期 DOMException
 * ABORT_ERR 的 legacy 識別，在 undici 沒有此屬性，保留只為防禦極舊環境 / polyfill。
 */
function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { name?: unknown; code?: unknown };
  return e.name === 'AbortError' || e.code === 20;
}

function useAsync<TReq, TData>(
  fn: (req: TReq, opts: CostApiOptions) => Promise<TData>,
): AsyncState<TData, TReq> {
  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // unmount 時取消任何 in-flight fetch；ref 設 null 讓 finally 認得「已卸載」狀態
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const run = useCallback(
    async (req?: TReq) => {
      // 取消上一輪未完成的 fetch（race-condition 防護核心）
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const result = await fn((req ?? {}) as TReq, { signal: controller.signal });
        // 防禦性檢查：若 fn 內部吃掉 AbortError 而沒 rethrow（非標準行為，但
        // 防止未來改 implementation 時破壞 race 安全性），仍依 signal.aborted 判定
        if (controller.signal.aborted) {
          return;
        }
        setData(result);
      } catch (e) {
        if (isAbortError(e) || controller.signal.aborted) {
          // 被新一輪 run / reset / unmount 取消 → 不寫 error、不關 loading
          // （loading 由新一輪的 setLoading(true) 接管，或由 reset/unmount 路徑處理）
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        // 只有「仍是當前 controller」且「未被 abort」才動 loading。
        // 否則 setLoading(false) 會踩到新一輪剛 setLoading(true) 的 state。
        // unmount 後 ref 已被 cleanup 設成 null，此判斷自然為 false → 不 setState
        // （組件已卸載，loading 留 true 無害，下次 mount useState(false) 重置）
        if (controllerRef.current === controller && !controller.signal.aborted) {
          setLoading(false);
          controllerRef.current = null;
        }
      }
    },
    // `fn` 是 module-level 常數（costApi.forecast 等 stable reference），
    // 所以 useCallback 實際上只在 mount 時建一次。若日後 costApi 改為工廠
    // 函式回傳新 reference，此 useCallback 才會每次重建。
    [fn],
  );

  const reset = useCallback(() => {
    // 同步 abort：避免「reset 清空 data → 舊 fetch 慢回 → setData 寫回 stale 結果」
    // 這條 UX bug（dataset 切換時 CostPage 對非 forecast panel 呼叫 reset，
    // 若該 panel 有 in-flight 請求，會用舊 dataset 結果蓋掉剛清空的視覺）
    controllerRef.current?.abort();
    controllerRef.current = null;
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, run, reset };
}

export function useCostData() {
  const forecast = useAsync<CostForecastRequest, CostForecastResponse>(costApi.forecast);
  const lcoe = useAsync<LCOERequest, LCOEResponse>(costApi.lcoe);
  const monteCarlo = useAsync<MonteCarloRequest, MonteCarloResponse>(costApi.monteCarlo);
  const varFluct = useAsync<VarFluctRequest, VarFluctResponse>(costApi.varFluct);

  return { forecast, lcoe, monteCarlo, varFluct };
}

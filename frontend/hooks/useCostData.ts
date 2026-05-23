/**
 * useCostData — 4 個 cost endpoint 的 stateful hook。
 *
 * 每個 endpoint 對應一個 (data, loading, error, run) 組合：
 *   - data: 最新 response（null = 還沒跑過）
 *   - loading: 是否正在 fetch
 *   - error: 上次失敗的 error message（成功會清掉）
 *   - run(req): 觸發 fetch，更新上述 state
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  costApi,
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
  /** 清空 data + error（給 dataset 切換時 reset 用，避免顯示 stale 數字）。 */
  reset: () => void;
}

/** fetch abort 時拋出的 error 不算真正失敗，不該寫進 error state。
 *  瀏覽器原生 fetch abort 拋 DOMException('AbortError')；polyfill 可能拋一般 Error，兩者都接。 */
function isAbortError(e: unknown): boolean {
  return (e instanceof DOMException || e instanceof Error) && e.name === 'AbortError';
}

function useAsync<TReq, TData>(
  fn: (req: TReq, signal?: AbortSignal) => Promise<TData>,
): AsyncState<TData, TReq> {
  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 指向「目前最新一筆 in-flight request」的 controller；下一筆 run 前先 abort 它，
  // 避免 React 18 Strict Mode 雙觸發或使用者快速切 dataset 時舊 fetch 後到蓋掉新結果（race）。
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback(
    async (req?: TReq) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const result = await fn((req ?? {}) as TReq, controller.signal);
        if (controller.signal.aborted) return; // 已被更新的 request 取代，丟棄 stale 結果
        setData(result);
      } catch (e) {
        if (isAbortError(e) || controller.signal.aborted) return; // 取消不算錯
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        // 只有自己仍是最新 request 才結束 loading。guard false 的兩種情況都已被妥善處理：
        //   (a) 被更新的 run 取代 → 那筆 run 自己管 loading；
        //   (b) 被 reset() 取代（controllerRef 設 null）→ reset 已呼叫 setLoading(false)。
        if (controllerRef.current === controller) {
          setLoading(false);
        }
      }
    },
    [fn],
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  // 元件卸載時 abort 仍 in-flight 的 request，避免 unmounted 後 setState 警告。
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  return { data, loading, error, run, reset };
}

export function useCostData() {
  const forecast = useAsync<CostForecastRequest, CostForecastResponse>(costApi.forecast);
  const lcoe = useAsync<LCOERequest, LCOEResponse>(costApi.lcoe);
  const monteCarlo = useAsync<MonteCarloRequest, MonteCarloResponse>(costApi.monteCarlo);
  const varFluct = useAsync<VarFluctRequest, VarFluctResponse>(costApi.varFluct);

  return { forecast, lcoe, monteCarlo, varFluct };
}

/**
 * useCostData — 4 個 cost endpoint 的 stateful hook。
 *
 * 每個 endpoint 對應一個 (data, loading, error, run) 組合：
 *   - data: 最新 response（null = 還沒跑過）
 *   - loading: 是否正在 fetch
 *   - error: 上次失敗的 error message（成功會清掉）
 *   - run(req): 觸發 fetch，更新上述 state
 */

import { useCallback, useState } from 'react';
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

function useAsync<TReq, TData>(
  fn: (req: TReq) => Promise<TData>,
): AsyncState<TData, TReq> {
  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (req?: TReq) => {
      setLoading(true);
      setError(null);
      try {
        const result = await fn((req ?? {}) as TReq);
        setData(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [fn],
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
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

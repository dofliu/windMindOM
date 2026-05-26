import { describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCostData } from './useCostData';
import { costApi, type CostForecastResponse } from '../services/costService';

/**
 * Regression tests for WMOM-20260504-13（cost fetch AbortController 防 race）。
 *
 * 核心不變式：快速連續 run（或 Strict Mode 雙觸發）時，先發出的舊 request 即使**後**才
 * resolve，也不可蓋掉新 request 的結果；且舊 request 後到不該污染 loading / error。
 */

// 把 costService 換成可控 mock；useCostData 在 hook 初始化時就抓 costApi.forecast，
// 因此 mock 必須在 import 前就位（vi.mock 會被 hoist）。
vi.mock('../services/costService', () => ({
  costApi: {
    forecast: vi.fn(),
    lcoe: vi.fn(),
    monteCarlo: vi.fn(),
    varFluct: vi.fn(),
  },
}));

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const RESP_A = { __tag: 'A' } as unknown as CostForecastResponse;
const RESP_B = { __tag: 'B' } as unknown as CostForecastResponse;

// mock reset 由 vitest.config 的 mockReset:true 統一處理（每個 test 前自動清）。
describe('useCostData AbortController 防 race', () => {
  it('舊 request 後到也不蓋掉新結果', async () => {
    const first = deferred<CostForecastResponse>();
    const second = deferred<CostForecastResponse>();
    vi.mocked(costApi.forecast)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useCostData());

    // 連續兩次 run：第二次會 abort 第一次的 controller。
    act(() => {
      void result.current.forecast.run({ dataset: 'a' });
    });
    act(() => {
      void result.current.forecast.run({ dataset: 'b' });
    });

    expect(costApi.forecast).toHaveBeenCalledTimes(2);

    // 新的（第二筆）先 resolve → 應寫入結果。
    await act(async () => {
      second.resolve(RESP_B);
      await Promise.resolve();
    });
    expect(result.current.forecast.data).toBe(RESP_B);

    // 舊的（第一筆）後 resolve → signal 已 abort，應被丟棄，不蓋掉 RESP_B。
    await act(async () => {
      first.resolve(RESP_A);
      await Promise.resolve();
    });

    expect(result.current.forecast.data).toBe(RESP_B);
    expect(result.current.forecast.loading).toBe(false);
    expect(result.current.forecast.error).toBeNull();
  });

  it('reset() 清空 data 並結束 loading', async () => {
    const pending = deferred<CostForecastResponse>();
    vi.mocked(costApi.forecast).mockReturnValueOnce(pending.promise);

    const { result } = renderHook(() => useCostData());

    act(() => {
      void result.current.forecast.run({ dataset: 'a' });
    });
    expect(result.current.forecast.loading).toBe(true);

    act(() => {
      result.current.forecast.reset();
    });

    expect(result.current.forecast.loading).toBe(false);
    expect(result.current.forecast.data).toBeNull();
    expect(result.current.forecast.error).toBeNull();

    // 被 reset abort 的 request 後到也不得寫回結果。
    await act(async () => {
      pending.resolve(RESP_A);
      await Promise.resolve();
    });
    expect(result.current.forecast.data).toBeNull();
  });

  it('fn() 拋出真實錯誤（非 abort）時寫入 error state', async () => {
    vi.mocked(costApi.forecast).mockRejectedValueOnce(new Error('API 500'));

    const { result } = renderHook(() => useCostData());

    await act(async () => {
      await result.current.forecast.run({ dataset: 'a' });
    });

    // 真實錯誤的 name 不是 'AbortError' → isAbortError 為 false → 應寫進 error state。
    expect(result.current.forecast.error).toBe('API 500');
    expect(result.current.forecast.loading).toBe(false);
    expect(result.current.forecast.data).toBeNull();
  });
});

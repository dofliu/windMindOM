import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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

describe('useCostData AbortController 防 race', () => {
  beforeEach(() => {
    vi.mocked(costApi.forecast).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

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
});

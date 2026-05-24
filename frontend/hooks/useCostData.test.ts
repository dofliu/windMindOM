import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCostData } from './useCostData';
import { costApi, type CostForecastResponse } from '../services/costService';

// WMOM-20260504-13 回歸測試：useCostData 的 useAsync race 防護（AbortController）。
// 鎖兩件事：(1) 後到的 stale 結果不得蓋掉較新的 request；(2) 被取代 request 拋的
// AbortError 不得寫進 error state。直接 mock costService.costApi，用可控 deferred 操縱回應時序。

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
  reject: (reason: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const forecastMock = costApi.forecast as unknown as Mock;

describe('useCostData useAsync race 防護（WMOM-20260504-13）', () => {
  beforeEach(() => {
    forecastMock.mockReset();
  });

  it('後到的 stale 結果不會蓋掉較新 request 的結果', async () => {
    const calls: { signal?: AbortSignal; d: Deferred<CostForecastResponse> }[] = [];
    forecastMock.mockImplementation((_req: unknown, signal?: AbortSignal) => {
      const d = deferred<CostForecastResponse>();
      calls.push({ signal, d });
      return d.promise;
    });

    const respA = { cost_per_kwh: 0.1 } as CostForecastResponse;
    const respB = { cost_per_kwh: 0.2 } as CostForecastResponse;

    const { result } = renderHook(() => useCostData());

    act(() => {
      void result.current.forecast.run({ dataset: 'A' });
    });
    act(() => {
      void result.current.forecast.run({ dataset: 'B' });
    });

    expect(calls).toHaveLength(2);
    expect(calls[0].signal?.aborted).toBe(true); // 第一筆已被第二筆 abort
    expect(calls[1].signal?.aborted).toBe(false);

    // 先回最新（B）
    await act(async () => {
      calls[1].d.resolve(respB);
    });
    expect(result.current.forecast.data).toBe(respB);

    // 後回 stale（A）→ 不得蓋掉 B
    await act(async () => {
      calls[0].d.resolve(respA);
    });
    expect(result.current.forecast.data).toBe(respB);
    // 流程結束後 loading 應為 false（守住 useAsync finally 的 controller identity 判斷：
    // 最新 request B 完成時關掉 loading，stale A 的 finally 不誤動 loading）。
    expect(result.current.forecast.loading).toBe(false);
  });

  it('被取代的 request 拋 AbortError 時不寫進 error state', async () => {
    const calls: { signal?: AbortSignal; d: Deferred<CostForecastResponse> }[] = [];
    forecastMock.mockImplementation((_req: unknown, signal?: AbortSignal) => {
      const d = deferred<CostForecastResponse>();
      calls.push({ signal, d });
      return d.promise;
    });

    const { result } = renderHook(() => useCostData());

    act(() => {
      void result.current.forecast.run({ dataset: 'A' });
    });
    act(() => {
      void result.current.forecast.run({ dataset: 'B' });
    });

    // 第一筆模擬被 abort 後 reject 的 DOMException
    await act(async () => {
      calls[0].d.reject(new DOMException('aborted', 'AbortError'));
    });
    expect(result.current.forecast.error).toBeNull();

    // 收尾：最新一筆正常完成，error 仍為 null
    await act(async () => {
      calls[1].d.resolve({ cost_per_kwh: 0.2 } as CostForecastResponse);
    });
    expect(result.current.forecast.error).toBeNull();
  });
});

/**
 * useCostData 回歸測試 — 守護 WMOM-20260504-13 的 AbortController 防 race 修法。
 *
 * 核心情境：React 18 Strict Mode 雙觸發 / 使用者快速切 dataset 時，較慢的舊
 * fetch 後到不該蓋掉較新的結果（stale-overwrites-fresh）。`useAsync` 用
 * `AbortController` + `signal.aborted` 早退守住。
 */

import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCostData } from '../useCostData';
import { costApi } from '../../services/costService';

// 把整個 cost service 換成可控的 mock；4 個 endpoint 都是 vi.fn()。
vi.mock('../../services/costService', () => ({
  costApi: {
    forecast: vi.fn(),
    lcoe: vi.fn(),
    monteCarlo: vi.fn(),
    varFluct: vi.fn(),
  },
}));

const forecastMock = costApi.forecast as unknown as Mock;

/** 建一個可由外部 resolve/reject 的 deferred promise。 */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useCostData / useAsync', () => {
  beforeEach(() => {
    forecastMock.mockReset();
  });

  it('happy path：run 成功後寫進 data、清掉 loading 與 error', async () => {
    forecastMock.mockResolvedValueOnce({ ok: 1 });
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      await result.current.forecast.run({ dataset: 'k13' });
    });

    expect(result.current.forecast.data).toEqual({ ok: 1 });
    expect(result.current.forecast.loading).toBe(false);
    expect(result.current.forecast.error).toBeNull();
  });

  it('race：較慢的舊 run 後到時不得蓋掉較新的結果', async () => {
    const slow = deferred<{ tag: string }>();
    const fast = deferred<{ tag: string }>();
    forecastMock.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise);

    const { result } = renderHook(() => useCostData());

    // run #1（慢）先送出，緊接著 run #2（快）— run #2 會 abort run #1 的 controller。
    let p1!: Promise<void>;
    let p2!: Promise<void>;
    act(() => {
      p1 = result.current.forecast.run({ dataset: 'A' });
      p2 = result.current.forecast.run({ dataset: 'B' });
    });

    // 較新的 run #2 先 resolve → data = B。
    await act(async () => {
      fast.resolve({ tag: 'B' });
      await p2;
    });
    expect(result.current.forecast.data).toEqual({ tag: 'B' });

    // 較舊的 run #1 後到 → 因 controller 已被 abort，early-return，data 維持 B。
    await act(async () => {
      slow.resolve({ tag: 'A' });
      await p1;
    });
    expect(result.current.forecast.data).toEqual({ tag: 'B' });
  });

  it('AbortError 不寫進 error state（取消不算失敗）', async () => {
    const abortErr = Object.assign(new Error('aborted'), { name: 'AbortError' });
    forecastMock.mockRejectedValueOnce(abortErr);
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      await result.current.forecast.run({ dataset: 'k13' });
    });

    expect(result.current.forecast.error).toBeNull();
    expect(result.current.forecast.data).toBeNull();
  });

  it('一般 Error 會寫進 error state 並結束 loading', async () => {
    forecastMock.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      await result.current.forecast.run({ dataset: 'k13' });
    });

    expect(result.current.forecast.error).toBe('boom');
    expect(result.current.forecast.loading).toBe(false);
  });

  it('reset 清空 data/error 並中止 in-flight request', async () => {
    forecastMock.mockResolvedValueOnce({ ok: 1 });
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      await result.current.forecast.run({ dataset: 'k13' });
    });
    expect(result.current.forecast.data).toEqual({ ok: 1 });

    act(() => {
      result.current.forecast.reset();
    });

    await waitFor(() => {
      expect(result.current.forecast.data).toBeNull();
      expect(result.current.forecast.error).toBeNull();
      expect(result.current.forecast.loading).toBe(false);
    });
  });
});

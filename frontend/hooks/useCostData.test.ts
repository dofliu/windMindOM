/**
 * useCostData regression test。
 *
 * 守住 WMOM-20260504-13（2026-05-23）的 AbortController race 防護：
 *   - 快速切換 dataset 時，舊（慢）fetch 後到不可蓋掉新結果（stale-overwrites-fresh）。
 *   - 被取消的 fetch 拋 AbortError 不可寫進 error state。
 *   - reset() 清空 data/error 並 abort 仍 in-flight 的 request。
 *
 * 作法：mock costService.costApi，讓每支 endpoint 回一個「外部可手動 resolve/reject」
 * 的 promise，藉以精準控制 A/B 兩筆 request 的完成順序。
 */
import { renderHook, act } from '@testing-library/react';
import { useCostData } from './useCostData';

interface PendingCall {
  req: unknown;
  signal?: AbortSignal;
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}

// vi.mock 會被 hoist 到 import 之上，故用 vi.hoisted 共享這個 calls 陣列。
const { calls } = vi.hoisted(() => ({ calls: [] as PendingCall[] }));

vi.mock('./../services/costService', () => {
  const makeFn =
    () =>
    (req: unknown, signal?: AbortSignal): Promise<unknown> =>
      new Promise((resolve, reject) => {
        calls.push({ req, signal, resolve, reject });
      });
  return {
    costApi: {
      forecast: makeFn(),
      lcoe: makeFn(),
      monteCarlo: makeFn(),
      varFluct: makeFn(),
    },
  };
});

beforeEach(() => {
  calls.length = 0;
});

describe('useCostData / useAsync — AbortController race 防護', () => {
  it('快速切換時，舊 fetch 後到不會蓋掉新結果', async () => {
    const { result } = renderHook(() => useCostData());

    // run A（慢）→ run B（快），B 會先 abort A 的 controller
    await act(async () => {
      void result.current.forecast.run({ dataset: 'A' });
    });
    await act(async () => {
      void result.current.forecast.run({ dataset: 'B' });
    });

    expect(calls).toHaveLength(2);
    expect(calls[0].signal?.aborted).toBe(true); // A 已被 B abort
    expect(calls[1].signal?.aborted).toBe(false);

    // 先 resolve B（新的），再 resolve A（舊的、慢的）
    await act(async () => {
      calls[1].resolve({ tag: 'B-data' });
    });
    await act(async () => {
      calls[0].resolve({ tag: 'A-data' });
    });

    // A 因 signal.aborted 早退，不得蓋掉 B
    expect((result.current.forecast.data as unknown as { tag: string } | null)?.tag).toBe('B-data');
    expect(result.current.forecast.loading).toBe(false);
    expect(result.current.forecast.error).toBeNull();
  });

  it('被取消的 fetch 拋 AbortError 不會寫進 error state', async () => {
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      void result.current.forecast.run();
    });
    await act(async () => {
      void result.current.forecast.run(); // abort 掉第一筆
    });

    await act(async () => {
      calls[0].reject(new DOMException('aborted', 'AbortError'));
    });

    expect(result.current.forecast.error).toBeNull();
  });

  it('reset() 清空 data/error 並 abort 仍 in-flight 的 request', async () => {
    const { result } = renderHook(() => useCostData());

    await act(async () => {
      void result.current.forecast.run();
    });
    await act(async () => {
      calls[0].resolve({ tag: 'X' });
    });
    expect((result.current.forecast.data as unknown as { tag: string } | null)?.tag).toBe('X');

    await act(async () => {
      void result.current.forecast.run(); // 第二筆 in-flight
    });
    await act(async () => {
      result.current.forecast.reset();
    });

    expect(result.current.forecast.data).toBeNull();
    expect(result.current.forecast.loading).toBe(false);
    expect(calls[1].signal?.aborted).toBe(true);
  });
});

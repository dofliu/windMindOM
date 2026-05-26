import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRealtimeData } from './useRealtimeData';

/**
 * Regression tests for WMOM-20260504-12（WS 殭屍重連洩漏根治）。
 *
 * 核心不變式：
 *   1. 元件 unmount 後，即使底層 socket 的 close() 觸發 onclose，也**不可**再排程重連
 *      → 沒有殭屍 WebSocket 累積（這是 5/24 修掉的記憶體成長真因）。
 *   2. 元件仍掛載時，server 端關閉連線**仍應**在 3 秒後重連（修復不可破壞正常重連）。
 */

// 受控的 WebSocket mock：記錄所有被建立的實例，close() 同步觸發 onclose
// （模擬瀏覽器 close → 觸發 close 事件的行為，正是舊版殭屍重連的觸發點）。
class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  readyState: number = MockWebSocket.CONNECTING;
  sent: string[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED;
    // 模擬瀏覽器：close() 會（非同步地）觸發 onclose。同步呼叫讓測試 deterministic。
    this.onclose?.();
  }
}

// 只結算 microtask（初始 REST fetch 的 fetch().then(json).then(setTurbines) 鏈需數個
// tick）。fake timers 下不能用 setTimeout flush（會卡住，timer 不會自己前進）。
function flushMicrotasks(): Promise<void> {
  return act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('useRealtimeData WS 生命週期', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    // 初始 REST fetch + poll fallback 不打真實網路。
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ json: () => Promise.resolve([]) })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('unmount 後不再建立新的 WebSocket（殭屍重連根治）', async () => {
    const { unmount } = renderHook(() => useRealtimeData());
    await flushMicrotasks();

    // 掛載後僅一條連線。
    expect(MockWebSocket.instances).toHaveLength(1);

    // unmount → cleanup 解除 handler 後 close()；close() 觸發的 onclose 不該排程重連。
    act(() => {
      unmount();
    });

    // 即使把時間快轉遠超過 3 秒重連間隔，也不該有第二條連線。
    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it('掛載期間 server 關閉連線後 3 秒內重連（不破壞正常重連）', async () => {
    renderHook(() => useRealtimeData());
    await flushMicrotasks();
    expect(MockWebSocket.instances).toHaveLength(1);

    // 模擬 server 端關閉：直接觸發第一條連線的 onclose（此時尚未 unmount，handler 仍在）。
    act(() => {
      MockWebSocket.instances[0].onclose?.();
    });

    // onclose 不立即重連（應排程一條 3s 後的 timer），故當下仍只有一條。
    expect(MockWebSocket.instances).toHaveLength(1);

    // 差 1ms 不到 3 秒 → 重連 timer 尚未觸發。
    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(MockWebSocket.instances).toHaveLength(1);

    // 補滿到 3 秒 → 應建立第二條連線。
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRealtimeData } from './useRealtimeData';

// WMOM-20260504-12 回歸測試：useRealtimeData 的 WebSocket 生命週期。
// 真因是「殭屍重連」——卸載時 ws.close() 非同步觸發 onclose，若 onclose 仍無條件
// 排程 setTimeout(connect) 就會在卸載後不斷產生新的 WebSocket。修法以 disposed 旗標 +
// 卸載時先解除 handler 再 close()。本測試以可控的 FakeWebSocket + fake timer 鎖住此行為。

type CloseHandler = (() => void) | null;

class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: CloseHandler = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = FakeWebSocket.CLOSED;
    // 模擬真實瀏覽器：onclose 在 close() 之後「非同步」觸發（不是同步）。這正是殭屍重連
    // bug 的核心 —— cleanup 跑完後 onclose 才放出，若那時 onclose 仍掛著且 connect 無
    // disposed guard，就會排出沒人清的重連 timer。用 setTimeout(…,0) 讓 fake timer 能驅動。
    setTimeout(() => this.onclose?.(), 0);
  });

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  /** 手動模擬伺服器主動斷線（非經由 close()）時觸發 onclose。 */
  emitClose(): void {
    this.onclose?.();
  }
}

function mockFetchEmptyTurbines() {
  return vi.fn(() => Promise.resolve({ json: () => Promise.resolve([]) } as Response));
}

describe('useRealtimeData WebSocket 生命週期（WMOM-20260504-12）', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('fetch', mockFetchEmptyTurbines());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('卸載後即使 socket 關閉也不再排程重連（無殭屍 WebSocket）', () => {
    const { unmount } = renderHook(() => useRealtimeData());
    expect(FakeWebSocket.instances).toHaveLength(1);
    const ws = FakeWebSocket.instances[0];

    // unmount → cleanup 解除 4 個 handler 後呼叫 close()；close() 會（如真實瀏覽器）
    // 觸發 onclose，但此時 onclose 已是 null，加上 disposed guard，故不得排程重連。
    act(() => {
      unmount();
    });

    expect(ws.close).toHaveBeenCalledTimes(1);
    expect(ws.onclose).toBeNull();
    expect(ws.onmessage).toBeNull();
    expect(ws.onopen).toBeNull();
    expect(ws.onerror).toBeNull();

    // 再推進時間確認沒有任何殘留的重連 timer 會建出第二條 WebSocket
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('掛載期間 socket 斷線仍會在 3 秒後重連（重連機制未被誤殺）', () => {
    const { unmount } = renderHook(() => useRealtimeData());
    expect(FakeWebSocket.instances).toHaveLength(1);
    const ws = FakeWebSocket.instances[0];

    // 模擬伺服器主動斷線（掛載中，disposed=false）
    act(() => {
      ws.emitClose();
      vi.advanceTimersByTime(3000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => {
      unmount();
    });
  });
});

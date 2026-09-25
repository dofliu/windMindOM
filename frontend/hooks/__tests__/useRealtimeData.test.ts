/**
 * useRealtimeData 回歸測試 — 守護 WMOM-20260504-12 的 WS 殭屍重連洩漏修法。
 *
 * 核心情境：`ws.close()` 會非同步觸發 `onclose`；若 `onclose` 無條件
 * `setTimeout(connect, 3000)` 重連，unmount 後仍會排一條清不到的重連 timer →
 * 殭屍 WebSocket 無限累積。修法用 `disposed` 旗標 + cleanup 先解除四個 handler
 * 再 close()（雙保險）。本測試同時驗「handler 被解除」與「殭屍 onclose 不重連」。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRealtimeData } from '../useRealtimeData';
import { TurbineStatus } from '../../types';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

type Handler = ((ev?: unknown) => void) | null;

/** 最小 WebSocket 替身：記錄所有 instance、close 次數，並允許手動觸發 handler。 */
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  url: string;
  readyState: number = MockWebSocket.CONNECTING;
  onopen: Handler = null;
  onmessage: Handler = null;
  onclose: Handler = null;
  onerror: Handler = null;
  sent: string[] = [];
  closeCalls = 0;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  // 真瀏覽器 close() 後會非同步 fire onclose；這裡只記次數，onclose 由測試手動觸發
  // 以精準驗證 disposed guard 行為。
  close(): void {
    this.closeCalls++;
    this.readyState = MockWebSocket.CLOSED;
  }
}

/** 一筆通過 apiToTurbineData 的最小 turbine payload。 */
function makeReading(name: string) {
  return {
    turbineId: name,
    name,
    timestamp: '2026-05-26T00:00:00Z',
    status: 'OPERATING',
    turState: 5,
    windSpeed: 8.2,
    powerOutput: 3.1,
    rotorSpeed: 12.0,
    bladeAngle: 1.5,
    temperature: 40,
    vibration: 0.2,
    voltage: 690,
    current: 100,
    yawAngle: 180,
    gearboxTemp: 55,
    frequency: 50,
    hydraulicPressure: 200,
    history: null,
  };
}

describe('useRealtimeData WebSocket 生命週期', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
    // jsdom 無原生 WebSocket；注入替身。
    vi.stubGlobal('WebSocket', MockWebSocket);
    // 初始 REST fetch + poll fallback 都打 fetch，給一個空陣列。
    // json 用同步回傳（hook 的 .then(res => res.json()) 會自動包 Promise），
    // 避免額外 microtask tick 讓 flush 順序隱性依賴 act() 深度。
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ json: () => [] }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('mount 後建立單一 WebSocket 連線', () => {
    renderHook(() => useRealtimeData());
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('/ws/realtime');
  });

  it('收到 message 後把 payload 映射進 turbines', () => {
    const { result } = renderHook(() => useRealtimeData());
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.();
      ws.onmessage?.({ data: JSON.stringify([makeReading('WTG-01'), makeReading('WTG-02')]) });
    });

    // setTurbines 在 act() 內同步完成，毋須 waitFor（fake timer 下 waitFor 會卡住）。
    expect(result.current.turbines).toHaveLength(2);
    expect(result.current.turbines[0].name).toBe('WTG-01');
    expect(result.current.turbines[0].status).toBe(TurbineStatus.OPERATING);
    expect(ws.sent).toContain('ping');
  });

  it('unmount 解除四個 handler 並 close（不留殭屍 handler）', () => {
    const { unmount } = renderHook(() => useRealtimeData());
    const ws = MockWebSocket.instances[0];

    unmount();

    expect(ws.closeCalls).toBe(1);
    expect(ws.onopen).toBeNull();
    expect(ws.onmessage).toBeNull();
    expect(ws.onclose).toBeNull();
    expect(ws.onerror).toBeNull();
  });

  it('unmount 後即使殘留的 onclose 被觸發也不重連（disposed guard）', () => {
    // 註：原始 bug 在 React StrictMode dev 的 mount→unmount→remount 雙觸發下累積殭屍。
    // vitest 預設不啟動 StrictMode double-invoke，故本測試改以「擷取 onclose closure →
    // unmount → 手動觸發」模擬殭屍 onclose 後到。守護目標是 disposed guard 的語意
    // （unmount 後 onclose 不得重連），與雙觸發路徑語意等價；非疏漏而是刻意取捨。
    const { unmount } = renderHook(() => useRealtimeData());
    const ws = MockWebSocket.instances[0];

    // 在 cleanup 解除 handler 前先擷取 onclose 參考，模擬「殭屍 onclose 後到」。
    const capturedOnclose = ws.onclose;
    expect(capturedOnclose).toBeTypeOf('function');

    unmount();

    // 殭屍 onclose 後到 → disposed guard 應使其變成 no-op，不排重連 timer。
    act(() => {
      capturedOnclose?.();
      vi.advanceTimersByTime(10_000);
    });

    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it('連線斷開（仍掛載）會在 3 秒後重連一條新連線', () => {
    renderHook(() => useRealtimeData());
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.onclose?.();
      vi.advanceTimersByTime(3000);
    });

    expect(MockWebSocket.instances).toHaveLength(2);
  });
});

// ─── authFetch 稽核（WMOM-20260925-01）───────────────────────────────────────
//
// 初始 REST fetch + WS 斷線輪詢 fallback 皆打 `GET /api/turbines`（後端
// `require_authenticated()`），先前是裸 fetch。本組鎖住兩處都已改 authFetch。

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

describe('useRealtimeData — authFetch 稽核（WMOM-20260925-01）', () => {
  const fetchMock = vi.fn().mockResolvedValue({ json: () => [] });

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', MockWebSocket);
    fetchMock.mockClear();
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    clearAuthToken();
  });

  it('已登入 → 初始 REST fetch 帶 Authorization header', () => {
    setAuthToken('test-token-realtime');
    renderHook(() => useRealtimeData());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBe(
      'Bearer test-token-realtime',
    );
  });

  it('未登入 → 初始 REST fetch 不帶 Authorization header（過渡期行為不變）', () => {
    renderHook(() => useRealtimeData());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBeUndefined();
  });

  it('已登入 → WS 斷線輪詢 fallback（5 秒）帶 Authorization header', () => {
    setAuthToken('test-token-realtime');
    renderHook(() => useRealtimeData());
    fetchMock.mockClear();
    // WS readyState 停在 CONNECTING（非 OPEN）→ 輪詢 fallback 條件成立。
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBe(
      'Bearer test-token-realtime',
    );
  });
});

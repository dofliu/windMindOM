/**
 * useRealtimeData regression test。
 *
 * 守住 WMOM-20260504-12（2026-05-24）的 WebSocket 殭屍重連根治：
 *   - 卸載後（unmount）不可再排程重連、不可再建立新 WebSocket（殭屍洩漏根因）。
 *   - 連線中斷（仍掛載）時，3 秒後仍應自動重連（正常行為不可被誤殺）。
 *   - 收到 WS 訊息會解析並更新 turbines。
 *
 * 作法：以 FakeWebSocket 取代全域 WebSocket，記錄所有被建立的實例與 handler，
 * 並用 vi 的 fake timer 推進重連倒數。fetch 以永不 resolve 的 promise mock 掉，
 * 避免初始 REST fetch / poll 干擾 WS 行為斷言。
 */
import { renderHook, act } from '@testing-library/react';
import { useRealtimeData } from './useRealtimeData';
import { TurbineStatus } from '../types';

type Handler = ((event?: unknown) => void) | null;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  url: string;
  readyState = FakeWebSocket.CONNECTING;
  onopen: Handler = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: Handler = null;
  onerror: Handler = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  // 真實 WebSocket.close() 會（若 handler 仍掛著）非同步觸發 onclose。
  // hook 的正確 cleanup 會在 close() 前先把 onclose 設 null，故這裡不會重排重連。
  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }

  // 測試輔助：模擬 server 行為
  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
  // 初始 REST fetch / poll 都走 fetch；回永不 resolve 的 promise，隔離成只測 WS。
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise<Response>(() => {})),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useRealtimeData — WebSocket 殭屍重連根治', () => {
  it('卸載後不再排程重連、不再建立新 WebSocket', () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useRealtimeData());
    expect(FakeWebSocket.instances).toHaveLength(1);

    unmount();

    // 推進超過重連間隔（3s）與 poll（5s）：若有殭屍重連，instances 會增加
    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('連線中斷（仍掛載）時，3 秒後自動重連', () => {
    vi.useFakeTimers();
    renderHook(() => useRealtimeData());
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.simulateOpen();
    });
    // 模擬 server 主動斷線（非卸載）：直接觸發 hook 的 onclose handler
    act(() => {
      ws.onclose?.();
    });
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2); // 重連建立新 WS
  });

  it('收到 WS 訊息會解析並更新 turbines', () => {
    const { result } = renderHook(() => useRealtimeData());
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.simulateOpen();
    });
    act(() => {
      ws.simulateMessage([
        {
          name: 'WT01',
          status: 'OPERATING',
          turState: 6,
          windSpeed: 8.2,
          powerOutput: 3.2,
          rotorSpeed: 12,
          bladeAngle: 2,
          temperature: 40,
          vibration: 1,
          voltage: 690,
          current: 100,
          history: [],
        },
      ]);
    });

    expect(result.current.turbines).toHaveLength(1);
    expect(result.current.turbines[0].name).toBe('WT01');
    expect(result.current.turbines[0].status).toBe(TurbineStatus.OPERATING);
  });
});

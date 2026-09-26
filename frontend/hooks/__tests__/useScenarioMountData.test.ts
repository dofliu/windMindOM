/**
 * useScenarioMountData 測試（PR C Phase 1，WMOM-20260926-03）。
 *
 * 給定 scenarioId，一次性 GET `/api/scenarios/{id}/turbines`（後端 `require_authenticated()`）
 * 並轉成 `TurbineData[]`（重用 `useRealtimeData.apiToTurbineData`）。全程 mock `fetch`，零真連線。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useScenarioMountData } from '../useScenarioMountData';
import { TurbineStatus } from '../../types';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

const fetchMock = vi.fn();

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function apiReading(over: Record<string, unknown> = {}) {
  return {
    turbineId: 'WT001',
    name: 'WTG-01',
    timestamp: '2026-03-01T00:00:00',
    status: 'OPERATING',
    turState: 6,
    windSpeed: 8.5,
    powerOutput: 1.8,
    rotorSpeed: 12.0,
    bladeAngle: 3,
    temperature: 44,
    vibration: 1.1,
    voltage: 690,
    current: 95,
    yawAngle: 0,
    gearboxTemp: 39,
    frequency: 50,
    hydraulicPressure: 120,
    history: null,
    ...over,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearAuthToken();
});

describe('useScenarioMountData', () => {
  it('scenarioId=null → 不發起 fetch，turbines 為空陣列', () => {
    const { result } = renderHook(() => useScenarioMountData(null));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.turbines).toEqual([]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('scenarioId 有值 → GET /api/scenarios/{id}/turbines，成功後映射成 TurbineData[]', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [apiReading({ turbineId: 'WT001', name: 'WTG-01', powerOutput: 1.8 })],
    } as unknown as Response);

    const { result } = renderHook(() => useScenarioMountData(7));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8100/api/scenarios/7/turbines',
      expect.any(Object),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.turbines).toHaveLength(1);
    expect(result.current.turbines[0]).toMatchObject({
      id: 1,
      name: 'WTG-01',
      status: TurbineStatus.OPERATING,
      powerOutput: 1.8,
    });
    expect(result.current.error).toBeNull();
  });

  it('HTTP 非 2xx → error 設定、turbines 為空陣列', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 } as unknown as Response);

    const { result } = renderHook(() => useScenarioMountData(999));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.turbines).toEqual([]);
    expect(result.current.error).toContain('404');
  });

  it('網路例外 → error 設定、turbines 為空陣列', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useScenarioMountData(7));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.turbines).toEqual([]);
    expect(result.current.error).toBe('network down');
  });

  it('scenarioId 變動 → 重新 fetch 新的情境', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url.includes('/7/')
            ? [apiReading({ turbineId: 'WT001' })]
            : [apiReading({ turbineId: 'WT002' }), apiReading({ turbineId: 'WT003' })],
      } as unknown as Response),
    );

    const { result, rerender } = renderHook(
      ({ id }: { id: number | null }) => useScenarioMountData(id),
      { initialProps: { id: 7 } },
    );
    await waitFor(() => expect(result.current.turbines).toHaveLength(1));

    rerender({ id: 12 });
    await waitFor(() => expect(result.current.turbines).toHaveLength(2));
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://localhost:8100/api/scenarios/12/turbines',
      expect.any(Object),
    );
  });

  it('已登入 → 走 authFetch 帶 Authorization header', async () => {
    setAuthToken('test-token-scenario-mount');
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] } as unknown as Response);

    renderHook(() => useScenarioMountData(7));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(authHeaderOf(fetchMock.mock.calls[0][1] as RequestInit | undefined)).toBe(
      'Bearer test-token-scenario-mount',
    );
  });
});

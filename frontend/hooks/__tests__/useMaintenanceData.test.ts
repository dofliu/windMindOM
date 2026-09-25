/**
 * useMaintenanceData — authFetch 稽核（WMOM-20260925-01）。
 *
 * `WMOM-20260923-10` 系列的 authFetch 稽核只掃 `components/*.tsx`，未涵蓋
 * `frontend/hooks/`——`MaintenanceHub.tsx` 的實際網路呼叫全部委派給本 hook，元件本身
 * 一個裸 fetch 都沒有，容易誤判「已全部 authFetch 化」。本檔先前無測試覆蓋，補上
 * mount GET（已登入/未登入對照）+ 兩個 SUPERVISOR-only 寫入呼叫（`toggleTechnicianStatus`
 * PATCH、`createWorkOrder` POST）的 header 斷言。全程 mock `fetch`，零真連線。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useMaintenanceData } from '../useMaintenanceData';
import { setAuthToken, clearAuthToken } from '../../services/authClient';
import { TechnicianStatus } from '../../types';

const fetchMock = vi.fn();

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function techniciansResponse(items: Array<Record<string, unknown>>) {
  return { ok: true, json: async () => ({ data: items }) } as unknown as Response;
}

function workOrdersResponse(items: Array<Record<string, unknown>>) {
  return { ok: true, json: async () => ({ data: items }) } as unknown as Response;
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).includes('/api/maintenance/technicians')) {
      return techniciansResponse([{ id: 1, name: 'Tech A', status: 'ON_DUTY' }]);
    }
    if (String(url).includes('/api/maintenance/work-orders')) {
      return workOrdersResponse([]);
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearAuthToken();
});

describe('useMaintenanceData — authFetch 稽核（WMOM-20260925-01）', () => {
  it('已登入 → mount 時 technicians/work-orders 兩條 GET 皆帶 Authorization header', async () => {
    setAuthToken('test-token-maint');
    renderHook(() => useMaintenanceData());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calls = fetchMock.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    for (const call of calls) {
      expect(authHeaderOf(call[1] as RequestInit | undefined)).toBe('Bearer test-token-maint');
    }
  });

  it('未登入 → mount 時兩條 GET 皆不帶 Authorization header（過渡期行為不變）', async () => {
    renderHook(() => useMaintenanceData());
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calls = fetchMock.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    for (const call of calls) {
      expect(authHeaderOf(call[1] as RequestInit | undefined)).toBeUndefined();
    }
  });

  it('已登入 → toggleTechnicianStatus（SUPERVISOR-only PATCH）帶 Authorization header', async () => {
    setAuthToken('test-token-maint');
    const { result } = renderHook(() => useMaintenanceData());
    await waitFor(() => expect(result.current.technicians).toHaveLength(1));
    fetchMock.mockClear();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: 'Tech A', status: 'OFF_DUTY' }),
    } as unknown as Response);
    await act(async () => {
      await result.current.toggleTechnicianStatus(1);
    });
    const patchCall = fetchMock.mock.calls.find(c =>
      String(c[0]).includes('/technicians/1/status'),
    );
    expect(patchCall).toBeTruthy();
    expect((patchCall![1] as RequestInit).method).toBe('PATCH');
    expect(authHeaderOf(patchCall![1] as RequestInit)).toBe('Bearer test-token-maint');
  });

  it('已登入 → createWorkOrder（SUPERVISOR-only POST）帶 Authorization header', async () => {
    setAuthToken('test-token-maint');
    const { result } = renderHook(() => useMaintenanceData());
    await waitFor(() => expect(result.current.technicians).toHaveLength(1));
    fetchMock.mockClear();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/work-orders')) {
        return {
          ok: true,
          json: async () => ({
            id: 'wo-9', turbineId: 1, turbineName: 'WT001', technicianId: 1,
            status: 'DISPATCHED', createdAt: 0, faultDescription: 'x', notes: '', photos: [],
          }),
        } as unknown as Response;
      }
      return techniciansResponse([{ id: 1, name: 'Tech A', status: 'DISPATCHED' }]);
    });
    await act(async () => {
      await result.current.createWorkOrder(1, 'WT001', 'x', 1);
    });
    const postCall = fetchMock.mock.calls.find(
      c => String(c[0]).endsWith('/api/maintenance/work-orders') && (c[1] as RequestInit)?.method === 'POST',
    );
    expect(postCall).toBeTruthy();
    expect(authHeaderOf(postCall![1] as RequestInit)).toBe('Bearer test-token-maint');
  });
});

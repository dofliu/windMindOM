/**
 * useSettings — baseWindSpeed 同步回歸測試（WMOM-20260718-01）。
 *
 * bug：`simChanged` 的變更偵測漏掉 `baseWindSpeed`，只改風速時不會 POST 到後端，
 * 導致 Settings 改風速對 sim 無反應。本測試守住「只改 baseWindSpeed 也要同步」。
 * 全程 mock `fetch`，零真連線。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSettings } from '../useSettings';

const fetchMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) } as unknown as Response);
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function simCall() {
  return fetchMock.mock.calls.find(c => String(c[0]).includes('/api/config/simulation'));
}

describe('useSettings — baseWindSpeed sync', () => {
  it('只改 baseWindSpeed 也會 POST /api/config/simulation（帶新風速）', () => {
    const { result } = renderHook(() => useSettings());
    const base = result.current.settings;
    const newSpeed = base.simulation.baseWindSpeed + 8;

    act(() => {
      result.current.saveSettings({
        ...base,
        simulation: { ...base.simulation, baseWindSpeed: newSpeed },
      });
    });

    const call = simCall();
    expect(call).toBeTruthy();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body.baseWindSpeed).toBe(newSpeed);
  });

  it('turbineCount 改變仍會同步（未回歸）', () => {
    const { result } = renderHook(() => useSettings());
    const base = result.current.settings;
    act(() => {
      result.current.saveSettings({
        ...base,
        simulation: { ...base.simulation, turbineCount: base.simulation.turbineCount + 1 },
      });
    });
    expect(simCall()).toBeTruthy();
  });

  it('simulation 參數皆未變 → 不呼叫後端', () => {
    const { result } = renderHook(() => useSettings());
    const base = result.current.settings;
    act(() => {
      result.current.saveSettings({ ...base, simulation: { ...base.simulation } });
    });
    expect(simCall()).toBeFalsy();
  });
});

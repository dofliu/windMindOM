/**
 * ScenarioMountContext / ScenarioMountProvider 測試（PR C Phase 1，WMOM-20260926-03）。
 *
 * 用 harness 元件把 context 值投影成 DOM 來斷言 mount/unmount 的公開行為，比照
 * `hooks/__tests__/useAuth.test.tsx` 既有範式。
 *
 * `turbines`/`loading`/`error` 由 Provider 內建的 `useScenarioMountData` 抓取（code review
 * should-fix：這三個欄位原本只在 App.tsx 算出來、從未真的被驗證過會正確隨 mount() 傳遞——
 * 全程 mock `fetch`，零真連線。
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import { ScenarioMountProvider, useScenarioMount } from '../ScenarioMountContext';

function Harness() {
  const { mounted, mount, unmount, turbines, loading, error } = useScenarioMount();
  return (
    <div>
      <div data-testid="mounted">{mounted ? `${mounted.id}:${mounted.name}` : 'none'}</div>
      <div data-testid="turbines">{turbines.map(t => t.name).join(',')}</div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="error">{error ?? 'none'}</div>
      <button onClick={() => mount({ id: 7, name: '颱風測試' })}>mount</button>
      <button onClick={() => mount({ id: 9, name: '另一個情境' })}>mount-other</button>
      <button onClick={unmount}>unmount</button>
    </div>
  );
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ScenarioMountContext', () => {
  it('未 mount 時 mounted 為 null，不發起任何 fetch', () => {
    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    expect(screen.getByTestId('mounted')).toHaveTextContent('none');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('mount(scenario) 後 mounted 反映該情境', () => {
    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    expect(screen.getByTestId('mounted')).toHaveTextContent('7:颱風測試');
  });

  it('再 mount 另一個情境 → 直接覆蓋（單一掛載，非疊加）', () => {
    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    fireEvent.click(screen.getByText('mount-other'));
    expect(screen.getByTestId('mounted')).toHaveTextContent('9:另一個情境');
  });

  it('unmount() 清空回 null', () => {
    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    expect(screen.getByTestId('mounted')).toHaveTextContent('7:颱風測試');
    fireEvent.click(screen.getByText('unmount'));
    expect(screen.getByTestId('mounted')).toHaveTextContent('none');
  });

  it('initialMounted seed 讓初次 render 就是已掛載狀態（測試用時序穩定性 seam）', () => {
    render(
      <ScenarioMountProvider initialMounted={{ id: 3, name: '種子情境' }}>
        <Harness />
      </ScenarioMountProvider>,
    );
    expect(screen.getByTestId('mounted')).toHaveTextContent('3:種子情境');
  });

  it('useScenarioMount 在 Provider 外呼叫 → fail-fast 拋錯（比照 useAuth/useTheme 慣例）', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Harness />)).toThrow(
      'useScenarioMount must be used within <ScenarioMountProvider>',
    );
    consoleErrorSpy.mockRestore();
  });

  // ── 內建 useScenarioMountData（code review should-fix）────────────────────

  it('mount 後成功 fetch → turbines/loading 隨 context 一起分發', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [{
        turbineId: 'WT001', name: 'WTG-01', timestamp: '2026-01-01T00:00:00',
        status: 'OPERATING', turState: 6, windSpeed: 8, powerOutput: 1.5,
        rotorSpeed: 12, bladeAngle: 3, temperature: 44, vibration: 1, voltage: 690,
        current: 90, yawAngle: 0, gearboxTemp: 39, frequency: 50,
        hydraulicPressure: 120, history: null,
      }],
    } as unknown as Response);

    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8100/api/scenarios/7/turbines',
      expect.any(Object),
    );
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('turbines')).toHaveTextContent('WTG-01');
    expect(screen.getByTestId('error')).toHaveTextContent('none');
  });

  it('mount 後 fetch 失敗（如情境已被刪除的 404）→ error 隨 context 分發', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 } as unknown as Response);

    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('404'));
    expect(screen.getByTestId('turbines')).toHaveTextContent('');
  });

  it('unmount() 後 turbines 清空、不殘留上一個情境的資料', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [{
        turbineId: 'WT001', name: 'WTG-01', timestamp: '2026-01-01T00:00:00',
        status: 'OPERATING', turState: 6, windSpeed: 8, powerOutput: 1.5,
        rotorSpeed: 12, bladeAngle: 3, temperature: 44, vibration: 1, voltage: 690,
        current: 90, yawAngle: 0, gearboxTemp: 39, frequency: 50,
        hydraulicPressure: 120, history: null,
      }],
    } as unknown as Response);

    render(
      <ScenarioMountProvider>
        <Harness />
      </ScenarioMountProvider>,
    );
    fireEvent.click(screen.getByText('mount'));
    await waitFor(() => expect(screen.getByTestId('turbines')).toHaveTextContent('WTG-01'));
    fireEvent.click(screen.getByText('unmount'));
    expect(screen.getByTestId('turbines')).toHaveTextContent('');
  });
});

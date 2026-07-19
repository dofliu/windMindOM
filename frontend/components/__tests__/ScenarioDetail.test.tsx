/**
 * ScenarioDetail render 測試（WMOM-20260719-02 前端，DEC-20260719-01）。
 *
 * ScenarioDetail 調閱單一已保存情境：讀 `/api/scenarios/{id}/turbines/{tid}/history`（session
 * 隔離）→ 詮釋資料 + 發電量/風速雙軸趨勢 + 故障事件清單。守住：mount 抓 history、詮釋資料呈現、
 * 故障事件清單、換機組重抓、返回回呼、空資料狀態。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import ScenarioDetail, { type SavedScenario } from '../ScenarioDetail';
import { ThemeProvider } from '../../theme/ThemeProvider';

const SCENARIO: SavedScenario = {
  id: 7,
  started_at: '2026-07-19T10:00:00',
  ended_at: '2026-07-19T10:01:00',
  turbine_count: 3,
  config: {
    kind: 'scenario',
    name: '暴風測試',
    wind_profile: 'storm',
    duration_hours: 24,
    time_step: 60,
    total_readings: 4320,
    faults_injected: 1,
    status: 'ok',
  },
};

const HISTORY = {
  scenario_id: 7,
  turbine_id: 'WT001',
  readings: [
    { timestamp: '2026-07-19T10:00:00', scada: { WTUR_TotPwrAt: 1500, WMET_WSpeedNac: 12 } },
    { timestamp: '2026-07-19T10:01:00', scada: { WTUR_TotPwrAt: 1600, WMET_WSpeedNac: 13 } },
  ],
  events: [
    {
      id: 1,
      timestamp: '2026-07-19T10:00:30',
      turbine_id: 'WT002',
      event_type: 'fault',
      title: 'Scenario fault: hydraulic_leak on WT002',
    },
  ],
  events_by_time_window: true,
};

function jsonRes(body: unknown, ok = true, status = 200): Promise<Response> {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

function installFetch(history: unknown = HISTORY) {
  fetchMock = vi.fn((url: string) => {
    if (url.includes('/api/scenarios/') && url.includes('/history')) return jsonRes(history);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function historyCalls() {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/history'));
}

async function renderDetail(onBack = vi.fn(), lang: 'en' | 'zh' = 'zh') {
  await act(async () => {
    render(
      <ThemeProvider>
        <ScenarioDetail scenario={SCENARIO} lang={lang} onBack={onBack} />
      </ThemeProvider>,
    );
  });
  return onBack;
}

beforeEach(() => installFetch());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ScenarioDetail — 詮釋資料 + mount', () => {
  it('顯示情境名稱與統計（時長 / 筆數 / 注入故障數）', async () => {
    await renderDetail();
    expect(screen.getByText('暴風測試')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
    expect(screen.getByText('4,320')).toBeInTheDocument(); // total_readings
  });

  it('mount 時抓該情境某機組的 history，且 limit 夠大（12000）覆蓋常見情境全長', async () => {
    await renderDetail();
    await waitFor(() =>
      expect(historyCalls().some(u => u.includes('/api/scenarios/7/turbines/WT001/history'))).toBe(true),
    );
    // Must-fix：limit 太小會把排在中段的排定故障截掉、看不到（本頁存在目的）。
    expect(historyCalls().some(u => u.includes('limit=12000'))).toBe(true);
  });

  it('資料達上限 → 顯示截斷提示（不靜默）', async () => {
    const bigReadings = Array.from({ length: 12000 }, (_, i) => ({
      timestamp: `2026-07-19T10:${String(i % 60).padStart(2, '0')}:00`,
      scada: { WTUR_TotPwrAt: 1500, WMET_WSpeedNac: 12 },
    }));
    installFetch({ ...HISTORY, readings: bigReadings });
    await renderDetail();
    await waitFor(() => expect(screen.getByText(/僅顯示最近/)).toBeInTheDocument());
  });

  it('渲染故障事件清單（含事件標題）', async () => {
    await renderDetail();
    await waitFor(() =>
      expect(screen.getByText('Scenario fault: hydraulic_leak on WT002')).toBeInTheDocument(),
    );
  });
});

describe('ScenarioDetail — 互動', () => {
  it('換機組 → 重抓該機組 history', async () => {
    await renderDetail();
    await waitFor(() => expect(historyCalls().length).toBeGreaterThanOrEqual(1));
    await act(async () => {
      fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT003' } });
    });
    await waitFor(() =>
      expect(historyCalls().some(u => u.includes('/turbines/WT003/history'))).toBe(true),
    );
  });

  it('點「返回」呼叫 onBack', async () => {
    const onBack = await renderDetail();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '返回情境列表' }));
    });
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

describe('ScenarioDetail — 空資料', () => {
  it('無 readings → 顯示「沒有資料」而非崩潰', async () => {
    installFetch({ ...HISTORY, readings: [], events: [] });
    await renderDetail();
    await waitFor(() => expect(screen.getByText(/沒有資料/)).toBeInTheDocument());
  });
});

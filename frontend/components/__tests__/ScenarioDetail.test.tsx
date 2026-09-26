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
import ScenarioDetail, { type SavedScenario, type ScenarioMountRequest } from '../ScenarioDetail';
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

const LOADS = { towerFa: null, towerSs: null, bladeFlap: null, bladeEdge: null };

/** 供切到「機組比較」頁籤時 ScenarioCompareView 的 `/summary` fetch 用（內容不影響本檔測項）。 */
const SUMMARY = {
  scenarioId: 7,
  name: '暴風測試',
  status: 'ok',
  windProfile: 'storm',
  durationHours: 24,
  timeStepSeconds: 60,
  ratedPowerKw: 2000,
  faultsInjected: 1,
  eventsByTimeWindow: true,
  farm: {
    turbineCount: 3,
    totalEnergyKwh: 0,
    avgCapacityFactor: 0,
    avgProductionRate: 0,
    totalFaultEvents: 0,
    maxTurbinePowerKw: 0,
    worstDamage: null,
    worstDamageTurbineId: null,
    minRulHours: null,
    minRulTurbineId: null,
  },
  turbines: [],
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

function installFetch(history: unknown = HISTORY, summary: unknown = SUMMARY) {
  fetchMock = vi.fn((url: string) => {
    if (url.includes('/api/scenarios/') && url.includes('/history')) return jsonRes(history);
    if (url.includes('/api/scenarios/') && url.includes('/summary')) return jsonRes(summary);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function historyCalls() {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/history'));
}

async function renderDetail(
  onBack = vi.fn(),
  lang: 'en' | 'zh' = 'zh',
  onMount?: (request: ScenarioMountRequest) => void,
) {
  await act(async () => {
    render(
      <ThemeProvider>
        <ScenarioDetail scenario={SCENARIO} lang={lang} onBack={onBack} onMount={onMount} />
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

  it('切到「機組比較」再切回「趨勢」→ 保留原選取機組（不重設回 WT001，WMOM-20260720-13 (2)）', async () => {
    await renderDetail();
    await waitFor(() =>
      expect(historyCalls().some(u => u.includes('/turbines/WT001/history'))).toBe(true),
    );
    // 先換選機組到 WT003
    await act(async () => {
      fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT003' } });
    });
    await waitFor(() => expect(historyCalls().some(u => u.includes('/turbines/WT003/history'))).toBe(true));

    // 切去「機組比較」頁籤（趨勢頁子元件 unmount）
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '機組比較' }));
    });
    await waitFor(() => expect(screen.getByText('風場層摘要')).toBeInTheDocument());

    // 切回「趨勢」→ Select 應仍顯示 WT003（未被重設回 WT001），且重抓的是 WT003 而非 WT001
    const callsBeforeReturn = historyCalls().length;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '趨勢' }));
    });
    await waitFor(() => expect(historyCalls().length).toBeGreaterThan(callsBeforeReturn));
    expect(screen.getByLabelText('風機')).toHaveValue('WT003');
    expect(historyCalls().slice(callsBeforeReturn).every(u => u.includes('/turbines/WT003/history'))).toBe(true);
  });
});

describe('ScenarioDetail — 空資料', () => {
  it('無 readings → 顯示「沒有資料」而非崩潰', async () => {
    installFetch({ ...HISTORY, readings: [], events: [] });
    await renderDetail();
    await waitFor(() => expect(screen.getByText(/沒有資料/)).toBeInTheDocument());
  });
});

// ─── 情境掛載入口（PR C Phase 1，DEC-20260926-01 / WMOM-20260926-03）─────────

describe('ScenarioDetail — 情境掛載入口', () => {
  it('未傳入 onMount（舊呼叫端）→ 不渲染掛載按鈕', async () => {
    await renderDetail();
    expect(screen.queryByRole('button', { name: /以此情境瀏覽/ })).not.toBeInTheDocument();
  });

  it('點「以此情境瀏覽總覽」→ onMount 帶 scenarioId/scenarioName/target=overview', async () => {
    const onMount = vi.fn();
    await renderDetail(vi.fn(), 'zh', onMount);
    fireEvent.click(screen.getByRole('button', { name: '以此情境瀏覽總覽' }));
    expect(onMount).toHaveBeenCalledWith({
      scenarioId: 7,
      scenarioName: '暴風測試',
      target: 'overview',
    });
  });

  it('點「以此情境瀏覽機組細節」→ onMount 帶目前選取機組的 WT id（預設 WT001）', async () => {
    const onMount = vi.fn();
    await renderDetail(vi.fn(), 'zh', onMount);
    fireEvent.click(screen.getByRole('button', { name: '以此情境瀏覽機組細節' }));
    expect(onMount).toHaveBeenCalledWith({
      scenarioId: 7,
      scenarioName: '暴風測試',
      target: 'turbine',
      turbineWtId: 'WT001',
    });
  });

  it('換選機組後點「以此情境瀏覽機組細節」→ turbineWtId 帶換選後的機組', async () => {
    const onMount = vi.fn();
    await renderDetail(vi.fn(), 'zh', onMount);
    await act(async () => {
      fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT003' } });
    });
    fireEvent.click(screen.getByRole('button', { name: '以此情境瀏覽機組細節' }));
    expect(onMount).toHaveBeenCalledWith(
      expect.objectContaining({ target: 'turbine', turbineWtId: 'WT003' }),
    );
  });

  it('未命名情境（無 cfg.name）→ scenarioName 退回「（未命名情境）」', async () => {
    const onMount = vi.fn();
    const unnamed: SavedScenario = { ...SCENARIO, config: { ...SCENARIO.config, name: undefined } };
    await act(async () => {
      render(
        <ThemeProvider>
          <ScenarioDetail scenario={unnamed} lang="zh" onBack={vi.fn()} onMount={onMount} />
        </ThemeProvider>,
      );
    });
    fireEvent.click(screen.getByRole('button', { name: '以此情境瀏覽總覽' }));
    expect(onMount).toHaveBeenCalledWith(
      expect.objectContaining({ scenarioName: '（未命名情境）' }),
    );
  });
});

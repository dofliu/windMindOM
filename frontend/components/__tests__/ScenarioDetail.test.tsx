/**
 * ScenarioDetail render 測試（WMOM-20260719-02 前端，DEC-20260719-01）。
 *
 * ScenarioDetail 調閱單一已保存情境：讀 `/api/scenarios/{id}/turbines/{tid}/history`（session
 * 隔離）→ 詮釋資料 + 發電量/風速雙軸趨勢 + 故障事件清單。守住：mount 抓 history、詮釋資料呈現、
 * 故障事件清單、換機組重抓、返回回呼、空資料狀態。
 *
 * 另守住頁籤 **keep-alive**（WMOM-20260720-13(2)）：切到「機組比較」再切回「趨勢」時，所選機組
 * 不得被重設回 WT001，也不得重打一次 history——原本的條件式渲染會 unmount 子元件、兩者皆發生。
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
    fault_schedule: [{ scenario_id: 'hydraulic_leak', turbine_id: 'WT002', offset_seconds: 0, severity_rate: 0.002 }],
  },
};

const LOADS = { towerFa: null, towerSs: null, bladeFlap: null, bladeEdge: null };

/** A0 摘要（「機組比較」頁籤消費）；此處只需最小可渲染形狀。 */
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
    turbineCount: 2, totalEnergyKwh: 7500, avgCapacityFactor: 0.45, avgProductionRate: 0.8,
    totalFaultEvents: 2, maxTurbinePowerKw: 1500, worstDamage: 0.05, worstDamageTurbineId: 'WT002',
    minRulHours: 12000, minRulTurbineId: 'WT002',
  },
  turbines: [
    {
      turbineId: 'WT001', samples: 360, avgPowerKw: 1200, maxPowerKw: 1500, energyKwh: 5000,
      capacityFactor: 0.6, productionRate: 0.95, estopSteps: 0, productionHours: 1.0,
      cumulativeDamage: LOADS, worstDamage: 0.001, rulHours: 90000,
      extremeLoad: LOADS, damageEquivalentLoad: LOADS, faultEvents: 0,
    },
    {
      turbineId: 'WT002', samples: 360, avgPowerKw: 600, maxPowerKw: 1000, energyKwh: 2500,
      capacityFactor: 0.3, productionRate: 0.5, estopSteps: 4, productionHours: 0.5,
      cumulativeDamage: LOADS, worstDamage: 0.05, rulHours: 12000,
      extremeLoad: LOADS, damageEquivalentLoad: LOADS, faultEvents: 2,
    },
  ],
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
    if (url.includes('/api/scenarios/') && url.includes('/summary')) return jsonRes(SUMMARY);
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

describe('ScenarioDetail — 頁籤 keep-alive（WMOM-20260720-13(2)）', () => {
  /** 點指定頁籤。 */
  async function clickTab(name: '趨勢' | '機組比較') {
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name }));
    });
  }

  it('切到比較再切回趨勢 → 保留所選機組（不重設回 WT001）', async () => {
    await renderDetail();
    await waitFor(() => expect(historyCalls().length).toBeGreaterThanOrEqual(1));
    await act(async () => {
      fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT003' } });
    });
    await waitFor(() => expect(historyCalls().some(u => u.includes('/turbines/WT003/history'))).toBe(true));

    await clickTab('機組比較');
    await waitFor(() => expect(historyCalls().length).toBeGreaterThanOrEqual(1));
    await clickTab('趨勢');

    // 條件式渲染會 unmount ScenarioTrendView → turbineId state 銷毀 → 這裡會變回 WT001。
    expect((screen.getByLabelText('風機') as HTMLSelectElement).value).toBe('WT003');
  });

  it('切到比較再切回趨勢 → 不重打 history（keep-alive 的實質收益）', async () => {
    await renderDetail();
    await waitFor(() => expect(historyCalls().length).toBeGreaterThanOrEqual(1));
    const before = historyCalls().length;

    await clickTab('機組比較');
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());
    await clickTab('趨勢');
    // 給可能的重抓一個發生的機會，再斷言沒發生（避免假綠）。
    await act(async () => { await Promise.resolve(); });

    expect(historyCalls().length).toBe(before);
  });

  it('比較頁籤只在首次造訪時掛載並抓 summary；來回切不重抓', async () => {
    await renderDetail();
    const summaryCalls = () => fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/summary'));
    // 尚未造訪 → 不該預先掛載（子視圖首次 mount 必須發生在可見狀態下，recharts 才量得到尺寸）
    expect(summaryCalls().length).toBe(0);

    await clickTab('機組比較');
    await waitFor(() => expect(summaryCalls().length).toBe(1));
    await clickTab('趨勢');
    await clickTab('機組比較');
    await act(async () => { await Promise.resolve(); });
    expect(summaryCalls().length).toBe(1);
  });

  it('非作用中的頁籤保持掛載但隱藏（切回來才不用重建）', async () => {
    await renderDetail();
    await waitFor(() => expect(historyCalls().length).toBeGreaterThanOrEqual(1));
    await clickTab('機組比較');
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());

    // 趨勢頁的機組選單仍在 DOM（只是被 display:none 的容器包住）。
    const select = screen.getByLabelText('風機');
    expect(select).toBeInTheDocument();
    expect(select.closest('div[style*="display: none"]')).not.toBeNull();
  });
});

describe('ScenarioDetail — 空資料', () => {
  it('無 readings → 顯示「沒有資料」而非崩潰', async () => {
    installFetch({ ...HISTORY, readings: [], events: [] });
    await renderDetail();
    await waitFor(() => expect(screen.getByText(/沒有資料/)).toBeInTheDocument());
  });
});

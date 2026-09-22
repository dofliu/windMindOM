/**
 * ScenarioCompareView render 測試（WMOM-20260720-10, A1）。
 *
 * 消費 A0 `/api/scenarios/{id}/summary` → 同情境內跨機組比較。守住：mount 抓 summary、風場層
 * headline、有故障/健康分群（由 fault_schedule 判定，非 faultEvents）、每台機組明細表 + faulted 標記、
 * 指標切換、eventsByTimeWindow 提示、載入失敗狀態。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor, within } from '@testing-library/react';
import React from 'react';
import ScenarioCompareView from '../ScenarioCompareView';
import type { SavedScenario } from '../ScenarioDetail';
import { ThemeProvider } from '../../theme/ThemeProvider';

// WT002 被排定注入故障（→ faulted）；WT001 未排（→ healthy）。
const SCENARIO: SavedScenario = {
  id: 7,
  started_at: '2026-07-19T10:00:00',
  turbine_count: 2,
  config: {
    kind: 'scenario',
    name: '暴風測試',
    wind_profile: 'storm',
    fault_schedule: [{ scenario_id: 'hydraulic_leak', turbine_id: 'WT002', offset_seconds: 0 }],
  },
};

const LOADS = { towerFa: null, towerSs: null, bladeFlap: null, bladeEdge: null };

const SUMMARY = {
  scenarioId: 7,
  name: '暴風測試',
  status: 'ok',
  windProfile: 'storm',
  durationHours: 1,
  timeStepSeconds: 10,
  ratedPowerKw: 2000,
  faultsInjected: 1,
  eventsByTimeWindow: true,
  farm: {
    turbineCount: 2,
    totalEnergyKwh: 7500,
    avgCapacityFactor: 0.45,
    avgProductionRate: 0.8,
    totalFaultEvents: 2,
    maxTurbinePowerKw: 1500,
    worstDamage: 0.05,
    worstDamageTurbineId: 'WT002',
    minRulHours: 12000,
    minRulTurbineId: 'WT002',
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

function jsonRes(body: unknown, ok = true, status = 200): Promise<Response> {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

function installFetch(summary: unknown = SUMMARY, ok = true) {
  fetchMock = vi.fn((url: string) => {
    if (url.includes('/api/scenarios/') && url.includes('/summary')) return jsonRes(summary, ok, ok ? 200 : 500);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function summaryCalls() {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/summary'));
}

async function renderView(lang: 'en' | 'zh' = 'zh', scenario: SavedScenario = SCENARIO) {
  await act(async () => {
    render(
      <ThemeProvider>
        <ScenarioCompareView scenario={scenario} lang={lang} />
      </ThemeProvider>,
    );
  });
}

beforeEach(() => installFetch());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ScenarioCompareView — mount + 風場 headline', () => {
  it('mount 抓該情境 summary', async () => {
    await renderView();
    await waitFor(() =>
      expect(summaryCalls().some(u => u.includes('/api/scenarios/7/summary'))).toBe(true),
    );
  });

  it('顯示風場層 headline（總發電量 + 最嚴重損傷機組）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('風場層摘要')).toBeInTheDocument());
    expect(screen.getByText('7,500')).toBeInTheDocument(); // totalEnergyKwh
    // 最嚴重損傷 / 最短 RUL 機組皆為 WT002（headline 標記）
    expect(screen.getAllByText('WT002').length).toBeGreaterThanOrEqual(1);
  });
});

describe('ScenarioCompareView — 有故障 vs 健康（A1 核心）', () => {
  it('faulted 由 fault_schedule 判定：WT002 標記故障、WT001 無', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());
    const wt002Row = screen.getByText('WT002', { selector: 'td span' }).closest('tr')!;
    expect(within(wt002Row).getByText('故障')).toBeInTheDocument();
    const wt001Row = screen.getByText('WT001', { selector: 'td span' }).closest('tr')!;
    expect(within(wt001Row).queryByText('故障')).toBeNull();
  });

  it('顯示有故障/健康分群平均對照', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText(/有故障機組平均/)).toBeInTheDocument());
    expect(screen.getByText(/健康機組平均/)).toBeInTheDocument();
  });

  it('faulted 判別**只**看 fault_schedule，不看 faultEvents（守住 A1 核心設計）', async () => {
    // 排程只有 WT001；但 summary 裡 WT001 faultEvents=0（排定未觸發）、WT002 faultEvents=5
    //（時間窗滲入其他情境的事件）。正確行為：WT001 標「排定未觸發」、WT002 **不**標故障。
    // 若誤用 faultEvents>0 判別，會反過來（WT002 標故障、WT001 不標）→ 本測抓到。
    const scenario: SavedScenario = {
      ...SCENARIO,
      config: { ...SCENARIO.config, fault_schedule: [{ scenario_id: 'x', turbine_id: 'WT001', offset_seconds: 0 }] },
    };
    installFetch({
      ...SUMMARY,
      turbines: [
        { ...SUMMARY.turbines[0], turbineId: 'WT001', faultEvents: 0 },
        { ...SUMMARY.turbines[1], turbineId: 'WT002', faultEvents: 5 },
      ],
    });
    await renderView('zh', scenario);
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());

    const wt001Row = screen.getByText('WT001', { selector: 'td span' }).closest('tr')!;
    expect(within(wt001Row).getByText('排定未觸發')).toBeInTheDocument(); // 排定但 faultEvents=0
    const wt002Row = screen.getByText('WT002', { selector: 'td span' }).closest('tr')!;
    expect(within(wt002Row).queryByText('故障')).toBeNull(); // 未排程 → healthy，即使 faultEvents=5
    expect(within(wt002Row).queryByText('排定未觸發')).toBeNull();
  });
});

describe('ScenarioCompareView — 指標切換 + 提示', () => {
  it('點指標按鈕切換（aria-pressed 隨選取變動）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('風場層摘要')).toBeInTheDocument());
    const energyBtn = screen.getByRole('button', { name: '發電量' });
    expect(energyBtn).toHaveAttribute('aria-pressed', 'false');
    await act(async () => { fireEvent.click(energyBtn); });
    expect(energyBtn).toHaveAttribute('aria-pressed', 'true');
    // 預設容量因數按鈕改為未選
    expect(screen.getByRole('button', { name: '容量因數' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('eventsByTimeWindow → 顯示故障計數時間窗提示', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText(/故障數走情境時間窗/)).toBeInTheDocument());
  });

  it('情境無 fault_schedule（欄位缺失）→ 顯示排程缺失防呆提示（Must-fix）', async () => {
    // 模擬 ScenarioPage 舊版手組 lastScenario（無 fault_schedule）→ 分群全落 healthy、不可信。
    const noSchedule: SavedScenario = { ...SCENARIO, config: { ...SCENARIO.config, fault_schedule: undefined } };
    installFetch(SUMMARY);
    await renderView('zh', noSchedule);
    await waitFor(() => expect(screen.getByText(/未帶故障排程/)).toBeInTheDocument());
  });

  it('欄位缺失且無任何觀測故障 → 仍要提示（沒有排程就無從判別，不該靜默宣告「全部健康」）', async () => {
    // 守住 WMOM-20260720-13(1) 的判別改動：舊判法額外要求「有機組 faultEvents>0」，
    // 故這個情形會靜默過去；新判法只看欄位在不在。
    const noSchedule: SavedScenario = { ...SCENARIO, config: { ...SCENARIO.config, fault_schedule: undefined } };
    installFetch({
      ...SUMMARY,
      turbines: SUMMARY.turbines.map(t => ({ ...t, faultEvents: 0 })),
    });
    await renderView('zh', noSchedule);
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());
    expect(screen.getByText(/未帶故障排程/)).toBeInTheDocument();
  });

  it('排程存在但刻意為空 [] → **不**提示，即使 faultEvents>0（WMOM-20260720-13(1) 誤報回歸）', async () => {
    // 純風況基準情境（沒排任何故障）緊接在有故障情境後生成 → faultEvents 被 eventsByTimeWindow
    // 的時間窗滲入（此處 WT002 faultEvents=2）。舊判法「faultedIds 空 && 有 faultEvents」會對這個
    // 乾淨情境誤報「未帶排程」，誤導使用者以為資料壞了。空排程是有意義的狀態，不是缺資料。
    const emptySchedule: SavedScenario = { ...SCENARIO, config: { ...SCENARIO.config, fault_schedule: [] } };
    installFetch(SUMMARY); // WT002 faultEvents=2
    await renderView('zh', emptySchedule);
    await waitFor(() => expect(screen.getByText('各機組明細')).toBeInTheDocument());
    expect(screen.queryByText(/未帶故障排程/)).toBeNull();
    // faultEvents 的可信度仍由既有 eventsByTimeWindow 提示負責說明（職責分離、不重疊）。
    expect(screen.getByText(/故障數走情境時間窗/)).toBeInTheDocument();
  });
});

describe('ScenarioCompareView — 失敗狀態', () => {
  it('summary 非 ok → 顯示錯誤而非崩潰', async () => {
    installFetch({}, false);
    await renderView();
    await waitFor(() => expect(screen.getByText(/載入情境摘要失敗/)).toBeInTheDocument());
  });
});

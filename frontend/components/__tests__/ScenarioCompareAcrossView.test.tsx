/**
 * ScenarioCompareAcrossView render 測試（WMOM-20260922-04, A2 Part 2 前端）。
 *
 * 消費 A2 Part 1 `/api/scenarios/compare?ids=...` → 跨情境（風場層 rollup）比較。守住：mount 帶
 * 正確 ids 抓 `/compare`、情境 headline 卡片、指標切換、全指標並排表、載入失敗狀態、onBack。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import ScenarioCompareAcrossView from '../ScenarioCompareAcrossView';
import { ThemeProvider } from '../../theme/ThemeProvider';

const FARM = (over: Record<string, unknown> = {}) => ({
  turbineCount: 3,
  totalEnergyKwh: 5000,
  avgCapacityFactor: 0.4,
  avgProductionRate: 0.8,
  totalFaultEvents: 1,
  maxTurbinePowerKw: 1800,
  worstDamage: 0.01,
  worstDamageTurbineId: 'WT001',
  minRulHours: 8000,
  minRulTurbineId: 'WT001',
  ...over,
});

function summary(id: number, over: Record<string, unknown> = {}) {
  return {
    scenarioId: id,
    name: null,
    status: 'ok',
    windProfile: 'moderate',
    durationHours: 24,
    timeStepSeconds: 60,
    ratedPowerKw: 2000,
    faultsInjected: 0,
    eventsByTimeWindow: true,
    farm: FARM(),
    turbines: [],
    ...over,
  };
}

const COMPARE_RESPONSE = {
  scenarios: [
    summary(3, { name: '暴風測試', farm: FARM({ totalEnergyKwh: 7000, avgCapacityFactor: 0.5 }) }),
    summary(5, { name: '晴朗微風', farm: FARM({ totalEnergyKwh: 3000, avgCapacityFactor: 0.2 }) }),
  ],
};

function jsonRes(body: unknown, ok = true, status = 200): Promise<Response> {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

function installFetch(body: unknown = COMPARE_RESPONSE, ok = true) {
  fetchMock = vi.fn((url: string) => {
    if (url.includes('/api/scenarios/compare')) return jsonRes(body, ok, ok ? 200 : 500);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function compareCalls() {
  return fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/compare'));
}

async function renderView(ids: number[] = [3, 5], lang: 'en' | 'zh' = 'zh', onBack = vi.fn()) {
  await act(async () => {
    render(
      <ThemeProvider>
        <ScenarioCompareAcrossView ids={ids} lang={lang} onBack={onBack} />
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

describe('ScenarioCompareAcrossView — mount + headline', () => {
  it('mount 帶 ids（逗號分隔）抓 /api/scenarios/compare', async () => {
    await renderView([3, 5]);
    await waitFor(() =>
      expect(compareCalls().some((u) => u.includes('ids=3,5'))).toBe(true),
    );
  });

  it('顯示每個情境的 headline 卡片（名稱 + 風況）', async () => {
    await renderView();
    // 情境名稱同時出現在 headline 卡片與並排表表頭，用 div 選取器鎖定 headline 卡片那一份。
    await waitFor(() => expect(screen.getByText('暴風測試', { selector: 'div' })).toBeInTheDocument());
    expect(screen.getByText('晴朗微風', { selector: 'div' })).toBeInTheDocument();
    expect(screen.getAllByText(/風況 中風/).length).toBeGreaterThanOrEqual(2);
  });

  it('情境未命名 → headline 回退 #{id}', async () => {
    installFetch({ scenarios: [summary(9, { name: null }), summary(11, { name: null })] });
    await renderView([9, 11]);
    await waitFor(() => expect(screen.getByText('#9', { selector: 'div' })).toBeInTheDocument());
    expect(screen.getByText('#11', { selector: 'div' })).toBeInTheDocument();
  });
});

describe('ScenarioCompareAcrossView — 指標切換 + 並排表', () => {
  it('點指標按鈕切換（aria-pressed 隨選取變動）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('依指標比較情境')).toBeInTheDocument());
    const energyBtn = screen.getByRole('button', { name: '總發電量' });
    expect(energyBtn).toHaveAttribute('aria-pressed', 'false');
    await act(async () => { fireEvent.click(energyBtn); });
    expect(energyBtn).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '平均容量因數' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('全指標並排表顯示每個情境的欄位值', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('全指標並排')).toBeInTheDocument());
    // 總發電量列：暴風測試 7,000 / 晴朗微風 3,000
    expect(screen.getByText('7,000 kWh')).toBeInTheDocument();
    expect(screen.getByText('3,000 kWh')).toBeInTheDocument();
  });

  it('風場層數值缺值 → 並排表顯示 —（不崩潰）', async () => {
    installFetch({
      scenarios: [
        summary(3, { name: 'A', farm: FARM({ minRulHours: null }) }),
        summary(5, { name: 'B' }),
      ],
    });
    await renderView([3, 5]);
    await waitFor(() => expect(screen.getByText('全指標並排')).toBeInTheDocument());
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('ScenarioCompareAcrossView — 失敗狀態 + onBack', () => {
  it('/compare 非 ok → 顯示錯誤而非崩潰', async () => {
    installFetch({}, false);
    await renderView();
    await waitFor(() => expect(screen.getByText(/載入跨情境比較失敗/)).toBeInTheDocument());
  });

  it('點返回呼叫 onBack', async () => {
    const onBack = await renderView([3, 5], 'zh', vi.fn());
    await waitFor(() => expect(screen.getByText('暴風測試', { selector: 'div' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '返回情境列表' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

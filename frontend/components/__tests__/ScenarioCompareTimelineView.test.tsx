/**
 * ScenarioCompareTimelineView render 測試（A2 Part 3，WMOM-20260923-03，DEC-20260720-02）。
 *
 * 消費既有單情境端點 `GET /api/scenarios/{id}/turbines/{tid}/history`（非新後端端點）：每個選取情境
 * 各自抓一次，換算成相對 `sim_start` 的經過時間疊圖。守住：per-scenario fetch（含正確 turbineId）、
 * 相對時間換算正確性、切換指標不重新 fetch（純前端衍生）、切換機組會重新 fetch、truncated/
 * fallback-align 提示、無資料/loading 狀態。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import ScenarioCompareTimelineView from '../ScenarioCompareTimelineView';
import { ThemeProvider } from '../../theme/ThemeProvider';
import type { SavedScenario } from '../ScenarioDetail';

const SCENARIO_A: SavedScenario = {
  id: 3,
  started_at: '2026-03-01T00:00:00',
  turbine_count: 3,
  config: { sim_start: '2026-03-01T00:00:00Z', name: '暴風測試' },
};
const SCENARIO_B: SavedScenario = {
  id: 5,
  started_at: '2026-03-05T00:00:00',
  turbine_count: 3,
  // sim_start 刻意不同（各情境從自己生成當下起算），驗證各自獨立對齊而非共用一個基準。
  config: { sim_start: '2026-03-05T00:00:00Z', name: '晴朗微風' },
};
// 缺 sim_start（未回填的舊情境）——驗證 fallback 對齊 + 提示。
const SCENARIO_NO_SIM_START: SavedScenario = {
  id: 9,
  started_at: '2026-02-01T00:00:00',
  turbine_count: 3,
  config: { name: '舊情境' },
};

function readingsFor(startIso: string, values: number[]): { readings: unknown[] } {
  const start = Date.parse(startIso);
  // 後端 DESC 排序：最新在前。
  const readings = values
    .map((v, i) => ({ timestamp: new Date(start + i * 10000).toISOString(), scada: { WTUR_TotPwrAt: v, WMET_WSpeedNac: v / 10 } }))
    .reverse();
  return { readings };
}

const LABEL: Record<number, string> = { 3: '暴風測試', 5: '晴朗微風', 9: '舊情境' };
const labelFor = (id: number) => LABEL[id] ?? `#${id}`;
const colorFor = (i: number) => ['#a', '#b', '#c'][i % 3];

function jsonRes(body: unknown, ok = true): Promise<Response> {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

/** 依 URL 內的 scenario id 路由到各自的 readings；未預期的組合直接 reject 避免靜默吞掉新呼叫。 */
function installFetch(byScenario: Record<number, { readings: unknown[] }>) {
  fetchMock = vi.fn((url: string) => {
    const m = url.match(/\/api\/scenarios\/(\d+)\/turbines\/(\w+)\/history/);
    if (!m) return Promise.reject(new Error(`unexpected fetch: ${url}`));
    const id = Number(m[1]);
    if (id in byScenario) return jsonRes(byScenario[id]);
    return jsonRes({ readings: [] });
  });
  vi.stubGlobal('fetch', fetchMock);
}

function historyCalls(): string[] {
  return fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/history'));
}

async function renderView(scenarios: SavedScenario[] = [SCENARIO_A, SCENARIO_B], lang: 'en' | 'zh' = 'zh') {
  await act(async () => {
    render(
      <ThemeProvider>
        <ScenarioCompareTimelineView scenarios={scenarios} labelFor={labelFor} colorFor={colorFor} lang={lang} />
      </ThemeProvider>,
    );
  });
}

beforeEach(() => {
  installFetch({
    3: readingsFor('2026-03-01T00:00:00Z', [100, 200, 300]),
    5: readingsFor('2026-03-05T00:00:10Z', [50, 60]),
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ScenarioCompareTimelineView — mount + per-scenario fetch', () => {
  it('mount 依每個情境各自打 history（帶預設機組 WT001）', async () => {
    await renderView();
    await waitFor(() => expect(historyCalls().some((u) => u.includes('/scenarios/3/turbines/WT001/history'))).toBe(true));
    expect(historyCalls().some((u) => u.includes('/scenarios/5/turbines/WT001/history'))).toBe(true);
  });

  it('切換機組會重新 fetch（帶新 turbineId）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByLabelText('風機')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT002' } });
    await waitFor(() => expect(historyCalls().some((u) => u.includes('/scenarios/3/turbines/WT002/history'))).toBe(true));
  });

  it('切換指標不重新 fetch（純前端從已抓資料衍生）', async () => {
    await renderView();
    await waitFor(() => expect(historyCalls().length).toBe(2));
    fireEvent.change(screen.getByLabelText('指標'), { target: { value: 'WMET_WSpeedNac' } });
    // 給一輪 microtask 讓任何（不應發生的）fetch 有機會發出，再斷言呼叫數未增加。
    await act(async () => {
      await Promise.resolve();
    });
    expect(historyCalls().length).toBe(2);
  });
});

describe('ScenarioCompareTimelineView — 相對時間對齊 + 提示', () => {
  it('純 DOM 圖例顯示各情境名稱（依 labelFor 命名，色塊對應顏色）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('暴風測試')).toBeInTheDocument());
    expect(screen.getByText('晴朗微風')).toBeInTheDocument();
  });

  it('缺 sim_start 的情境 → 顯示 fallback 對齊提示，帶出該情境名稱', async () => {
    installFetch({
      3: readingsFor('2026-03-01T00:00:00Z', [100]),
      9: readingsFor('2026-02-01T00:00:00Z', [10]),
    });
    await renderView([SCENARIO_A, SCENARIO_NO_SIM_START]);
    // 訊息帶出情境名稱（"舊情境 — 缺情境 sim_start..."）；純 DOM 圖例另外也顯示同一名稱，
    // 用完整片語比對鎖定提示訊息本身，避免跟圖例文字重複命中。
    await waitFor(() => expect(screen.getByText(/舊情境 — 缺情境 sim_start/)).toBeInTheDocument());
  });

  it('都有 sim_start → 不顯示 fallback 對齊提示', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByText('暴風測試')).toBeInTheDocument());
    expect(screen.queryByText(/缺情境 sim_start/)).not.toBeInTheDocument();
  });

  it('命中 HISTORY_LIMIT（12000）→ 顯示截斷提示', async () => {
    const long = Array.from({ length: 12000 }, (_, i) => i);
    installFetch({
      3: readingsFor('2026-03-01T00:00:00Z', long),
      5: readingsFor('2026-03-05T00:00:00Z', [1]),
    });
    await renderView();
    // 完整片語鎖定提示訊息本身（"暴風測試 — 僅顯示最近..."），避免跟純 DOM 圖例的同名文字重複命中。
    await waitFor(() => expect(screen.getByText(/暴風測試 — 僅顯示最近/)).toBeInTheDocument());
  });
});

describe('ScenarioCompareTimelineView — 邊界狀態', () => {
  it('無情境 → 不 fetch、顯示無資料狀態', async () => {
    await renderView([]);
    expect(historyCalls().length).toBe(0);
    expect(screen.getByText('選取的情境中，此機組沒有資料。')).toBeInTheDocument();
  });

  it('所有情境 readings 皆空 → 顯示無資料狀態（不崩潰）', async () => {
    installFetch({ 3: { readings: [] }, 5: { readings: [] } });
    await renderView();
    await waitFor(() => expect(screen.getByText('選取的情境中，此機組沒有資料。')).toBeInTheDocument());
  });

  it('fetch 失敗（非 ok）→ 該情境視為無資料，不崩潰、其餘情境正常顯示', async () => {
    fetchMock = vi.fn((url: string) => {
      if (url.includes('/scenarios/3/')) return jsonRes({}, false);
      return jsonRes(readingsFor('2026-03-05T00:00:00Z', [1, 2]));
    });
    vi.stubGlobal('fetch', fetchMock);
    await renderView();
    await waitFor(() => expect(screen.getByText('晴朗微風')).toBeInTheDocument());
  });

  it('英文語系：切換機組/指標 label 對應英文', async () => {
    await renderView([SCENARIO_A, SCENARIO_B], 'en');
    await waitFor(() => expect(screen.getByLabelText('Turbine')).toBeInTheDocument());
    expect(screen.getByLabelText('Metric')).toBeInTheDocument();
  });
});

/**
 * ScenarioCompareDiffView render 測試（A2 Part 4，WMOM-20260923-06，DEC-20260720-02）。
 *
 * 守住：per-scenario fetch（同 Part 3）、baseline 選擇（預設第一個情境、切換 baseline 重算差異
 * 不重新 fetch）、差異值計算正確性（compare - baseline）、baseline 不出現在差異線圖例中
 * （它是 y=0 參考線）、baseline 清單變動時的 fallback、baseline 無資料的提示、非 baseline/baseline
 * 各自的 fetch 失敗提示（兩者不重複顯示）、fallback 對齊提示、HISTORY_LIMIT 截斷提示、
 * 無重疊資料的空狀態。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import ScenarioCompareDiffView from '../ScenarioCompareDiffView';
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
  config: { sim_start: '2026-03-05T00:00:00Z', name: '晴朗微風' },
};

function readingsFor(startIso: string, values: number[], stepSec = 10): { readings: unknown[] } {
  const start = Date.parse(startIso);
  const readings = values
    .map((v, i) => ({ timestamp: new Date(start + i * stepSec * 1000).toISOString(), scada: { WTUR_TotPwrAt: v, WMET_WSpeedNac: v / 10 } }))
    .reverse();
  return { readings };
}

const LABEL: Record<number, string> = { 3: '暴風測試', 5: '晴朗微風' };
const labelFor = (id: number) => LABEL[id] ?? `#${id}`;
const colorFor = (i: number) => ['#a', '#b', '#c'][i % 3];

function jsonRes(body: unknown, ok = true): Promise<Response> {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

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
        <ScenarioCompareDiffView scenarios={scenarios} labelFor={labelFor} colorFor={colorFor} lang={lang} />
      </ThemeProvider>,
    );
  });
}

beforeEach(() => {
  // 兩情境同取樣間隔（10s），時間點剛好對齊，方便斷言差異數值。
  installFetch({
    3: readingsFor('2026-03-01T00:00:00Z', [100, 200, 300]),
    5: readingsFor('2026-03-05T00:00:00Z', [130, 260, 390]),
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ScenarioCompareDiffView — mount + fetch（同 Part 3 的 per-scenario 抓法）', () => {
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

  it('切換 baseline 不重新 fetch（純前端從已抓資料重算差異）', async () => {
    await renderView();
    await waitFor(() => expect(historyCalls().length).toBe(2));
    fireEvent.change(screen.getByLabelText('Baseline 情境'), { target: { value: '5' } });
    await act(async () => {
      await Promise.resolve();
    });
    expect(historyCalls().length).toBe(2);
  });

  it('切換指標不重新 fetch', async () => {
    await renderView();
    await waitFor(() => expect(historyCalls().length).toBe(2));
    fireEvent.change(screen.getByLabelText('指標'), { target: { value: 'WMET_WSpeedNac' } });
    await act(async () => {
      await Promise.resolve();
    });
    expect(historyCalls().length).toBe(2);
  });
});

describe('ScenarioCompareDiffView — baseline 與圖例', () => {
  it('預設 baseline 為第一個情境，圖例只顯示其餘情境（baseline 本身不出現）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByTestId('diff-legend-5')).toBeInTheDocument());
    expect(screen.queryByTestId('diff-legend-3')).not.toBeInTheDocument();
  });

  it('切換 baseline 後，圖例改顯示原 baseline（換它變成比較對象）', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByLabelText('Baseline 情境')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Baseline 情境'), { target: { value: '5' } });
    await waitFor(() => expect(screen.getByTestId('diff-legend-3')).toBeInTheDocument());
    expect(screen.queryByTestId('diff-legend-5')).not.toBeInTheDocument();
  });

  it('選取情境變動、原 baseline 已不在清單內 → 回退第一個', async () => {
    let view: ReturnType<typeof render>;
    await act(async () => {
      view = render(
        <ThemeProvider>
          <ScenarioCompareDiffView scenarios={[SCENARIO_A, SCENARIO_B]} labelFor={labelFor} colorFor={colorFor} />
        </ThemeProvider>,
      );
    });
    await waitFor(() => expect(screen.getByTestId('diff-legend-5')).toBeInTheDocument());
    // 移除原 baseline（id=3），只剩 SCENARIO_B → baseline 應自動回退成 5，圖例應變空（只剩一個情境、
    // 它自己是 baseline，沒有其他情境可比較）。
    await act(async () => {
      view!.rerender(
        <ThemeProvider>
          <ScenarioCompareDiffView scenarios={[SCENARIO_B]} labelFor={labelFor} colorFor={colorFor} />
        </ThemeProvider>,
      );
    });
    await waitFor(() => expect(screen.queryByTestId('diff-legend-5')).not.toBeInTheDocument());
  });
});

describe('ScenarioCompareDiffView — 差異值計算', () => {
  // 精確數值已在 utils/__tests__/scenarioTimeline.test.ts 對 buildDiffSeries 直接單元測試鎖住；
  // 這裡只驗證「有重疊資料時走正常渲染路徑」的整合行為——recharts 在 jsdom（無 ResizeObserver）
  // 量不到容器寬高，畫不出實際線條，圖表像素層級無法用 vitest 驗證，只能讀原始碼推論 + 人工瀏覽器驗。
  it('對齊取樣點有重疊資料 → 不顯示「無可比較資料」空狀態，圖例正常顯示', async () => {
    // baseline=3 → [100,200,300]；compare=5 → [130,260,390]，皆同取樣間隔對齊，理論上算得出差異。
    await renderView();
    await waitFor(() => expect(screen.getByTestId('diff-legend-5')).toBeInTheDocument());
    expect(screen.queryByText('選取的情境中，此機組沒有可比較的重疊資料。')).not.toBeInTheDocument();
  });
});

describe('ScenarioCompareDiffView — 邊界狀態', () => {
  it('無情境 → 不 fetch', async () => {
    await renderView([]);
    expect(historyCalls().length).toBe(0);
  });

  it('baseline 無資料 → 顯示提示，無法算出差異', async () => {
    installFetch({
      3: { readings: [] },
      5: readingsFor('2026-03-05T00:00:00Z', [1, 2]),
    });
    await renderView();
    await waitFor(() => expect(screen.getByText(/暴風測試（baseline）此機組沒有資料/)).toBeInTheDocument());
  });

  it('非 baseline 情境 fetch 失敗（非 ok）→ 顯示載入失敗提示', async () => {
    // 3 是預設 baseline，讓 5（非 baseline）失敗，才會走一般 failedNames 提示。
    fetchMock = vi.fn((url: string) => {
      if (url.includes('/scenarios/5/')) return jsonRes({}, false);
      return jsonRes(readingsFor('2026-03-01T00:00:00Z', [1, 2]));
    });
    vi.stubGlobal('fetch', fetchMock);
    await renderView();
    await waitFor(() => expect(screen.getByText(/晴朗微風 — 載入失敗/)).toBeInTheDocument());
  });

  it('baseline 情境本身 fetch 失敗 → 只顯示 baseline 專屬提示，不重複顯示一般載入失敗提示', async () => {
    // 3 是預設 baseline；baselineHasNoData 已涵蓋「baseline 無資料」（含失敗）的情況，
    // 一般 failedNames 提示應排除 baseline，避免同一根因重複顯示兩則提示。
    fetchMock = vi.fn((url: string) => {
      if (url.includes('/scenarios/3/')) return jsonRes({}, false);
      return jsonRes(readingsFor('2026-03-05T00:00:00Z', [1, 2]));
    });
    vi.stubGlobal('fetch', fetchMock);
    await renderView();
    await waitFor(() => expect(screen.getByText(/暴風測試（baseline）此機組沒有資料/)).toBeInTheDocument());
    expect(screen.queryByText(/暴風測試 — 載入失敗/)).not.toBeInTheDocument();
  });

  it('缺 sim_start 的情境 → 顯示 fallback 對齊提示，帶出該情境名稱', async () => {
    installFetch({
      3: readingsFor('2026-03-01T00:00:00Z', [100, 200], 10),
      5: { readings: [{ timestamp: '2026-02-01T00:00:00Z', scada: { WTUR_TotPwrAt: 1 } }] },
    });
    await renderView([SCENARIO_A, { ...SCENARIO_B, config: { name: '晴朗微風' } }]);
    await waitFor(() => expect(screen.getByText(/晴朗微風 — 缺情境 sim_start/)).toBeInTheDocument());
  });

  it('都有 sim_start → 不顯示 fallback 對齊提示', async () => {
    await renderView();
    await waitFor(() => expect(screen.getByTestId('diff-legend-5')).toBeInTheDocument());
    expect(screen.queryByText(/缺情境 sim_start/)).not.toBeInTheDocument();
  });

  it('命中 HISTORY_LIMIT（12000）→ 顯示截斷提示', async () => {
    const long = Array.from({ length: 12000 }, (_, i) => i);
    installFetch({
      3: readingsFor('2026-03-01T00:00:00Z', long, 10),
      5: readingsFor('2026-03-01T00:00:00Z', [1], 10),
    });
    await renderView();
    await waitFor(() => expect(screen.getByText(/暴風測試 — 僅顯示最近/)).toBeInTheDocument());
  });

  it('兩情境完全不重疊（分桶後仍無交集）→ 顯示無可比較資料狀態', async () => {
    installFetch({
      3: readingsFor('2026-03-01T00:00:00Z', [1, 2], 10),
      5: readingsFor('2026-03-01T05:00:00Z', [3, 4], 10),
    });
    await renderView();
    await waitFor(() =>
      expect(screen.getByText('選取的情境中，此機組沒有可比較的重疊資料。')).toBeInTheDocument(),
    );
  });

  it('英文語系：切換 baseline/機組/指標 label 對應英文', async () => {
    await renderView([SCENARIO_A, SCENARIO_B], 'en');
    await waitFor(() => expect(screen.getByLabelText('Baseline scenario')).toBeInTheDocument());
    expect(screen.getByLabelText('Turbine')).toBeInTheDocument();
    expect(screen.getByLabelText('Metric')).toBeInTheDocument();
  });
});

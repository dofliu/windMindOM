/**
 * ScenarioPage component render 測試（WMOM-20260718-04, DEC-20260718-01）。
 *
 * `ScenarioPage.tsx` 是 Scenario 模式的「情境設定」頁：
 *   - mount 時 GET `/api/faults/scenarios`（故障場景清單）+ `/api/farms`（取 active farm → 台數）
 *   - 情境設定：風況 profile / 時長（小時，含 1天/1週/1月 preset）/ 解析度 time_step
 *   - 故障排程：可增可刪，每列 {場景 / 風機 / 第幾小時 / 發展速率}；at_hour ≥ 時長顯示警告
 *   - 生成：先 POST `/api/config/wind {profile}` 再 POST `/api/config/simulation/generate-bulk
 *     {duration_hours, time_step, fault_schedule}` → 結果卡（筆數 / 注入數 / 最終故障狀態）
 *   - 生成後「查看歷史資料 →」呼叫 onExplore
 *
 * 全走 `authFetch`（底層即 global `fetch`）→ **mock `global.fetch`** 路由四端點；
 * `useTheme` 用真實 ThemeProvider。守住：mount fetch / 控制項殼層 / preset / 排程增刪 /
 * 生成接線（wind + generate-bulk body 正確）/ 結果呈現 / 越界警告 / onExplore / 錯誤路徑 / 語系。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor, within } from '@testing-library/react';
import React from 'react';
import ScenarioPage from '../ScenarioPage';
import { ThemeProvider } from '../../theme/ThemeProvider';

type Lang = 'en' | 'zh';

const SCENARIOS = [
  { id: 'hydraulic_leak', name_en: 'Yaw Brake Hydraulic Leak', name_zh: '偏航煞車液壓洩漏' },
  { id: 'bearing_wear', name_en: 'Generator Bearing Wear', name_zh: '發電機軸承磨損' },
];

const FARMS = { farms: [{ farm_id: 'f1', name: '彰化離岸風場', turbine_count: 3 }], active_farm_id: 'f1' };

const GEN_RESULT = {
  status: 'ok',
  duration_hours: 168,
  time_step: 60,
  total_readings: 999,
  faults_injected: 1,
  final_fault_status: [
    { turbine_id: 'WT002', scenario_id: 'hydraulic_leak', severity: 0.5, phase: 'advanced', tripped: false },
  ],
  storage_stats: { db_size_mb: 12 },
};

function jsonRes(body: unknown, ok = true, status = 200): Promise<Response> {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

function installFetch(
  opts: { scenarios?: unknown; farmsBody?: unknown; genOk?: boolean; genBody?: unknown } = {},
) {
  const scenarios = opts.scenarios ?? SCENARIOS;
  const farmsBody = opts.farmsBody ?? FARMS;
  const genOk = opts.genOk ?? true;
  const genBody = opts.genBody ?? GEN_RESULT;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/api/faults/scenarios')) return jsonRes(scenarios);
    if (url.includes('/api/config/simulation/generate-bulk')) return jsonRes(genBody, genOk, genOk ? 200 : 400);
    if (url.includes('/api/config/wind')) return jsonRes({});
    if (url.includes('/api/farms')) return jsonRes(farmsBody);
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function calls(pred: (url: string, method: string) => boolean): Array<[string, string]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), String((c[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase()] as [string, string])
    .filter(([u, m]) => pred(u, m));
}

function bodyOf(pred: (url: string, method: string) => boolean): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(
    c => pred(String(c[0]), String((c[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase()),
  );
  return JSON.parse(String((call![1] as RequestInit).body));
}

async function renderPage(lang: Lang = 'zh', onExplore?: () => void) {
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <ScenarioPage lang={lang} onExplore={onExplore} />
      </ThemeProvider>,
    );
  });
  return utils;
}

/** 渲染後新增一列故障（等 scenarios 落地才點）。 */
async function addFault(lang: Lang = 'zh') {
  await renderPage(lang);
  await waitFor(() => expect(screen.getByRole('button', { name: lang === 'zh' ? '新增故障' : 'Add fault' })).toBeInTheDocument());
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: lang === 'zh' ? '新增故障' : 'Add fault' }));
  });
}

beforeEach(() => installFetch());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═════════════════════════════════════════════════════════════════════════════

describe('ScenarioPage — mount fetch / 殼層', () => {
  it('mount 時 GET /api/faults/scenarios 與 /api/farms 各一次', async () => {
    await renderPage('zh');
    await waitFor(() => {
      expect(calls((u, m) => u.includes('/api/faults/scenarios') && m === 'GET').length).toBe(1);
      expect(calls((u, m) => u.includes('/api/farms') && m === 'GET').length).toBe(1);
    });
  });

  it('渲染標題「情境模擬」', async () => {
    await renderPage('zh');
    expect(screen.getByText('情境模擬')).toBeInTheDocument();
  });

  it('lang=en 標題 = Scenario Simulation', async () => {
    await renderPage('en');
    expect(screen.getByText('Scenario Simulation')).toBeInTheDocument();
  });

  it('farm 落地後顯示風場名 + 台數', async () => {
    await renderPage('zh');
    await waitFor(() => expect(screen.getByText(/彰化離岸風場（3 台）/)).toBeInTheDocument());
  });

  it('渲染風況 / 時長 / 解析度控制項', async () => {
    await renderPage('zh');
    expect(screen.getByLabelText('風況')).toBeInTheDocument();
    expect(screen.getByLabelText('時長小時')).toBeInTheDocument();
    expect(screen.getByLabelText('解析度')).toBeInTheDocument();
  });
});

describe('ScenarioPage — 時長 preset', () => {
  it('點「1 月」把時長設為 720', async () => {
    await renderPage('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '1 月' }));
    });
    expect(screen.getByLabelText('時長小時')).toHaveValue(720);
  });

  it('手動改時長輸入生效', async () => {
    await renderPage('zh');
    fireEvent.change(screen.getByLabelText('時長小時'), { target: { value: '48' } });
    expect(screen.getByLabelText('時長小時')).toHaveValue(48);
  });
});

describe('ScenarioPage — 故障排程增刪', () => {
  it('初始為空狀態（無排定故障提示）', async () => {
    await renderPage('zh');
    expect(screen.getByText(/無排定故障/)).toBeInTheDocument();
  });

  it('點「新增故障」加入一列（含場景 / 風機 選單）', async () => {
    await addFault('zh');
    expect(screen.getByLabelText('故障場景')).toBeInTheDocument();
    expect(screen.getByLabelText('風機')).toBeInTheDocument();
    expect(screen.getByLabelText('第幾小時')).toBeInTheDocument();
    expect(screen.getByLabelText('發展速率')).toBeInTheDocument();
    // 空狀態消失
    expect(screen.queryByText(/無排定故障/)).not.toBeInTheDocument();
  });

  it('風機下拉依 active farm 台數（3 台 → WT001..WT003）', async () => {
    await addFault('zh');
    const turbineSel = screen.getByLabelText('風機');
    expect(within(turbineSel).getByRole('option', { name: 'WT001' })).toBeInTheDocument();
    expect(within(turbineSel).getByRole('option', { name: 'WT003' })).toBeInTheDocument();
    expect(within(turbineSel).queryByRole('option', { name: 'WT004' })).not.toBeInTheDocument();
  });

  it('點「✕」移除該列 → 回空狀態', async () => {
    await addFault('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '移除故障' }));
    });
    expect(screen.getByText(/無排定故障/)).toBeInTheDocument();
  });

  it('at_hour ≥ 時長 顯示「不會被注入」警告', async () => {
    await addFault('zh');
    // 預設時長 168；把 at_hour 設 200（越界）
    fireEvent.change(screen.getByLabelText('第幾小時'), { target: { value: '200' } });
    expect(screen.getByText(/不會被注入/)).toBeInTheDocument();
  });
});

describe('ScenarioPage — 生成', () => {
  it('點「生成情境」→ POST /api/config/wind 再 POST generate-bulk', async () => {
    await renderPage('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() => {
      expect(calls((u, m) => u.includes('/api/config/wind') && m === 'POST').length).toBe(1);
      expect(calls((u, m) => u.includes('/api/config/simulation/generate-bulk') && m === 'POST').length).toBe(1);
    });
  });

  it('wind POST 帶選定 profile；generate-bulk 帶 duration/time_step', async () => {
    await renderPage('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() =>
      expect(calls((u, m) => u.includes('/generate-bulk') && m === 'POST').length).toBe(1),
    );
    expect(bodyOf(u => u.includes('/api/config/wind')).profile).toBe('moderate');
    const gen = bodyOf(u => u.includes('/generate-bulk'));
    expect(gen.duration_hours).toBe(168);
    expect(gen.time_step).toBe(60);
  });

  it('生成時把排定故障轉成 fault_schedule（scenario_id/turbine_id/at_hour/severity_rate）', async () => {
    await addFault('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() =>
      expect(calls((u, m) => u.includes('/generate-bulk') && m === 'POST').length).toBe(1),
    );
    const gen = bodyOf(u => u.includes('/generate-bulk'));
    const sched = gen.fault_schedule as Array<Record<string, unknown>>;
    expect(sched).toHaveLength(1);
    expect(sched[0].scenario_id).toBe('hydraulic_leak'); // scenarios[0]
    expect(sched[0].turbine_id).toBe('WT001');
    expect(sched[0].at_hour).toBe(84); // round(168/2)
    expect(sched[0].severity_rate).toBe(0.002);
  });

  it('生成成功 → 顯示結果卡（筆數 + 最終故障狀態列）', async () => {
    await renderPage('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() => expect(screen.getByText('情境資料集')).toBeInTheDocument());
    expect(screen.getByText('999')).toBeInTheDocument(); // total_readings
    expect(screen.getByText('WT002')).toBeInTheDocument(); // final fault turbine
    expect(screen.getByText('50%')).toBeInTheDocument(); // severity
  });

  it('生成失敗（generate-bulk 非 ok）→ 顯示錯誤橫幅（role=alert）', async () => {
    installFetch({ genOk: false, genBody: { detail: '未知機組' } });
    await renderPage('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toHaveTextContent(/未知機組/);
    });
  });
});

describe('ScenarioPage — 探索跳頁', () => {
  it('生成後點「查看歷史資料」呼叫 onExplore', async () => {
    const onExplore = vi.fn();
    await renderPage('zh', onExplore);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '生成情境' }));
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '查看歷史資料' })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '查看歷史資料' }));
    });
    expect(onExplore).toHaveBeenCalledTimes(1);
  });
});

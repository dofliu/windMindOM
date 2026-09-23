/**
 * FaultInjectionPanel component render 測試（WMOM-20260923-02，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin` 故障模擬頁面元件（555 行）先前零 component 測試。比照 `TrendChartPanel` /
 * `SettingsPage` 範式（fetch mock + fake timers），涵蓋：
 *
 *   - PageHeader：標題 / sub / 注入・清除全部按鈕（注入按鈕未選場景時 disabled）
 *   - 注入參數 Fields：場景 Select（含 fetch 到的選項 + placeholder）、風機 Select
 *     （固定 14 台 WT001..WT014）、速率 Input
 *   - handleInject：POST `/api/faults/inject` 帶正確 body、成功後顯示訊息並觸發
 *     `refreshActive`、訊息 3s 後自動清除
 *   - handleClearAll：POST `/api/faults/clear`、訊息顯示與自動清除
 *   - 活躍故障表：僅在 `activeFaults` 非空時渲染，欄位含嚴重度 / 階段（+ TRIP 後綴）/
 *     告警字串或「—」
 *   - 診斷測試計畫卡片：難度 label 對映（含未知 id fallback「極限」）、時長/故障數、
 *     風機/場景 chips（場景 chips 超過 4 個顯示 `+N`）
 *   - handleRunPlan：執行中按鈕文字 + 全域 disable 其他計畫、成功後渲染結果卡
 *     （Stat 區塊 + 可選的最終故障狀態表）、失敗訊息
 *   - 3s 輪詢 `refreshActive` 與 unmount 後 `clearInterval` 生效（不再繼續 fetch）
 *
 * 外部依賴的隔離策略：
 *   - `useTheme` → `ThemeProvider` 包裹（真實 theme，驗實際渲染）。
 *   - `global.fetch` → `vi.fn()` 依 URL + method 路由；未預期的組合直接 reject，
 *     避免靜默吞掉新 API 呼叫。
 *   - 計時器：全檔用 `vi.useFakeTimers()`（元件無 `Date.now()` 依賴，不受影響），
 *     用來精確控制 3s 輪詢 / 3s·8s 訊息清除，而非依賴真實時間流逝拖慢測試。
 *   - `handleRunPlan` 的執行中間態用可手動 resolve 的 pending Promise 控制（比照
 *     `EventComparisonView.test.tsx` / `ScenarioPage.test.tsx` 既有範式）。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import FaultInjectionPanel from '../FaultInjectionPanel';
import { ThemeProvider } from '../../theme/ThemeProvider';
import type { FaultScenario } from '../../types';

type Lang = 'en' | 'zh';

// ─── 元件內部型別的測試側鏡射（元件未 export，僅供 fixture 建構用）───────────────

interface TestPlanFixture {
  id: string;
  name_en: string;
  name_zh: string;
  description_en: string;
  description_zh: string;
  duration_hours: number;
  fault_count: number;
  turbines_affected: string[];
  scenarios_used: string[];
}

interface ActiveFaultFixture {
  turbine_id: string;
  scenario_id?: string;
  name_en: string;
  name_zh: string;
  severity: number;
  phase: string;
  tripped: boolean;
  active_alarms?: { type: string; code: number; desc: string }[];
}

interface TestPlanResultFixture {
  status: string;
  plan_id: string;
  duration_hours: number;
  total_readings: number;
  faults_injected: number;
  final_fault_status: ActiveFaultFixture[];
  storage_stats: { db_size_mb?: number };
}

// ─── 工廠 ──────────────────────────────────────────────────────────────────

function makeScenario(over: Partial<FaultScenario> = {}): FaultScenario {
  return {
    id: 'gearbox_wear',
    name_en: 'Gearbox Wear',
    name_zh: '齒輪箱磨損',
    description_en: '',
    description_zh: '',
    affected_tags: [],
    alarm_codes: [],
    ...over,
  };
}

function makeTestPlan(over: Partial<TestPlanFixture> = {}): TestPlanFixture {
  return {
    id: 'basic_validation',
    name_en: 'Basic Validation',
    name_zh: '基本驗證',
    description_en: 'Runs the standard suite.',
    description_zh: '執行標準測試組合。',
    duration_hours: 24,
    fault_count: 3,
    turbines_affected: ['WT002', 'WT001'],
    scenarios_used: ['gearbox_wear', 'bearing_overheat'],
    ...over,
  };
}

function makeActiveFault(over: Partial<ActiveFaultFixture> = {}): ActiveFaultFixture {
  return {
    turbine_id: 'WT001',
    scenario_id: 'gearbox_wear',
    name_en: 'Gearbox Wear',
    name_zh: '齒輪箱磨損',
    severity: 0.42,
    phase: 'developing',
    tripped: false,
    active_alarms: [],
    ...over,
  };
}

function makeTestPlanResult(over: Partial<TestPlanResultFixture> = {}): TestPlanResultFixture {
  return {
    status: 'completed',
    plan_id: 'basic_validation',
    duration_hours: 48,
    total_readings: 17280,
    faults_injected: 5,
    final_fault_status: [],
    storage_stats: { db_size_mb: 12.5 },
    ...over,
  };
}

// ─── fetch stub ──────────────────────────────────────────────────────────────

function jsonRes(body: unknown, ok = true): Promise<Response> {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

interface FetchOpts {
  scenarios?: FaultScenario[];
  testPlans?: TestPlanFixture[];
  active?: ActiveFaultFixture[];
  /** GET 系（mount 用的 3 條）全部 reject，驗證元件不崩潰、維持預設空陣列狀態。 */
  rejectMount?: boolean;
  /** `/api/faults/inject` 回應的 `ok`（預設 true）。 */
  injectOk?: boolean;
  /** 覆寫 run 端點行為（預設回傳 `makeTestPlanResult()`；'reject' 模擬失敗）。 */
  runHandler?: (url: string) => Promise<Response>;
}

/**
 * 安裝 fetch stub 並接管 `global.fetch`，依 URL + method 路由到對應假回應。
 * 未預期的組合直接 reject（避免新增 API 呼叫卻被靜默吞掉）。
 */
function installFetch(opts: FetchOpts = {}) {
  const scenarios = opts.scenarios ?? [];
  const testPlans = opts.testPlans ?? [];
  const active = opts.active ?? [];
  const runHandler =
    opts.runHandler ?? (() => jsonRes(makeTestPlanResult()));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'GET' && opts.rejectMount) {
      return Promise.reject(new Error(`network down: ${url}`));
    }
    if (method === 'GET' && url.includes('/api/faults/scenarios')) return jsonRes(scenarios);
    if (method === 'GET' && url.includes('/api/faults/test-plans')) return jsonRes(testPlans);
    if (method === 'GET' && url.includes('/api/faults/active')) return jsonRes(active);
    if (method === 'POST' && url.includes('/api/faults/inject')) {
      return jsonRes({}, opts.injectOk ?? true);
    }
    if (method === 'POST' && url.includes('/api/faults/clear')) return jsonRes({});
    if (method === 'POST' && /\/api\/faults\/test-plans\/.+\/run$/.test(url)) return runHandler(url);
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

/** 取得對某端點（URL 子字串）的所有 fetch 呼叫。 */
function callsTo(urlSubstr: string): [string, RequestInit | undefined][] {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), c[1] as RequestInit | undefined] as [string, RequestInit | undefined])
    .filter(([url]) => url.includes(urlSubstr));
}

/**
 * 取得計畫卡的「執行」按鈕。注意：`Btn` 的 `aria-label` 固定為「執行計畫」/"Run plan"，
 * 不隨 `isRunning` 切換（切換的只有可見文字「執行」⇄「執行中…」），故用 aria-label 取按鈕、
 * 再用 `.textContent`（而非 `toHaveTextContent` 的子字串比對，會誤配「執行」⊂「執行中…」）
 * 精確比對目前顯示的文字。
 */
function runButtons(): HTMLButtonElement[] {
  return screen.getAllByRole('button', { name: '執行計畫' }) as HTMLButtonElement[];
}

/** 依名稱文字找到計畫卡容器（name div → minWidth 容器 → row1 → Card div，共 3 層）。 */
function planCardByName(name: string): HTMLElement {
  const nameEl = screen.getByText(name);
  return nameEl.parentElement!.parentElement!.parentElement as HTMLElement;
}

// ─── render helper（flush 3 條 mount fetch effect）────────────────────────────

async function renderPanel(lang?: Lang) {
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <FaultInjectionPanel lang={lang} />
      </ThemeProvider>,
    );
  });
  return utils;
}

// ─── 共用 setup ──────────────────────────────────────────────────────────────

beforeEach(() => {
  // fake timers：精確控制 3s 輪詢 + 3s/8s 訊息清除；元件無 Date.now() 依賴不受影響。
  vi.useFakeTimers();
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═════════════════════════════════════════════════════════════════════════════

describe('FaultInjectionPanel — 殼層 / PageHeader', () => {
  it('渲染標題「故障模擬」（預設 zh）', async () => {
    await renderPanel();
    expect(screen.getByRole('heading', { name: '故障模擬' })).toBeInTheDocument();
  });

  it('lang=en → 標題 "Fault Injection"', async () => {
    await renderPanel('en');
    expect(screen.getByRole('heading', { name: 'Fault Injection' })).toBeInTheDocument();
  });

  it('sub 顯示說明文字（zh/en）', async () => {
    await renderPanel();
    expect(
      screen.getByText('手動注入故障・診斷測試計畫・模擬故障行為'),
    ).toBeInTheDocument();
  });

  it('未選場景時「注入故障」按鈕 disabled，「清除全部」按鈕可點', async () => {
    await renderPanel();
    expect(screen.getByRole('button', { name: '注入故障' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '清除全部' })).not.toBeDisabled();
  });

  it('mount 時觸發 3 條 GET fetch：scenarios / test-plans / active', async () => {
    await renderPanel();
    expect(callsTo('/api/faults/scenarios')).toHaveLength(1);
    expect(callsTo('/api/faults/test-plans')).toHaveLength(1);
    expect(callsTo('/api/faults/active')).toHaveLength(1);
  });

  it('mount fetch 全部失敗（rejectMount）→ 不崩潰，維持空狀態', async () => {
    installFetch({ rejectMount: true });
    await renderPanel();
    expect(screen.getByRole('heading', { name: '故障模擬' })).toBeInTheDocument();
    expect(screen.queryByText(/活躍故障/)).not.toBeInTheDocument();
  });
});

// ─── 注入參數 Fields ─────────────────────────────────────────────────────────

describe('FaultInjectionPanel — 注入參數 Fields', () => {
  it('場景 Select 顯示 placeholder + 依語系顯示 fetch 到的場景名稱', async () => {
    installFetch({
      scenarios: [makeScenario({ id: 's1', name_zh: '齒輪箱磨損', name_en: 'Gearbox Wear' })],
    });
    await renderPanel();
    const select = screen.getByRole('combobox', { name: '故障場景' });
    expect(within(select).getByText('-- 選擇故障場景 --')).toBeInTheDocument();
    expect(within(select).getByText('齒輪箱磨損')).toBeInTheDocument();
  });

  it('lang=en 場景 Select 顯示英文名稱', async () => {
    installFetch({
      scenarios: [makeScenario({ id: 's1', name_zh: '齒輪箱磨損', name_en: 'Gearbox Wear' })],
    });
    await renderPanel('en');
    const select = screen.getByRole('combobox', { name: 'Scenario' });
    expect(within(select).getByText('Gearbox Wear')).toBeInTheDocument();
  });

  it('風機 Select 固定 14 個選項 WT001..WT014，預設值 WT001', async () => {
    await renderPanel();
    const select = screen.getByRole('combobox', { name: '風機' }) as HTMLSelectElement;
    const options = within(select).getAllByRole('option');
    expect(options).toHaveLength(14);
    expect(options[0]).toHaveTextContent('WT001');
    expect(options[13]).toHaveTextContent('WT014');
    expect(select).toHaveValue('WT001');
  });

  it('選擇場景後「注入故障」按鈕變為可點', async () => {
    installFetch({ scenarios: [makeScenario({ id: 's1' })] });
    await renderPanel();
    const select = screen.getByRole('combobox', { name: '故障場景' });
    fireEvent.change(select, { target: { value: 's1' } });
    expect(screen.getByRole('button', { name: '注入故障' })).not.toBeDisabled();
  });

  it('速率 Input 預設值 0.005，可修改', async () => {
    await renderPanel();
    const input = screen.getByRole('spinbutton', { name: '速率' }) as HTMLInputElement;
    expect(input).toHaveValue(0.005);
    fireEvent.change(input, { target: { value: '0.02' } });
    expect(input).toHaveValue(0.02);
  });
});

// ─── handleInject ────────────────────────────────────────────────────────────

describe('FaultInjectionPanel — 注入故障', () => {
  async function setupWithScenario() {
    installFetch({ scenarios: [makeScenario({ id: 's1' })] });
    await renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '故障場景' }), {
      target: { value: 's1' },
    });
  }

  it('點擊注入 → POST /api/faults/inject 帶 scenarioId/turbineId/severityRate', async () => {
    await setupWithScenario();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '注入故障' }));
    });
    const calls = callsTo('/api/faults/inject');
    expect(calls).toHaveLength(1);
    const [, init] = calls[0];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init!.body as string)).toEqual({
      scenarioId: 's1',
      turbineId: 'WT001',
      severityRate: 0.005,
    });
  });

  it('注入成功 → 顯示訊息 + 觸發 refreshActive（active fetch 次數 +1）', async () => {
    await setupWithScenario();
    expect(callsTo('/api/faults/active')).toHaveLength(1); // mount 的那次
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '注入故障' }));
    });
    expect(screen.getByText('已注入故障到 WT001')).toBeInTheDocument();
    expect(callsTo('/api/faults/active')).toHaveLength(2);
  });

  it('注入失敗（res.ok=false）→ 不顯示成功訊息、不觸發 refreshActive', async () => {
    installFetch({ scenarios: [makeScenario({ id: 's1' })], injectOk: false });
    await renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '故障場景' }), {
      target: { value: 's1' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '注入故障' }));
    });
    expect(screen.queryByText('已注入故障到 WT001')).not.toBeInTheDocument();
    expect(callsTo('/api/faults/active')).toHaveLength(1);
  });

  it('訊息 3 秒後自動清除', async () => {
    await setupWithScenario();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '注入故障' }));
    });
    expect(screen.getByText('已注入故障到 WT001')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.queryByText('已注入故障到 WT001')).not.toBeInTheDocument();
  });
});

// ─── handleClearAll ──────────────────────────────────────────────────────────

describe('FaultInjectionPanel — 清除全部', () => {
  it('點擊 → POST /api/faults/clear 帶空 body，顯示訊息並觸發 refreshActive', async () => {
    await renderPanel();
    expect(callsTo('/api/faults/active')).toHaveLength(1);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '清除全部' }));
    });
    const calls = callsTo('/api/faults/clear');
    expect(calls).toHaveLength(1);
    const [, init] = calls[0];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init!.body as string)).toEqual({});
    expect(screen.getByText('已清除所有故障')).toBeInTheDocument();
    expect(callsTo('/api/faults/active')).toHaveLength(2);
  });

  it('lang=en 訊息顯示英文', async () => {
    await renderPanel('en');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
    });
    expect(screen.getByText('All faults cleared')).toBeInTheDocument();
  });
});

// ─── 活躍故障表 ────────────────────────────────────────────────────────────────

describe('FaultInjectionPanel — 活躍故障表', () => {
  it('activeFaults 為空 → 不渲染活躍故障卡', async () => {
    await renderPanel();
    expect(screen.queryByText(/活躍故障/)).not.toBeInTheDocument();
  });

  it('activeFaults 非空 → 顯示標題含筆數 + 各欄位', async () => {
    installFetch({
      active: [
        makeActiveFault({
          turbine_id: 'WT003',
          name_zh: '軸承過熱',
          severity: 0.8,
          phase: 'critical',
          tripped: true,
          active_alarms: [{ type: 'TEMP', code: 101, desc: 'over temp' }],
        }),
      ],
    });
    await renderPanel();
    expect(screen.getByText('活躍故障 (1)')).toBeInTheDocument();
    const card = screen.getByText('活躍故障 (1)').parentElement as HTMLElement;
    const row = within(card).getAllByRole('row')[1];
    expect(within(row).getByText('WT003')).toBeInTheDocument();
    expect(within(row).getByText('軸承過熱')).toBeInTheDocument();
    expect(within(row).getByText('80%')).toBeInTheDocument();
    expect(within(row).getByText(/critical/)).toBeInTheDocument();
    expect(within(row).getByText(/· TRIP/)).toBeInTheDocument();
    expect(within(row).getByText('[TEMP]')).toBeInTheDocument();
  });

  it('未 tripped 且無告警 → 無 TRIP 後綴、告警欄顯示「—」', async () => {
    installFetch({
      active: [makeActiveFault({ tripped: false, active_alarms: [] })],
    });
    await renderPanel();
    const card = screen.getByText(/活躍故障/).parentElement as HTMLElement;
    const row = within(card).getAllByRole('row')[1];
    expect(within(row).queryByText(/TRIP/)).not.toBeInTheDocument();
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('lang=en 標頭與內容顯示英文', async () => {
    installFetch({ active: [makeActiveFault({ name_en: 'Gearbox Wear' })] });
    await renderPanel('en');
    expect(screen.getByText('Active faults (1)')).toBeInTheDocument();
    const card = screen.getByText('Active faults (1)').parentElement as HTMLElement;
    const header = within(card).getAllByRole('row')[0];
    ['Turbine', 'Fault', 'Severity', 'Phase', 'Alarms'].forEach(h => {
      expect(within(header).getByText(h)).toBeInTheDocument();
    });
  });
});

// ─── 診斷測試計畫卡片 ──────────────────────────────────────────────────────────

describe('FaultInjectionPanel — 診斷測試計畫卡片', () => {
  it('顯示章節標題與說明', async () => {
    await renderPanel();
    expect(screen.getByRole('heading', { name: '診斷測試計畫' })).toBeInTheDocument();
    expect(
      screen.getByText('產生含預排程故障注入的模擬歷史資料，用於外部診斷系統測試。'),
    ).toBeInTheDocument();
  });

  it('每張計畫卡顯示名稱 / 時長 / 故障數 / 說明 / 風機 chips（已排序）', async () => {
    installFetch({
      testPlans: [
        makeTestPlan({
          name_zh: '基本驗證',
          duration_hours: 24,
          fault_count: 3,
          turbines_affected: ['WT010', 'WT002'],
        }),
      ],
    });
    await renderPanel();
    const card = planCardByName('基本驗證');
    expect(within(card).getByText('24h')).toBeInTheDocument();
    expect(within(card).getByText('3 故障')).toBeInTheDocument();
    expect(within(card).getByText('執行標準測試組合。')).toBeInTheDocument();
    // 傳入順序為 ['WT010','WT002']，DOM 順序應已排序為 WT002 在前
    const chipTexts = within(card)
      .getAllByText(/^WT\d+$/)
      .map(el => el.textContent);
    expect(chipTexts).toEqual(['WT002', 'WT010']);
  });

  it.each([
    ['basic_validation', '簡單'],
    ['subtle_challenge', '困難'],
    ['mixed_difficulty', '混合'],
    ['unknown_plan', '極限'],
  ])('計畫 id=%s → 難度 label「%s」', async (id, label) => {
    installFetch({ testPlans: [makeTestPlan({ id })] });
    await renderPanel();
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('scenarios_used 超過 4 個 → 只顯示前 4 個 + 「+N」', async () => {
    installFetch({
      testPlans: [
        makeTestPlan({
          scenarios_used: ['s1', 's2', 's3', 's4', 's5', 's6'],
        }),
      ],
    });
    await renderPanel();
    ['s1', 's2', 's3', 's4'].forEach(s => expect(screen.getByText(s)).toBeInTheDocument());
    expect(screen.queryByText('s5')).not.toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });

  it('scenarios_used 剛好 4 個 → 不顯示 「+N」', async () => {
    installFetch({ testPlans: [makeTestPlan({ scenarios_used: ['s1', 's2', 's3', 's4'] })] });
    await renderPanel();
    expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument();
  });
});

// ─── handleRunPlan + 執行結果卡 ────────────────────────────────────────────────

describe('FaultInjectionPanel — 執行測試計畫', () => {
  it('執行中 → 按鈕文字變「執行中…」且 disabled，其他計畫按鈕同時 disabled', async () => {
    let resolveRun!: (r: Response) => void;
    const pending = new Promise<Response>(res => {
      resolveRun = res;
    });
    installFetch({
      testPlans: [
        makeTestPlan({ id: 'plan-a', name_zh: '計畫甲' }),
        makeTestPlan({ id: 'plan-b', name_zh: '計畫乙' }),
      ],
      runHandler: () => pending,
    });
    await renderPanel();
    const before = runButtons();
    expect(before).toHaveLength(2);
    before.forEach(b => expect(b.textContent).toBe('執行'));
    fireEvent.click(before[0]);

    const during = runButtons();
    expect(during[0].textContent).toBe('執行中…');
    expect(during[0]).toBeDisabled();
    expect(during[1].textContent).toBe('執行'); // 未被點擊的那顆文字不變
    expect(during[1]).toBeDisabled(); // 但因 runningPlan !== null 同樣被 disable

    // 收尾 resolve，避免懸掛的 promise 在 afterEach 後才 settle
    await act(async () => {
      resolveRun({ ok: true, json: () => Promise.resolve(makeTestPlanResult({ plan_id: 'plan-a' })) } as Response);
    });
  });

  it('執行成功 → POST 帶 time_step:10、恢復按鈕文字、渲染結果卡 Stat 區塊', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () =>
        jsonRes(
          makeTestPlanResult({
            plan_id: 'plan-a',
            duration_hours: 48,
            total_readings: 17280,
            faults_injected: 5,
            storage_stats: { db_size_mb: 12.5 },
          }),
        ),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });

    const calls = callsTo('/api/faults/test-plans/plan-a/run');
    expect(calls).toHaveLength(1);
    expect(JSON.parse(calls[0][1]!.body as string)).toEqual({ time_step: 10 });

    expect(runButtons()[0].textContent).toBe('執行');
    expect(runButtons()[0]).not.toBeDisabled();
    expect(screen.getByText('測試計畫結果 — plan-a')).toBeInTheDocument();
    expect(screen.getByText('48h')).toBeInTheDocument();
    expect(screen.getByText('17,280')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('12.5')).toBeInTheDocument();
    expect(screen.getByText('MB')).toBeInTheDocument();
  });

  it('storage_stats.db_size_mb 缺值 → DB 大小顯示「—」', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () => jsonRes(makeTestPlanResult({ storage_stats: {} })),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    const resultCard = screen.getByText(/測試計畫結果/).parentElement as HTMLElement;
    expect(within(resultCard).getByText('—')).toBeInTheDocument();
  });

  it('final_fault_status 非空 → 渲染最終故障狀態表（scenario_id 缺值 fallback name_en）', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () =>
        jsonRes(
          makeTestPlanResult({
            final_fault_status: [
              makeActiveFault({
                turbine_id: 'WT004',
                scenario_id: undefined,
                name_en: 'Bearing Overheat',
                severity: 0.65,
                phase: 'advanced',
                tripped: true,
              }),
            ],
          }),
        ),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    expect(screen.getByText('最終故障狀態')).toBeInTheDocument();
    const resultCard = screen.getByText('最終故障狀態').parentElement as HTMLElement;
    const row = within(resultCard).getAllByRole('row')[1];
    expect(within(row).getByText('WT004')).toBeInTheDocument();
    expect(within(row).getByText('Bearing Overheat')).toBeInTheDocument();
    expect(within(row).getByText('65%')).toBeInTheDocument();
    expect(within(row).getByText('TRIP')).toBeInTheDocument();
  });

  it('final_fault_status 為空 → 不渲染最終故障狀態表', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () => jsonRes(makeTestPlanResult({ final_fault_status: [] })),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    expect(screen.queryByText('最終故障狀態')).not.toBeInTheDocument();
  });

  it('未 tripped → 最終故障狀態表跳脫欄顯示「—」', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () =>
        jsonRes(
          makeTestPlanResult({
            final_fault_status: [makeActiveFault({ tripped: false })],
          }),
        ),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    const resultCard = screen.getByText('最終故障狀態').parentElement as HTMLElement;
    const row = within(resultCard).getAllByRole('row')[1];
    expect(within(row).getByText('—')).toBeInTheDocument();
    expect(within(row).queryByText('TRIP')).not.toBeInTheDocument();
  });

  it('執行失敗（fetch reject）→ 顯示失敗訊息、不渲染結果卡、恢復按鈕文字', async () => {
    installFetch({
      testPlans: [makeTestPlan({ id: 'plan-a' })],
      runHandler: () => Promise.reject(new Error('boom')),
    });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    expect(screen.getByText('測試計畫執行失敗')).toBeInTheDocument();
    expect(screen.queryByText(/測試計畫結果/)).not.toBeInTheDocument();
    expect(runButtons()[0]).not.toBeDisabled();
  });

  it('訊息 8 秒後自動清除', async () => {
    installFetch({ testPlans: [makeTestPlan({ id: 'plan-a' })] });
    await renderPanel();
    await act(async () => {
      fireEvent.click(runButtons()[0]);
    });
    expect(screen.getByText('測試計畫「plan-a」執行完成')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(screen.queryByText('測試計畫「plan-a」執行完成')).not.toBeInTheDocument();
  });
});

// ─── 3s 輪詢 + unmount cleanup ─────────────────────────────────────────────────

describe('FaultInjectionPanel — 輪詢與 cleanup', () => {
  it('每 3 秒輪詢一次 /api/faults/active', async () => {
    await renderPanel();
    expect(callsTo('/api/faults/active')).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(callsTo('/api/faults/active')).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(callsTo('/api/faults/active')).toHaveLength(3);
  });

  it('unmount 後停止輪詢（clearInterval 生效）', async () => {
    const { unmount } = await renderPanel();
    expect(callsTo('/api/faults/active')).toHaveLength(1);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(callsTo('/api/faults/active')).toHaveLength(1);
  });
});

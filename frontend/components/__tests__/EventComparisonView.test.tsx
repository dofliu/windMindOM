/**
 * EventComparisonView component render 測試（WMOM-20260607-03，EPIC-M5 測試覆蓋擴大）。
 *
 * `components/EventComparisonView.tsx`（332 行）是「多風機事件比較」分析面板：
 *   - 風機選擇器：每台一顆 toggle 按鈕（`aria-pressed`），預設選前 4 台 + 全選 / 清除
 *   - filters：開始 / 結束時間（datetime-local）、事件類型 Select、匯出 CSV 鈕
 *   - 狀態列：載入中 / `N 事件 · M 台`
 *   - 單機摘要（selectedIds 非空才顯示）：每台事件總數 + by_type pills
 *   - 全場事件（farm_events 非空才顯示）
 *   - 事件時間線（含空狀態「未找到事件。」）
 *
 * 本元件先前零 component 測試。延續既有 render 測試範式（真實 ThemeProvider + ui 元件 +
 * jest-dom matcher + afterEach cleanup + async act flush）。
 *
 * 外部依賴的隔離策略：
 *   - `useTheme` → ThemeProvider 包裹（用真實 theme，驗實際渲染）。
 *   - `global.fetch` → 以 `vi.fn()` 接管，路由 `/api/maintenance/events/compare` 回
 *     `{ timeline, summary, farm_events }`；未預期 URL 直接 reject，避免靜默吞掉新呼叫。
 *   - `window.open` → stub 成 `vi.fn`（匯出 CSV 驗 URL 拼裝；jsdom 未實作 open）。
 *
 * ⚠️ mount 時 effect 會 fetch→setState；所有 render 一律以 `await renderView(...)`
 * （內部 `act(async)` 包 render + flush microtask）收尾，避免 act() 警告污染輸出。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor, within } from '@testing-library/react';
import React from 'react';

import EventComparisonView from '../EventComparisonView';
import { ThemeProvider } from '../../theme/ThemeProvider';
import type { TurbineData } from '../../types';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

type Lang = 'en' | 'zh';

// ─── turbine fixture（最小欄位即可，元件只用 id 拼 WT###）─────────────────────────
function makeTurbine(id: number): TurbineData {
  return {
    id,
    name: `Turbine ${id}`,
    status: 'running' as TurbineData['status'],
    powerOutput: 0,
    windSpeed: 0,
    rotorSpeed: 0,
    bladeAngle: 0,
    temperature: 0,
    vibration: 0,
    voltage: 0,
    current: 0,
    history: [],
  };
}

// 預設 5 台 → allTurbineIds = WT001..WT005，元件預設選前 4 台（WT001-WT004）。
const TURBINES: TurbineData[] = [1, 2, 3, 4, 5].map(makeTurbine);

// ─── fetch stub ──────────────────────────────────────────────────────────────

interface CompareBody {
  timeline?: unknown[];
  summary?: Record<string, { total: number; by_type: Record<string, number> }>;
  farm_events?: unknown[];
}

function jsonRes(body: unknown): Promise<Response> {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

/**
 * 安裝 fetch stub 並接管 `global.fetch`。
 * - `body`：compare 端點回傳內容（預設空 timeline / summary / farm_events）。
 * - `rejectAll`：所有 fetch 直接 reject（驗容錯不崩潰）。
 */
function installFetch(opts: { body?: CompareBody; rejectAll?: boolean } = {}) {
  const body: CompareBody = opts.body ?? { timeline: [], summary: {}, farm_events: [] };
  fetchMock = vi.fn((url: string) => {
    if (opts.rejectAll) return Promise.reject(new Error(`network down: ${url}`));
    if (url.includes('/api/maintenance/events/compare')) return jsonRes(body);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

/** 取得所有 compare fetch 的 URL（依呼叫順序）。 */
function compareCalls(): string[] {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/events/compare'));
}

// ─── window.open stub（匯出 CSV）──────────────────────────────────────────────
let openMock: Mock;

// ─── render helper（flush mount fetch effect）────────────────────────────────

async function renderView(props: { lang?: Lang; turbines?: TurbineData[] } = {}) {
  const { lang = 'zh', turbines = TURBINES } = props;
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <EventComparisonView turbines={turbines} lang={lang} />
      </ThemeProvider>,
    );
  });
  return { ...utils, lang };
}

// ─── 共用 setup ──────────────────────────────────────────────────────────────

beforeEach(() => {
  installFetch();
  openMock = vi.fn();
  vi.stubGlobal('open', openMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═════════════════════════════════════════════════════════════════════════════

describe('EventComparisonView — 殼層 / 標題', () => {
  it('渲染中文區塊標題（選擇風機 / 事件時間線）', async () => {
    await renderView({ lang: 'zh' });
    expect(screen.getByText('選擇風機')).toBeInTheDocument();
    expect(screen.getByText('事件時間線')).toBeInTheDocument();
  });

  it('lang=en 渲染英文區塊標題（Select turbines / Event timeline）', async () => {
    await renderView({ lang: 'en' });
    expect(screen.getByText('Select turbines')).toBeInTheDocument();
    expect(screen.getByText('Event timeline')).toBeInTheDocument();
  });

  it('預設 lang（未傳）走中文', async () => {
    await act(async () => {
      render(
        <ThemeProvider>
          <EventComparisonView turbines={TURBINES} />
        </ThemeProvider>,
      );
    });
    expect(screen.getByText('選擇風機')).toBeInTheDocument();
  });
});

describe('EventComparisonView — 風機選擇器', () => {
  it('每台風機渲染一顆 toggle 按鈕（WT001..WT005）', async () => {
    await renderView({ lang: 'zh' });
    for (const tid of ['WT001', 'WT002', 'WT003', 'WT004', 'WT005']) {
      expect(screen.getByRole('button', { name: tid })).toBeInTheDocument();
    }
  });

  it('預設選取前 4 台（aria-pressed=true），第 5 台未選（pressed=false）', async () => {
    await renderView({ lang: 'zh' });
    for (const tid of ['WT001', 'WT002', 'WT003', 'WT004']) {
      expect(screen.getByRole('button', { name: tid, pressed: true })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'WT005', pressed: false })).toBeInTheDocument();
  });

  it('點選未選風機 → 加入選取（pressed 轉 true）', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'WT005' }));
    });
    expect(screen.getByRole('button', { name: 'WT005', pressed: true })).toBeInTheDocument();
  });

  it('點選已選風機 → 取消選取（pressed 轉 false）', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'WT001' }));
    });
    expect(screen.getByRole('button', { name: 'WT001', pressed: false })).toBeInTheDocument();
  });

  it('「全選」→ 全部風機 pressed=true', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '全選' }));
    });
    for (const tid of ['WT001', 'WT002', 'WT003', 'WT004', 'WT005']) {
      expect(screen.getByRole('button', { name: tid, pressed: true })).toBeInTheDocument();
    }
  });

  it('「清除」→ 全部風機 pressed=false + 單機摘要隱藏', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '清除' }));
    });
    for (const tid of ['WT001', 'WT002', 'WT003', 'WT004', 'WT005']) {
      expect(screen.getByRole('button', { name: tid, pressed: false })).toBeInTheDocument();
    }
    // selectedIds 為空 → 單機摘要區塊不渲染
    expect(screen.queryByText('單機摘要')).not.toBeInTheDocument();
  });

  it('lang=en 全選 / 清除鈕文字（All / None）', async () => {
    await renderView({ lang: 'en' });
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'None' })).toBeInTheDocument();
  });
});

describe('EventComparisonView — filters / 匯出', () => {
  it('事件類型 Select 渲染（中文選項）', async () => {
    await renderView({ lang: 'zh' });
    const select = screen.getByRole('combobox');
    expect(within(select).getByRole('option', { name: '全部' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: '故障' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: '電網' })).toBeInTheDocument();
  });

  it('lang=en 事件類型選項（All / Fault / Grid）', async () => {
    await renderView({ lang: 'en' });
    const select = screen.getByRole('combobox');
    expect(within(select).getByRole('option', { name: 'All' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'Fault' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'Grid' })).toBeInTheDocument();
  });

  it('「匯出 CSV」→ window.open 帶 /api/export/events?format=csv', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '匯出 CSV' }));
    });
    expect(openMock).toHaveBeenCalledTimes(1);
    const url = String(openMock.mock.calls[0][0]);
    expect(url).toContain('/api/export/events');
    expect(url).toContain('format=csv');
  });

  it('lang=en 匯出鈕文字（Export CSV）', async () => {
    await renderView({ lang: 'en' });
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
  });
});

describe('EventComparisonView — fetch 接線', () => {
  it('mount 時 fetch compare（URL 帶選取的 turbine_ids + limit=500）', async () => {
    await renderView({ lang: 'zh' });
    const calls = compareCalls();
    expect(calls.length).toBeGreaterThan(0);
    // 預設選前 4 台 → turbine_ids=WT001,WT002,WT003,WT004（URL encode 後逗號為 %2C）
    expect(calls.some(u => /turbine_ids=WT001(%2C|,)WT002(%2C|,)WT003(%2C|,)WT004/.test(u))).toBe(true);
    expect(calls.some(u => u.includes('limit=500'))).toBe(true);
  });

  it('選事件類型 → 觸發帶 event_type 的新 compare fetch', async () => {
    await renderView({ lang: 'zh' });
    const countBefore = compareCalls().length;
    await act(async () => {
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'fault' } });
    });
    await waitFor(() => {
      expect(compareCalls().slice(countBefore).some(u => u.includes('event_type=fault'))).toBe(true);
    });
  });

  it('變更開始時間（datetime-local）→ 觸發新 compare fetch', async () => {
    const { container } = await renderView({ lang: 'zh' });
    // rangeStart 在 effect deps 內 → 變更日期應觸發新 fetch（與 event_type filter 對等覆蓋）
    const startInput = container.querySelector('input[type="datetime-local"]') as HTMLInputElement;
    const countBefore = compareCalls().length;
    await act(async () => {
      fireEvent.change(startInput, { target: { value: '2026-06-01T00:00' } });
    });
    await waitFor(() => {
      expect(compareCalls().length).toBeGreaterThan(countBefore);
    });
  });

  it('清除全部風機 → selectedIds 空 → 不再觸發 compare fetch', async () => {
    await renderView({ lang: 'zh' });
    const countBefore = compareCalls().length;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '清除' }));
    });
    // effect 在 selectedIds.length === 0 時 early-return → 無新增 fetch
    expect(compareCalls().length).toBe(countBefore);
  });
});

describe('EventComparisonView — 狀態列', () => {
  it('fetch settle 後狀態列顯示「N 事件 · M 台」', async () => {
    // timeline fixture 帶完整 ComparisonEvent 欄位（避免殘缺欄位觸發 Invalid Date 等非預期渲染路徑）
    installFetch({
      body: {
        timeline: [
          { id: 1, timestamp: '2026-06-01T08:00:00Z', event_type: 'fault', source: 'scada', title: '事件A' },
          { id: 2, timestamp: '2026-06-01T09:00:00Z', event_type: 'grid', source: 'scada', title: '事件B' },
        ],
        summary: {},
        farm_events: [],
      },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText(/2 事件 · 4 台/)).toBeInTheDocument();
    });
  });

  it('fetch pending 時狀態列顯示「載入中…」', async () => {
    // 用一個遲遲不 resolve 的 fetch，讓 loading 維持 true 以觀測載入態 UI
    let resolveFn!: (v: Response) => void;
    const pending = new Promise<Response>(res => {
      resolveFn = res;
    });
    fetchMock = vi.fn(() => pending);
    vi.stubGlobal('fetch', fetchMock);
    await renderView({ lang: 'zh' });
    expect(screen.getByText('載入中…')).toBeInTheDocument();
    // 收尾 resolve 避免懸掛的 promise 在 afterEach 後才 settle
    await act(async () => {
      resolveFn({ json: () => Promise.resolve({ timeline: [], summary: {}, farm_events: [] }) } as Response);
    });
  });

  it('清除風機後狀態列台數歸 0（0 台）', async () => {
    await renderView({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '清除' }));
    });
    expect(screen.getByText(/· 0 台/)).toBeInTheDocument();
  });
});

describe('EventComparisonView — 單機摘要', () => {
  it('summary 有資料 → 顯示每台事件總數 + by_type pills', async () => {
    installFetch({
      body: {
        timeline: [],
        summary: { WT001: { total: 7, by_type: { fault: 3, grid: 2 } } },
        farm_events: [],
      },
    });
    await renderView({ lang: 'zh' });
    // waitFor 等待 fetch 產物（total 數字）本身，而非 mount 即存在的 section heading
    await waitFor(() => {
      expect(screen.getByText('7')).toBeInTheDocument();
    });
    expect(screen.getByText('單機摘要')).toBeInTheDocument();
    // by_type pills（StatusPill 文字 `type: count`）
    expect(screen.getByText('fault: 3')).toBeInTheDocument();
    expect(screen.getByText('grid: 2')).toBeInTheDocument();
  });

  it('summary 缺某台 → 退回 total=0（不崩潰）', async () => {
    // summary 只給 WT002，WT001/3/4 走 fallback { total: 0, by_type: {} }
    installFetch({
      body: { timeline: [], summary: { WT002: { total: 5, by_type: {} } }, farm_events: [] },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });
    // 3 台走 fallback（WT001 / WT003 / WT004），各顯示一個 '0'
    expect(screen.getAllByText('0')).toHaveLength(3);
  });
});

describe('EventComparisonView — 全場事件', () => {
  it('farm_events 有資料 → 顯示「全場事件」區塊 + 事件標題', async () => {
    installFetch({
      body: {
        timeline: [],
        summary: {},
        farm_events: [
          { id: 1, timestamp: '2026-06-01T10:00:00Z', event_type: 'grid', source: 'scada', title: '全場電網跳脫事件' },
        ],
      },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('全場事件')).toBeInTheDocument();
    });
    expect(screen.getByText('全場電網跳脫事件')).toBeInTheDocument();
  });

  it('farm_events 為空 → 不渲染「全場事件」區塊', async () => {
    await renderView({ lang: 'zh' });
    expect(screen.queryByText('全場事件')).not.toBeInTheDocument();
  });
});

describe('EventComparisonView — 事件時間線', () => {
  it('timeline 有事件 → 渲染事件標題 + 類型 pill', async () => {
    installFetch({
      body: {
        timeline: [
          {
            id: 1,
            timestamp: '2026-06-01T08:00:00Z',
            turbine_id: 'WT001',
            event_type: 'fault',
            source: 'scada',
            title: '齒輪箱溫度過高',
            severity: 'critical',
          },
        ],
        summary: {},
        farm_events: [],
      },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('齒輪箱溫度過高')).toBeInTheDocument();
    });
    expect(screen.getByText('critical')).toBeInTheDocument();
  });

  it('事件帶 detail → 渲染行內細節文字', async () => {
    installFetch({
      body: {
        timeline: [
          {
            id: 1,
            timestamp: '2026-06-01T08:00:00Z',
            turbine_id: 'WT001',
            event_type: 'fault',
            source: 'scada',
            title: '主標題',
            detail: '附註細節說明',
          },
        ],
        summary: {},
        farm_events: [],
      },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('附註細節說明')).toBeInTheDocument();
    });
  });

  it('時間線 turbine 欄：_turbine_id 優先，皆缺顯示「—」', async () => {
    installFetch({
      body: {
        timeline: [
          // _turbine_id 優先於 turbine_id
          { id: 1, timestamp: '2026-06-01T08:00:00Z', turbine_id: 'WT002', _turbine_id: 'WT009', event_type: 'fault', source: 'scada', title: 'A' },
          // 兩者皆缺 → fallback '—'
          { id: 2, timestamp: '2026-06-01T09:00:00Z', turbine_id: null, event_type: 'grid', source: 'scada', title: 'B' },
        ],
        summary: {},
        farm_events: [],
      },
    });
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('A')).toBeInTheDocument();
    });
    expect(screen.getByText('WT009')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('timeline 空 + 非載入中 → 顯示空狀態「未找到事件。」', async () => {
    await renderView({ lang: 'zh' });
    await waitFor(() => {
      expect(screen.getByText('未找到事件。')).toBeInTheDocument();
    });
  });

  it('lang=en 空狀態文字（No events found.）', async () => {
    await renderView({ lang: 'en' });
    await waitFor(() => {
      expect(screen.getByText('No events found.')).toBeInTheDocument();
    });
  });
});

describe('EventComparisonView — 容錯', () => {
  it('compare fetch reject → 不崩潰，仍渲染殼層 + 空狀態', async () => {
    installFetch({ rejectAll: true });
    await renderView({ lang: 'zh' });
    expect(screen.getByText('選擇風機')).toBeInTheDocument();
    // catch 後 timeline 維持空 + loading 收尾為 false → 空狀態出現
    await waitFor(() => {
      expect(screen.getByText('未找到事件。')).toBeInTheDocument();
    });
  });

  it('空 turbines 陣列 → 無風機按鈕、無 compare fetch（selectedIds 空）', async () => {
    await renderView({ lang: 'zh', turbines: [] });
    expect(screen.queryByRole('button', { name: 'WT001' })).not.toBeInTheDocument();
    expect(compareCalls().length).toBe(0);
  });
});

// ─── authFetch 稽核（WMOM-20260923-10）──────────────────────────────────────
//
// 上方既有測試用 compareCalls() 只比對 URL，對「裸 fetch vs authFetch」不敏感
// （同款根因見 WMOM-20260923-07/-09/-20260924-01~04）。故另補這組直接檢查
// `Authorization` header 內容的專測，鎖住本次修復（唯一一處 fetch 呼叫：mount 時
// GET /api/maintenance/events/compare，讀取端點、後端掛 require_authenticated()）。

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function compareCallsWithHeaders(): Array<[string, RequestInit | undefined]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), c[1] as RequestInit | undefined] as [string, RequestInit | undefined])
    .filter(([u]) => u.includes('/events/compare'));
}

describe('EventComparisonView — authFetch 稽核（WMOM-20260923-10）', () => {
  afterEach(() => {
    clearAuthToken();
  });

  it('已登入（有 token）→ mount 時 GET compare 帶 Authorization header', async () => {
    setAuthToken('test-token-eventcompare');
    await renderView({ lang: 'zh' });
    const calls = compareCallsWithHeaders();
    expect(calls).toHaveLength(1);
    expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-eventcompare');
  });

  it('未登入（無 token）→ mount 時 GET compare 不帶 Authorization header（過渡期行為不變）', async () => {
    await renderView({ lang: 'zh' });
    const calls = compareCallsWithHeaders();
    expect(calls).toHaveLength(1);
    expect(authHeaderOf(calls[0][1])).toBeUndefined();
  });
});

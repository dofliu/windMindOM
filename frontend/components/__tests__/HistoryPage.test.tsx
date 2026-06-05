/**
 * HistoryPage component render 測試（WMOM-20260605-01，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/history` 歷史資料頁（`components/HistoryPage.tsx`，809 行）先前零 component
 * 測試。本檔延續 CostPage / FarmOverview / SettingsPage 已落地的 render 測試範式
 * （ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup + `global.fetch` stub +
 * `await act(async)` flush mount effect），守住 HistoryPage 的核心 UX 契約：
 *
 *   - PageHeader：zh/en 標題 + CSV（區間 / 聚焦）匯出按鈕
 *   - 單機 / 多機比較 tab 切換（aria-pressed）+ compare tab 掛 EventComparisonView
 *   - 查詢條件卡：風機 Select options 由 turbines props 生成 / 筆數 Select
 *   - 歷史 fetch 接線：mount → GET /api/turbines/:id/history → 圖表資料 + 事件填充
 *   - 事件紀錄清單：title + 類型 pill / 點選 → 事件詳情（title / detail / payload）
 *   - 事件類型篩選 toggle（aria-pressed）→ 關掉某類型 → 該類事件從清單消失
 *   - 事件搜尋：關鍵字過濾事件清單
 *   - 標籤預設按鈕 / 自訂標籤套用 → activeTags 變更 → 重新 fetch + 表頭更新
 *   - CSV 匯出：window.open 帶 /api/export/history?...format=csv
 *   - 最近 20 筆資料表：數值 toFixed(2) + 缺值「—」
 *   - i18n 標籤對映：getLabel(tag) 套用到表頭與「目前顯示」
 *   - 空事件 → 「目前區間沒有事件。」warn
 *   - 語系：lang=en → 標題 / tab / 表頭英文
 *
 * HistoryPage 純由 props（turbines / lang）驅動，唯三外部依賴是 `useTheme`
 * （ThemeProvider 包裹）、`/api/i18n/tags` + `/api/turbines/:id/history` 兩條 fetch、
 * 以及 compare tab 的 `EventComparisonView`（mock 成 sentinel，避免其自身 fetch
 * 污染本檔且讓 compare-tab 測試聚焦）。所有 mount / 互動皆以 `await act(async)`
 * flush fetch effect，避免「state update not wrapped in act()」警告。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import HistoryPage from '../HistoryPage';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { TurbineStatus, type TurbineData } from '../../types';

// compare tab 的 EventComparisonView 有自己的 fetch / 圖表依賴，mock 成 sentinel
// 讓「切到多機比較」測試聚焦於 tab 接線，且不污染 single 模式的 fetch 斷言。
vi.mock('../EventComparisonView', () => ({
  default: () => <div data-testid="event-comparison">compare-view</div>,
}));

// recharts：圖表元件全 stub 成 marker div（對齊 CostPage 範式）。HistoryPage 的折線圖
// 在 jsdom 下 ResponsiveContainer 0 寬度本就不渲染內部，但顯式 stub 可確保資料表 /
// 事件清單的文字斷言不被未來 recharts 版本的 tick / tooltip 渲染細節干擾而 flaky。
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    LineChart: Stub,
    Line: Stub,
    CartesianGrid: Stub,
    XAxis: Stub,
    YAxis: Stub,
    Tooltip: Stub,
    Legend: Stub,
    ReferenceArea: Stub,
    ReferenceLine: Stub,
  };
});

// ─── fixtures ──────────────────────────────────────────────────────────────

/**
 * TurbineData 工廠：核心欄位全列、不用 `as` 強轉，讓 tsc 守住與 types.ts 對齊
 * （漏必填欄位編譯失敗而非靜默假綠）。
 */
function makeTurbine(over: Partial<TurbineData> = {}): TurbineData {
  return {
    id: 1,
    name: 'WTG-01',
    status: TurbineStatus.OPERATING,
    powerOutput: 2.1,
    windSpeed: 8.0,
    rotorSpeed: 12.3,
    bladeAngle: 4,
    temperature: 45,
    vibration: 1.2,
    voltage: 690,
    current: 100,
    history: [],
    ...over,
  };
}

const TURBINES: TurbineData[] = [
  makeTurbine({ id: 1, name: 'WTG-01' }),
  makeTurbine({ id: 2, name: 'WTG-02' }),
];

// startup preset（HistoryPage 預設 activeTags）涵蓋的 SCADA 標籤。
const STARTUP_TAGS = ['WTUR_TurSt', 'WROT_RotSpd', 'WTUR_TotPwrAt', 'WGEN_GnVtgMs', 'WCNV_CnvGnFrq'];

interface HistoryPayload {
  data: Array<{ timestamp: string; scada: Record<string, number> }>;
  events: Array<Record<string, unknown>>;
}

/** 預設歷史回應：2 筆資料（第二筆缺 WCNV_CnvGnFrq → 表格顯示「—」）+ 1 故障 1 電網事件。 */
function makeHistoryPayload(over: Partial<HistoryPayload> = {}): HistoryPayload {
  return {
    data: [
      {
        timestamp: '2026-06-05T10:00:00Z',
        scada: { WTUR_TurSt: 1, WROT_RotSpd: 12.34, WTUR_TotPwrAt: 2100, WGEN_GnVtgMs: 690, WCNV_CnvGnFrq: 50 },
      },
      {
        // 缺 WCNV_CnvGnFrq → point[tag] = null → 表格 cell 顯示「—」
        timestamp: '2026-06-05T10:00:01Z',
        scada: { WTUR_TurSt: 1, WROT_RotSpd: 12.5, WTUR_TotPwrAt: 2150, WGEN_GnVtgMs: 691 },
      },
    ],
    events: [
      {
        id: 1,
        timestamp: '2026-06-05T10:00:00Z',
        event_type: 'fault',
        source: 'PLC',
        title: '齒輪箱高溫',
        detail: '齒輪箱溫度超過閾值',
        payload: { temp: 92 },
      },
      {
        id: 2,
        timestamp: '2026-06-05T10:00:30Z',
        event_type: 'grid',
        source: 'SCADA',
        title: '電網電壓驟降',
        detail: null,
        payload: {},
      },
    ],
    ...over,
  };
}

// ─── fetch stub ──────────────────────────────────────────────────────────────

let fetchMock: ReturnType<typeof vi.fn>;
let openSpy: ReturnType<typeof vi.fn>;

/** 建一個 fetch Response-like（對齊 ok/status 契約，避免日後加 r.ok 守衛時靜默）。 */
function jsonResponse(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as unknown as Response;
}

/**
 * 把所有 pending microtask + 一輪 macrotask drain 乾淨。history fetch chain 是
 * fetch → r.json() → setState → finally(setLoading)，單一 microtask tick 不保證
 * drain，用 setTimeout(0) 確保多層 .then/.finally settle 後再 yield。
 */
const flushAsync = (): Promise<void> => new Promise(resolve => setTimeout(resolve, 0));

/** 預設 i18n 標籤對映（空 → getLabel 回傳原始 tag）；個別測試可覆寫。 */
let tagLabels: Record<string, string> = {};

beforeEach(() => {
  tagLabels = {};
  fetchMock = vi.fn((url: string | URL) => {
    const u = String(url);
    if (u.includes('/api/i18n/tags')) {
      return Promise.resolve(jsonResponse(tagLabels));
    }
    if (u.includes('/history')) {
      return Promise.resolve(jsonResponse(makeHistoryPayload()));
    }
    // 未預期的 URL 直接 reject，避免新增的 fetch 呼叫被靜默吞掉。
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  });
  vi.stubGlobal('fetch', fetchMock);
  // window.open 在 jsdom 未實作（會印 Not implemented），且 CSV 匯出契約只需驗
  // 「有無被以正確 URL 呼叫」→ 以 spy 取代。
  openSpy = vi.fn();
  vi.stubGlobal('open', openSpy);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

// ─── render helper ───────────────────────────────────────────────────────────

interface RenderOpts {
  turbines?: TurbineData[];
  lang?: 'en' | 'zh';
}

/** ThemeProvider 包裹 render + `act(async)` flush i18n / history fetch effect。 */
async function renderHistory(opts: RenderOpts = {}) {
  const turbines = opts.turbines ?? TURBINES;
  const lang = opts.lang ?? 'zh';
  await act(async () => {
    render(
      <ThemeProvider>
        <HistoryPage turbines={turbines} lang={lang} />
      </ThemeProvider>,
    );
    await flushAsync();
  });
}

/** 包一個會觸發 fetch / setState 的互動並 flush，避免 act 警告。 */
async function actFlush(fn: () => void) {
  await act(async () => {
    fn();
    await flushAsync();
  });
}

// 取 fetch 呼叫過的所有 URL（字串化）。
const fetchedUrls = () => fetchMock.mock.calls.map(c => String(c[0]));

// ─── tests ────────────────────────────────────────────────────────────────

describe('HistoryPage — 基本渲染與語系', () => {
  it('zh：標題「歷史資料」+ CSV 匯出按鈕 + 單機/多機 tab', async () => {
    await renderHistory({ lang: 'zh' });
    expect(screen.getByText('歷史資料')).toBeInTheDocument();
    expect(screen.getByText('匯出區間')).toBeInTheDocument();
    expect(screen.getByText('匯出聚焦')).toBeInTheDocument();
    expect(screen.getByText('單機歷史')).toBeInTheDocument();
    expect(screen.getByText('多機比較')).toBeInTheDocument();
  });

  it('en：標題 / tab / 表頭走英文（守 tr() 映射未對調）', async () => {
    await renderHistory({ lang: 'en' });
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.getByText('Single turbine')).toBeInTheDocument();
    expect(screen.getByText('Multi compare')).toBeInTheDocument();
    expect(screen.getByText('CSV (range)')).toBeInTheDocument();
    expect(screen.getByText('Latest 20 rows')).toBeInTheDocument();
    // zh 字串不應外洩到 en 畫面
    expect(screen.queryByText('歷史資料')).not.toBeInTheDocument();
  });

  it('en：i18n GET 帶 lang=en（語系傳遞到後端）', async () => {
    await renderHistory({ lang: 'en' });
    expect(fetchedUrls().some(u => u.includes('/api/i18n/tags') && u.includes('lang=en'))).toBe(true);
  });
});

describe('HistoryPage — tab 切換', () => {
  it('預設 single tab aria-pressed；compare 為 false', async () => {
    await renderHistory();
    const single = screen.getByText('單機歷史');
    const compare = screen.getByText('多機比較');
    expect(single).toHaveAttribute('aria-pressed', 'true');
    expect(compare).toHaveAttribute('aria-pressed', 'false');
  });

  it('點「多機比較」→ 掛 EventComparisonView，single 查詢卡消失', async () => {
    await renderHistory();
    // single 模式查詢條件卡存在（風機 Select）
    expect(screen.getByLabelText('風機')).toBeInTheDocument();
    await actFlush(() => fireEvent.click(screen.getByText('多機比較')));
    expect(screen.getByTestId('event-comparison')).toBeInTheDocument();
    expect(screen.queryByLabelText('風機')).not.toBeInTheDocument();
    expect(screen.getByText('多機比較')).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('HistoryPage — 查詢條件卡', () => {
  it('風機 Select options 由 turbines props 生成（WT00x · 名稱）', async () => {
    await renderHistory();
    const select = screen.getByLabelText('風機') as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map(o => o.textContent);
    expect(optionTexts).toContain('WT001 · WTG-01');
    expect(optionTexts).toContain('WT002 · WTG-02');
  });

  it('mount 即向預設風機 WT001 拉歷史資料', async () => {
    await renderHistory();
    expect(fetchedUrls().some(u => u.includes('/api/turbines/WT001/history'))).toBe(true);
  });

  it('切換風機 Select → 重新向新風機拉歷史', async () => {
    await renderHistory();
    await actFlush(() =>
      fireEvent.change(screen.getByLabelText('風機'), { target: { value: 'WT002' } }),
    );
    expect(fetchedUrls().some(u => u.includes('/api/turbines/WT002/history'))).toBe(true);
  });

  it('切換筆數 Select → 重新 fetch 帶 limit', async () => {
    await renderHistory();
    await actFlush(() =>
      fireEvent.change(screen.getByLabelText('筆數'), { target: { value: '600' } }),
    );
    expect(fetchedUrls().some(u => u.includes('/history') && u.includes('limit=600'))).toBe(true);
  });
});

describe('HistoryPage — 歷史資料表', () => {
  it('資料表渲染數值 toFixed(2)，缺值顯示「—」', async () => {
    await renderHistory();
    // 第一筆 WROT_RotSpd=12.34 → 表格顯示 '12.34'
    expect(screen.getByText('12.34')).toBeInTheDocument();
    // 第二筆缺 WCNV_CnvGnFrq → cell '—'
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('表頭預設顯示 startup 標籤（i18n 空 → 原始 tag）', async () => {
    await renderHistory();
    for (const tag of STARTUP_TAGS) {
      expect(screen.getAllByText(tag).length).toBeGreaterThan(0);
    }
  });
});

describe('HistoryPage — 事件紀錄與詳情', () => {
  it('事件清單渲染各事件 title', async () => {
    await renderHistory();
    // 事件 title 同時出現在「事件紀錄」清單 button 與「事件詳情」div；
    // 以 button role 鎖定清單項（詳情 title 是 div，不會誤命中）。
    expect(screen.getByRole('button', { name: /齒輪箱高溫/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /電網電壓驟降/ })).toBeInTheDocument();
  });

  it('點故障事件 → 事件詳情顯示 title / detail / payload', async () => {
    await renderHistory();
    // 以 button role 點清單項（非 span），確保點到帶 onClick 的 button 本身。
    await actFlush(() => fireEvent.click(screen.getByRole('button', { name: /齒輪箱高溫/ })));
    // 詳情區 detail 文字
    expect(screen.getByText('齒輪箱溫度超過閾值')).toBeInTheDocument();
    // payload pre 內含 temp
    expect(screen.getByText(/"temp": 92/)).toBeInTheDocument();
  });

  it('空事件 → 「目前區間沒有事件。」warn + 詳情提示選擇事件', async () => {
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes('/api/i18n/tags')) return Promise.resolve(jsonResponse(tagLabels));
      if (u.includes('/history')) return Promise.resolve(jsonResponse(makeHistoryPayload({ events: [] })));
      return Promise.reject(new Error(`Unexpected fetch: ${u}`));
    });
    await renderHistory();
    // 事件清單欄：空事件警告
    expect(screen.getByText('目前區間沒有事件。')).toBeInTheDocument();
    // 事件詳情欄：selectedEvent=null → 提示語（與清單警告並存，非矛盾，屬預期）
    expect(screen.getByText('請從左側選擇事件。')).toBeInTheDocument();
  });

  it('history fetch 失敗 → UI 不崩潰、事件清單顯示空狀態', async () => {
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes('/api/i18n/tags')) return Promise.resolve(jsonResponse(tagLabels));
      if (u.includes('/history')) return Promise.reject(new Error('Network error'));
      return Promise.reject(new Error(`Unexpected fetch: ${u}`));
    });
    await renderHistory();
    // production code 的 history fetch .catch(() => {}) 靜默吞錯 → chartData/events 維持空
    // → 頁面不崩潰、事件清單落空狀態。
    expect(screen.getByText('目前區間沒有事件。')).toBeInTheDocument();
    expect(screen.getByText('歷史資料')).toBeInTheDocument();
  });
});

describe('HistoryPage — 事件篩選', () => {
  it('關掉「故障」類型 toggle → 故障事件從清單消失（grid 仍在）', async () => {
    await renderHistory();
    expect(screen.getByRole('button', { name: /齒輪箱高溫/ })).toBeInTheDocument();
    // 事件篩選區的「故障」toggle 按鈕（aria-pressed 預設 true）
    const faultToggle = screen
      .getAllByText('故障')
      .find(el => el.getAttribute('aria-pressed') === 'true');
    expect(faultToggle).toBeTruthy();
    await actFlush(() => fireEvent.click(faultToggle!));
    expect(screen.queryByRole('button', { name: /齒輪箱高溫/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /電網電壓驟降/ })).toBeInTheDocument();
  });

  it('事件搜尋關鍵字 → 只留命中事件', async () => {
    await renderHistory();
    await actFlush(() =>
      fireEvent.change(screen.getByLabelText('事件搜尋'), { target: { value: '電網' } }),
    );
    expect(screen.getByRole('button', { name: /電網電壓驟降/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /齒輪箱高溫/ })).not.toBeInTheDocument();
  });
});

describe('HistoryPage — 標籤切換', () => {
  it('點標籤預設「thermal」→ 重新 fetch + 表頭換成 thermal 標籤', async () => {
    await renderHistory();
    const callsBefore = fetchMock.mock.calls.length;
    await actFlush(() => fireEvent.click(screen.getByText('thermal')));
    // activeTags 變更觸發 history effect 重新 fetch
    expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore);
    // thermal preset 第一個標籤 WGEN_GnStaTmp1 出現在表頭
    expect(screen.getAllByText('WGEN_GnStaTmp1').length).toBeGreaterThan(0);
    // startup 標籤已不在表頭
    expect(screen.queryByText('WTUR_TurSt')).not.toBeInTheDocument();
  });

  it('自訂標籤輸入 + 套用 → activeTags 換成自訂值（舊標籤離場）', async () => {
    await renderHistory();
    await actFlush(() =>
      fireEvent.change(screen.getByLabelText('自訂標籤'), {
        target: { value: 'WTUR_TotWh, WROT_RotSpd' },
      }),
    );
    await actFlush(() => fireEvent.click(screen.getByText('套用')));
    // 自訂的兩個標籤都進表頭
    expect(screen.getAllByText('WTUR_TotWh').length).toBeGreaterThan(0);
    expect(screen.getAllByText('WROT_RotSpd').length).toBeGreaterThan(0);
    // 原 startup 標籤 WTUR_TurSt 已離開表頭（守住 setActiveTags 整批取代而非疊加）
    expect(screen.queryByText('WTUR_TurSt')).not.toBeInTheDocument();
  });
});

describe('HistoryPage — CSV 匯出', () => {
  it('點「匯出區間」→ window.open 帶 /api/export/history?...format=csv', async () => {
    await renderHistory();
    await actFlush(() => fireEvent.click(screen.getByText('匯出區間')));
    expect(openSpy).toHaveBeenCalledTimes(1);
    const url = String(openSpy.mock.calls[0][0]);
    expect(url).toContain('/api/export/history');
    expect(url).toContain('format=csv');
    expect(url).toContain('turbine_id=WT001');
  });
});

describe('HistoryPage — i18n 標籤對映', () => {
  it('i18n 回標籤對映 → 表頭顯示中文標籤而非原始 tag', async () => {
    tagLabels = { WTUR_TurSt: '渦輪狀態' };
    await renderHistory();
    expect(screen.getAllByText('渦輪狀態').length).toBeGreaterThan(0);
  });
});

/**
 * TrendChartPanel component render 測試（WMOM-20260607-02，EPIC-M5 測試覆蓋擴大）。
 *
 * `components/TrendChartPanel.tsx`（225 行）是風機詳情頁的「即時趨勢圖」面板：
 *   - 標題（即時趨勢圖 / Real-time trend）
 *   - 7 個 tag preset 按鈕（功率與風速 / 溫度監控 / 振動與轉速 / 葉片角度 / 變頻器 /
 *     轉向系統 / 載荷與疲勞），預設 active = power（`aria-pressed`）
 *   - 自訂 tag 輸入框（逗號分隔）+ 套用鈕 → 切到自訂 tags、清掉 preset 高亮
 *   - recharts LineChart（本測試以輕量 stub 取代，避免 jsdom 0 寬度噪音）
 *   - 底部「顯示標籤」列（`data-testid="trend-footer"`）：以 i18n label（getLabel）顯示目前 active tags
 *
 * 本元件先前零 component 測試。延續既有 render 測試範式（ThemeProvider 包裹 +
 * jest-dom matcher + afterEach cleanup + async act flush）。
 *
 * 外部依賴的隔離策略：
 *   - `useTheme` → ThemeProvider 包裹（用真實 theme，驗實際渲染）。
 *   - `recharts` → 元件實際 import 的 7 支元件全 stub 成 marker div，聚焦 panel 的
 *     preset / 自訂 / i18n / fetch 接線，不被 ResponsiveContainer 在 jsdom 下 0 寬度的
 *     渲染細節干擾。
 *   - `global.fetch` → 以 `vi.fn()` 接管，依 URL 路由：
 *       `/api/i18n/tags` → 回傳 tag label 對映（驗 getLabel 解析）
 *       `/api/turbines/:id/trend` → 回傳 `{ data: [...] }`
 *     未預期的 URL 直接 reject，避免靜默吞掉新 API 呼叫。
 *
 * ⚠️ mount 時兩條非同步 effect（i18n labels + trend）會 fetch→setState；所有 render
 * 一律以 `await renderPanel(...)`（內部 `act(async)` 包 render + flush microtask）收尾，
 * 避免「state update not wrapped in act()」警告污染輸出。2s 輪詢預設用 real timer，
 * 快速測試內不會二次觸發；輪詢 / cleanup 專屬測試另以 fake timer 精確驗證。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';

// ─── mock：recharts（元件實際 import 的元件全 stub 成 marker div）──────────────
// 只 stub 元件真正 import 的 7 支（LineChart/Line/XAxis/YAxis/ResponsiveContainer/
// Tooltip/Legend）——mock 清單對齊 component import，未用的不補。
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    LineChart: Stub,
    Line: Stub,
    XAxis: Stub,
    YAxis: Stub,
    Tooltip: Stub,
    Legend: Stub,
  };
});

import TrendChartPanel from '../TrendChartPanel';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

type Lang = 'en' | 'zh';

// ─── preset tag 常數（與元件內 TAG_PRESETS 對齊）───────────────────────────────
const POWER_TAGS = ['WTUR_TotPwrAt', 'WMET_WSpeedNac'];
const TEMP_TAGS = ['WGEN_GnStaTmp1', 'WGEN_GnBrgTmp1', 'WGEN_GnAirTmp1', 'WCNV_CnvCabinTmp', 'WGDC_TrfCoreTmp'];

// ─── fetch stub ──────────────────────────────────────────────────────────────

function jsonRes(body: unknown): Promise<Response> {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

/**
 * 安裝 fetch stub 並接管 `global.fetch`。
 * - `labels`：i18n 回傳的 tag label 對映（預設空物件）
 * - `trendData`：trend 回傳 `{ data }` 的內容（預設空陣列）
 * - `trendBody`：覆寫整個 trend 回應 body（驗「缺 data 欄位」等 edge case）
 * - `rejectAll`：所有 fetch 直接 reject（驗容錯不崩潰）
 */
function installFetch(
  opts: { labels?: Record<string, string>; trendData?: unknown[]; trendBody?: unknown; rejectAll?: boolean } = {},
) {
  const labels = opts.labels ?? {};
  const trendData = opts.trendData ?? [];
  fetchMock = vi.fn((url: string) => {
    if (opts.rejectAll) return Promise.reject(new Error(`network down: ${url}`));
    if (url.includes('/api/i18n/tags')) return jsonRes(labels);
    if (url.includes('/trend')) return jsonRes('trendBody' in opts ? opts.trendBody : { data: trendData });
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

/** 取得所有 trend fetch 的 URL（依呼叫順序）。 */
function trendCalls(): string[] {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/trend'));
}

/** 取得所有 i18n fetch 的 URL。 */
function i18nCalls(): string[] {
  return fetchMock.mock.calls.map(c => String(c[0])).filter(u => u.includes('/api/i18n/tags'));
}

// ─── render helper（flush 兩條 mount fetch effect）────────────────────────────

async function renderPanel(props: { turbineId?: string; lang?: Lang } = {}) {
  const { turbineId = 'WT001', lang = 'zh' } = props;
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <TrendChartPanel turbineId={turbineId} lang={lang} />
      </ThemeProvider>,
    );
  });
  return { ...utils, lang };
}

/** 取得底部「顯示標籤 / Showing」列（穩定 data-testid，避免 DOM 結構改動造成的多元素命中）。 */
function getFooter(): HTMLElement {
  return screen.getByTestId('trend-footer');
}

// ─── 共用 setup ──────────────────────────────────────────────────────────────

beforeEach(() => {
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═════════════════════════════════════════════════════════════════════════════

describe('TrendChartPanel — 標題 / 殼層', () => {
  it('渲染中文標題「即時趨勢圖」', async () => {
    await renderPanel({ lang: 'zh' });
    expect(screen.getByText('即時趨勢圖')).toBeInTheDocument();
  });

  it('lang=en 渲染英文標題「Real-time trend」', async () => {
    await renderPanel({ lang: 'en' });
    expect(screen.getByText('Real-time trend')).toBeInTheDocument();
  });

  it('預設 lang（未傳）走中文', async () => {
    // 直接渲染不帶 lang prop，驗元件 default 參數 'zh' 生效。
    await act(async () => {
      render(
        <ThemeProvider>
          <TrendChartPanel turbineId="WT001" />
        </ThemeProvider>,
      );
    });
    expect(screen.getByText('即時趨勢圖')).toBeInTheDocument();
  });
});

describe('TrendChartPanel — preset 按鈕', () => {
  it('渲染全部 7 個 preset 按鈕（中文 label）', async () => {
    await renderPanel({ lang: 'zh' });
    for (const label of ['功率與風速', '溫度監控', '振動與轉速', '葉片角度', '變頻器', '轉向系統', '載荷與疲勞']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('lang=en 渲染英文 preset label', async () => {
    await renderPanel({ lang: 'en' });
    for (const label of ['Power & Wind', 'Temperatures', 'Vibration & RPM', 'Blade Angles', 'Converter', 'Yaw System', 'Load & Fatigue']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('預設 active preset = power（pressed=true，其餘 pressed=false）', async () => {
    await renderPanel({ lang: 'zh' });
    // 以 RTL accessible `pressed` 查詢（語意正確，且 attribute 缺失時不會假綠）。
    expect(screen.getByRole('button', { name: '功率與風速', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '溫度監控', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '載荷與疲勞', pressed: false })).toBeInTheDocument();
  });

  it('點選其他 preset → pressed 高亮轉移（power 變 false、temperature 變 true）', async () => {
    await renderPanel({ lang: 'zh' });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '溫度監控' }));
    });
    expect(screen.getByRole('button', { name: '溫度監控', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '功率與風速', pressed: false })).toBeInTheDocument();
  });
});

describe('TrendChartPanel — 自訂 tag', () => {
  it('渲染自訂 tag 輸入框（中文 placeholder）+ 套用鈕', async () => {
    await renderPanel({ lang: 'zh' });
    expect(screen.getByPlaceholderText('自訂標籤（逗號分隔）')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用' })).toBeInTheDocument();
  });

  it('lang=en placeholder + Apply 鈕', async () => {
    await renderPanel({ lang: 'en' });
    expect(screen.getByPlaceholderText('Custom tags (comma-separated)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument();
  });

  it('輸入自訂 tag + 套用 → 切到自訂 tags、所有 preset 取消高亮、footer 反映', async () => {
    await renderPanel({ lang: 'zh' });
    const input = screen.getByPlaceholderText('自訂標籤（逗號分隔）');
    fireEvent.change(input, { target: { value: 'TAG_A, TAG_B' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用' }));
    });
    // 無 preset 仍 active
    expect(screen.getByRole('button', { name: '功率與風速', pressed: false })).toBeInTheDocument();
    // footer 顯示自訂 tags（無 label → raw tag，· 連接）
    expect(getFooter().textContent).toContain('TAG_A · TAG_B');
  });

  it('自訂 tag 自動 trim 兩側空白後送出（footer + trend fetch URL 雙重驗證）', async () => {
    await renderPanel({ lang: 'zh' });
    const input = screen.getByPlaceholderText('自訂標籤（逗號分隔）');
    fireEvent.change(input, { target: { value: '  FOO ,  BAR  ' } });
    const countBefore = trendCalls().length;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用' }));
    });
    expect(getFooter().textContent).toContain('FOO · BAR');
    // 套用「之後」新增的 trend fetch 帶 trim 後的 tags（slice 確保是本次觸發，非 mount 殘留）
    await waitFor(() => {
      expect(trendCalls().slice(countBefore).some(u => u.includes('tags=FOO,BAR'))).toBe(true);
    });
  });

  it('空白 / 純逗號輸入 + 套用 → guard 不變更（power 仍 active、無新增 trend fetch）', async () => {
    await renderPanel({ lang: 'zh' });
    const input = screen.getByPlaceholderText('自訂標籤（逗號分隔）');
    const countBefore = trendCalls().length;
    fireEvent.change(input, { target: { value: '  ,  ,' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用' }));
    });
    expect(screen.getByRole('button', { name: '功率與風速', pressed: true })).toBeInTheDocument();
    // footer 仍顯示 power tags（raw，因 i18n 預設無 label）
    expect(getFooter().textContent).toContain(POWER_TAGS.join(' · '));
    // guard 生效 → activeTags 不變 → 不觸發新 trend fetch
    expect(trendCalls().length).toBe(countBefore);
  });
});

describe('TrendChartPanel — fetch 接線', () => {
  it('mount 時 fetch i18n labels（URL 帶 lang）', async () => {
    await renderPanel({ lang: 'zh' });
    expect(i18nCalls().some(u => u.includes('lang=zh'))).toBe(true);
  });

  it('lang=en → i18n fetch URL 帶 lang=en', async () => {
    await renderPanel({ lang: 'en' });
    expect(i18nCalls().some(u => u.includes('lang=en'))).toBe(true);
  });

  it('mount 時 fetch trend（URL 帶 turbineId + 預設 power tags + limit=120）', async () => {
    await renderPanel({ turbineId: 'WT042' });
    const calls = trendCalls();
    expect(calls.some(u => u.includes('/api/turbines/WT042/trend'))).toBe(true);
    expect(calls.some(u => u.includes(`tags=${POWER_TAGS.join(',')}`))).toBe(true);
    expect(calls.some(u => u.includes('limit=120'))).toBe(true);
  });

  it('點 preset 切換 tags → 觸發帶新 tags 的 trend fetch', async () => {
    await renderPanel({ turbineId: 'WT001' });
    const countBefore = trendCalls().length;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '溫度監控' }));
    });
    await waitFor(() => {
      expect(trendCalls().slice(countBefore).some(u => u.includes(`tags=${TEMP_TAGS.join(',')}`))).toBe(true);
    });
  });

  it('turbineId prop 變動（rerender）→ 觸發帶新 turbineId 的 trend fetch', async () => {
    const { rerender } = await renderPanel({ turbineId: 'WT001' });
    const countBefore = trendCalls().length;
    await act(async () => {
      rerender(
        <ThemeProvider>
          <TrendChartPanel turbineId="WT999" lang="zh" />
        </ThemeProvider>,
      );
    });
    await waitFor(() => {
      expect(trendCalls().slice(countBefore).some(u => u.includes('/api/turbines/WT999/trend'))).toBe(true);
    });
  });

  it('lang prop 變動（rerender）→ 重新 fetch i18n（帶新 lang）', async () => {
    const { rerender } = await renderPanel({ lang: 'zh' });
    const countBefore = i18nCalls().length;
    await act(async () => {
      rerender(
        <ThemeProvider>
          <TrendChartPanel turbineId="WT001" lang="en" />
        </ThemeProvider>,
      );
    });
    await waitFor(() => {
      expect(i18nCalls().slice(countBefore).some(u => u.includes('lang=en'))).toBe(true);
    });
  });
});

describe('TrendChartPanel — i18n label 解析（footer）', () => {
  it('有 label → footer 以中文 label 顯示而非 raw tag', async () => {
    installFetch({ labels: { WTUR_TotPwrAt: '總功率', WMET_WSpeedNac: '風速' } });
    await renderPanel({ lang: 'zh' });
    // waitFor 確保 i18n fetch settle → setTagLabels 生效；若 state 更新被吞會在此失敗。
    await waitFor(() => {
      expect(getFooter().textContent).toContain('總功率 · 風速');
    });
  });

  it('i18n 回空 label 物件 → footer 退回顯示 raw tag（settle 後仍 raw，不被覆蓋成空白）', async () => {
    installFetch({ labels: {} });
    await renderPanel({ lang: 'zh' });
    await waitFor(() => {
      // 等 i18n settle（i18nCalls 已記錄呼叫）後斷言 footer 仍為 raw tags。
      expect(i18nCalls().length).toBeGreaterThan(0);
    });
    expect(getFooter().textContent).toContain(POWER_TAGS.join(' · '));
  });

  it('部分 label → 有 label 用 label、缺的用 raw tag', async () => {
    installFetch({ labels: { WTUR_TotPwrAt: '總功率' } });
    await renderPanel({ lang: 'zh' });
    await waitFor(() => {
      expect(getFooter().textContent).toContain('總功率 · WMET_WSpeedNac');
    });
  });

  it('footer 中文前綴「顯示標籤」', async () => {
    await renderPanel({ lang: 'zh' });
    expect(getFooter().textContent?.startsWith('顯示標籤')).toBe(true);
  });

  it('footer 英文前綴「Showing」', async () => {
    await renderPanel({ lang: 'en' });
    expect(getFooter().textContent?.startsWith('Showing')).toBe(true);
  });
});

describe('TrendChartPanel — 輪詢 / cleanup', () => {
  it('每 2 秒輪詢一次 trend fetch', async () => {
    vi.useFakeTimers();
    try {
      await act(async () => {
        render(
          <ThemeProvider>
            <TrendChartPanel turbineId="WT001" lang="zh" />
          </ThemeProvider>,
        );
      });
      const before = trendCalls().length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(trendCalls().length).toBe(before + 1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('unmount 後 clearInterval → 不再輪詢', async () => {
    vi.useFakeTimers();
    try {
      let utils!: ReturnType<typeof render>;
      await act(async () => {
        utils = render(
          <ThemeProvider>
            <TrendChartPanel turbineId="WT001" lang="zh" />
          </ThemeProvider>,
        );
      });
      // unmount 包進 act，flush React cleanup（clearInterval）的 side-effect，避免 flaky。
      await act(async () => {
        utils.unmount();
      });
      const after = trendCalls().length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(trendCalls().length).toBe(after);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('TrendChartPanel — 容錯（fetch reject 不崩潰）', () => {
  it('i18n + trend fetch 皆 reject → 仍渲染標題 + footer（raw tags）', async () => {
    installFetch({ rejectAll: true });
    await renderPanel({ lang: 'zh' });
    expect(screen.getByText('即時趨勢圖')).toBeInTheDocument();
    expect(getFooter().textContent).toContain(POWER_TAGS.join(' · '));
  });

  it('trend 回應缺 data 欄位 → 不崩潰，仍渲染殼層', async () => {
    installFetch({ trendBody: {} }); // 無 data 欄位
    await renderPanel({ lang: 'zh' });
    expect(screen.getByText('即時趨勢圖')).toBeInTheDocument();
  });
});

// ─── authFetch 稽核（WMOM-20260923-10 sub-task 7/7）───────────────────────────
//
// 上方既有測試用 trendCalls()/i18nCalls() 只比對 URL，對「裸 fetch vs authFetch」不敏感
// （同款根因見 WMOM-20260923-07/-09/-20260924-01~06）。故另補這組直接檢查
// `Authorization` header 內容的專測，鎖住本次修復（兩處 fetch 呼叫：mount 時
// GET /api/i18n/tags 與輪詢 GET /api/turbines/:id/trend，皆讀取端點、後端掛
// require_authenticated()）。

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function callsMatching(pathFragment: string): Array<[string, RequestInit | undefined]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), c[1] as RequestInit | undefined] as [string, RequestInit | undefined])
    .filter(([u]) => u.includes(pathFragment));
}

describe('TrendChartPanel — authFetch 稽核（WMOM-20260923-10）', () => {
  afterEach(() => {
    clearAuthToken();
  });

  it('已登入（有 token）→ mount 時 GET i18n/tags 與 trend 皆帶 Authorization header', async () => {
    setAuthToken('test-token-trend');
    await renderPanel({ turbineId: 'WT001' });
    const tagCalls = callsMatching('/api/i18n/tags');
    const trendFetchCalls = callsMatching('/api/turbines/WT001/trend');
    expect(tagCalls.length).toBeGreaterThan(0);
    expect(trendFetchCalls.length).toBeGreaterThan(0);
    for (const [, init] of tagCalls) {
      expect(authHeaderOf(init)).toBe('Bearer test-token-trend');
    }
    for (const [, init] of trendFetchCalls) {
      expect(authHeaderOf(init)).toBe('Bearer test-token-trend');
    }
  });

  it('未登入（無 token）→ mount 時 GET i18n/tags 與 trend 皆不帶 Authorization header（過渡期行為不變）', async () => {
    await renderPanel({ turbineId: 'WT001' });
    const tagCalls = callsMatching('/api/i18n/tags');
    const trendFetchCalls = callsMatching('/api/turbines/WT001/trend');
    expect(tagCalls.length).toBeGreaterThan(0);
    expect(trendFetchCalls.length).toBeGreaterThan(0);
    for (const [, init] of tagCalls) {
      expect(authHeaderOf(init)).toBeUndefined();
    }
    for (const [, init] of trendFetchCalls) {
      expect(authHeaderOf(init)).toBeUndefined();
    }
  });
});

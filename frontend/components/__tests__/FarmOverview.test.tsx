/**
 * FarmOverview component render 測試（WMOM-20260604-04，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin` 風場總覽（admin 落地頁，730 行）先前零 component 測試。本檔延續
 * FieldPage / ReportsPage / CostPage 已落地的 render 測試範式（ThemeProvider
 * 包裹 + jest-dom matcher + afterEach cleanup + async act flush），守住 FarmOverview
 * 的核心 UX 契約：
 *
 *   - PageHeader：zh/en 標題 + MOCK 資料源徽章（dataSource=MOCK 才出現）
 *   - HeroStats：風場功率加總 / 運轉中計數 + 全部健康·狀態混合 / 故障中 + 請關注·一切順利 / 平均風速
 *   - 三種檢視模式切換（cards / summary / table）+ aria-pressed
 *   - 點風機卡片 / 列表 row → onSelectTurbine 帶正確 turbine
 *   - summary 模式 fmtPower（<1 MW 顯示 kW）
 *   - table 模式欄位格式化 + 缺值顯示「—」
 *   - TrendCard：預設 24H aria-pressed + 時段切換 + farm-trend fetch 接線 + 收集中/有資料兩態
 *   - 語系：lang=en → 標題 / 表頭英文
 *
 * FarmOverview 純由 props（turbines / settings / lang）驅動，唯二外部依賴是
 * `useTheme`（ThemeProvider 包裹）與 TrendCard 的 `/api/turbines/farm-trend`
 * fetch。fetch 以 stub 取代：beforeEach 預設回**空** trend 資料，讓
 * 模組級 `_trendCache['24H']` 維持空、「資料收集中…」穩定出現。
 *
 * ⚠️ FarmOverview.tsx 的 `_trendCache` 是模組級可變狀態、`cleanup()` 不會清，naïve
 * 寫法會讓「有資料 vs 收集中」測試**跨測試順序 flaky**。對策：所有「有資料 → 渲染
 * 圖表」的驗證都先以空資料 mount（24H 快取維持空）後，再切到 **6H** 並回資料 →
 * 只填充 6H 快取，24H 快取始終為空，故與「無資料」測試彼此獨立、**不依賴執行順序**
 * （`vitest --randomize` / watch 局部重跑皆安全）。
 *
 * 所有測試以 `await renderOverview(...)`（內部 `act(async)` 包 render）flush 掉
 * TrendCard 的 farm-trend fetch effect，避免「state update not wrapped in act()」
 * 警告污染輸出。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within, waitFor } from '@testing-library/react';
import React from 'react';
import FarmOverview from '../FarmOverview';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { downloadBlob } from '../../services/reportingService';
import { setAuthToken, clearAuthToken } from '../../services/authClient';
import {
  TurbineStatus,
  DataSourceType,
  type TurbineData,
  type AppSettings,
} from '../../types';

// ─── fixtures ──────────────────────────────────────────────────────────────

/**
 * TurbineData 工廠：核心欄位全列、不用 `as` 強轉，讓 tsc 守住與 types.ts 對齊
 * （漏必填欄位編譯失敗而非靜默假綠）。table 模式用到的 optional 欄位透過 over 注入。
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

const SETTINGS_MOCK: AppSettings = {
  dataSource: DataSourceType.MOCK,
  opcDa: { server: '', progId: '' },
  modbusTcp: { ip: '', port: 502, slaveId: 1 },
  simulation: { turbineCount: 12, baseWindSpeed: 8, turbulenceIntensity: 0.1 },
};

const SETTINGS_LIVE: AppSettings = {
  ...SETTINGS_MOCK,
  dataSource: DataSourceType.SIMULATION,
};

// ─── 匯出快照：mock downloadBlob（不在 jsdom 真跑 URL.createObjectURL）─────
//
// FarmOverview 直接呼叫 downloadBlob（非像 MonthlyReportPanel 走注入 prop
// `onDownloadPdf` 那樣的依賴反轉），本檔是本 repo 第一支需要 `vi.mock`
// reportingService 模組的測試——只斷言 downloadBlob 有沒有被正確呼叫，不
// 真的觸發瀏覽器下載副作用。
vi.mock('../../services/reportingService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/reportingService')>();
  return { ...actual, downloadBlob: vi.fn() };
});
const downloadBlobMock = downloadBlob as unknown as Mock;

// ─── fetch stub ──────────────────────────────────────────────────────────────

let fetchMock: ReturnType<typeof vi.fn>;

/**
 * 建一個 fetch Response-like。含 `ok` / `status` 對齊真實契約（CostPage.test
 * 的 okJson 同款做法）——目前 TrendCard 未檢查 `r.ok`，但日後若加 `if (!r.ok)`
 * 守衛，這個 stub 仍能正確走 happy path 而非靜默。mock 情境下完整實作 Response
 * 所有欄位沒有意義，故以 `as unknown as Response` 收束。
 */
function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as unknown as Response;
}

/**
 * `/api/export/snapshot` 的 Response-like stub：`handleExportSnapshot` 走
 * `resp.blob()`（不解析 JSON，保留後端原始位元組），故 stub 只需提供 `blob()`。
 */
function blobResponse(payload: unknown, opts: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: opts.ok ?? true,
    status: opts.status ?? 200,
    blob: async () => new Blob([JSON.stringify(payload)], { type: 'application/json' }),
  } as unknown as Response;
}

/**
 * 把所有 pending microtask + 一輪 macrotask drain 乾淨。TrendCard 的 fetch chain
 * 是 fetch → .then(r.json()) → .then(setApiData) 共 2-3 個 microtask tick，
 * 單一 `await Promise.resolve()` 不保證 drain 完整 → 用 `setTimeout(0)` 確保
 * 多層 .then 都 settle 後再 yield。
 */
const flushAsync = (): Promise<void> => new Promise(resolve => setTimeout(resolve, 0));

beforeEach(() => {
  // 預設：farm-trend 回空資料 → _trendCache['24H'] 維持空 → 「資料收集中…」穩定出現。
  fetchMock = vi.fn((url: string | URL) => {
    const u = String(url);
    if (u.includes('/api/turbines/farm-trend')) {
      return Promise.resolve(jsonResponse({ data: [] }));
    }
    if (u.includes('/api/export/snapshot')) {
      return Promise.resolve(blobResponse({ count: 0, data: [] }));
    }
    // 未預期的 URL 直接 reject，避免新增的 fetch 呼叫被靜默吞掉。
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

// ─── render helper ───────────────────────────────────────────────────────────

interface RenderOpts {
  turbines?: TurbineData[];
  settings?: AppSettings;
  lang?: 'en' | 'zh';
}

/**
 * 以 ThemeProvider 包裹 render，並 `act(async)` flush TrendCard 的
 * farm-trend fetch effect（避免 act 警告）。回傳 onSelect spy 供斷言導航接線。
 */
async function renderOverview(opts: RenderOpts = {}) {
  const turbines = opts.turbines ?? [makeTurbine()];
  const settings = opts.settings ?? SETTINGS_MOCK;
  const onSelect = vi.fn();
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <FarmOverview
          turbines={turbines}
          onSelectTurbine={onSelect}
          settings={settings}
          lang={opts.lang}
        />
      </ThemeProvider>,
    );
    // flush farm-trend fetch chain（fetch → json → setApiData）
    await flushAsync();
  });
  return { onSelect, ...utils };
}

// 兩台運轉中風機：power 2.1 + 1.0 = 3.1 MW；wind (8+6)/2 = 7.0 m/s。
const TWO_HEALTHY: TurbineData[] = [
  makeTurbine({ id: 1, name: 'WTG-01', powerOutput: 2.1, windSpeed: 8.0 }),
  makeTurbine({ id: 2, name: 'WTG-02', powerOutput: 1.0, windSpeed: 6.0 }),
];

// ─── PageHeader / 資料源徽章 ──────────────────────────────────────────────────

describe('FarmOverview — PageHeader', () => {
  it('預設語系 zh：顯示繁中標題與風場副標', async () => {
    await renderOverview();
    expect(screen.getByText('早安，營運團隊。')).toBeInTheDocument();
    expect(screen.getByText(/彰化沿海/)).toBeInTheDocument();
  });

  it('lang=en：顯示英文標題', async () => {
    await renderOverview({ lang: 'en' });
    expect(screen.getByText('Good morning, Operator.')).toBeInTheDocument();
  });

  it('dataSource=MOCK：顯示 MOCK 資料源徽章', async () => {
    await renderOverview({ settings: SETTINGS_MOCK });
    expect(screen.getByText('MOCK')).toBeInTheDocument();
  });

  it('dataSource 非 MOCK（SIMULATION）：不顯示 MOCK 徽章', async () => {
    await renderOverview({ settings: SETTINGS_LIVE });
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument();
  });
});

// ─── HeroStats ───────────────────────────────────────────────────────────────

describe('FarmOverview — HeroStats', () => {
  it('全運轉：功率加總 / 平均風速 / 全部健康 / 一切順利', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    // 風場功率 2.1 + 1.0 = 3.1 MW
    expect(screen.getByText('3.1')).toBeInTheDocument();
    // 平均風速 (8 + 6) / 2 = 7.0 m/s
    expect(screen.getByText('7.0')).toBeInTheDocument();
    // 全部運轉 → 全部健康 + 故障 0 → 一切順利
    expect(screen.getByText('全部健康')).toBeInTheDocument();
    expect(screen.getByText('一切順利')).toBeInTheDocument();
  });

  it('有故障：狀態混合 + 故障中計數 + 請關注', async () => {
    const turbines = [
      makeTurbine({ id: 1, name: 'WTG-01', status: TurbineStatus.OPERATING }),
      makeTurbine({ id: 2, name: 'WTG-02', status: TurbineStatus.FAULT }),
    ];
    await renderOverview({ turbines });
    expect(screen.getByText('狀態混合')).toBeInTheDocument();
    expect(screen.getByText('請關注 →')).toBeInTheDocument();
  });
});

// ─── 檢視模式切換 ────────────────────────────────────────────────────────────

describe('FarmOverview — 檢視模式切換', () => {
  it('預設 cards 模式：渲染各風機卡片名稱 + 切換鈕 aria-pressed', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    expect(screen.getByText('WTG-01')).toBeInTheDocument();
    expect(screen.getByText('WTG-02')).toBeInTheDocument();
    // 卡片模式按鈕為 active
    expect(screen.getByRole('button', { name: '卡片' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '列表' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('切到 summary 模式：CompactTile 用 fmtPower（<1 MW 顯示 kW）', async () => {
    const turbines = [makeTurbine({ id: 1, name: 'WTG-01', powerOutput: 0.5 })];
    await renderOverview({ turbines });
    fireEvent.click(screen.getByRole('button', { name: '摘要' }));
    expect(screen.getByRole('button', { name: '摘要' })).toHaveAttribute('aria-pressed', 'true');
    // 0.5 MW → 500 kW
    expect(screen.getByText('500 kW')).toBeInTheDocument();
  });

  it('切到 table 模式：顯示表頭與欄位值，缺值顯示「—」', async () => {
    const turbines = [
      makeTurbine({
        id: 1,
        name: 'WTG-01',
        powerOutput: 2.13,
        genStatorTemp1: 60.5,
        // 刻意不給 vibrationX / yawError → 應顯示「—」
      }),
    ];
    await renderOverview({ turbines });
    fireEvent.click(screen.getByRole('button', { name: '列表' }));
    // 表頭
    expect(screen.getByText('風機')).toBeInTheDocument();
    expect(screen.getByText('狀態')).toBeInTheDocument();
    expect(screen.getByText('功率 MW')).toBeInTheDocument();
    // 針對資料 row 的特定 cell 斷言（而非全頁 '—' 計數魔術數字，後者在新增欄位時
    // 會因「對錯誤理由」失敗）。欄位順序見 TableView cols：
    // 0 name / 1 status / 2 power / 3 wind / 4 rpm / 5 genTemp / 6 vibX / 7 blade / 8 freq / 9 yaw
    const dataRow = screen.getAllByRole('row')[1]; // [0] 是 thead row
    const cells = within(dataRow).getAllByRole('cell');
    expect(cells[2]).toHaveTextContent('2.13'); // 功率 toFixed(2)
    expect(cells[5]).toHaveTextContent('60.5'); // 發電機溫度 toFixed(1)
    // 缺值 optional 欄位逐一回傳「—」
    expect(cells[6]).toHaveTextContent('—'); // vibrationX
    expect(cells[7]).toHaveTextContent('—'); // bladeAngle1
    expect(cells[8]).toHaveTextContent('—'); // cnvGenFreq
    expect(cells[9]).toHaveTextContent('—'); // yawError
  });
});

// ─── onSelectTurbine 導航接線 ─────────────────────────────────────────────────

describe('FarmOverview — onSelectTurbine 接線', () => {
  it('cards 模式點卡片 → 帶該 turbine 呼叫 onSelectTurbine', async () => {
    const { onSelect } = await renderOverview({ turbines: TWO_HEALTHY });
    fireEvent.click(screen.getByText('WTG-02'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({ id: 2, name: 'WTG-02' });
  });

  it('table 模式點 row → 帶該 turbine 呼叫 onSelectTurbine', async () => {
    const { onSelect } = await renderOverview({ turbines: TWO_HEALTHY });
    fireEvent.click(screen.getByRole('button', { name: '列表' }));
    fireEvent.click(screen.getByText('WTG-01'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({ id: 1, name: 'WTG-01' });
  });
});

// ─── TrendCard ───────────────────────────────────────────────────────────────

describe('FarmOverview — TrendCard', () => {
  it('預設 24H：aria-pressed 正確 + mount 觸發 farm-trend fetch（range=1d）', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    expect(screen.getByRole('button', { name: '時段 24H' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '時段 1H' })).toHaveAttribute('aria-pressed', 'false');
    // mount 即抓 farm-trend（24H → range=1d）
    const calledUrls = fetchMock.mock.calls.map(c => String(c[0]));
    expect(calledUrls.some(u => u.includes('/api/turbines/farm-trend') && u.includes('range=1d'))).toBe(true);
  });

  it('切換時段 1H：aria-pressed 翻轉到 1H', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    // 1H 走 live accumulator（有 `if (range === '1H') return` 守衛、不發 fetch），
    // setLiveData 同步在 fireEvent 的 act 內 flush，無 act 警告。
    fireEvent.click(screen.getByRole('button', { name: '時段 1H' }));
    expect(screen.getByRole('button', { name: '時段 1H' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '時段 24H' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('切換時段 6H：發送 range=12h 的 fetch', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    fetchMock.mockClear();
    // 切到非 1H 時段會啟動新 fetch effect → 包 act 等 chain settle，避免 act 警告。
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '時段 6H' }));
      await flushAsync();
    });
    const urls = fetchMock.mock.calls.map(c => String(c[0]));
    expect(urls.some(u => u.includes('range=12h'))).toBe(true);
  });

  it('切換時段 7D：發送 range=1d 的 fetch（後端僅支援至 1d，刻意 cap）', async () => {
    // 守住 RANGE_TO_API['7D'] === '1d' 的「刻意映射」契約：後端 farm-trend 只接受
    // 5m/1h/12h/1d，無 7d；若有人改成 range=7d，後端會 fallback 成 5m → 7D 視圖壞掉。
    await renderOverview({ turbines: TWO_HEALTHY });
    fetchMock.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '時段 7D' }));
      await flushAsync();
    });
    const urls = fetchMock.mock.calls.map(c => String(c[0]));
    expect(urls.some(u => u.includes('range=1d'))).toBe(true);
    // 確認沒有送出後端不認得的 range=7d
    expect(urls.some(u => u.includes('range=7d'))).toBe(false);
  });

  it('trend 無資料：顯示「資料收集中…」', async () => {
    await renderOverview({ turbines: TWO_HEALTHY });
    expect(screen.getByText('資料收集中…')).toBeInTheDocument();
  });
});

// ─── 語系 ────────────────────────────────────────────────────────────────────

describe('FarmOverview — 語系', () => {
  it('lang=en：table 表頭顯示英文', async () => {
    await renderOverview({ turbines: TWO_HEALTHY, lang: 'en' });
    fireEvent.click(screen.getByRole('button', { name: 'Table' }));
    expect(screen.getByText('Turbine')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Power MW')).toBeInTheDocument();
  });
});

// ─── TrendCard 有資料 ────────────────────────────────────────────────────────

describe('FarmOverview — TrendCard 有資料', () => {
  it('farm-trend 回資料：「資料收集中…」消失（改渲染圖表）', async () => {
    // FarmOverview.tsx 的 _trendCache 是模組級可變狀態、cleanup 不會清。為避免
    // 跨測試順序污染（讓本測試與「無資料」測試彼此獨立、不依賴執行順序）：
    //   1. 先以 beforeEach 預設（空資料）mount → 24H 快取維持空。
    //   2. 之後才切換 fetch 為「回資料」並點到 *6H*（非 24H）→ 只填充 6H 快取，
    //      24H 快取始終為空，故無論本測試先跑或後跑都不影響「無資料」測試。
    await renderOverview({ turbines: TWO_HEALTHY });
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes('/api/turbines/farm-trend')) {
        return Promise.resolve(
          jsonResponse({
            data: [
              { timestamp: '2026-06-04T00:00:00Z', totalPower: 18.2 },
              { timestamp: '2026-06-04T01:00:00Z', totalPower: 20.5 },
              { timestamp: '2026-06-04T02:00:00Z', totalPower: 19.1 },
            ],
          }),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${u}`));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '時段 6H' }));
      await flushAsync();
    });
    expect(screen.queryByText('資料收集中…')).not.toBeInTheDocument();
  });
});

// ─── 匯出風場快照（WMOM-20260507-02 sub-task a）──────────────────────────────

describe('FarmOverview — 匯出風場快照', () => {
  it('點擊匯出 → 打 GET /api/export/snapshot，成功後以 Blob + 日期檔名觸發下載', async () => {
    await renderOverview();
    const btn = screen.getByRole('button', { name: '匯出報告' });
    await act(async () => {
      fireEvent.click(btn);
      await flushAsync();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/export/snapshot'),
      expect.any(Object),
    );
    expect(downloadBlobMock).toHaveBeenCalledTimes(1);
    const [blobArg, filenameArg] = downloadBlobMock.mock.calls[0] as [Blob, string];
    expect(blobArg).toBeInstanceOf(Blob);
    expect(filenameArg).toMatch(/^farm-snapshot-\d{4}-\d{2}-\d{2}\.json$/);
  });

  it('已登入（有 token）→ 走 authFetch 帶 Authorization header（後端 require_authenticated 閘門）', async () => {
    // 驗證 handleExportSnapshot 真的走 authFetch 而非裸 fetch：`expect.any(Object)`
    // 無法區分兩者（authFetch 內部仍是包一層 fetch），必須實際檢查 header 內容。
    setAuthToken('test-token-abc');
    try {
      await renderOverview();
      fireEvent.click(screen.getByRole('button', { name: '匯出報告' }));
      await act(async () => {
        await flushAsync();
      });
      const exportCall = fetchMock.mock.calls.find(([url]: [string]) =>
        String(url).includes('/api/export/snapshot'),
      );
      expect(exportCall).toBeDefined();
      const [, init] = exportCall as [string, RequestInit];
      expect((init.headers as Record<string, string>).Authorization).toBe('Bearer test-token-abc');
    } finally {
      // 避免污染同檔案後續測試（本檔第一支真正呼叫 setAuthToken 的測試）。
      clearAuthToken();
    }
  });

  it('下載期間按鈕 disabled，完成後恢復可點擊', async () => {
    let resolveFetch!: (r: Response) => void;
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes('/api/turbines/farm-trend')) {
        return Promise.resolve(jsonResponse({ data: [] }));
      }
      if (u.includes('/api/export/snapshot')) {
        return new Promise<Response>(res => { resolveFetch = res; });
      }
      return Promise.reject(new Error(`Unexpected fetch: ${u}`));
    });
    await renderOverview();
    fireEvent.click(screen.getByRole('button', { name: '匯出報告' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '匯出報告' })).toBeDisabled();
    });
    await act(async () => {
      resolveFetch(blobResponse({ count: 0, data: [] }));
      await flushAsync();
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '匯出報告' })).toBeEnabled();
    });
  });

  it('後端回非 2xx → console.error 記錄失敗、不呼叫 downloadBlob、按鈕恢復可點擊', async () => {
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes('/api/turbines/farm-trend')) {
        return Promise.resolve(jsonResponse({ data: [] }));
      }
      if (u.includes('/api/export/snapshot')) {
        return Promise.resolve(blobResponse({}, { ok: false, status: 500 }));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${u}`));
    });
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    await renderOverview();
    const btn = screen.getByRole('button', { name: '匯出報告' });
    await act(async () => {
      fireEvent.click(btn);
      await flushAsync();
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith('匯出風場快照失敗', expect.any(Error));
    expect(downloadBlobMock).not.toHaveBeenCalled();
    expect(btn).toBeEnabled();
    consoleErrorSpy.mockRestore();
  });
});

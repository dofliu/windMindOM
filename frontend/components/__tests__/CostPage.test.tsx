/**
 * CostPage component render 測試（WMOM-20260604-03，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/cost` 成本模型主入口先前只有 useCostData hook 的單元測試，
 * 頁面層（dataset 自動接線 / 4 panel run / loading·error 態 / KPI 格式化 /
 * DatasetMetaBadge / 語系）零覆蓋。本檔延續 FieldPage / ReportsPage 已落地的
 * render 測試範式（mock hook + ThemeProvider 包裹 + jest-dom matcher +
 * afterEach cleanup），守住 CostPage 的 UX 契約：
 *
 *   - mount 自動接線：dataset effect 觸發 forecast.run + 其他三個 reset
 *   - dataset 切換：選 farm → forecast.run 帶新 dataset + 其他 reset
 *   - farms 載入：/api/farms resolve → dataset selector 出現 farm 選項
 *   - Run scenario：header 按鈕 → 4 個 run 帶正確 params
 *   - 各 panel run 按鈕：Forecast / LCOE / MonteCarlo / VarFluct
 *   - loading / error 態：按鈕 disabled + 計算中… / ErrorBox
 *   - KPI strip 格式化：data present → 正確格式；無資料顯示「—」
 *   - DatasetMetaBadge：meta source + farm_id → 對應繁中標籤
 *   - 語系：localStorage en → 標題 / 按鈕英文
 *
 * recharts 以輕量 stub 取代（避免 jsdom 0-width 圖表噪音 + 讓 data-present
 * 渲染穩定）。useCostData 全 mock；global.fetch 路由 /api/farms 與 /api/i18n
 * （未預期的 URL 直接 reject，避免靜默吞掉新 API 呼叫）。
 *
 * 所有測試以 `await renderCost(...)`（內部 `act(async)` 包 render）flush 掉
 * CostPage farms fetch 與 useI18n i18n fetch 兩條非同步 effect，避免「state
 * update not wrapped in act()」警告污染輸出。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { setAuthToken, clearAuthToken } from '../../services/authClient';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import React from 'react';
import CostPage from '../CostPage';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { useCostData } from '../../hooks/useCostData';
import type {
  CostForecastRequest,
  CostForecastResponse,
  LCOERequest,
  LCOEResponse,
  MonteCarloRequest,
  MonteCarloResponse,
  VarFluctRequest,
  VarFluctResponse,
  SeasonalCostBreakdown,
  DatasetMeta,
} from '../../services/costService';

vi.mock('../../hooks/useCostData');

// recharts：圖表元件全 stub 成 marker div，測試聚焦 CostPage 路由 / 接線 / KPI 文字，
// 不被 ResponsiveContainer 在 jsdom 下 0 寬度的渲染細節干擾。
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    BarChart: Stub,
    LineChart: Stub,
    Bar: Stub,
    Line: Stub,
    Cell: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    Legend: Stub,
  };
});

const mockedUseCostData = useCostData as unknown as Mock;

// ─── useCostData mock 工廠 ─────────────────────────────────────────────────
//   每個 endpoint 是一個 AsyncState：data / loading / error / run / reset。
//   run / reset 是 vi.fn spy，供斷言 CostPage 的接線。

type CostReturn = ReturnType<typeof useCostData>;

// 單一 endpoint 的 AsyncState 形狀，與 useCostData 內部 AsyncState<TData, TReq> 完全對齊
// （含 run 的 `(req?: TReq)` 參數型別）；如此 makeCost 回傳結構式滿足 CostReturn，
// 任一欄位 / run 簽章漂移 tsc 即編譯失敗，而非靜默假綠。
interface Slice<TData, TReq> {
  data: TData | null;
  loading: boolean;
  error: string | null;
  run: (req?: TReq) => Promise<void>;
  reset: () => void;
}

function slice<TData, TReq>(over: Partial<Slice<TData, TReq>> = {}): Slice<TData, TReq> {
  return {
    data: null,
    loading: false,
    error: null,
    run: vi.fn(),
    reset: vi.fn(),
    ...over,
  };
}

function makeCost(over: {
  forecast?: Partial<Slice<CostForecastResponse, CostForecastRequest>>;
  lcoe?: Partial<Slice<LCOEResponse, LCOERequest>>;
  monteCarlo?: Partial<Slice<MonteCarloResponse, MonteCarloRequest>>;
  varFluct?: Partial<Slice<VarFluctResponse, VarFluctRequest>>;
} = {}): CostReturn {
  return {
    forecast: slice<CostForecastResponse, CostForecastRequest>(over.forecast),
    lcoe: slice<LCOEResponse, LCOERequest>(over.lcoe),
    monteCarlo: slice<MonteCarloResponse, MonteCarloRequest>(over.monteCarlo),
    varFluct: slice<VarFluctResponse, VarFluctRequest>(over.varFluct),
  };
}

// ─── 資料 fixtures（型別嚴格，不用 as 強轉）─────────────────────────────────

function meta(source: DatasetMeta['source']): DatasetMeta {
  return {
    dataset_used: 'k13',
    farm_id: 'farm-001',
    is_fallback: false,
    source,
    warning: null,
  };
}

function season(s: SeasonalCostBreakdown['season']): SeasonalCostBreakdown {
  return {
    season: s,
    corrective_wt_material: 1e6,
    corrective_wt_labour: 5e5,
    corrective_wt_equipment: 3e5,
    corrective_wt_mob: 2e5,
    corrective_wt_revenue_loss: 4e5,
    corrective_wt_downtime: 10,
    corrective_bop_total: 1e5,
    preventive_total: 6e5,
    preventive_material: 2e5,
    preventive_revenue_loss: 1e5,
    preventive_downtime: 5,
    fixed_cost: 3e5,
    total_effort: 3.5e6,
    total_downtime: 15,
  };
}

const FORECAST: CostForecastResponse = {
  availability_time: 0.965,
  availability_energy: 0.972,
  total_revenue_loss: 1.2e6,
  total_repair_cost: 8e6,
  total_effort: 14_000_000, // KPI Total Cost → €14.0M
  cost_per_kwh: 0.0123,
  seasonal: {
    winter: season('winter'),
    spring: season('spring'),
    summer: season('summer'),
    autumn: season('autumn'),
  },
  dataset_meta: meta('farm_overlay'),
};

// MonteCarlo 的 deterministic 用「不同」total_effort（13_000_000），避免它的
// 「確定值」SmallStat 與 forecast 的 €14.0M 同字串，讓 KPI 計數可精確斷言。
const FORECAST_DETERMINISTIC: CostForecastResponse = { ...FORECAST, total_effort: 13_000_000 };

const LCOE: LCOEResponse = {
  lcoe: 64.27, // KPI LCOE → '64.27'（唯一：panel 為 '64.27 EUR/MWh' 單一節點）
  capex_total: 525_000_000, // KPI CapEx → €525.0M
  opex_total_npv: 180_000_000,
  energy_total_npv: 9_000_000,
  total_cost_npv: 705_000_000,
  dataset_meta: meta('k13_baseline'),
};

const MONTE_CARLO: MonteCarloResponse = {
  n_simulations: 1000,
  seed: 42,
  deterministic: FORECAST_DETERMINISTIC,
  percentiles: {
    cost: { p10: 12_000_000, p50: 14_500_000, p90: 18_000_000, mean: 15_000_000, std: 2_000_000 },
    availability_time: { p10: 0.95, p50: 0.96, p90: 0.97, mean: 0.96, std: 0.01 },
    availability_energy: { p10: 0.96, p50: 0.97, p90: 0.98, mean: 0.97, std: 0.01 },
  },
  dataset_meta: meta('k13_baseline'),
};

const VARFLUCT: VarFluctResponse = {
  yearly: [
    {
      year: 1,
      failure_multiplier: 1.2,
      cost_escalation_factor: 1.0,
      kwh_price: 0.1,
      capacity_factor_multiplier: 1.0,
      total_repair_cost: 8e6,
      total_effort: 13_000_000,
      revenue_loss: 1e6,
      fixed: 3e5,
      availability_time: 0.96,
      availability_energy: 0.97,
    },
  ],
  summary: {
    npv_total_effort: 210_000_000, // KPI NPV → €210.0M
    npv_total_repair: 120_000_000,
    npv_total_revenue_loss: 30_000_000,
    avg_annual_effort: 14_300_000, // KPI Avg/yr → €14.3M（與其他 KPI 字串不撞）
    min_year_effort: 11_000_000,
    max_year_effort: 19_000_000,
    min_year_index: 2,
    max_year_index: 17,
    lifetime_availability_time: 0.95,
    lifetime_availability_energy: 0.96,
  },
  dataset_meta: meta('registry_derived'),
};

// ─── global.fetch 路由（/api/farms + /api/i18n/tags/all）──────────────────

const fetchMock = vi.fn();

function okJson(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

const FARMS_BODY = {
  farms: [
    {
      farm_id: 'farm-001',
      name: '彰化外海一期',
      turbine_count: 21,
      turbine_spec: { rated_power_kw: 8000 },
    },
  ],
};

/** 已知端點回傳對應 body；未知 URL 回 null → fetchMock 改 reject（不靜默吞掉新 API 呼叫）。 */
function routeFetch(url: string): Response | null {
  if (url.includes('/api/farms')) return okJson(FARMS_BODY);
  if (url.includes('/api/i18n')) return okJson({});
  return null;
}

// ─── render helper ─────────────────────────────────────────────────────────

async function renderCost(
  lang: 'zh' | 'en' = 'zh',
  cost: CostReturn = makeCost(),
): Promise<CostReturn> {
  // CostPage 經 useI18n 讀 localStorage（不吃 prop），故在 render 前設定語系。
  localStorage.setItem('windFarmLang', lang);
  mockedUseCostData.mockReturnValue(cost);
  // act(async) 包 render → flush farms fetch + useI18n fetch 兩條 effect 的 microtask，
  // 避免測試體結束後 setFarms / setTagLabels 觸發 act() 警告。
  await act(async () => {
    render(
      <ThemeProvider>
        <CostPage />
      </ThemeProvider>,
    );
  });
  return cost;
}

describe('CostPage 成本模型主入口', () => {
  beforeEach(() => {
    mockedUseCostData.mockReset();
    fetchMock.mockReset();
    fetchMock.mockImplementation((input: string) => {
      const res = routeFetch(String(input));
      return res
        ? Promise.resolve(res)
        : Promise.reject(new Error(`Unexpected fetch in test: ${String(input)}`));
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  // ── mount 自動接線 ────────────────────────────────────────────────────

  it('mount 時 dataset effect 觸發 forecast.run({dataset:k13}) + 其他三個 reset', async () => {
    const cost = await renderCost();
    expect(cost.forecast.run).toHaveBeenCalledWith({ dataset: 'k13' });
    expect(cost.lcoe.reset).toHaveBeenCalledTimes(1);
    expect(cost.monteCarlo.reset).toHaveBeenCalledTimes(1);
    expect(cost.varFluct.reset).toHaveBeenCalledTimes(1);
  });

  it('預設渲染：標題 + dataset selector 預設 K13 + 4 panel run 按鈕在場', async () => {
    await renderCost();
    expect(screen.getByText('成本模型')).toBeInTheDocument();
    const selector = screen.getByRole('combobox', { name: '資料集' });
    expect(selector).toHaveValue('k13');
    expect(screen.getByRole('button', { name: '執行情境' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '執行預測' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '計算 LCOE' })).toBeInTheDocument();
  });

  // ── farms 載入 + dataset 切換 ──────────────────────────────────────────

  it('farms fetch resolve 後 dataset selector 出現 farm 選項', async () => {
    await renderCost();
    // farms effect 已於 renderCost 的 act flush 完成 → 選項以 farm 名 + 額定功率標籤呈現。
    expect(screen.getByRole('option', { name: /彰化外海一期/ })).toBeInTheDocument();
  });

  it('切換 dataset 到 farm → forecast.run 帶新 dataset + 其他三個 reset', async () => {
    const cost = await renderCost();

    (cost.forecast.run as Mock).mockClear();
    (cost.lcoe.reset as Mock).mockClear();
    (cost.monteCarlo.reset as Mock).mockClear();
    (cost.varFluct.reset as Mock).mockClear();

    fireEvent.change(screen.getByRole('combobox', { name: '資料集' }), {
      target: { value: 'farm:farm-001' },
    });

    expect(cost.forecast.run).toHaveBeenCalledWith({ dataset: 'farm:farm-001' });
    expect(cost.lcoe.reset).toHaveBeenCalledTimes(1);
    expect(cost.monteCarlo.reset).toHaveBeenCalledTimes(1);
    expect(cost.varFluct.reset).toHaveBeenCalledTimes(1);
  });

  // ── Run scenario（全跑）+ 各 panel run 接線 ────────────────────────────

  it('Run scenario 按鈕 → 4 個 endpoint run 帶正確 params', async () => {
    const cost = await renderCost();
    (cost.forecast.run as Mock).mockClear(); // 清掉 mount effect 那次

    fireEvent.click(screen.getByRole('button', { name: '執行情境' }));

    expect(cost.forecast.run).toHaveBeenCalledWith({ dataset: 'k13' });
    expect(cost.lcoe.run).toHaveBeenCalledWith({
      dataset: 'k13',
      capex_per_kw: 1250,
      discount_rate: 0.08,
    });
    expect(cost.monteCarlo.run).toHaveBeenCalledWith({
      dataset: 'k13',
      n_simulations: 1000,
      seed: 42,
    });
    expect(cost.varFluct.run).toHaveBeenCalledWith({ dataset: 'k13' });
  });

  it('Forecast panel run 按鈕 → forecast.run({dataset})', async () => {
    const cost = await renderCost();
    (cost.forecast.run as Mock).mockClear();
    fireEvent.click(screen.getByRole('button', { name: '執行預測' }));
    expect(cost.forecast.run).toHaveBeenCalledWith({ dataset: 'k13' });
  });

  it('LCOE panel 計算按鈕 → lcoe.run 帶 capex / discount 預設值', async () => {
    const cost = await renderCost();
    fireEvent.click(screen.getByRole('button', { name: '計算 LCOE' }));
    expect(cost.lcoe.run).toHaveBeenCalledWith({
      dataset: 'k13',
      capex_per_kw: 1250,
      discount_rate: 0.08,
    });
  });

  it('MonteCarlo panel 執行按鈕 → monteCarlo.run 帶 nSim / seed 預設值', async () => {
    const cost = await renderCost();
    // MonteCarlo 按鈕 accessible name 為精確 '執行'（VarFluct 是 '執行 20 年模擬'，
    // ForecastPanel 是 '執行預測'，header 是 '執行情境'）→ getByRole 精確匹配只命中 MonteCarlo。
    fireEvent.click(screen.getByRole('button', { name: '執行' }));
    expect(cost.monteCarlo.run).toHaveBeenCalledWith({
      dataset: 'k13',
      n_simulations: 100,
      seed: 42,
    });
  });

  it('VarFluct panel run 按鈕 → varFluct.run({dataset})', async () => {
    const cost = await renderCost();
    fireEvent.click(screen.getByRole('button', { name: '執行 20 年模擬' }));
    expect(cost.varFluct.run).toHaveBeenCalledWith({ dataset: 'k13' });
  });

  // ── loading / error 態 ─────────────────────────────────────────────────

  it('forecast.loading=true → 預測按鈕 disabled + 顯示「計算中…」', async () => {
    await renderCost('zh', makeCost({ forecast: { loading: true } }));
    const btn = screen.getByRole('button', { name: '執行預測' });
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('計算中…');
  });

  it('forecast.error → ErrorBox 顯示錯誤訊息', async () => {
    await renderCost('zh', makeCost({ forecast: { error: '資料集載入失敗' } }));
    expect(screen.getByText(/資料集載入失敗/)).toBeInTheDocument();
  });

  // ── KPI strip 格式化 ───────────────────────────────────────────────────

  it('無任何資料 → KPI strip 6 個卡片全顯示「—」', async () => {
    await renderCost();
    // KpiStrip 固定 6 個 item，無資料時每個都是 '—'，總數精確為 6。
    expect(screen.getAllByText('—')).toHaveLength(6);
  });

  it('forecast / lcoe / varFluct / monteCarlo data present → KPI 顯示格式化數值', async () => {
    await renderCost(
      'zh',
      makeCost({
        forecast: { data: FORECAST },
        lcoe: { data: LCOE },
        monteCarlo: { data: MONTE_CARLO },
        varFluct: { data: VARFLUCT },
      }),
    );
    // LCOE KPI：64.27（兩位小數）—— 此值唯一（panel 內為 '64.27 EUR/MWh' 單一節點，
    // 與 KPI Stat 的精確文字 '64.27' 不同），故 getByText 可專指 KPI strip。
    expect(screen.getByText('64.27')).toBeInTheDocument();
    // money 格式（fmtMoney €M）：KPI 與「對應且唯一」的 panel SmallStat 由同一份 hook data
    // 驅動，fixture 已調成每個字串「恰好出現 2 次」（KPI + 對應 panel），精確斷言 → KPI strip
    // 被移除時計數降為 1 即會失敗（比 length>=1 強）。
    expect(screen.getAllByText('€14.0M')).toHaveLength(2); // Total Cost + Forecast Total
    expect(screen.getAllByText('€210.0M')).toHaveLength(2); // NPV + VarFluct NPV
    expect(screen.getAllByText('€14.5M')).toHaveLength(2); // MC P50 + MonteCarlo P50
    expect(screen.getAllByText('€525.0M')).toHaveLength(2); // CapEx + LCOE CAPEX
  });

  it('forecast.data 的 DatasetMetaBadge 顯示對應繁中標籤 + farm_id（farm_overlay → 風場覆寫 · farm-001）', async () => {
    await renderCost('zh', makeCost({ forecast: { data: FORECAST } }));
    expect(screen.getByText(/風場覆寫 · farm-001/)).toBeInTheDocument();
  });

  // ── 語系 ───────────────────────────────────────────────────────────────

  it('localStorage lang=en → 標題與按鈕顯示英文', async () => {
    await renderCost('en');
    expect(screen.getByText('Cost Model')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run scenario' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run forecast' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run lifetime sim' })).toBeInTheDocument();
  });
});

// ─── authFetch 稽核（WMOM-20260923-10）──────────────────────────────────────
//
// 上方既有測試用 routeFetch 只比對 URL 前綴，對「裸 fetch vs authFetch」不敏感
// （同款根因見 WMOM-20260923-07/-09/-20260924-01/-02/-03）。故另補這組直接檢查
// `Authorization` header 內容的專測，鎖住本次修復（唯一一處 fetch 呼叫：mount 時
// GET /api/farms，讀取端點、後端掛 require_authenticated()）。

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function farmsGetCalls(): Array<[string, RequestInit | undefined]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), c[1] as RequestInit | undefined] as [string, RequestInit | undefined])
    .filter(([u]) => u.includes('/api/farms'));
}

describe('CostPage — authFetch 稽核（WMOM-20260923-10）', () => {
  beforeEach(() => {
    mockedUseCostData.mockReset();
    mockedUseCostData.mockReturnValue(makeCost());
    fetchMock.mockReset();
    fetchMock.mockImplementation((input: string) => {
      const res = routeFetch(String(input));
      return res
        ? Promise.resolve(res)
        : Promise.reject(new Error(`Unexpected fetch in test: ${String(input)}`));
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    clearAuthToken();
  });

  it('已登入（有 token）→ mount 時 GET /api/farms 帶 Authorization header', async () => {
    setAuthToken('test-token-costpage');
    await renderCost();
    const calls = farmsGetCalls();
    expect(calls).toHaveLength(1);
    expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-costpage');
  });

  it('未登入（無 token）→ mount 時 GET /api/farms 不帶 Authorization header（過渡期行為不變）', async () => {
    const calls0 = farmsGetCalls();
    expect(calls0).toHaveLength(0);
    await renderCost();
    const calls = farmsGetCalls();
    expect(calls).toHaveLength(1);
    expect(authHeaderOf(calls[0][1])).toBeUndefined();
  });
});

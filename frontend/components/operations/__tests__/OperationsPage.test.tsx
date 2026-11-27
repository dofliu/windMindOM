/**
 * 營運頁（WMOM-20261127-01）render 測試。
 *
 * 守住的契約：
 *   - 收支與可用率：先不帶時間問一次（後端用風場時鐘的最近 30 天），其他區間從回傳的 end 往前算；
 *     金額 / 電量 / 可用率的格式；每台機組一列；費率來源；閉環沒開的提醒；403 的說明
 *   - 自動運轉：讀設定、改一個數字＋開關、儲存時送完整的設定（畫面沒列的欄位沿用）；不是數字時不送
 *   - 實測風況：目前的風況；匯入（讀檔的內容、名稱預設檔名、摘要與警告）；套用（對時、播完、起點）；
 *     回到模型；刪除
 *
 * global.fetch 依 URL 與 method 路由，沒預期的呼叫直接失敗。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import OperationsPage from '../OperationsPage';
import { ThemeProvider } from '../../../theme/ThemeProvider';

type Handler = (url: URL, init: RequestInit) => { status?: number; body: unknown };

let routes: Record<string, Handler>;
let calls: { method: string; url: URL; body: unknown }[];

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  calls = [];
  routes = {};
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      const method = (init.method ?? 'GET').toUpperCase();
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
      calls.push({ method, url, body });
      const handler = routes[`${method} ${url.pathname}`];
      if (!handler) return json(404, { detail: `unexpected ${method} ${url.pathname}` });
      const out = handler(url, init);
      return json(out.status ?? 200, out.body);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const END = '2026-11-29T14:00:00.000000+00:00';

const FINANCE = {
  start: '2026-10-30T14:00:00.000000+00:00',
  end: END,
  enabled: true,
  rates: { farm_id: 'legacy', currency: 'EUR', kwh_price: 0.13, hourly_labour_rate: 83.33, source: 'k13_fallback' },
  energy_kwh: 473225.7,
  revenue: 61519.34,
  lost_revenue: { planned: 0, unplanned: 4333.57 },
  expenses: { material: 17000, labour: 10333.35, equipment: 0, total: 27333.35 },
  net: 34185.99,
  turbines: [
    { turbine_id: 'WT001', energy_kwh: 41127.5, revenue: 5346.58, lost_planned: 0, lost_unplanned: 0 },
    { turbine_id: 'WT005', energy_kwh: 24656.6, revenue: 3205.36, lost_planned: 0, lost_unplanned: 1418.87 },
  ],
};

const metrics = (over: Record<string, unknown> = {}) => ({
  recorded_hours: 73,
  producing_hours: 70,
  ready_hours: 0,
  planned_downtime_hours: 0,
  unplanned_downtime_hours: 0,
  energy_kwh: 0,
  lost_planned_kwh: 0,
  lost_unplanned_kwh: 0,
  time_availability: 0.923,
  energy_availability: 0.912,
  ...over,
});

const AVAILABILITY = {
  start: FINANCE.start,
  end: END,
  enabled: true,
  farm: metrics(),
  turbines: [
    metrics({ turbine_id: 'WT001', time_availability: 1 }),
    metrics({ turbine_id: 'WT005', time_availability: 0.78, unplanned_downtime_hours: 15.8 }),
  ],
};

async function renderPage(lang: 'zh' | 'en' = 'zh') {
  await act(async () => {
    render(
      <ThemeProvider>
        <OperationsPage lang={lang} />
      </ThemeProvider>,
    );
  });
}

// ─── 收支與可用率 ──────────────────────────────────────────────────────────

describe('收支與可用率', () => {
  beforeEach(() => {
    routes['GET /api/operations/finance'] = () => ({ body: FINANCE });
    routes['GET /api/operations/availability'] = () => ({ body: AVAILABILITY });
  });

  it('第一次不帶時間，可用率用同一個時間窗；金額、電量、可用率、每台機組', async () => {
    await renderPage();
    await screen.findByText('61,519.34');
    const finance = calls.filter(c => c.url.pathname === '/api/operations/finance');
    expect(finance[0].url.search).toBe('');
    const avail = calls.find(c => c.url.pathname === '/api/operations/availability')!;
    expect(avail.url.searchParams.get('start')).toBe(FINANCE.start);
    expect(avail.url.searchParams.get('end')).toBe(END);
    expect(screen.getByText('473.2 MWh')).toBeInTheDocument();
    expect(screen.getByText('34,185.99')).toBeInTheDocument();
    expect(screen.getByText('92.3%')).toBeInTheDocument();
    expect(screen.getByText('WT005')).toBeInTheDocument();
    expect(screen.getByText('78.0%')).toBeInTheDocument();
    expect(screen.getByText('15.8')).toBeInTheDocument();
    expect(screen.getByText(/K13 參考值/)).toBeInTheDocument();
  });

  it('固定成本的明細；工單工時已含在年薪裡、不另算', async () => {
    routes['GET /api/operations/finance'] = () => ({
      body: {
        ...FINANCE,
        expenses: { material: 17000, labour: 4931.51, equipment: 64410.96, total: 86342.47 },
        fixed_costs: {
          days: 3.0, staff: 2465.75, equipment: 410.96, total: 2876.71, technicians: 5, yearly_salary: 60000,
          staff_per_year: 300000, equipment_per_year: 50000,
          equipment_items: [{ name: '工程車與工具', per_year: 50000 }], source: 'onshore_default',
        },
        work_order_labour: { amount: 10333.35, counted: false },
      },
    });
    await renderPage();
    const box = await screen.findByTestId('fixed-costs');
    expect(box).toHaveTextContent('固定成本：攤 3.0 天運轉');
    expect(box).toHaveTextContent('5 位技師 × 年薪 60,000.00');
    expect(box).toHaveTextContent('工程車與工具');
    expect(box).toHaveTextContent('不另算');
    expect(screen.getByText(/固定成本：陸域假設值/)).toBeInTheDocument();
  });

  it('固定成本只有一部分是風場的設定；缺了設備明細也照樣顯示', async () => {
    routes['GET /api/operations/finance'] = () => ({
      body: {
        ...FINANCE,
        fixed_costs: {
          days: 1.5, staff: 900, equipment: 0, total: 900, technicians: 6, yearly_salary: 60000,
          staff_per_year: 360000, equipment_per_year: 0, source: 'mixed',
        },
        work_order_labour: { amount: 200, counted: false },
      },
    });
    await renderPage();
    const box = await screen.findByTestId('fixed-costs');
    expect(box).toHaveTextContent('6 位技師 × 年薪 60,000.00');
    expect(screen.getByText(/固定成本：部分用陸域假設值/)).toBeInTheDocument();
  });

  it('其他區間從風場時鐘的 end 往前算', async () => {
    await renderPage();
    await screen.findByText('61,519.34');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '最近 7 天' }));
    });
    const last = calls.filter(c => c.url.pathname === '/api/operations/finance').at(-1)!;
    expect(last.url.searchParams.get('end')).toBe(END);
    expect(Date.parse(END) - Date.parse(last.url.searchParams.get('start')!)).toBe(7 * 86400_000);
  });

  it('閉環沒開時提醒；不是主管時說明要主管登入', async () => {
    routes['GET /api/operations/finance'] = () => ({ body: { ...FINANCE, enabled: false } });
    await renderPage();
    expect(await screen.findByText(/運維閉環沒有開/)).toBeInTheDocument();
    cleanup();
    routes['GET /api/operations/finance'] = () => ({ status: 403, body: { detail: 'forbidden' } });
    await renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('主管');
  });
});

// ─── 自動運轉 ─────────────────────────────────────────────────────────────

const GENERATOR = {
  config: {
    enabled: false,
    mean_days_between_faults: 30,
    scenario_weights: { blade_icing: 0, bearing_wear: 2 },
    turbine_weights: {},
    wear_gain: 4,
    min_hours_to_full: 0.5,
    max_hours_to_full: 48,
    max_active_per_turbine: 1,
    seed: 20261126,
    fatigue_reference: 0.1,
    fouling_reference: 0.02,
  },
  generated: 15,
  scenarios: { bearing_wear: 1 },
};

const CREW = {
  config: {
    enabled: false,
    response_minutes: 120,
    repair_minutes: 240,
    inspection_minutes: 240,
    crews: 2,
    close_after_finish: true,
  },
};

const PLAN = {
  config: { enabled: false, interval_days: 182 },
  clock: '2026-03-01T08:00:00.000000+00:00',
  schedules: [
    {
      turbine_id: 'WT001',
      active: true,
      next_due_at: '2026-03-14T08:00:00.000000+00:00',
      last_spawned_at: null,
      last_work_order_id: null,
      overdue: true,
    },
    {
      turbine_id: 'WT002',
      active: false,
      next_due_at: '2026-03-27T08:00:00.000000+00:00',
      last_spawned_at: '2025-09-27T08:00:00.000000+00:00',
      last_work_order_id: 'wo-2',
      overdue: false,
    },
  ],
};

describe('自動運轉', () => {
  beforeEach(() => {
    routes['GET /api/operations/inspection-plan'] = () => ({ body: PLAN });
    routes['PUT /api/operations/inspection-plan'] = (_u, init) => ({
      body: { ...PLAN, config: JSON.parse(String(init.body)) },
    });
    routes['GET /api/operations/finance'] = () => ({ body: FINANCE });
    routes['GET /api/operations/availability'] = () => ({ body: AVAILABILITY });
    routes['GET /api/operations/fault-generator'] = () => ({ body: GENERATOR });
    routes['GET /api/operations/crew'] = () => ({ body: CREW });
    routes['PUT /api/operations/fault-generator'] = (_u, init) => ({
      body: { ...GENERATOR, config: JSON.parse(String(init.body)) },
    });
    routes['PUT /api/operations/crew'] = (_u, init) => ({ body: { config: JSON.parse(String(init.body)) } });
  });

  async function openTab() {
    await renderPage();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '自動運轉' }));
    });
    await screen.findByLabelText('平均幾天一個故障（每台機組）');
  }

  it('儲存產生器時送完整的設定，畫面沒列的欄位沿用', async () => {
    await openTab();
    expect(screen.getByText('15')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('平均幾天一個故障（每台機組）'), { target: { value: '3' } });
    const enabled = screen.getAllByLabelText('開啟')[0];
    fireEvent.click(enabled);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存產生器設定' }));
    });
    const put = calls.find(c => c.method === 'PUT' && c.url.pathname === '/api/operations/fault-generator')!;
    expect(put.body).toEqual({ ...GENERATOR.config, enabled: true, mean_days_between_faults: 3 });
    expect(await screen.findByText('已儲存')).toBeInTheDocument();
  });

  it('不是數字時不送', async () => {
    await openTab();
    fireEvent.change(screen.getByLabelText('一台機組同時最多幾個故障'), { target: { value: '1.5' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存產生器設定' }));
    });
    expect(calls.some(c => c.method === 'PUT')).toBe(false);
    expect(screen.getByRole('alert')).toHaveTextContent('不是有效的數字');
  });

  it('維修班設定', async () => {
    await openTab();
    await screen.findByLabelText('同時幾組在施工');
    fireEvent.change(screen.getByLabelText('故障維修要幾分鐘'), { target: { value: '180' } });
    fireEvent.click(screen.getAllByLabelText('開啟')[1]);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存維修班設定' }));
    });
    const put = calls.find(c => c.method === 'PUT' && c.url.pathname === '/api/operations/crew')!;
    expect(put.body).toEqual({ ...CREW.config, enabled: true, repair_minutes: 180 });
  });

  it('自動定檢計畫：列出排程、儲存週期', async () => {
    await openTab();
    const days = await screen.findByLabelText('每台機組幾天定檢一次');
    expect(screen.getByText('2026-03-14 08:00 UTC')).toBeInTheDocument();
    expect(screen.getByText('暫停')).toBeInTheDocument();
    expect(screen.getByText('到期、還沒開單')).toBeInTheDocument();
    expect(screen.getByText(/未結案工單已經滿三張/)).toBeInTheDocument();
    expect(screen.getByText('2025-09-27 08:00 UTC')).toBeInTheDocument();
    fireEvent.change(days, { target: { value: '30' } });
    fireEvent.click(screen.getAllByLabelText('開啟')[2]);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存定檢計畫' }));
    });
    const put = calls.find(c => c.method === 'PUT' && c.url.pathname === '/api/operations/inspection-plan')!;
    expect(put.body).toEqual({ enabled: true, interval_days: 30 });
    expect(await screen.findByText(/排程在即時模擬的下一批讀值時整理/)).toBeInTheDocument();
  });

  it('自動定檢計畫：週期不是 1–730 的整數時不送', async () => {
    await openTab();
    fireEvent.change(await screen.findByLabelText('每台機組幾天定檢一次'), { target: { value: '0' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存定檢計畫' }));
    });
    expect(calls.some(c => c.method === 'PUT')).toBe(false);
    expect(screen.getByRole('alert')).toHaveTextContent('1–730 的整數天數');
  });
});

// ─── 實測風況 ─────────────────────────────────────────────────────────────

const SUMMARY = {
  rows: 29224,
  start: '1995-01-01T00:00:00+00:00',
  end: '2004-12-31T21:00:00+00:00',
  step_s: 10800,
  quantities: ['wind_speed'],
  missing: { wind_speed: 0 },
  out_of_range: {},
  duplicates_dropped: 0,
  unreadable_times: 0,
  long_gaps: 0,
  longest_gap_s: 10800,
  max_gap_s: 21600,
  height_scale: 1,
  wind_speed_mean: 7.473,
  wind_speed_max: 24.89,
  timezone: 'UTC',
  warnings: [],
};

const SERIES = { id: 7, name: 'K13 1995–2004', created_at: '2026-11-27T03:00:00+00:00', summary: SUMMARY };

const STATUS_MEASURED = {
  mode: 'measured',
  profile: null,
  override_wind_speed: null,
  turbulence_intensity: 0.1,
  time_scale: 1,
  measured: {
    series_id: 7,
    name: 'K13 1995–2004',
    alignment: 'replay',
    at_end: 'loop',
    start_offset_s: 0,
    started_at: '2026-11-29T14:00:00+00:00',
    quantities: ['wind_speed'],
    pending: false,
  },
};

describe('實測風況', () => {
  beforeEach(() => {
    routes['GET /api/operations/finance'] = () => ({ body: FINANCE });
    routes['GET /api/operations/availability'] = () => ({ body: AVAILABILITY });
    routes['GET /api/config/wind'] = () => ({ body: STATUS_MEASURED });
    routes['GET /api/config/wind/series'] = () => ({ body: { series: [SERIES] } });
  });

  async function openTab() {
    await renderPage();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '實測風況' }));
    });
    await screen.findByText('K13 1995–2004', { selector: 'td' });
  }

  it('目前的風況與匯入過的序列', async () => {
    await openTab();
    expect(screen.getByTestId('wind-mode')).toHaveTextContent('依實測序列');
    expect(screen.getByText('播放中')).toBeInTheDocument();
    expect(screen.getByText('29,224')).toBeInTheDocument();
    expect(screen.getByText('3 h')).toBeInTheDocument();
  });

  it('匯入：送檔案內容，名稱預設檔名，顯示摘要與警告', async () => {
    routes['POST /api/config/wind/series'] = () => ({
      body: { ...SERIES, id: 8, name: 'met.csv', summary: { ...SUMMARY, warnings: ['pressure_hpa：單位可能不對'] } },
    });
    await openTab();
    const file = new File(['timestamp,wind_speed\n2026-03-01 00:00,8\n'], 'met.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('CSV 檔'), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText('量測高度'), { target: { value: '10' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '匯入' }));
    });
    const post = calls.find(c => c.method === 'POST' && c.url.pathname === '/api/config/wind/series')!;
    expect(post.body).toEqual({
      name: 'met.csv',
      csv: 'timestamp,wind_speed\n2026-03-01 00:00,8\n',
      heightM: 10,
    });
    const summary = await screen.findByTestId('import-summary');
    expect(summary).toHaveTextContent('已匯入「met.csv」');
    expect(summary).toHaveTextContent('單位可能不對');
  });

  it('套用：對時、播完、起點都送出去；回到模型', async () => {
    routes['POST /api/config/wind/series/7/apply'] = () => ({ body: STATUS_MEASURED });
    routes['POST /api/config/wind/clear'] = () => ({ body: { status: 'ok', mode: 'auto' } });
    await openTab();
    fireEvent.change(screen.getByLabelText('對時方式'), { target: { value: 'absolute' } });
    fireEvent.change(screen.getByLabelText('播完之後'), { target: { value: 'hold' } });
    fireEvent.change(screen.getByLabelText('從第幾小時開始'), { target: { value: '24' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用' }));
    });
    const apply = calls.find(c => c.url.pathname === '/api/config/wind/series/7/apply')!;
    expect(apply.body).toEqual({ alignment: 'absolute', atEnd: 'hold', startOffsetHours: 24 });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '回到模型的風況' }));
    });
    expect(calls.some(c => c.method === 'POST' && c.url.pathname === '/api/config/wind/clear')).toBe(true);
  });

  it('刪除要確認', async () => {
    routes['DELETE /api/config/wind/series/7'] = () => ({ body: { status: 'ok', id: 7 } });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    await openTab();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '刪除' }));
    });
    expect(calls.some(c => c.method === 'DELETE')).toBe(false);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '刪除' }));
    });
    await waitFor(() => expect(calls.some(c => c.method === 'DELETE')).toBe(true));
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});

describe('語系', () => {
  it('英文', async () => {
    routes['GET /api/operations/finance'] = () => ({ body: FINANCE });
    routes['GET /api/operations/availability'] = () => ({ body: AVAILABILITY });
    await renderPage('en');
    expect(screen.getByRole('heading', { name: 'Operations' })).toBeInTheDocument();
    expect((await screen.findAllByText('Revenue')).length).toBeGreaterThan(0);
    expect(screen.getByText('Availability (time)')).toBeInTheDocument();
  });
});

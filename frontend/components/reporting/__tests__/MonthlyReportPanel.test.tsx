/**
 * MonthlyReportPanel component render 測試（WMOM-20260606-07，EPIC-M5 測試覆蓋擴大）。
 *
 * `MonthlyReportPanel`（357 行）是 A9 月報生成面板，直接餵 M6-6「第一份自動月報交業主」
 * 的 deliverable：選 year/month → Generate → 顯示 KPI 卡 + 4 大類成本明細表 + HTML iframe
 * 預覽 + PDF 下載。先前頁面層只有 ReportsPage（mock 掉本面板）+ formatters 單元測試覆蓋，
 * 本面板本體（filter bar / 生成接線 / KPI 卡 / 成本表 / 下載 async 流 / 雙 error 獨立顯示 /
 * empty state / 語系）零 render 覆蓋。
 *
 * 本檔延續既有 render 測試範式（純 props-driven 元件 + ThemeProvider 包裹 +
 * jest-dom matcher + afterEach cleanup）。本元件依賴僅 `useTheme`，無 fetch / 無自訂 hook，
 * 唯一 async 副作用是 `onDownloadPdf`（prop 注入的 Promise）→ 以受控 Promise 驗下載中態 +
 * 失敗錯誤卡。`Btn`/`Card`/`Field`/`Select`/`Stat` 用真實 ui 元件不 mock（驗整合輸出）。
 *
 * 守住的 UX 契約：
 *   - 殼層 / filter bar：年月 Select + Generate 鈕（farmId 空 disabled）
 *   - empty state：未生成且非 loading / error 時的引導卡
 *   - 生成接線：Generate → onGenerate(year, month) 帶當前選擇
 *   - loading：Generate 鈕轉「生成中…」+ disabled
 *   - KPI 卡：5 個 Stat（總成本 / 確認比例 / 完工工單 / 平均工時 / 可用率）格式化
 *   - 成本明細表：4 類別 row + 合計列 + Decimal 字串格式化
 *   - PDF 下載：data 存在才顯示下載鈕 → 下載中態 → 失敗錯誤卡（與 generate error 獨立）
 *   - 雙 error 獨立：generate error + download error 各自顯示、generate 清掉舊 download error
 *   - HTML preview：html 非空才渲染 iframe（srcDoc + sandbox="")
 *   - 語系：lang='en' 顯示英文標題與標籤
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import MonthlyReportPanel from '../MonthlyReportPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  CostBreakdownItem,
  CostSummary,
  KpiHighlights,
  MonthlyReportData,
} from '../../../services/reportingService';

// ─── 工廠：結構式滿足型別（不用 `as`），overrides 末尾 spread ──────────────────

function makeKpi(overrides: Partial<KpiHighlights> = {}): KpiHighlights {
  return {
    grand_total_cost: '1234567.89',
    confirmed_cost_ratio: 0.732,
    work_orders_finished: 8,
    average_repair_hours: 4.5,
    time_availability: 0.961,
    ...overrides,
  };
}

function makeCategory(
  category: CostBreakdownItem['category'],
  overrides: Partial<CostBreakdownItem> = {},
): CostBreakdownItem {
  return {
    category,
    estimated: '1000.00',
    confirmed: '900.00',
    total: '1900.00',
    ...overrides,
  };
}

function makeCost(overrides: Partial<CostSummary> = {}): CostSummary {
  return {
    by_category: [
      makeCategory('material', { estimated: '5000.00', confirmed: '4800.00', total: '9800.00' }),
      makeCategory('labour', { estimated: '3000.00', confirmed: '2900.00', total: '5900.00' }),
      makeCategory('equipment', { estimated: '1500.00', confirmed: '1400.00', total: '2900.00' }),
      makeCategory('revenue_loss', { estimated: '800.00', confirmed: '750.00', total: '1550.00' }),
    ],
    estimated_total: '10300.00',
    confirmed_total: '9850.00',
    grand_total: '20150.00',
    ...overrides,
  };
}

function makeData(overrides: Partial<MonthlyReportData> = {}): MonthlyReportData {
  return {
    farm_id: 'farm-001',
    farm_name: '海風一號',
    year: 2026,
    month: 5,
    period_start: '2026-05-01T00:00:00Z',
    period_end: '2026-05-31T23:59:59Z',
    generated_at: '2026-06-01T08:30:45.123456',
    kpi: makeKpi(),
    cost: makeCost(),
    work_orders: {
      by_type: [],
      total_finished: 8,
      total_closed: 6,
      total_in_progress: 2,
      total_actual_hours: 36,
    },
    availability: {
      time_availability: 0.961,
      energy_availability: 0.95,
      total_hours_in_period: 744,
      downtime_hours: 29,
      source: 'scada',
    },
    notable_events: [],
    ...overrides,
  };
}

// 預設 props——測試多只覆寫關注欄位，避免每個 test 重複 8 個 prop。
function baseProps() {
  return {
    farmId: 'farm-001',
    farmName: '海風一號',
    lang: 'zh' as const,
    data: null,
    html: null,
    loading: false,
    error: null,
    onGenerate: vi.fn(),
    onDownloadPdf: vi.fn<(year: number, month: number) => Promise<void>>(
      () => Promise.resolve(),
    ),
  };
}

type PanelProps = React.ComponentProps<typeof MonthlyReportPanel>;

function renderPanel(overrides: Partial<PanelProps> = {}) {
  const props = { ...baseProps(), ...overrides };
  render(
    <ThemeProvider>
      <MonthlyReportPanel {...props} />
    </ThemeProvider>,
  );
  return props;
}

// 預設選擇 = 上個月，依賴元件內部 `new Date()`。不用 fake timers（會卡死 waitFor/findBy
// 的 polling），改在測試裡用與元件相同的邏輯動態算出期望年/月，跨月跑也穩定。
const NOW = new Date();
const EXPECTED_YEAR = NOW.getMonth() === 0 ? NOW.getFullYear() - 1 : NOW.getFullYear();
// JS getMonth() 是 0-indexed：現在是 3 月時 getMonth()=2，上月 2 月的 1-based 值正好是 2，
// 故非 1 月時「上月的 1-based month number」就等於 getMonth()（不需 -1）。
// 邊界：1 月（getMonth()=0）上月是去年 12 月 → special-case 成 12（年份同步退 1，見上行）。
const EXPECTED_MONTH = NOW.getMonth() === 0 ? 12 : NOW.getMonth();
const MONTHS_EN = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

// ─── 殼層 / filter bar ────────────────────────────────────────────────────
describe('MonthlyReportPanel — 殼層 / filter bar', () => {
  it('渲染年份 / 月份 Select 與生成月報按鈕', () => {
    renderPanel();
    expect(screen.getByLabelText('年份')).toBeInTheDocument();
    expect(screen.getByLabelText('月份')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成月報' })).toBeInTheDocument();
  });

  it('farmId 為空時生成按鈕 disabled（沒有 active farm 不能生成）', () => {
    renderPanel({ farmId: '' });
    expect(screen.getByRole('button', { name: '生成月報' })).toBeDisabled();
  });

  it('farmId 非空時生成按鈕可按', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: '生成月報' })).toBeEnabled();
  });

  it('預設年月 = 上個月（依當前系統時間動態算）', () => {
    renderPanel();
    const year = screen.getByLabelText('年份') as HTMLSelectElement;
    const month = screen.getByLabelText('月份') as HTMLSelectElement;
    expect(year.value).toBe(String(EXPECTED_YEAR));
    expect(month.value).toBe(String(EXPECTED_MONTH));
  });

  it('年份選項涵蓋 5 年歷史 + 1 年 forecast（cur-4 … cur+1）', () => {
    renderPanel();
    const year = screen.getByLabelText('年份') as HTMLSelectElement;
    const values = Array.from(year.options).map(o => o.value);
    const cur = NOW.getFullYear();
    const expected = [cur - 4, cur - 3, cur - 2, cur - 1, cur, cur + 1].map(String);
    expect(values).toEqual(expected);
  });
});

// ─── 生成接線 ─────────────────────────────────────────────────────────────
describe('MonthlyReportPanel — 生成接線', () => {
  it('點生成 → onGenerate(year, month) 帶當前選擇（預設上個月）', () => {
    const props = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '生成月報' }));
    expect(props.onGenerate).toHaveBeenCalledWith(EXPECTED_YEAR, EXPECTED_MONTH);
  });

  it('改選年月後 → onGenerate 帶新選擇', () => {
    const props = renderPanel();
    fireEvent.change(screen.getByLabelText('年份'), { target: { value: '2024' } });
    fireEvent.change(screen.getByLabelText('月份'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '生成月報' }));
    expect(props.onGenerate).toHaveBeenCalledWith(2024, 3);
  });

  it('loading 時按鈕顯示「生成中…」且 disabled', () => {
    renderPanel({ loading: true });
    const btn = screen.getByRole('button', { name: '生成月報' });
    expect(btn).toHaveTextContent('生成中…');
    expect(btn).toBeDisabled();
  });
});

// ─── empty state ──────────────────────────────────────────────────────────
describe('MonthlyReportPanel — empty state', () => {
  it('未生成且非 loading/error → 顯示引導空狀態卡', () => {
    renderPanel();
    expect(screen.getByText(/請於上方選擇月份並點/)).toBeInTheDocument();
  });

  it('loading 時不顯示空狀態卡', () => {
    renderPanel({ loading: true });
    expect(screen.queryByText(/請於上方選擇月份並點/)).not.toBeInTheDocument();
  });

  it('有 data 時不顯示空狀態卡', () => {
    renderPanel({ data: makeData() });
    expect(screen.queryByText(/請於上方選擇月份並點/)).not.toBeInTheDocument();
  });

  it('error 時不顯示空狀態卡（避免空狀態與錯誤訊息並存）', () => {
    renderPanel({ error: '後端 500' });
    expect(screen.queryByText(/請於上方選擇月份並點/)).not.toBeInTheDocument();
  });
});

// ─── KPI 卡 ───────────────────────────────────────────────────────────────
describe('MonthlyReportPanel — KPI 卡', () => {
  it('有 data → 渲染 5 個 KPI（總成本 / 確認比例 / 完工工單 / 平均工時 / 可用率）並格式化', () => {
    renderPanel({ data: makeData() });
    // 總成本 1234567.89 → €1.23M（fmtMoneyDecimal，|n|≥1e6）
    expect(screen.getByText('€1.23M')).toBeInTheDocument();
    // 確認比例 0.732 → 73.2%（fmtPct）
    expect(screen.getByText('73.2%')).toBeInTheDocument();
    // 完工工單 8 —— 用 within 鎖定該 Stat 容器，避免裸數字 '8' 撞其他欄位。
    // Stat 結構為 <div>(outer)<div>{label}</div><div>{value}</div></div>，label 與 value 為
    // 兄弟節點，故從 label 取 parentElement（outer div）才同時涵蓋 value。
    const finishedStat = screen.getByText('完工工單').parentElement;
    expect(finishedStat).not.toBeNull();
    expect(within(finishedStat as HTMLElement).getByText('8')).toBeInTheDocument();
    // 平均工時 4.5 → 4.50 h
    expect(screen.getByText('4.50 h')).toBeInTheDocument();
    // 時間可用率 0.961 → 96.1%
    expect(screen.getByText('96.1%')).toBeInTheDocument();
  });

  it('header 顯示風場名 + 年/月（zero-pad）+ 產出時間（T 換空白、截 19 字）', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByText('海風一號')).toBeInTheDocument();
    // 2026 / 05（month padStart 2）
    expect(screen.getByText(/2026 \/ 05/)).toBeInTheDocument();
    // generated_at T → 空白、slice(0,19)
    expect(screen.getByText('2026-06-01 08:30:45')).toBeInTheDocument();
  });

  it('farmName prop 為空字串 → header 退而顯示 farmId（prop-level fallback）', () => {
    // header 只讀 farmName prop（不讀 data.farm_name），故只需把 prop 設空即觸發 fallback。
    renderPanel({ farmName: '', data: makeData() });
    expect(screen.getByText('farm-001')).toBeInTheDocument();
  });

  it('KPI 降級資料（NaN）不 crash，照現行格式輸出（記錄現況、提醒未來可加 guard）', () => {
    // SCADA 異常時 average_repair_hours / 各比例可能為 NaN；目前元件無 guard，
    // toFixed/fmtPct 會輸出 'NaN h' / 'NaN%'。本 test 守住「不 crash」並記錄現行行為。
    renderPanel({
      data: makeData({
        kpi: makeKpi({ average_repair_hours: NaN, confirmed_cost_ratio: NaN }),
      }),
    });
    expect(screen.getByText('NaN h')).toBeInTheDocument();
    expect(screen.getByText('NaN%')).toBeInTheDocument();
  });
});

// ─── 成本明細表 ───────────────────────────────────────────────────────────
describe('MonthlyReportPanel — 成本明細表', () => {
  it('渲染 4 大類 row（繁中 label）+ 合計列', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByText('物料')).toBeInTheDocument();
    expect(screen.getByText('人力')).toBeInTheDocument();
    expect(screen.getByText('設備')).toBeInTheDocument();
    expect(screen.getByText('收益損失')).toBeInTheDocument();
    // 標題「成本明細（4 大類）」
    expect(screen.getByText('成本明細（4 大類）')).toBeInTheDocument();
  });

  it('合計列顯示 estimated/confirmed/grand total 格式化金額', () => {
    renderPanel({ data: makeData() });
    // 10300.00 → €10.30k、9850.00 → €9.85k、20150.00 → €20.15k
    expect(screen.getByText('€10.30k')).toBeInTheDocument();
    expect(screen.getByText('€9.85k')).toBeInTheDocument();
    expect(screen.getByText('€20.15k')).toBeInTheDocument();
  });

  it('每類別 row 三欄金額格式化（material: 估5000/確4800/合9800）', () => {
    renderPanel({ data: makeData() });
    const materialRow = screen.getByText('物料').closest('tr');
    expect(materialRow).not.toBeNull(); // 結構變更時給有意義的失敗訊息（不靠 `!` 吞 null）
    const cells = within(materialRow as HTMLElement);
    expect(cells.getByText('€5.00k')).toBeInTheDocument();
    expect(cells.getByText('€4.80k')).toBeInTheDocument();
    expect(cells.getByText('€9.80k')).toBeInTheDocument();
  });

  it('金額為非數字字串 → fmtMoneyDecimal 退 dash「—」', () => {
    renderPanel({
      data: makeData({
        cost: makeCost({
          by_category: [makeCategory('material', { estimated: '', confirmed: '', total: '' })],
        }),
      }),
    });
    const materialRow = screen.getByText('物料').closest('tr');
    expect(materialRow).not.toBeNull();
    expect(within(materialRow as HTMLElement).getAllByText('—').length).toBe(3);
  });
});

// ─── PDF 下載 ─────────────────────────────────────────────────────────────
describe('MonthlyReportPanel — PDF 下載', () => {
  it('無 data 時不顯示下載鈕', () => {
    renderPanel({ data: null });
    expect(screen.queryByRole('button', { name: '下載 PDF' })).not.toBeInTheDocument();
  });

  it('有 data 時顯示下載鈕', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByRole('button', { name: '下載 PDF' })).toBeInTheDocument();
  });

  it('點下載 → onDownloadPdf(year, month) 帶當前選擇', () => {
    // handleDownload 是 async，但 onDownloadPdf(...) 在第一個 await 前就同步呼叫 → 不需 waitFor。
    const props = renderPanel({ data: makeData() });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(props.onDownloadPdf).toHaveBeenCalledWith(EXPECTED_YEAR, EXPECTED_MONTH);
  });

  it('下載中顯示「下載中…」且 disabled，完成後恢復', async () => {
    // 受控 Promise 卡住下載，斷言中間態
    let resolveDownload!: () => void;
    const onDownloadPdf = vi.fn<(year: number, month: number) => Promise<void>>(
      () => new Promise<void>(res => { resolveDownload = res; }),
    );
    renderPanel({ data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    // waitFor 內每次重新查詢按鈕，避免快取舊 DOM 參考在 re-render 後成 stale node。
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: '下載 PDF' });
      expect(btn).toHaveTextContent('下載中…');
      expect(btn).toBeDisabled();
    });
    resolveDownload();
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: '下載 PDF' });
      expect(btn).toHaveTextContent('↓ 下載 PDF');
      expect(btn).toBeEnabled();
    });
  });

  it('下載失敗 → 顯示下載失敗錯誤卡（Error.message）', async () => {
    const onDownloadPdf = vi.fn<(year: number, month: number) => Promise<void>>(
      () => Promise.reject(new Error('PDF 服務逾時')),
    );
    renderPanel({ data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*PDF 服務逾時/)).toBeInTheDocument();
  });
});

// ─── 雙 error 獨立顯示 ────────────────────────────────────────────────────
describe('MonthlyReportPanel — 雙 error 獨立顯示', () => {
  it('generate error 顯示為「生成失敗」卡', () => {
    renderPanel({ error: '後端 500' });
    expect(screen.getByText(/生成失敗.*後端 500/)).toBeInTheDocument();
  });

  it('generate error 與 download error 可同時各自顯示', async () => {
    const onDownloadPdf = vi.fn<(year: number, month: number) => Promise<void>>(
      () => Promise.reject(new Error('下載逾時')),
    );
    renderPanel({ error: '生成逾時', data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*下載逾時/)).toBeInTheDocument();
    // generate error 仍在（兩者獨立區塊，不互相覆蓋）
    expect(screen.getByText(/生成失敗.*生成逾時/)).toBeInTheDocument();
  });

  it('再次點生成 → 清掉舊 download error（generate 不殘留下載錯誤）', async () => {
    const onDownloadPdf = vi.fn<(year: number, month: number) => Promise<void>>(
      () => Promise.reject(new Error('下載逾時')),
    );
    const props = renderPanel({ data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*下載逾時/)).toBeInTheDocument();
    // 再次生成應清掉 download error
    fireEvent.click(screen.getByRole('button', { name: '生成月報' }));
    await waitFor(() =>
      expect(screen.queryByText(/下載失敗.*下載逾時/)).not.toBeInTheDocument(),
    );
    expect(props.onGenerate).toHaveBeenCalled();
  });
});

// ─── HTML preview iframe ──────────────────────────────────────────────────
describe('MonthlyReportPanel — HTML preview', () => {
  it('html 為空時不渲染 iframe', () => {
    renderPanel({ data: makeData(), html: null });
    expect(screen.queryByTitle('月報 HTML 預覽')).not.toBeInTheDocument();
  });

  it('html 非空 → 渲染 iframe（srcDoc 帶入 + sandbox="" 隔離）', () => {
    const html = '<html><body><h1>月報</h1></body></html>';
    renderPanel({ data: makeData(), html });
    const iframe = screen.getByTitle('月報 HTML 預覽') as HTMLIFrameElement;
    expect(iframe).toBeInTheDocument();
    expect(iframe.getAttribute('srcdoc')).toBe(html);
    // sandbox="" → XSS 防護（不含 allow-scripts / allow-same-origin）
    expect(iframe.getAttribute('sandbox')).toBe('');
  });
});

// ─── 語系 ─────────────────────────────────────────────────────────────────
describe('MonthlyReportPanel — 語系', () => {
  it('lang=en → 英文按鈕與標籤', () => {
    renderPanel({ lang: 'en' });
    expect(screen.getByRole('button', { name: 'Generate report' })).toBeInTheDocument();
    expect(screen.getByLabelText('Year')).toBeInTheDocument();
    expect(screen.getByLabelText('Month')).toBeInTheDocument();
    expect(screen.getByText(/Pick a month above/)).toBeInTheDocument();
  });

  it('lang=en → KPI 與成本表英文標題', () => {
    renderPanel({ lang: 'en', data: makeData() });
    expect(screen.getByText('Cost breakdown (4 categories)')).toBeInTheDocument();
    expect(screen.getByText('Material')).toBeInTheDocument();
    expect(screen.getByText('Revenue loss')).toBeInTheDocument();
    // 欄表頭也語系化，一併守住（避免 ui('Estimated','估計') 日後傳錯字串無人發現）
    expect(screen.getByText('Estimated')).toBeInTheDocument();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('lang=en → 預設月份顯示對應英文月名', () => {
    renderPanel({ lang: 'en' });
    const month = screen.getByLabelText('Month') as HTMLSelectElement;
    const selected = month.options[month.selectedIndex];
    expect(selected.textContent).toBe(MONTHS_EN[EXPECTED_MONTH - 1]);
  });
});

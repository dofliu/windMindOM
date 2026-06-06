/**
 * AnnualBudgetPanel component render 測試（WMOM-20260606-08，EPIC-M5 測試覆蓋擴大）。
 *
 * `AnnualBudgetPanel` 是 A9 年度預算面板（MonthlyReportPanel 的姊妹面板），同樣直接餵
 * M6-6「第一份自動月報 / 預算交業主」deliverable：選 year + current month（結算邊界）→
 * Generate → 顯示 KPI 卡（全年預測 / 實際合計）+ 12 個月 forecast vs actual BarChart +
 * 月份明細表（4 大類成本 + method pill + 合計列）+ PDF 下載。先前頁面層 ReportsPage 把它
 * mock 掉、僅 formatters 有單元測試，本面板本體（filter bar / 生成接線 / KPI / method pill
 * 三態 / 明細表 / 下載 async 流 / 雙 error 獨立 / empty state / 語系）零 render 覆蓋。
 *
 * 本檔延續既有 render 測試範式（純 props-driven 元件 + ThemeProvider 包裹 +
 * jest-dom matcher + afterEach cleanup）。本元件依賴僅 `useTheme`，無 fetch / 無自訂 hook，
 * 唯一 async 副作用是 `onDownloadPdf`（prop 注入的 Promise）→ 以受控 Promise 驗下載中態 +
 * 失敗錯誤卡。`Btn`/`Card`/`Field`/`Select`/`Stat`/`StatusPill` 用真實 ui 元件不 mock
 * （驗整合輸出）。recharts 全 stub 成 marker div（對齊 CostPage 範式），避免 jsdom 下
 * ResponsiveContainer 0 寬度的圖表渲染細節干擾文字斷言。
 *
 * 守住的 UX 契約：
 *   - 殼層 / filter bar：年份 + 當月（結算邊界）Select + Generate 鈕（farmId 空 disabled）
 *   - 預設選擇：year = 今年、currentMonth = 本月（1-based）；年份範圍 cur-4…cur+1
 *   - 生成接線：Generate → onGenerate(year, currentMonth) 帶當前選擇（含改選後）
 *   - loading：Generate 鈕轉「生成中…」+ disabled
 *   - empty state：未生成且非 loading / error 時的引導卡
 *   - KPI 卡：farm / year / method + 2 個 Stat（全年預測 / 實際合計）格式化
 *   - method pill 三態：actual → 實際 / actual_partial → 當月部分 / historical_average → 預測
 *   - 明細表：12 月 row + 4 類別成本 + forecast / actual 欄 + 年度合計列
 *   - PDF 下載：data 存在才顯示下載鈕 → 下載中態 → 失敗錯誤卡（與 generate error 獨立）
 *   - 雙 error 獨立：generate error + download error 各自顯示、generate 清掉舊 download error
 *   - notes：data.notes 非空才顯示
 *   - 語系：lang='en' 顯示英文標題與標籤
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import AnnualBudgetPanel from '../AnnualBudgetPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  AnnualBudgetData,
  MonthlyBudgetEntry,
} from '../../../services/reportingService';

// recharts：圖表元件全 stub 成 marker div（對齊 CostPage 範式），測試聚焦 filter bar /
// 接線 / KPI / 明細表的文字，不被 ResponsiveContainer 在 jsdom 下 0 寬度的渲染細節干擾。
vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    BarChart: Stub,
    Bar: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    Legend: Stub,
  };
});

// ─── 工廠：結構式滿足型別（不用 `as`），overrides 末尾 spread ──────────────────

function makeMonth(
  month: number,
  overrides: Partial<MonthlyBudgetEntry> = {},
): MonthlyBudgetEntry {
  return {
    month,
    forecast_total: '10000.00',
    forecast_by_category: {
      material: '4000.00',
      labour: '3000.00',
      equipment: '2000.00',
      revenue_loss: '1000.00',
    },
    actual_total: '9500.00',
    method: 'actual',
    ...overrides,
  };
}

// 三個月覆蓋三種 method 狀態（pill 三態 + actual null → dash）。
function makeMonths(): MonthlyBudgetEntry[] {
  return [
    makeMonth(1, { method: 'actual', actual_total: '9500.00' }),
    makeMonth(2, { method: 'actual_partial', actual_total: '5000.00' }),
    makeMonth(3, { method: 'historical_average', actual_total: null }),
  ];
}

function makeData(overrides: Partial<AnnualBudgetData> = {}): AnnualBudgetData {
  return {
    farm_id: 'farm-001',
    farm_name: '海風一號',
    year: 2026,
    generated_at: '2026-06-01T08:30:45.123456',
    months: makeMonths(),
    annual_forecast_total: '1234567.89',
    annual_actual_total: '456789.00',
    method: 'historical_average',
    notes: null,
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
    loading: false,
    error: null,
    onGenerate: vi.fn(),
    onDownloadPdf: vi.fn<(year: number, currentMonth: number) => Promise<void>>(
      () => Promise.resolve(),
    ),
  };
}

type PanelProps = React.ComponentProps<typeof AnnualBudgetPanel>;

function renderPanel(overrides: Partial<PanelProps> = {}) {
  const props = { ...baseProps(), ...overrides };
  render(
    <ThemeProvider>
      <AnnualBudgetPanel {...props} />
    </ThemeProvider>,
  );
  return props;
}

// 預設選擇 = 今年 + 本月（1-based），依賴元件內部 `new Date()`。不用 fake timers
// （會卡死 waitFor polling），改用與元件相同邏輯動態算期望值，跨月 / 跨年跑都穩定。
const NOW = new Date();
const EXPECTED_YEAR = NOW.getFullYear();
const EXPECTED_MONTH = NOW.getMonth() + 1; // getMonth() 0-indexed → +1 還原 1-based

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

// ─── 殼層 / filter bar ────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 殼層 / filter bar', () => {
  it('渲染年份 / 當月 Select 與生成年度預算按鈕', () => {
    renderPanel();
    expect(screen.getByLabelText('年份')).toBeInTheDocument();
    expect(screen.getByLabelText('當月')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成年度預算' })).toBeInTheDocument();
  });

  it('farmId 為空時生成按鈕 disabled（沒有 active farm 不能生成）', () => {
    renderPanel({ farmId: '' });
    expect(screen.getByRole('button', { name: '生成年度預算' })).toBeDisabled();
  });

  it('farmId 非空時生成按鈕可按', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: '生成年度預算' })).toBeEnabled();
  });

  it('預設年份選今年、當月選本月（1-based）', () => {
    renderPanel();
    expect(screen.getByLabelText<HTMLSelectElement>('年份').value).toBe(String(EXPECTED_YEAR));
    expect(screen.getByLabelText<HTMLSelectElement>('當月').value).toBe(String(EXPECTED_MONTH));
  });

  it('年份選項範圍為 cur-4 … cur+1（共 6 個，給 multi-year O&M 查歷史）', () => {
    renderPanel();
    const yearSelect = screen.getByLabelText<HTMLSelectElement>('年份');
    const opts = within(yearSelect).getAllByRole('option') as HTMLOptionElement[];
    expect(opts).toHaveLength(6);
    expect(opts[0].value).toBe(String(EXPECTED_YEAR - 4));
    expect(opts[opts.length - 1].value).toBe(String(EXPECTED_YEAR + 1));
  });
});

// ─── 生成接線 ──────────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 生成接線', () => {
  it('點生成 → onGenerate(year, currentMonth) 帶當前預設選擇', () => {
    const props = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '生成年度預算' }));
    expect(props.onGenerate).toHaveBeenCalledWith(EXPECTED_YEAR, EXPECTED_MONTH);
  });

  it('改選年份後生成 → onGenerate 帶新年份', () => {
    const props = renderPanel();
    const targetYear = EXPECTED_YEAR - 2;
    fireEvent.change(screen.getByLabelText('年份'), { target: { value: String(targetYear) } });
    fireEvent.click(screen.getByRole('button', { name: '生成年度預算' }));
    expect(props.onGenerate).toHaveBeenCalledWith(targetYear, EXPECTED_MONTH);
  });

  it('改選當月後生成 → onGenerate 帶新當月', () => {
    const props = renderPanel();
    fireEvent.change(screen.getByLabelText('當月'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: '生成年度預算' }));
    expect(props.onGenerate).toHaveBeenCalledWith(EXPECTED_YEAR, 7);
  });

  it('loading 時生成按鈕轉「生成中…」且 disabled', () => {
    // Btn 的 aria-label 固定（accessible name 不隨文字變），故以 aria-label 取鈕、textContent 驗載入態。
    renderPanel({ loading: true });
    const btn = screen.getByRole('button', { name: '生成年度預算' });
    expect(btn).toHaveTextContent('生成中…');
    expect(btn).toBeDisabled();
  });
});

// ─── empty state ──────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — empty state', () => {
  it('未生成且非 loading / error 時顯示引導卡', () => {
    renderPanel();
    expect(screen.getByText(/請於上方選擇年份與當月/)).toBeInTheDocument();
  });

  it('loading 時不顯示引導卡', () => {
    renderPanel({ loading: true });
    expect(screen.queryByText(/請於上方選擇年份與當月/)).not.toBeInTheDocument();
  });

  it('有 error 時不顯示引導卡', () => {
    renderPanel({ error: '後端 500' });
    expect(screen.queryByText(/請於上方選擇年份與當月/)).not.toBeInTheDocument();
  });

  it('有 data 時不顯示引導卡', () => {
    renderPanel({ data: makeData() });
    expect(screen.queryByText(/請於上方選擇年份與當月/)).not.toBeInTheDocument();
  });
});

// ─── KPI summary ──────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — KPI summary', () => {
  it('顯示風場名 / 年份 / 預測法', () => {
    // 年份在 KPI 卡是與 farm / method 同一 div 的 inline text node（非獨立元素），
    // 且年份 Select 也有 <option>2026</option> → 裸 getByText('2026') 會誤命中選項而假綠。
    // 改以 farm span 的 closest div 限縮到 KPI header，再用 toHaveTextContent 精確守住年份顯示。
    renderPanel({ data: makeData() });
    const kpiHeader = screen.getByText('海風一號').closest('div') as HTMLElement;
    expect(kpiHeader).not.toBeNull();
    expect(kpiHeader).toHaveTextContent('2026');
    expect(kpiHeader).toHaveTextContent('historical_average');
  });

  it('farmName 為空時退回 farmId 顯示', () => {
    renderPanel({ farmName: '', data: makeData({ farm_name: null }) });
    expect(screen.getByText('farm-001')).toBeInTheDocument();
  });

  it('全年預測 / 實際合計 Stat 用 fmtMoneyDecimal 格式化（M / k 縮寫）', () => {
    renderPanel({ data: makeData() });
    // 各值出現「恰兩次」：KPI Stat + 明細表年度合計列。用 toHaveLength(2) 嚴格守住兩個渲染點，
    // 避免 >= 1 讓其中一處（如合計列）渲染故障時靜悄悄通過。
    expect(screen.getAllByText('€1.23M')).toHaveLength(2); // 1,234,567.89
    expect(screen.getAllByText('€456.79k')).toHaveLength(2); // 456,789.00
  });

  it('data.notes 非空時顯示備註', () => {
    renderPanel({ data: makeData({ notes: '本年含一次大修預估' }) });
    expect(screen.getByText('本年含一次大修預估')).toBeInTheDocument();
  });

  it('data.notes 為 null 時不顯示備註區', () => {
    renderPanel({ data: makeData({ notes: null }) });
    expect(screen.queryByText('本年含一次大修預估')).not.toBeInTheDocument();
  });
});

// ─── 圖表 ──────────────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 圖表', () => {
  it('有 data 且 months 非空時渲染圖表卡標題', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByText('12 個月預測 vs 實際')).toBeInTheDocument();
  });

  it('months 為空陣列時不渲染圖表卡', () => {
    renderPanel({ data: makeData({ months: [] }) });
    expect(screen.queryByText('12 個月預測 vs 實際')).not.toBeInTheDocument();
  });
});

// ─── 明細表 ────────────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 明細表', () => {
  it('渲染月份明細表表頭（4 大類別欄）', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByText('月份明細')).toBeInTheDocument();
    expect(screen.getByText('物料')).toBeInTheDocument();
    expect(screen.getByText('人力')).toBeInTheDocument();
    expect(screen.getByText('設備')).toBeInTheDocument();
    expect(screen.getByText('收益損失')).toBeInTheDocument();
  });

  it('method pill 三態：actual → 實際 / partial → 當月部分 / forecast → 預測', () => {
    renderPanel({ data: makeData() });
    // 月份標籤同時出現在當月 Select 選項與表格 cell，故先 scope 到 table 再取 row。
    const table = screen.getByRole('table');
    const row1 = within(table).getByText('1月').closest('tr');
    const row2 = within(table).getByText('2月').closest('tr');
    const row3 = within(table).getByText('3月').closest('tr');
    // null guard：表格結構若變動（cell 不在 <tr> 內）給有意義的失敗訊息，不靠 `!` 吞 null。
    expect(row1).not.toBeNull();
    expect(row2).not.toBeNull();
    expect(row3).not.toBeNull();
    expect(within(row1 as HTMLElement).getByText('實際')).toBeInTheDocument();
    expect(within(row2 as HTMLElement).getByText('當月部分')).toBeInTheDocument();
    expect(within(row3 as HTMLElement).getByText('預測')).toBeInTheDocument();
  });

  it('月份 row 顯示各類別成本（fmtMoneyDecimal scope 在該 row）', () => {
    renderPanel({ data: makeData() });
    const table = screen.getByRole('table');
    const row1 = within(table).getByText('1月').closest('tr') as HTMLElement;
    // material 4000 → €4.00k、labour 3000 → €3.00k、equipment 2000 → €2.00k、rev_loss 1000 → €1.00k
    expect(within(row1).getByText('€4.00k')).toBeInTheDocument();
    expect(within(row1).getByText('€3.00k')).toBeInTheDocument();
    expect(within(row1).getByText('€2.00k')).toBeInTheDocument();
    expect(within(row1).getByText('€1.00k')).toBeInTheDocument();
    // forecast_total 10000 → €10.00k、actual_total 9500 → €9.50k
    expect(within(row1).getByText('€10.00k')).toBeInTheDocument();
    expect(within(row1).getByText('€9.50k')).toBeInTheDocument();
  });

  it('actual_total 為 null 的月份顯示 dash「—」', () => {
    renderPanel({ data: makeData() });
    const table = screen.getByRole('table');
    const row3 = within(table).getByText('3月').closest('tr') as HTMLElement;
    expect(within(row3).getByText('—')).toBeInTheDocument();
  });

  it('actual_total 為 undefined（欄位 omit）的月份同樣顯示 dash「—」', () => {
    // actual_total?: string | null —— optional 欄位可為 undefined（backend omit）。
    // 元件用 `!= null` 同時過濾 null / undefined → fmtMoneyDecimal(undefined) 回 '—'。
    const months = [makeMonth(1, { actual_total: undefined })];
    renderPanel({ data: makeData({ months }) });
    const table = screen.getByRole('table');
    const row1 = within(table).getByText('1月').closest('tr') as HTMLElement;
    expect(within(row1).getByText('—')).toBeInTheDocument();
  });

  it('年度合計列顯示全年預測 / 實際合計', () => {
    renderPanel({ data: makeData() });
    const totalRow = screen.getByText('年度合計').closest('tr') as HTMLElement;
    expect(totalRow).not.toBeNull();
    expect(within(totalRow).getByText('€1.23M')).toBeInTheDocument();
    expect(within(totalRow).getByText('€456.79k')).toBeInTheDocument();
  });
});

// ─── PDF 下載 ──────────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — PDF 下載', () => {
  it('無 data 時不顯示下載按鈕', () => {
    renderPanel();
    expect(screen.queryByRole('button', { name: '下載 PDF' })).not.toBeInTheDocument();
  });

  it('有 data 時顯示下載按鈕', () => {
    renderPanel({ data: makeData() });
    expect(screen.getByRole('button', { name: '下載 PDF' })).toBeInTheDocument();
  });

  it('點下載 → onDownloadPdf(year, currentMonth) 帶當前選擇', () => {
    // handleDownload 是 async，但 onDownloadPdf(...) 在第一個 await 前就同步呼叫 → 不需 waitFor。
    const props = renderPanel({ data: makeData() });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(props.onDownloadPdf).toHaveBeenCalledWith(EXPECTED_YEAR, EXPECTED_MONTH);
  });

  it('下載中顯示「下載中…」且 disabled，完成後恢復', async () => {
    let resolveDownload!: () => void;
    const onDownloadPdf = vi.fn<(year: number, currentMonth: number) => Promise<void>>(
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
    const onDownloadPdf = vi.fn<(year: number, currentMonth: number) => Promise<void>>(
      () => Promise.reject(new Error('PDF 服務逾時')),
    );
    renderPanel({ data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*PDF 服務逾時/)).toBeInTheDocument();
  });
});

// ─── 雙 error 獨立顯示 ────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 雙 error 獨立顯示', () => {
  it('generate error 顯示為「生成失敗」卡', () => {
    renderPanel({ error: '後端 500' });
    expect(screen.getByText(/生成失敗.*後端 500/)).toBeInTheDocument();
  });

  it('generate error 與 download error 可同時各自顯示', async () => {
    const onDownloadPdf = vi.fn<(year: number, currentMonth: number) => Promise<void>>(
      () => Promise.reject(new Error('下載逾時')),
    );
    renderPanel({ error: '生成逾時', data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*下載逾時/)).toBeInTheDocument();
    // generate error 仍在（兩者獨立區塊，不互相覆蓋）
    expect(screen.getByText(/生成失敗.*生成逾時/)).toBeInTheDocument();
  });

  it('再次點生成 → 清掉舊 download error（generate 不殘留下載錯誤）', async () => {
    const onDownloadPdf = vi.fn<(year: number, currentMonth: number) => Promise<void>>(
      () => Promise.reject(new Error('下載逾時')),
    );
    const props = renderPanel({ data: makeData(), onDownloadPdf });
    fireEvent.click(screen.getByRole('button', { name: '下載 PDF' }));
    expect(await screen.findByText(/下載失敗.*下載逾時/)).toBeInTheDocument();
    // 再次生成應清掉 download error
    fireEvent.click(screen.getByRole('button', { name: '生成年度預算' }));
    await waitFor(() =>
      expect(screen.queryByText(/下載失敗.*下載逾時/)).not.toBeInTheDocument(),
    );
    expect(props.onGenerate).toHaveBeenCalled();
  });
});

// ─── 語系 ──────────────────────────────────────────────────────────────────
describe('AnnualBudgetPanel — 語系（en）', () => {
  it('lang=en 顯示英文 filter / 按鈕標籤', () => {
    renderPanel({ lang: 'en' });
    expect(screen.getByLabelText('Year')).toBeInTheDocument();
    expect(screen.getByLabelText('Current month')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate annual budget' })).toBeInTheDocument();
  });

  it('lang=en 顯示英文 KPI / 表格 / 圖表標題與 method pill', () => {
    renderPanel({ lang: 'en', data: makeData() });
    expect(screen.getByText('Annual forecast total')).toBeInTheDocument();
    expect(screen.getByText('Annual actual total')).toBeInTheDocument();
    expect(screen.getByText('Monthly breakdown')).toBeInTheDocument();
    expect(screen.getByText('Monthly forecast vs actual')).toBeInTheDocument();
    // method pill en 三態（scope 在 table 各 row，避開 Select 選項與表頭重複文字）：
    // actual → Actual / actual_partial → Partial / historical_average → Forecast
    const table = screen.getByRole('table');
    const janRow = within(table).getByText('Jan').closest('tr') as HTMLElement;
    const febRow = within(table).getByText('Feb').closest('tr') as HTMLElement;
    const marRow = within(table).getByText('Mar').closest('tr') as HTMLElement;
    expect(within(janRow).getByText('Actual')).toBeInTheDocument();
    expect(within(febRow).getByText('Partial')).toBeInTheDocument();
    expect(within(marRow).getByText('Forecast')).toBeInTheDocument();
  });

  it('lang=en 顯示英文 empty state 引導文字', () => {
    renderPanel({ lang: 'en' });
    expect(screen.getByText(/Pick a year and current month above/)).toBeInTheDocument();
  });
});

/**
 * ReportsPage component render 測試（WMOM-20260604-02，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/reports` 主入口先前只有 useReports hook + formatters 的單元測試，
 * 頁面層（active farm 載入四態 / tab 切換 / 子面板 props wiring / 語系）零覆蓋。
 * 本檔延續 FieldPage 已落地的 render 測試範式（mock hook + ThemeProvider 包裹 +
 * jest-dom matcher + afterEach cleanup），守住 ReportsPage 的 UX 契約：
 *
 *   - active farm 載入四態：載入中 / fetch 失敗 / 無啟用風場 / 成功
 *   - tab 切換：月報 ⇄ 年度預算（對應子面板渲染 + aria-pressed）
 *   - 子面板 props wiring：farmId / farmName / lang 正確傳入
 *   - onGenerate 接線：子面板觸發 → 帶 active farm_id 呼叫對應 useReports action
 *   - 語系：lang='en' 顯示英文標題
 *
 * 兩個重量級子面板（MonthlyReportPanel / AnnualBudgetPanel，各 350+ 行）以輕量
 * mock 取代，只渲染 marker + 回傳收到的 props，讓測試聚焦在 ReportsPage 的
 * 路由 / 狀態 / 接線邏輯，不被子面板內部細節干擾。
 * farmApi.list 與 useReports 皆 mock（零真連線、零真 useEffect 副作用）。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import ReportsPage from '../ReportsPage';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { farmApi, type FarmsResponse } from '../../../services/workOrderService';
import { useReports } from '../../../hooks/useReports';

// workOrderService 用顯式 factory mock（ReportsPage 只消費 farmApi.list）——不依賴 auto-mock
// 對嵌套物件 method 的未定義行為，明確把 list 換成可控 vi.fn。
vi.mock('../../../services/workOrderService', () => ({
  farmApi: { list: vi.fn() },
}));
vi.mock('../../../hooks/useReports');

// 子面板 mock 的 props 型別綁定真實元件 Props（type-only dynamic import，零 runtime / 零 production 改動）：
// 一旦 MonthlyReportPanel / AnnualBudgetPanel 的 Props 契約變動（如 onGenerate 簽章改變），
// 這裡的 tsc 會爆型別錯誤而非靜默假綠。
type MonthlyPanelProps = React.ComponentProps<typeof import('../MonthlyReportPanel')['default']>;
type AnnualPanelProps = React.ComponentProps<typeof import('../AnnualBudgetPanel')['default']>;

// mock 觸發 onGenerate 用的固定參數（抽常數避免 mock 與斷言硬寫值不同步漂移）。
const MOCK_YEAR = 2026;
const MOCK_MONTHLY_MONTH = 5;
const MOCK_ANNUAL_MONTH = 6;

// ─── 子面板輕量 mock：渲染 marker + 把關鍵 props 攤平成 data-* / 文字，供斷言接線 ──
//   按鈕模擬使用者「生成」動作 → 觸發 onGenerate(year, month)，驗 ReportsPage 帶 farm_id 接線。
vi.mock('../MonthlyReportPanel', () => ({
  default: (props: MonthlyPanelProps) => (
    <div
      data-testid="monthly-panel"
      data-farm-id={props.farmId}
      data-farm-name={props.farmName}
      data-lang={props.lang}
    >
      <button onClick={() => props.onGenerate(MOCK_YEAR, MOCK_MONTHLY_MONTH)}>
        mock-generate-monthly
      </button>
    </div>
  ),
}));

vi.mock('../AnnualBudgetPanel', () => ({
  default: (props: AnnualPanelProps) => (
    <div
      data-testid="annual-panel"
      data-farm-id={props.farmId}
      data-farm-name={props.farmName}
      data-lang={props.lang}
    >
      <button onClick={() => props.onGenerate(MOCK_YEAR, MOCK_ANNUAL_MONTH)}>
        mock-generate-annual
      </button>
    </div>
  ),
}));

const mockedFarmList = farmApi.list as unknown as Mock;
const mockedUseReports = useReports as unknown as Mock;

// ─── fixtures ──────────────────────────────────────────────────────────────

function farm(farm_id: string, name: string): FarmsResponse['farms'][number] {
  return {
    farm_id,
    name,
    turbine_count: 21,
    is_active: true,
    location: 'Changhua',
    description: '',
    created_at: '2026-01-01T00:00:00Z',
    turbine_spec: {},
  };
}

const FARM_ACTIVE: FarmsResponse = {
  active_farm_id: 'farm-001',
  farms: [farm('farm-001', '彰化外海一期')],
};

// active farm 存在但 name 為空字串 → 驗 header `{farmName || farmId}` fallback。
const FARM_NO_NAME: FarmsResponse = {
  active_farm_id: 'farm-001',
  farms: [farm('farm-001', '')],
};

const FARM_NONE: FarmsResponse = { active_farm_id: null, farms: [] };

/** useReports 回傳的兩條 sub-state + 四個 action（loading=false / error=null / data=null）。 */
type ReportsReturn = ReturnType<typeof useReports>;

function makeReports(overrides: Partial<ReportsReturn> = {}): ReportsReturn {
  // 六個欄位全列，不用 `as` 強轉——讓 tsc 守住與 hook 真實 signature 對齊；漏欄位編譯失敗而非靜默假綠。
  return {
    monthly: { loading: false, error: null, data: null, html: null },
    annual: { loading: false, error: null, data: null },
    generateMonthly: vi.fn(),
    downloadMonthlyPdf: vi.fn(),
    generateAnnual: vi.fn(),
    downloadAnnualPdf: vi.fn(),
    ...overrides,
  };
}

/** 渲染 ReportsPage；回傳 mock 的 useReports 物件以便斷言 action 呼叫。 */
function renderReports(
  lang: 'zh' | 'en' = 'zh',
  reportsOverrides: Partial<ReportsReturn> = {},
): ReportsReturn {
  const reports = makeReports(reportsOverrides);
  mockedUseReports.mockReturnValue(reports);
  render(
    <ThemeProvider>
      <ReportsPage lang={lang} />
    </ThemeProvider>,
  );
  return reports;
}

describe('ReportsPage 報表主入口', () => {
  beforeEach(() => {
    // mockReset 清 call history + 移除 returnValue；每 test 由 renderReports / 各自 mockResolvedValue 重設。
    mockedFarmList.mockReset();
    mockedUseReports.mockReset();
  });

  // globals:false 時 RTL 不自動 cleanup，需手動清 DOM 避免跨測試 render 累積。
  afterEach(() => {
    cleanup();
  });

  // ── active farm 載入四態 ───────────────────────────────────────────────

  it('farm 載入中（fetch 未 resolve）顯示載入提示，不渲染子面板', async () => {
    // 永不 resolve 的 promise → farmLoaded 維持 false；用 findBy 等 effect flush 後仍是載入態。
    mockedFarmList.mockReturnValue(new Promise<FarmsResponse>(() => {}));
    renderReports();
    expect(await screen.findByText('載入風場中…')).toBeInTheDocument();
    expect(screen.queryByTestId('monthly-panel')).not.toBeInTheDocument();
  });

  it('farm fetch 失敗顯示錯誤訊息（剝技術前綴後的繁中 detail）', async () => {
    mockedFarmList.mockRejectedValue(new Error('伺服器忙碌'));
    renderReports();
    expect(await screen.findByText(/伺服器忙碌/)).toBeInTheDocument();
    expect(screen.getByText(/無法載入目前風場/)).toBeInTheDocument();
    expect(screen.queryByTestId('monthly-panel')).not.toBeInTheDocument();
  });

  it('無啟用風場（active_farm_id=null）顯示引導訊息，不渲染子面板', async () => {
    mockedFarmList.mockResolvedValue(FARM_NONE);
    renderReports();
    expect(await screen.findByText(/目前沒有啟用的風場/)).toBeInTheDocument();
    expect(screen.queryByTestId('monthly-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('annual-panel')).not.toBeInTheDocument();
  });

  it('成功載入 active farm → header 顯示風場名稱 + 預設月報 tab + 月報面板', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    renderReports();
    // 等 active farm 載入完成（header 出現風場名）
    expect(await screen.findByText('彰化外海一期')).toBeInTheDocument();
    // 預設 tab=monthly → 月報面板在場、年度面板不在
    expect(screen.getByTestId('monthly-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('annual-panel')).not.toBeInTheDocument();
  });

  it('active farm 名稱為空 → header 退回顯示 farmId（farmName || farmId fallback）', async () => {
    mockedFarmList.mockResolvedValue(FARM_NO_NAME);
    renderReports();
    await screen.findByTestId('monthly-panel');
    // name='' → header sub 顯示 farm_id；子面板也收到空 farmName
    expect(screen.getByText('farm-001')).toBeInTheDocument();
    expect(screen.getByTestId('monthly-panel')).toHaveAttribute('data-farm-name', '');
  });

  // ── tab 切換 + aria-pressed ────────────────────────────────────────────

  it('預設月報 tab aria-pressed 正確（monthly active / annual inactive）', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    renderReports();
    await screen.findByTestId('monthly-panel');
    expect(screen.getByRole('button', { name: '月報頁籤' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '年度預算頁籤' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('點年度預算 tab → 切換到年度面板、月報面板消失、aria-pressed 翻轉', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    renderReports();
    await screen.findByTestId('monthly-panel');

    fireEvent.click(screen.getByRole('button', { name: '年度預算頁籤' }));

    expect(screen.getByTestId('annual-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('monthly-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '年度預算頁籤' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '月報頁籤' })).toHaveAttribute('aria-pressed', 'false');
  });

  // ── 子面板 props wiring ────────────────────────────────────────────────

  it('月報面板收到正確的 farmId / farmName / lang props', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    renderReports('zh');
    const panel = await screen.findByTestId('monthly-panel');
    expect(panel).toHaveAttribute('data-farm-id', 'farm-001');
    expect(panel).toHaveAttribute('data-farm-name', '彰化外海一期');
    expect(panel).toHaveAttribute('data-lang', 'zh');
  });

  // ── onGenerate 接線（帶 active farm_id）────────────────────────────────

  it('月報面板觸發 onGenerate → 帶 active farm_id 呼叫 generateMonthly', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    const reports = renderReports();
    await screen.findByTestId('monthly-panel');

    fireEvent.click(screen.getByText('mock-generate-monthly'));

    expect(reports.generateMonthly).toHaveBeenCalledTimes(1);
    expect(reports.generateMonthly).toHaveBeenCalledWith({
      farm_id: 'farm-001',
      year: MOCK_YEAR,
      month: MOCK_MONTHLY_MONTH,
      farm_name: '彰化外海一期',
    });
  });

  it('年度面板觸發 onGenerate → 帶 active farm_id + current_month 呼叫 generateAnnual', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    const reports = renderReports();
    await screen.findByTestId('monthly-panel');
    fireEvent.click(screen.getByRole('button', { name: '年度預算頁籤' }));
    await screen.findByTestId('annual-panel'); // 確認 tab 切換完成再觸發生成

    fireEvent.click(screen.getByText('mock-generate-annual'));

    expect(reports.generateAnnual).toHaveBeenCalledTimes(1);
    expect(reports.generateAnnual).toHaveBeenCalledWith({
      farm_id: 'farm-001',
      year: MOCK_YEAR,
      current_month: MOCK_ANNUAL_MONTH,
      farm_name: '彰化外海一期',
    });
  });

  // ── 語系 ───────────────────────────────────────────────────────────────

  it('lang=en → 標題與 tab 顯示英文', async () => {
    mockedFarmList.mockResolvedValue(FARM_ACTIVE);
    renderReports('en');
    await screen.findByTestId('monthly-panel');
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Monthly report tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Annual budget tab' })).toBeInTheDocument();
  });
});

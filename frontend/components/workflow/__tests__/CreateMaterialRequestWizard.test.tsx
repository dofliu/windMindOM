/**
 * CreateMaterialRequestWizard component render 測試（WMOM-20260606-02，EPIC-M5 測試覆蓋擴大）。
 *
 * `CreateMaterialRequestWizard.tsx`（690 行）是 `/admin/workflow` 領料單 tab 的「建立領料單」3 步精靈：
 *   Step 1 選關聯工單（可不關聯 — backend 容許 null；closed/cancelled 工單不顯示）
 *   → Step 2 左右 split picker（左可選料件 / 右 cart：qty + stock_kind）
 *   → Step 3 檢閱 + submit。
 *
 * 與本系列先前的 CreateWorkOrderWizard 同屬多步驟 wizard，但**首次引入需 mock 自訂 hook**
 * （`useInventoryItems`，async picker 來源）+ cart 增刪 + `window.confirm` 守門的 backdrop 關閉路徑。
 * 核心契約：step machine + gating（Step 1 無 gating / Step 2 canNext2 = cart 非空且每行 qty>0）+
 * cart 增刪同步 availableItems + buildRequest 序列化 + async 送出中間態 + confirm-gated 關閉。
 *
 * 延續既有 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup）。
 * 本元件不依賴 useCurrentUser（requesterId 由 prop 傳入），故僅需 ThemeProvider。
 * 工廠以結構式滿足型別（不用 `as` 強轉）；async 送出以受控 Promise 斷言中間態並 await 收尾。
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import CreateMaterialRequestWizard from '../CreateMaterialRequestWizard';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type { InventoryItemSummary, CreateMaterialRequestPayload } from '../../../services/materialService';
import type { WorkOrderResponse } from '../../../services/workOrderService';

// ─── useInventoryItems hook mock（picker 來源；以 hoisted fn 注入可控狀態） ──────

const { mockUseInventoryItems } = vi.hoisted(() => ({
  mockUseInventoryItems: vi.fn(),
}));

vi.mock('../../../hooks/useInventoryItems', () => ({
  useInventoryItems: (...args: unknown[]) => mockUseInventoryItems(...args),
}));

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 InventoryItemSummary（不用 `as`）。 */
function makeItem(overrides: Partial<InventoryItemSummary> = {}): InventoryItemSummary {
  return {
    id: 'item-1',
    sku: 'SKU-001',
    name: '齒輪箱軸承',
    description: 'NDE bearing',
    unit: 'pcs',
    farm_id: 'farm-a',
    warehouse_id: 'wh-1',
    stock_new: 10,
    stock_used: 3,
    stock_repairing: 1,
    safety_stock: 5,
    unit_cost: '1200.00',
    last_received_at: null,
    last_used_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    total_available: 13,
    below_safety: false,
    ...overrides,
  };
}

/** 產生結構完整的 WorkOrderResponse（僅填精靈用得到的欄位，其餘以合理 default 補齊）。 */
function makeWorkOrder(overrides: Partial<WorkOrderResponse> = {}): WorkOrderResponse {
  return {
    id: 'wo-1',
    business_key: 'WO-2026-001',
    farm_id: 'farm-a',
    turbine_id: 'WT-01',
    type: 'corrective',
    status: 'in_progress',
    priority: 'normal',
    title: '齒輪箱維修',
    description: '更換 NDE 軸承',
    source_alarm_id: null,
    source_alarm_code: null,
    assignee_id: null,
    crew_size: 1,
    estimated_hours: null,
    dispatched_at: null,
    dispatched_by: null,
    vessel_id: null,
    weather_window_id: null,
    logistic_hours: null,
    started_at: null,
    progress_notes: [],
    finished_at: null,
    actual_hours: null,
    work_summary: null,
    unfinished_items: null,
    followup_kind: 'none',
    followup_note: null,
    signoff_chain_id: null,
    closed_at: null,
    cancelled_at: null,
    cancel_reason: null,
    rejected_at: null,
    reject_reason: null,
    reopened_at: null,
    reopen_reason: null,
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const DEFAULT_ITEMS: InventoryItemSummary[] = [
  makeItem({ id: 'item-1', sku: 'SKU-001', name: '齒輪箱軸承', stock_new: 10, stock_used: 3, stock_repairing: 1, below_safety: false }),
  makeItem({ id: 'item-2', sku: 'SKU-002', name: '液壓油封', unit: 'set', stock_new: 1, stock_used: 0, stock_repairing: 0, below_safety: true }),
];

const DEFAULT_WORK_ORDERS: WorkOrderResponse[] = [
  makeWorkOrder({ id: 'wo-1', business_key: 'WO-2026-001', turbine_id: 'WT-01', type: 'corrective', title: '齒輪箱維修', status: 'in_progress' }),
  makeWorkOrder({ id: 'wo-2', business_key: 'WO-2026-002', turbine_id: 'WT-02', type: 'preventive', title: '年度保養', status: 'dispatched' }),
];

type Lang = 'en' | 'zh';

// ─── inv mock 狀態 helper ────────────────────────────────────────────────────

let mockRefresh: ReturnType<typeof vi.fn>;

function setInvState(opts: {
  items?: InventoryItemSummary[];
  loading?: boolean;
  error?: string | null;
} = {}) {
  const items = opts.items ?? DEFAULT_ITEMS;
  mockUseInventoryItems.mockReturnValue({
    items,
    total: items.length,
    loading: opts.loading ?? false,
    error: opts.error ?? null,
    refresh: mockRefresh,
  });
}

beforeEach(() => {
  mockRefresh = vi.fn().mockResolvedValue(undefined);
  setInvState();
});

afterEach(() => {
  // 順序：① 先清 useInventoryItems mock 的返回值登錄（避免殘留洩漏到下一測試）
  //       ② cleanup 卸載 DOM
  //       ③ 最後 restoreAllMocks 還原各測試內 vi.spyOn(window,'confirm') 的 spy
  mockUseInventoryItems.mockReset();
  cleanup();
  vi.restoreAllMocks();
});

// ─── render helper ───────────────────────────────────────────────────────────

interface RenderOpts {
  workOrders?: WorkOrderResponse[];
  preselectWorkOrderId?: string | null;
  onClose?: () => void;
  onSubmit?: (req: CreateMaterialRequestPayload) => Promise<void>;
  lang?: Lang;
}

function renderWizard(opts: RenderOpts = {}) {
  const onClose = opts.onClose ?? vi.fn();
  const onSubmit = opts.onSubmit ?? vi.fn().mockResolvedValue(undefined);
  render(
    <ThemeProvider>
      <CreateMaterialRequestWizard
        farmId="farm-a"
        requesterId="req-uuid-001"
        workOrders={opts.workOrders ?? DEFAULT_WORK_ORDERS}
        preselectWorkOrderId={opts.preselectWorkOrderId}
        onClose={onClose}
        onSubmit={onSubmit}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onClose, onSubmit };
}

// ─── 步驟導覽 helper（lang-aware） ───────────────────────────────────────────

const L = (lang: Lang) => ({
  next: lang === 'zh' ? '下一步' : 'Next',
  add: lang === 'zh' ? '加入' : 'Add',
});

/** Step 1 → Step 2（Step 1 無 gating，直接 Next）。 */
function gotoStep2(lang: Lang = 'zh') {
  fireEvent.click(screen.getByRole('button', { name: L(lang).next }));
}

/** 加入指定 sku 的料件到 cart（在 Step 2）。 */
function addItem(sku: string, lang: Lang = 'zh') {
  fireEvent.click(screen.getByRole('button', { name: `${L(lang).add} ${sku}` }));
}

/**
 * Step 1 → Step 3（Next → 加一料件 → Next）。
 * 注意：sku 預設 'SKU-001'，呼叫前須確保該 sku 存在於目前 inv mock 的 items（預設 DEFAULT_ITEMS 有）。
 */
function gotoStep3(sku = 'SKU-001', lang: Lang = 'zh') {
  gotoStep2(lang);
  addItem(sku, lang);
  fireEvent.click(screen.getByRole('button', { name: L(lang).next }));
}

/** 取得 Step 3 檢閱 summary 區塊（h3「檢閱」的容器 div）；集中脆弱的 DOM traversal 一處。 */
function getReviewSection(): HTMLElement {
  const el = screen.getByText('檢閱').parentElement;
  if (!el) throw new Error('summary 檢閱卡未找到');
  return el;
}

// ─── 1. 殼層 / dialog / header / step indicator ──────────────────────────────

describe('CreateMaterialRequestWizard — 殼層與 step indicator', () => {
  it('dialog aria-label 與標題隨 lang 切換（zh）', () => {
    renderWizard({ lang: 'zh' });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', '建立領料單');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('建立領料單');
  });

  it('dialog aria-label 與標題隨 lang 切換（en，不外洩中文）', () => {
    renderWizard({ lang: 'en' });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Create material request');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Create material request');
    expect(screen.queryByText('建立領料單')).not.toBeInTheDocument();
  });

  it('step indicator 起始於第 1 步 / 共 3 步（zh）', () => {
    renderWizard({ lang: 'zh' });
    expect(screen.getByText('第 1 步 / 共 3 步')).toBeInTheDocument();
  });

  it('step indicator 起始於 Step 1 of 3（en）', () => {
    renderWizard({ lang: 'en' });
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });

  it('footer 一律有取消鈕；step 1 無上一步、有下一步、無建立鈕', () => {
    renderWizard();
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '上一步' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立領料單' })).not.toBeInTheDocument();
  });
});

// ─── 2. Step 1：關聯工單 ─────────────────────────────────────────────────────

describe('CreateMaterialRequestWizard — Step 1 關聯工單', () => {
  it('「不關聯工單」選項預設選中（workOrderId 預設 null）', () => {
    renderWizard();
    expect(screen.getByRole('button', { name: /不關聯工單/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('工單卡顯示 business_key / turbine · 類型 / 標題', () => {
    renderWizard();
    const card = screen.getByRole('button', { name: /WO-2026-001/ });
    expect(within(card).getByText('WO-2026-001')).toBeInTheDocument();
    expect(within(card).getByText('WT-01 · 故障維修')).toBeInTheDocument();
    expect(within(card).getByText('齒輪箱維修')).toBeInTheDocument();
  });

  it('closed / cancelled 工單不顯示（避免關聯死案）', () => {
    renderWizard({
      workOrders: [
        makeWorkOrder({ id: 'wo-1', business_key: 'WO-OPEN', status: 'in_progress' }),
        makeWorkOrder({ id: 'wo-2', business_key: 'WO-CLOSED', status: 'closed' }),
        makeWorkOrder({ id: 'wo-3', business_key: 'WO-CANCELLED', status: 'cancelled' }),
      ],
    });
    expect(screen.getByRole('button', { name: /WO-OPEN/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /WO-CLOSED/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /WO-CANCELLED/ })).not.toBeInTheDocument();
  });

  it('工單依 business_key 降冪排序（WO-002 排在 WO-001 前）', () => {
    renderWizard();
    const cards = screen.getAllByRole('button', { name: /WO-2026-00/ });
    expect(cards[0]).toHaveTextContent('WO-2026-002');
    expect(cards[1]).toHaveTextContent('WO-2026-001');
  });

  it('無可關聯工單時顯示提示卡（zh）', () => {
    renderWizard({ workOrders: [] });
    expect(screen.getByText('目前沒有可關聯的進行中工單。')).toBeInTheDocument();
  });

  it('無可關聯工單時顯示提示卡（en）', () => {
    renderWizard({ workOrders: [], lang: 'en' });
    expect(screen.getByText('No open work orders available to link.')).toBeInTheDocument();
  });

  it('點工單卡 → 該卡 aria-pressed、「不關聯」取消選中；再點「不關聯」復原', () => {
    renderWizard();
    const wo = screen.getByRole('button', { name: /WO-2026-001/ });
    const noLink = screen.getByRole('button', { name: /不關聯工單/ });
    fireEvent.click(wo);
    expect(wo).toHaveAttribute('aria-pressed', 'true');
    expect(noLink).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(noLink);
    expect(noLink).toHaveAttribute('aria-pressed', 'true');
    expect(wo).toHaveAttribute('aria-pressed', 'false');
  });

  it('preselectWorkOrderId 預選對應工單卡、「不關聯」非選中', () => {
    renderWizard({ preselectWorkOrderId: 'wo-2' });
    expect(screen.getByRole('button', { name: /WO-2026-002/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /不關聯工單/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('Step 1 下一步無 gating（恆可按）', () => {
    renderWizard();
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });
});

// ─── 3. Step 2：料件 picker + cart ───────────────────────────────────────────

describe('CreateMaterialRequestWizard — Step 2 料件 picker', () => {
  it('進入 Step 2 即呼叫 inv.refresh、顯示搜尋欄與 step indicator 更新', () => {
    renderWizard();
    gotoStep2();
    expect(mockRefresh).toHaveBeenCalledTimes(1); // step→2 的 useEffect 恰呼一次
    expect(screen.getByText('第 2 步 / 共 3 步')).toBeInTheDocument();
    expect(screen.getByLabelText('搜尋料件')).toBeInTheDocument();
  });

  it('可選清單渲染 sku / name / N/U/R 庫存；below_safety 顯示 Low pill', () => {
    renderWizard();
    gotoStep2();
    const card2 = screen.getByRole('button', { name: /加入 SKU-002/ });
    expect(within(card2).getByText('SKU-002')).toBeInTheDocument();
    expect(within(card2).getByText('液壓油封')).toBeInTheDocument();
    expect(within(card2).getByText('N 1 / U 0 / R 0')).toBeInTheDocument();
    expect(within(card2).getByText('不足')).toBeInTheDocument(); // below_safety
    const card1 = screen.getByRole('button', { name: /加入 SKU-001/ });
    expect(within(card1).queryByText('不足')).not.toBeInTheDocument();
  });

  it('inv.loading 且無料件 → 顯示載入中提示', () => {
    setInvState({ items: [], loading: true });
    renderWizard();
    gotoStep2();
    expect(screen.getByText('載入中…')).toBeInTheDocument();
  });

  it('無符合料件 → 顯示空提示', () => {
    setInvState({ items: [], loading: false });
    renderWizard();
    gotoStep2();
    expect(screen.getByText('沒有符合的料件。')).toBeInTheDocument();
  });

  it('inv.error → 顯示 ⚠ 警示卡（純錯誤態，items 空）', () => {
    // items 設空，驗純錯誤態：警示卡出現且左側顯示空提示，無殘留前資料
    setInvState({ error: '庫存服務連線失敗', items: [] });
    renderWizard();
    gotoStep2();
    expect(screen.getByText('⚠ 庫存服務連線失敗')).toBeInTheDocument();
    expect(screen.getByText('沒有符合的料件。')).toBeInTheDocument();
  });

  it('加入料件 → 移到 cart 並從可選清單消失', () => {
    renderWizard();
    gotoStep2();
    addItem('SKU-001');
    // 左側可選清單該料件消失（加入鈕不在）
    expect(screen.queryByRole('button', { name: '加入 SKU-001' })).not.toBeInTheDocument();
    // cart 出現移除鈕
    expect(screen.getByRole('button', { name: '移除 SKU-001' })).toBeInTheDocument();
    expect(screen.getByText('已選 · 1 項')).toBeInTheDocument();
  });

  it('加入多筆料件 → 已選計數更新（2 項）且兩筆皆在 cart', () => {
    renderWizard();
    gotoStep2();
    addItem('SKU-001');
    addItem('SKU-002');
    expect(screen.getByText('已選 · 2 項')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '移除 SKU-001' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '移除 SKU-002' })).toBeInTheDocument();
  });

  it('移除 cart 料件 → 回到可選清單', () => {
    renderWizard();
    gotoStep2();
    addItem('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '移除 SKU-001' }));
    expect(screen.getByRole('button', { name: '加入 SKU-001' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '移除 SKU-001' })).not.toBeInTheDocument();
  });

  it('cart 空 → 提示卡；Next disabled。加入後 → Next enabled', () => {
    renderWizard();
    gotoStep2();
    expect(screen.getByText('從左側挑選料件加入領料單。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    addItem('SKU-001');
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('qty input 夾限 min 1（輸入 0 → 回 1）', () => {
    renderWizard();
    gotoStep2();
    addItem('SKU-001');
    const qty = screen.getByLabelText('預估數量');
    fireEvent.change(qty, { target: { value: '0' } });
    expect(qty).toHaveValue(1);
    fireEvent.change(qty, { target: { value: '' } }); // 空字串（parseInt NaN）→ 仍夾到 1
    expect(qty).toHaveValue(1);
    fireEvent.change(qty, { target: { value: '5' } });
    expect(qty).toHaveValue(5);
  });

  it('stock kind select 提供完整三類選項', () => {
    renderWizard();
    gotoStep2();
    addItem('SKU-001');
    const sel = screen.getByLabelText('庫存類型');
    expect(within(sel).getAllByRole('option')).toHaveLength(3); // 恰三類，無多餘選項
    expect(within(sel).getByRole('option', { name: '全新' })).toBeInTheDocument();
    expect(within(sel).getByRole('option', { name: '良品' })).toBeInTheDocument();
    expect(within(sel).getByRole('option', { name: '維修中' })).toBeInTheDocument();
  });

  it('Back 從 Step 2 回 Step 1', () => {
    renderWizard();
    gotoStep2();
    fireEvent.click(screen.getByRole('button', { name: '上一步' }));
    expect(screen.getByText('第 1 步 / 共 3 步')).toBeInTheDocument();
  });
});

// ─── 4. Step 3：檢閱 summary ─────────────────────────────────────────────────

describe('CreateMaterialRequestWizard — Step 3 檢閱', () => {
  it('summary 反映料件數與每行 sku · name × qty unit · 庫存類型', () => {
    renderWizard();
    gotoStep3('SKU-001');
    expect(screen.getByText('第 3 步 / 共 3 步')).toBeInTheDocument();
    const review = getReviewSection();
    expect(review).toHaveTextContent('SKU-001');
    expect(review).toHaveTextContent('齒輪箱軸承 × 1 pcs');
    expect(review).toHaveTextContent('全新'); // 預設 stock_kind=new
  });

  it('無關聯工單 → summary 關聯工單顯示（無）', () => {
    renderWizard();
    gotoStep3('SKU-001');
    expect(getReviewSection()).toHaveTextContent('（無）');
  });

  it('有關聯工單 → summary 顯示其 business_key', () => {
    renderWizard({ preselectWorkOrderId: 'wo-1' });
    gotoStep3('SKU-001');
    expect(getReviewSection()).toHaveTextContent('WO-2026-001');
  });

  it('Step 3 顯示建立鈕、無下一步', () => {
    renderWizard();
    gotoStep3('SKU-001');
    expect(screen.getByRole('button', { name: '建立領料單' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一步' })).not.toBeInTheDocument();
  });
});

// ─── 5. 送出（buildRequest 序列化 + async 中間態 + 錯誤） ──────────────────────

describe('CreateMaterialRequestWizard — 送出', () => {
  it('送出帶完整 payload：farm_id / requester_id / 無關聯→work_order_id null / items', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWizard({ onSubmit });
    gotoStep3('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      farm_id: 'farm-a',
      requester_id: 'req-uuid-001',
      work_order_id: null,
      items: [{ item_id: 'item-1', estimated_qty: 1, stock_kind: 'new' }],
    });
  });

  it('送出反映關聯工單 + 修改後 qty/stock_kind', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWizard({ onSubmit, preselectWorkOrderId: 'wo-2' });
    gotoStep2();
    addItem('SKU-002');
    fireEvent.change(screen.getByLabelText('預估數量'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('庫存類型'), { target: { value: 'used' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      farm_id: 'farm-a',
      requester_id: 'req-uuid-001',
      work_order_id: 'wo-2',
      items: [{ item_id: 'item-2', estimated_qty: 4, stock_kind: 'used' }],
    });
  });

  it('送出中：建立鈕文案改「建立中…」且 disabled（防重複送出）', async () => {
    let resolveSubmit: () => void = () => {};
    const onSubmit = vi.fn(() => new Promise<void>(res => { resolveSubmit = res; }));
    renderWizard({ onSubmit });
    gotoStep3('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    // 送出鈕 aria-label 恆為「建立領料單」，中間態僅反映在可見文字 → 以 text 查詢
    const submittingBtn = (await screen.findByText('建立中…')).closest('button');
    expect(submittingBtn).toBeDisabled();
    expect(onSubmit).toHaveBeenCalledTimes(1);
    // resolve 後 submitting 應回 false：文案還原「建立領料單」且鈕回復可按（非僅等 onSubmit 計數）
    resolveSubmit();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '建立領料單' })).toBeEnabled(),
    );
    expect(screen.queryByText('建立中…')).not.toBeInTheDocument();
  });

  it('onSubmit reject → 顯示 ⚠ 錯誤卡、不關閉、建立鈕回復可按', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue(new Error('後端拒絕：庫存不足'));
    renderWizard({ onSubmit, onClose });
    gotoStep3('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    expect(await screen.findByText('⚠ 後端拒絕：庫存不足')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '建立領料單' })).toBeEnabled();
  });

  it('onSubmit resolve → 元件不自動 onClose（關閉由呼叫端負責）', async () => {
    const { onClose, onSubmit } = renderWizard();
    gotoStep3('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
  });
});

// ─── 6. 關閉路徑（含 window.confirm 守門） ────────────────────────────────────

describe('CreateMaterialRequestWizard — 關閉路徑', () => {
  it('✕ 鈕 → 直接 onClose（不經 confirm，即使 cart 有料件）', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onClose } = renderWizard();
    gotoStep2();
    addItem('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('取消鈕 → 直接 onClose（不經 confirm）', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onClose } = renderWizard();
    gotoStep2();
    addItem('SKU-001');
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('遮罩點擊 + cart 空 → 直接 onClose（不彈 confirm）', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('dialog'));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('遮罩點擊 + cart 有料件 + confirm OK → onClose', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { onClose } = renderWizard();
    gotoStep2();
    addItem('SKU-001');
    fireEvent.click(screen.getByRole('dialog'));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('遮罩點擊 + cart 有料件 + confirm Cancel → 不 onClose', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { onClose } = renderWizard();
    gotoStep2();
    addItem('SKU-001');
    fireEvent.click(screen.getByRole('dialog'));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('對話框內容點擊（stopPropagation）→ 不 onClose', () => {
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('heading', { level: 2 }));
    expect(onClose).not.toHaveBeenCalled();
  });
});

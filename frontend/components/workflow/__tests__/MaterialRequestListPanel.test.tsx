/**
 * MaterialRequestListPanel component render 測試（WMOM-20260605-03，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/workflow`（領料 tab）的領料單列表面板（`MaterialRequestListPanel.tsx`，203 行）
 * 是核心「庫存派工」模組的領料清單。本面板與 WorkOrderListPanel 高度同構（純 props、無 hook /
 * 無 fetch / 無 internal state），但其真實渲染（status filter / search / counter / error /
 * empty / 每筆 row 的 business_key·work_order 連結·料件項數與預估總量·更新時間·狀態 pill /
 * 點擊接線）此前零覆蓋。
 *
 * 本檔延續 CostPage / FarmOverview / HistoryPage / WorkOrderListPanel 已落地的 render 測試範式
 * （ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），守住面板 UX 契約：
 *
 *   - 基本渲染 + 語系（zh/en 標籤、counter、status 選項；含 negative 守 zh 不外洩）
 *   - status filter Select：選項涵蓋 all + 9 個 MR status；value 反映 prop；onChange → onStatusChange
 *   - search Input：value 反映 prop；onChange → onSearchChange
 *   - Refresh 按鈕：onClick → onRefresh；loading → 文案「載入中…」/「Loading…」且 disabled
 *   - counter：顯示 items.length / total（含 filter 截斷語意）
 *   - error 態：warn card 顯示 ⚠ + 訊息
 *   - empty 態：items=[] 且 !loading !error → 空狀態文案；loading/error 時不顯示空狀態
 *   - 列表 row：business_key / work_order 連結（有/無）/ 料件項數·預估總量 / 更新時間 / 狀態 label；
 *     aria-label 帶 business_key
 *   - 點擊 row → onSelect(該 mr)
 *
 * MaterialRequestListPanel 是純 props 元件，故測試直接以工廠 `makeMR()` 結構式滿足
 * `MaterialRequestResponse` 型別（不用 `as` 強轉），透過 props 注入各情境，斷言聚焦面板自身的
 * 渲染與回呼接線。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import MaterialRequestListPanel from '../MaterialRequestListPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import {
  type MaterialRequestResponse,
  type MaterialRequestItem,
  type MaterialRequestStatus,
} from '../../../services/materialService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/**
 * 產生結構完整的 MaterialRequestItem（不用 `as` 強轉）。
 *
 * 注意：`sku` / `name` / `unit` 是 backend 從 inventory_items join 來的欄位，
 * 在 data drift / 缺漏時實際可為 `null`（見 `materialService.MaterialRequestItem`）。
 * 本工廠預設帶齊以涵蓋常態；若要測試 join 欄位空態（例如 `MaterialRequestDetailModal`
 * 顯示料件名稱的渲染路徑），請傳入 overrides `{ sku: null, name: null, unit: null }`。
 * MaterialRequestListPanel 本身不渲染這三個欄位（只用 `items.length` 與 `estimated_qty` 加總），
 * 故對本面板測試無假綠風險。
 */
function makeItem(overrides: Partial<MaterialRequestItem> = {}): MaterialRequestItem {
  return {
    id: 'mri-1',
    request_id: 'mr-1',
    item_id: 'item-1',
    estimated_qty: 2,
    actual_qty: null,
    stock_kind: 'new',
    sku: 'SKU-001',
    name: '齒輪箱濾芯',
    unit: 'pcs',
    ...overrides,
  };
}

/**
 * 產生結構完整的 MaterialRequestResponse（所有欄位齊備，不用 `as` 強轉）。
 * 各測試以 overrides 客製需要驗證的欄位。
 */
function makeMR(overrides: Partial<MaterialRequestResponse> = {}): MaterialRequestResponse {
  return {
    id: 'mr-1',
    business_key: 'MR-2026-0001',
    farm_id: 'farm-a',
    requester_id: 'user-1',
    work_order_id: 'wo-abcdef0123456789',
    status: 'awaiting_approval',
    items: [makeItem()],
    signoff_chain_id: null,
    requested_at: '2026-06-01T00:00:00Z',
    submitted_at: null,
    approved_at: null,
    dispatched_at: null,
    received_at: null,
    used_at: null,
    closed_at: null,
    cancelled_at: null,
    rejected_at: null,
    cancel_reason: null,
    reject_reason: null,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-02T08:30:00Z',
    ...overrides,
  };
}

interface RenderOpts {
  items?: MaterialRequestResponse[];
  total?: number;
  loading?: boolean;
  error?: string | null;
  status?: MaterialRequestStatus | 'all';
  search?: string;
  lang?: 'en' | 'zh';
}

/** 渲染 MaterialRequestListPanel + 回傳所有 callback spy，供斷言接線。 */
function renderPanel(opts: RenderOpts = {}) {
  const onStatusChange = vi.fn();
  const onSearchChange = vi.fn();
  const onSelect = vi.fn();
  const onRefresh = vi.fn();
  render(
    <ThemeProvider>
      <MaterialRequestListPanel
        items={opts.items ?? [makeMR()]}
        total={opts.total ?? 1}
        loading={opts.loading ?? false}
        error={opts.error ?? null}
        status={opts.status ?? 'all'}
        onStatusChange={onStatusChange}
        search={opts.search ?? ''}
        onSearchChange={onSearchChange}
        onSelect={onSelect}
        onRefresh={onRefresh}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onStatusChange, onSearchChange, onSelect, onRefresh };
}

describe('MaterialRequestListPanel 領料單列表面板', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 基本渲染 + 語系 ─────────────────────────────────────────────────────

  it('zh：渲染狀態/搜尋欄位標籤、重新整理按鈕與領料單筆數', () => {
    renderPanel({ lang: 'zh', items: [makeMR()], total: 3 });
    expect(screen.getByText('狀態')).toBeInTheDocument();
    expect(screen.getByText('搜尋（領料編號 / 工單）')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理列表' })).toHaveTextContent('重新整理');
    // counter：顯示 items.length / total
    expect(screen.getByText('顯示 1 / 3 筆領料單')).toBeInTheDocument();
  });

  it('en：標籤/按鈕/counter 走英文（且不外洩 zh 文案）', () => {
    renderPanel({ lang: 'en', items: [makeMR()], total: 5 });
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Search (key / work order)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh list' })).toHaveTextContent('Refresh');
    expect(screen.getByText('Showing 1 of 5 material requests')).toBeInTheDocument();
    // negative：en 模式不應出現任何 zh 專屬文案（守住 ui() zh/en 沒倒置）
    expect(screen.queryByText('重新整理')).not.toBeInTheDocument();
    expect(screen.queryByText('狀態')).not.toBeInTheDocument();
    expect(screen.queryByText('全部狀態')).not.toBeInTheDocument();
    expect(screen.queryByText(/顯示.*筆領料單/)).not.toBeInTheDocument();
  });

  // ── status filter ──────────────────────────────────────────────────────

  it('status Select：選項涵蓋「全部狀態」+ 9 個 MR status label（順序鎖定）', () => {
    renderPanel({ lang: 'zh', status: 'all' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    // 順序鎖定 MaterialRequestStatusValues（新增/重排 status 會讓測試失敗而非靜默漂移）
    expect(optionTexts).toEqual([
      '全部狀態',
      '草稿',
      '待簽核',
      '已通過',
      '已出庫',
      '已簽收',
      '已使用',
      '已結案',
      '已取消',
      '已駁回',
    ]);
  });

  it('status Select（en）：選項涵蓋「All status」+ 9 個 MR status 英文 label（順序鎖定）', () => {
    renderPanel({ lang: 'en', status: 'all' });
    const select = screen.getByRole('combobox', { name: 'Filter by status' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    // 守住 mrStatusLabel en 路徑拼字（例如 'AWAITING APPROVAL' 而非 'AWAITING_APPROVAL'）
    expect(optionTexts).toEqual([
      'All status',
      'DRAFT',
      'AWAITING APPROVAL',
      'APPROVED',
      'DISPATCHED',
      'RECEIVED',
      'USED',
      'CLOSED',
      'CANCELLED',
      'REJECTED',
    ]);
  });

  it('status Select：value 反映 status prop', () => {
    renderPanel({ status: 'dispatched' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' }) as HTMLSelectElement;
    expect(select.value).toBe('dispatched');
  });

  it('status Select：onChange → onStatusChange 帶選取值', () => {
    const { onStatusChange } = renderPanel({ status: 'all' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' });
    fireEvent.change(select, { target: { value: 'approved' } });
    expect(onStatusChange).toHaveBeenCalledWith('approved');
  });

  // ── search ───────────────────────────────────────────────────────────────

  it('search Input：value 反映 search prop', () => {
    renderPanel({ search: 'MR-2026' });
    const input = screen.getByRole('textbox', { name: '搜尋領料單' }) as HTMLInputElement;
    expect(input.value).toBe('MR-2026');
  });

  it('search Input：onChange → onSearchChange 帶輸入值', () => {
    const { onSearchChange } = renderPanel();
    const input = screen.getByRole('textbox', { name: '搜尋領料單' });
    fireEvent.change(input, { target: { value: 'MR-0009' } });
    expect(onSearchChange).toHaveBeenCalledWith('MR-0009');
  });

  // ── refresh ──────────────────────────────────────────────────────────────

  it('Refresh 按鈕：onClick → onRefresh', () => {
    const { onRefresh } = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '重新整理列表' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('loading=true：Refresh 按鈕文案顯示「載入中…」且 disabled（防載入中重複點擊）', () => {
    renderPanel({ loading: true });
    const btn = screen.getByRole('button', { name: '重新整理列表' });
    expect(btn).toHaveTextContent('載入中…');
    // loading 期間按鈕應 disabled（Btn loading prop → isDisabled），避免重複觸發 onRefresh
    expect(btn).toBeDisabled();
  });

  it('loading=true（en）：Refresh 按鈕文案顯示「Loading…」且 disabled', () => {
    renderPanel({ loading: true, lang: 'en' });
    const btn = screen.getByRole('button', { name: 'Refresh list' });
    expect(btn).toHaveTextContent('Loading…');
    expect(btn).toBeDisabled();
  });

  it('loading=true：Refresh 按鈕 disabled → 點擊不觸發 onRefresh（守住「防重複觸發」UX 契約）', () => {
    const { onRefresh } = renderPanel({ loading: true });
    fireEvent.click(screen.getByRole('button', { name: '重新整理列表' }));
    // 守住行為而非僅屬性：即使日後 Btn 改用 role=button + aria-disabled（原生 disabled 失效），此斷言仍能抓回歸
    expect(onRefresh).not.toHaveBeenCalled();
  });

  // ── error 態 ───────────────────────────────────────────────────────────

  it('error：顯示 warn card 帶 ⚠ 與錯誤訊息', () => {
    renderPanel({ error: '載入領料單失敗（500）' });
    // 直接斷言錯誤訊息文字節點本身（不繞過 ⚠ icon，避免 icon 被抽成獨立元素時的結構耦合）
    expect(screen.getByText(/載入領料單失敗（500）/)).toBeInTheDocument();
    // 另獨立守住 ⚠ 視覺提示存在
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });

  // ── empty 態 ───────────────────────────────────────────────────────────

  it('empty（items=[] 且 !loading !error）：顯示空狀態文案', () => {
    renderPanel({ items: [], total: 0 });
    expect(screen.getByText('目前沒有符合條件的領料單。')).toBeInTheDocument();
  });

  it('empty 態在 loading 中不顯示（避免閃爍）', () => {
    renderPanel({ items: [], total: 0, loading: true });
    expect(screen.queryByText('目前沒有符合條件的領料單。')).not.toBeInTheDocument();
  });

  it('empty 態在 error 時不顯示（讓位給錯誤卡）', () => {
    renderPanel({ items: [], total: 0, error: 'boom' });
    expect(screen.queryByText('目前沒有符合條件的領料單。')).not.toBeInTheDocument();
    // 直接比對錯誤訊息文字（不繞過 ⚠ icon），避免日後別處新增含 ⚠ 元素時 getByText(/⚠/) 命中多元素而炸
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });

  // ── 列表 row 渲染 ──────────────────────────────────────────────────────

  it('row：渲染 business_key / 關聯工單 / 料件項數·預估總量 / 更新時間 / 狀態 label', () => {
    renderPanel({
      lang: 'zh',
      items: [
        makeMR({
          business_key: 'MR-2026-0009',
          work_order_id: 'wo-aaaa1122334455',
          status: 'dispatched',
          items: [
            makeItem({ id: 'i1', estimated_qty: 2 }),
            makeItem({ id: 'i2', estimated_qty: 3 }),
          ],
        }),
      ],
    });
    const row = screen.getByRole('button', { name: '開啟領料單 MR-2026-0009' });
    expect(row).toHaveTextContent('MR-2026-0009');
    // 關聯工單：顯示「工單 …{後 8 碼}」
    expect(row).toHaveTextContent('工單 …22334455');
    // 料件摘要：2 項料件、預估總量 2 + 3 = 5
    expect(row).toHaveTextContent('2 項料件 · 預估總量 5');
    expect(row).toHaveTextContent('已出庫'); // mrStatusLabel(dispatched, zh)
    // 更新時間：makeMR 預設 updated_at '2026-06-02T08:30:00Z' → fmtDateTime(Asia/Taipei) = 2026-06-02 16:30
    expect(row).toHaveTextContent('更新於');
    expect(row).toHaveTextContent('2026-06-02 16:30');
  });

  it('row：work_order_id 為 null → 顯示「（無關聯工單）」', () => {
    renderPanel({ items: [makeMR({ work_order_id: null })] });
    const row = screen.getByRole('button', { name: /開啟領料單/ });
    expect(row).toHaveTextContent('（無關聯工單）');
  });

  it('row（en）：單一料件用單數 item、work_order 連結走 WO 前綴', () => {
    renderPanel({
      lang: 'en',
      items: [makeMR({ work_order_id: 'wo-zzzz9988776655', items: [makeItem({ estimated_qty: 4 })] })],
    });
    const row = screen.getByRole('button', { name: /Open material request/ });
    // 單數 item（無 s）+ 預估總量 4
    expect(row).toHaveTextContent('1 item · est. total qty 4');
    expect(row).toHaveTextContent('WO …88776655');
    expect(row).toHaveTextContent('Updated');
  });

  it('多筆領料單：各自渲染一張可點擊 row（以 business_key 區分）', () => {
    renderPanel({
      items: [
        makeMR({ id: 'a', business_key: 'MR-A' }),
        makeMR({ id: 'b', business_key: 'MR-B' }),
        makeMR({ id: 'c', business_key: 'MR-C' }),
      ],
      total: 3,
    });
    expect(screen.getByRole('button', { name: '開啟領料單 MR-A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟領料單 MR-B' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟領料單 MR-C' })).toBeInTheDocument();
    // counter 與 items.length / total 對齊
    expect(screen.getByText('顯示 3 / 3 筆領料單')).toBeInTheDocument();
  });

  it('counter：items 被 filter 截斷（items.length < total）時如實顯示 N / total', () => {
    renderPanel({
      items: [makeMR({ id: 'a', business_key: 'MR-A' }), makeMR({ id: 'b', business_key: 'MR-B' })],
      total: 50,
    });
    expect(screen.getByText('顯示 2 / 50 筆領料單')).toBeInTheDocument();
  });

  // ── 點擊接線 ─────────────────────────────────────────────────────────────

  it('點擊 row → onSelect 帶該筆 material request', () => {
    const target = makeMR({ id: 'b', business_key: 'MR-B' });
    const { onSelect } = renderPanel({
      items: [makeMR({ id: 'a', business_key: 'MR-A' }), target],
      total: 2,
    });
    fireEvent.click(screen.getByRole('button', { name: '開啟領料單 MR-B' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    // 守語意契約（傳回含正確 id 的領料單）而非物件 identity，避免日後面板淺複製 items 時假紅
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: target.id, business_key: target.business_key }),
    );
  });
});

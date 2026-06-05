/**
 * InventoryListPanel component render 測試（WMOM-20260605-04，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/workflow`（庫存 tab）的料件列表面板（`InventoryListPanel.tsx`，286 行）是
 * 核心「庫存」模組的主操作清單。先前無任何測試覆蓋本面板的真實渲染
 * （warehouse selector / below-safety toggle / search / counter / error / empty /
 * 每筆 row 的 SKU·name·unit·三欄 stock·安全/可用·LOW pill·最後出庫時間 / 點擊接線）。
 *
 * 本檔延續 WorkOrderListPanel / MaterialRequestListPanel 已落地的 render 測試範式
 * （ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），守住面板 UX 契約：
 *
 *   - 基本渲染 + 語系（zh/en 標籤、counter；含 negative 守 zh 不外洩）
 *   - warehouse Select：選項涵蓋「全部倉」+ 各倉（default 倉前綴 ★）；value 反映 prop；
 *     onChange → onWarehouseChange
 *   - below-safety toggle：文案 / variant 隨 belowSafetyOnly 切換；aria-pressed 反映狀態；
 *     onClick → onBelowSafetyChange(取反)
 *   - search Input：value 反映 prop；onChange → onSearchChange
 *   - Refresh 按鈕：onClick → onRefresh；loading → 文案「載入中…」/「Loading…」且 disabled
 *   - counter：顯示 items.length / total
 *   - error 態：warn card 顯示 ⚠ + 訊息
 *   - empty 態：items=[] 且 !loading !error → 空狀態文案；loading/error 時不顯示空狀態
 *   - 列表 row：SKU / name / unit / 三欄 stock / 安全·可用 / LOW pill（below_safety）/
 *     最後出庫時間（last_used_at 時區）；aria-label 帶 SKU
 *   - 點擊 row → onSelect(該 item)
 *
 * InventoryListPanel 是純 props 元件（無 hook / 無 fetch / 無 internal state），
 * 故測試直接以工廠 `makeItem()` / `makeWarehouse()` 結構式滿足型別（不用 `as` 強轉），
 * 透過 props 注入各情境，斷言聚焦面板自身的渲染與回呼接線。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import InventoryListPanel from '../InventoryListPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  InventoryItemResponse,
  WarehouseResponse,
} from '../../../services/inventoryService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/**
 * 產生結構完整的 InventoryItemResponse（所有欄位齊備，不用 `as` 強轉）。
 *
 * 注意：`total_available` / `below_safety` 是 backend `@computed_field`，
 * 前端視為唯讀；本工廠預設給一致的值（available = new+used 之類），
 * 但測試若要驗證 LOW pill 等行為，請以 overrides 明確指定 `below_safety`，
 * 避免依賴工廠對 computed 欄位的推導假設。
 */
function makeItem(overrides: Partial<InventoryItemResponse> = {}): InventoryItemResponse {
  return {
    id: 'inv-1',
    sku: 'BRG-6209',
    name: '齒輪箱主軸承',
    description: '高速軸承，更換週期約 5 年。',
    unit: '顆',
    farm_id: 'farm-a',
    warehouse_id: 'wh-1',
    stock_new: 3,
    stock_used: 1,
    stock_repairing: 0,
    safety_stock: 2,
    unit_cost: '12500.00',
    last_received_at: '2026-05-01T00:00:00Z',
    last_used_at: '2026-06-02T08:30:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-06-02T08:30:00Z',
    total_available: 4,
    below_safety: false,
    ...overrides,
  };
}

/** 產生結構完整的 WarehouseResponse。 */
function makeWarehouse(overrides: Partial<WarehouseResponse> = {}): WarehouseResponse {
  return {
    id: 'wh-1',
    farm_id: 'farm-a',
    name: '岸基倉',
    location_kind: 'onshore_base',
    is_default: false,
    ...overrides,
  };
}

interface RenderOpts {
  items?: InventoryItemResponse[];
  total?: number;
  loading?: boolean;
  error?: string | null;
  warehouses?: WarehouseResponse[];
  warehouseId?: string | 'all';
  belowSafetyOnly?: boolean;
  search?: string;
  lang?: 'en' | 'zh';
}

/** 渲染 InventoryListPanel + 回傳所有 callback spy，供斷言接線。 */
function renderPanel(opts: RenderOpts = {}) {
  const onWarehouseChange = vi.fn();
  const onBelowSafetyChange = vi.fn();
  const onSearchChange = vi.fn();
  const onSelect = vi.fn();
  const onRefresh = vi.fn();
  render(
    <ThemeProvider>
      <InventoryListPanel
        items={opts.items ?? [makeItem()]}
        total={opts.total ?? 1}
        loading={opts.loading ?? false}
        error={opts.error ?? null}
        warehouses={opts.warehouses ?? []}
        warehouseId={opts.warehouseId ?? 'all'}
        onWarehouseChange={onWarehouseChange}
        belowSafetyOnly={opts.belowSafetyOnly ?? false}
        onBelowSafetyChange={onBelowSafetyChange}
        search={opts.search ?? ''}
        onSearchChange={onSearchChange}
        onSelect={onSelect}
        onRefresh={onRefresh}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onWarehouseChange, onBelowSafetyChange, onSearchChange, onSelect, onRefresh };
}

describe('InventoryListPanel 庫存料件列表面板', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 基本渲染 + 語系 ─────────────────────────────────────────────────────

  it('zh：渲染倉別/搜尋欄位標籤、重新整理按鈕與料件筆數', () => {
    renderPanel({ lang: 'zh', items: [makeItem()], total: 3 });
    expect(screen.getByText('倉別')).toBeInTheDocument();
    expect(screen.getByText('搜尋（料號 / 名稱）')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理列表' })).toHaveTextContent('重新整理');
    // counter：顯示 items.length / total
    expect(screen.getByText('顯示 1 / 3 個料件')).toBeInTheDocument();
  });

  it('en：標籤/按鈕/counter 走英文（且不外洩 zh 文案）', () => {
    renderPanel({ lang: 'en', items: [makeItem()], total: 5 });
    expect(screen.getByText('Warehouse')).toBeInTheDocument();
    expect(screen.getByText('Search (SKU / name)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh list' })).toHaveTextContent('Refresh');
    expect(screen.getByText('Showing 1 of 5 inventory items')).toBeInTheDocument();
    // negative：en 模式不應出現任何 zh 專屬文案（守住 ui() zh/en 沒倒置）
    expect(screen.queryByText('重新整理')).not.toBeInTheDocument();
    expect(screen.queryByText('倉別')).not.toBeInTheDocument();
    expect(screen.queryByText('全部倉')).not.toBeInTheDocument();
    expect(screen.queryByText(/顯示.*個料件/)).not.toBeInTheDocument();
  });

  // ── warehouse filter ─────────────────────────────────────────────────────

  it('warehouse Select：選項涵蓋「全部倉」+ 各倉（default 倉前綴 ★）', () => {
    renderPanel({
      lang: 'zh',
      warehouseId: 'all',
      warehouses: [
        makeWarehouse({ id: 'wh-1', name: '岸基倉', is_default: true }),
        makeWarehouse({ id: 'wh-2', name: '船上倉', is_default: false }),
      ],
    });
    const select = screen.getByRole('combobox', { name: '依倉別過濾' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    expect(optionTexts).toEqual(['全部倉', '★ 岸基倉', '船上倉']);
  });

  it('warehouse Select（en）：「全部倉」選項走英文「All warehouses」（不外洩 zh）', () => {
    renderPanel({
      lang: 'en',
      warehouseId: 'all',
      warehouses: [makeWarehouse({ id: 'wh-1', name: 'Onshore base' })],
    });
    const select = screen.getByRole('combobox', { name: 'Filter by warehouse' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    // 正向守住 en 選項文案（避免 ui('All warehouses','全部倉') 參數倒置時僅靠 negative test 誤判通過）
    expect(optionTexts).toEqual(['All warehouses', 'Onshore base']);
    expect(screen.queryByText('全部倉')).not.toBeInTheDocument();
  });

  it('warehouse Select：value 反映 warehouseId prop', () => {
    renderPanel({
      warehouseId: 'wh-2',
      warehouses: [makeWarehouse({ id: 'wh-2', name: '船上倉' })],
    });
    const select = screen.getByRole('combobox', { name: '依倉別過濾' }) as HTMLSelectElement;
    expect(select.value).toBe('wh-2');
  });

  it('warehouse Select：onChange → onWarehouseChange 帶選取值', () => {
    const { onWarehouseChange } = renderPanel({
      warehouseId: 'all',
      warehouses: [makeWarehouse({ id: 'wh-2', name: '船上倉' })],
    });
    const select = screen.getByRole('combobox', { name: '依倉別過濾' });
    fireEvent.change(select, { target: { value: 'wh-2' } });
    expect(onWarehouseChange).toHaveBeenCalledWith('wh-2');
  });

  // ── below-safety toggle ─────────────────────────────────────────────────

  it('below-safety toggle：未開啟時文案「全部」、aria-pressed=false', () => {
    renderPanel({ belowSafetyOnly: false });
    const btn = screen.getByRole('button', { name: '切換低於安全庫存過濾' });
    expect(btn).toHaveTextContent('全部');
    expect(btn).toHaveAttribute('aria-pressed', 'false');
  });

  it('below-safety toggle：開啟時文案「只顯示低於安全庫存」、aria-pressed=true', () => {
    renderPanel({ belowSafetyOnly: true });
    const btn = screen.getByRole('button', { name: '切換低於安全庫存過濾' });
    expect(btn).toHaveTextContent('只顯示低於安全庫存');
    expect(btn).toHaveAttribute('aria-pressed', 'true');
  });

  it('below-safety toggle（en，未開啟）：文案顯示「All stock」（不外洩 zh）', () => {
    renderPanel({ belowSafetyOnly: false, lang: 'en' });
    expect(screen.getByRole('button', { name: 'Toggle low-stock filter' })).toHaveTextContent(
      'All stock',
    );
    // 守住 en/zh 參數沒倒置（負向：en 模式不外洩 zh 文案）
    expect(screen.queryByText('全部')).not.toBeInTheDocument();
  });

  it('below-safety toggle（en，開啟）：文案顯示「Showing low stock only」', () => {
    renderPanel({ belowSafetyOnly: true, lang: 'en' });
    expect(screen.getByRole('button', { name: 'Toggle low-stock filter' })).toHaveTextContent(
      'Showing low stock only',
    );
  });

  it('below-safety toggle：belowSafetyOnly=false 時 onClick → onBelowSafetyChange(true)', () => {
    const { onBelowSafetyChange } = renderPanel({ belowSafetyOnly: false });
    fireEvent.click(screen.getByRole('button', { name: '切換低於安全庫存過濾' }));
    expect(onBelowSafetyChange).toHaveBeenCalledWith(true);
  });

  it('below-safety toggle：belowSafetyOnly=true 時 onClick → onBelowSafetyChange(false)（守 !belowSafetyOnly 反轉）', () => {
    const { onBelowSafetyChange } = renderPanel({ belowSafetyOnly: true });
    fireEvent.click(screen.getByRole('button', { name: '切換低於安全庫存過濾' }));
    expect(onBelowSafetyChange).toHaveBeenCalledWith(false);
  });

  // ── search ───────────────────────────────────────────────────────────────

  it('search Input：value 反映 search prop', () => {
    renderPanel({ search: 'BRG-' });
    const input = screen.getByRole('textbox', { name: '搜尋料件' }) as HTMLInputElement;
    expect(input.value).toBe('BRG-');
  });

  it('search Input：onChange → onSearchChange 帶輸入值', () => {
    const { onSearchChange } = renderPanel();
    const input = screen.getByRole('textbox', { name: '搜尋料件' });
    fireEvent.change(input, { target: { value: 'gearbox' } });
    expect(onSearchChange).toHaveBeenCalledWith('gearbox');
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

  it('loading=true：點擊 disabled 的 Refresh 不觸發 onRefresh（守防重複觸發行為）', () => {
    const { onRefresh } = renderPanel({ loading: true });
    fireEvent.click(screen.getByRole('button', { name: '重新整理列表' }));
    expect(onRefresh).not.toHaveBeenCalled();
  });

  // ── error 態 ───────────────────────────────────────────────────────────

  it('error：顯示 warn card 帶 ⚠ 與錯誤訊息', () => {
    renderPanel({ error: '載入庫存失敗（500）' });
    // 直接斷言錯誤訊息文字節點本身（不繞過 ⚠ icon，避免 icon 被抽成獨立元素時的結構耦合）
    expect(screen.getByText(/載入庫存失敗（500）/)).toBeInTheDocument();
    // 另獨立守住 ⚠ 視覺提示存在
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });

  // ── empty 態 ───────────────────────────────────────────────────────────

  it('empty（items=[] 且 !loading !error）：顯示空狀態文案', () => {
    renderPanel({ items: [], total: 0 });
    expect(screen.getByText('目前沒有符合條件的料件。')).toBeInTheDocument();
  });

  it('empty 態在 loading 中不顯示（避免閃爍）', () => {
    renderPanel({ items: [], total: 0, loading: true });
    expect(screen.queryByText('目前沒有符合條件的料件。')).not.toBeInTheDocument();
  });

  it('empty 態在 error 時不顯示（讓位給錯誤卡）', () => {
    renderPanel({ items: [], total: 0, error: 'boom' });
    expect(screen.queryByText('目前沒有符合條件的料件。')).not.toBeInTheDocument();
    // 直接比對訊息文字（避免日後別處新增含 ⚠ 元素時 getByText(/⚠/) 命中多元素而炸）
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });

  // ── 列表 row 渲染 ──────────────────────────────────────────────────────

  it('row：渲染 SKU / name / 單位 / 三欄 stock / 安全·可用 / 最後出庫時間', () => {
    renderPanel({
      lang: 'zh',
      items: [
        makeItem({
          sku: 'GBX-OIL-32',
          name: '齒輪箱潤滑油',
          unit: '桶',
          stock_new: 5,
          stock_used: 2,
          stock_repairing: 1,
          safety_stock: 3,
          total_available: 7,
          below_safety: false,
          last_used_at: '2026-06-02T08:30:00Z',
        }),
      ],
    });
    const row = screen.getByRole('button', { name: '開啟料件 GBX-OIL-32' });
    expect(row).toHaveTextContent('GBX-OIL-32');
    expect(row).toHaveTextContent('齒輪箱潤滑油');
    expect(row).toHaveTextContent('單位: 桶');
    // 三欄 stock label（全新 / 良品 / 維修中）
    expect(row).toHaveTextContent('全新');
    expect(row).toHaveTextContent('良品');
    expect(row).toHaveTextContent('維修中');
    // 安全 / 可用
    expect(row).toHaveTextContent('安全: 3');
    expect(row).toHaveTextContent('可用: 7');
    // 最後出庫時間：last_used_at '2026-06-02T08:30:00Z' → fmtDateTime(Asia/Taipei) = 2026-06-02 16:30
    expect(row).toHaveTextContent('最後出庫');
    expect(row).toHaveTextContent('2026-06-02 16:30');
  });

  it('row：below_safety=true → 顯示 LOW pill「低於安全」', () => {
    renderPanel({ items: [makeItem({ sku: 'LOW-1', below_safety: true })] });
    const lowRow = screen.getByRole('button', { name: '開啟料件 LOW-1' });
    expect(lowRow).toHaveTextContent('低於安全');
  });

  it('row：below_safety=false → 不顯示 LOW pill', () => {
    renderPanel({ items: [makeItem({ sku: 'OK-1', below_safety: false })] });
    const okRow = screen.getByRole('button', { name: '開啟料件 OK-1' });
    expect(okRow).not.toHaveTextContent('低於安全');
  });

  it('row：last_used_at 為 null → 不顯示「最後出庫」', () => {
    renderPanel({ items: [makeItem({ last_used_at: null })] });
    const row = screen.getByRole('button', { name: /開啟料件/ });
    expect(row).not.toHaveTextContent('最後出庫');
  });

  it('多筆料件：各自渲染一張可點擊 row（以 SKU 區分）', () => {
    renderPanel({
      items: [
        makeItem({ id: 'a', sku: 'SKU-A' }),
        makeItem({ id: 'b', sku: 'SKU-B' }),
        makeItem({ id: 'c', sku: 'SKU-C' }),
      ],
      total: 3,
    });
    expect(screen.getByRole('button', { name: '開啟料件 SKU-A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟料件 SKU-B' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟料件 SKU-C' })).toBeInTheDocument();
    // counter 與 items.length / total 對齊
    expect(screen.getByText('顯示 3 / 3 個料件')).toBeInTheDocument();
  });

  it('counter：items 被 filter 截斷（items.length < total）時如實顯示 N / total', () => {
    renderPanel({
      items: [makeItem({ id: 'a', sku: 'SKU-A' }), makeItem({ id: 'b', sku: 'SKU-B' })],
      total: 50,
    });
    expect(screen.getByText('顯示 2 / 50 個料件')).toBeInTheDocument();
  });

  // ── 點擊接線 ─────────────────────────────────────────────────────────────

  it('點擊 row → onSelect 帶該筆 inventory item', () => {
    const target = makeItem({ id: 'b', sku: 'SKU-B' });
    const { onSelect } = renderPanel({
      items: [makeItem({ id: 'a', sku: 'SKU-A' }), target],
      total: 2,
    });
    fireEvent.click(screen.getByRole('button', { name: '開啟料件 SKU-B' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    // 守語意契約（傳回含正確 id 的料件）而非物件 identity，避免日後面板淺複製 items 時假紅
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: target.id, sku: target.sku }),
    );
  });
});

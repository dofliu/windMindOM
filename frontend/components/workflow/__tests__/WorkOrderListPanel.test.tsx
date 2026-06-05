/**
 * WorkOrderListPanel component render 測試（WMOM-20260605-02，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/workflow`（工單 tab）的工單列表面板（`WorkOrderListPanel.tsx`，221 行）是
 * 核心「派工」模組的主操作清單。先前 `WorkflowPage.test.tsx` 把本面板 mock 成 marker，
 * 其真實渲染（status filter / search / counter / error / empty / 每筆 row 的
 * business_key·turbine·type·title·更新時間·預估工時·優先級+狀態 pill / 點擊接線）零覆蓋。
 *
 * 本檔延續 CostPage / FarmOverview / HistoryPage / WorkflowPage 已落地的 render 測試範式
 * （ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），守住面板 UX 契約：
 *
 *   - 基本渲染 + 語系（zh/en 標籤、counter、status 選項；含 negative 守 zh 不外洩）
 *   - status filter Select：選項涵蓋 all + 7 個 status；onChange → onStatusChange
 *   - search Input：onChange → onSearchChange；value 反映 prop
 *   - Refresh 按鈕：onClick → onRefresh；loading → 文案「載入中…」/「Loading…」
 *   - counter：顯示 items.length / total
 *   - error 態：warn card 顯示 ⚠ + 訊息
 *   - empty 態：items=[] 且 !loading !error → 空狀態文案；loading/error 時不顯示空狀態
 *   - 列表 row：business_key / turbine · type / title / 更新時間 / 預估工時 /
 *     優先級+狀態 label；estimated_hours null → 不顯示「預估」；aria-label 帶 business_key
 *   - 點擊 row → onSelect(該 wo)
 *
 * WorkOrderListPanel 是純 props 元件（無 hook / 無 fetch / 無 internal state），
 * 故測試直接以工廠 `makeWO()` 結構式滿足 `WorkOrderResponse` 型別（不用 `as` 強轉），
 * 透過 props 注入各情境，斷言聚焦面板自身的渲染與回呼接線。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import WorkOrderListPanel from '../WorkOrderListPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import {
  type WorkOrderResponse,
  type WorkOrderStatus,
} from '../../../services/workOrderService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/**
 * 產生結構完整的 WorkOrderResponse（所有欄位齊備，不用 `as` 強轉）。
 * 各測試以 overrides 客製需要驗證的欄位。
 */
function makeWO(overrides: Partial<WorkOrderResponse> = {}): WorkOrderResponse {
  return {
    id: 'wo-1',
    business_key: 'WO-2026-0001',
    farm_id: 'farm-a',
    turbine_id: 'WTG-01',
    type: 'corrective',
    status: 'dispatched',
    priority: 'high',
    title: '齒輪箱高溫處置',
    description: '齒輪箱溫度超過門檻，需現場檢查潤滑系統。',
    source_alarm_id: null,
    source_alarm_code: null,
    assignee_id: null,
    crew_size: 2,
    estimated_hours: 4,
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
    created_at: '2026-06-01T00:00:00Z',
    created_by: null,
    updated_at: '2026-06-02T08:30:00Z',
    ...overrides,
  };
}

interface RenderOpts {
  items?: WorkOrderResponse[];
  total?: number;
  loading?: boolean;
  error?: string | null;
  status?: WorkOrderStatus | 'all';
  search?: string;
  lang?: 'en' | 'zh';
}

/** 渲染 WorkOrderListPanel + 回傳所有 callback spy，供斷言接線。 */
function renderPanel(opts: RenderOpts = {}) {
  const onStatusChange = vi.fn();
  const onSearchChange = vi.fn();
  const onSelect = vi.fn();
  const onRefresh = vi.fn();
  render(
    <ThemeProvider>
      <WorkOrderListPanel
        items={opts.items ?? [makeWO()]}
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

describe('WorkOrderListPanel 工單列表面板', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 基本渲染 + 語系 ─────────────────────────────────────────────────────

  it('zh：渲染狀態/搜尋欄位標籤、重新整理按鈕與工單筆數', () => {
    renderPanel({ lang: 'zh', items: [makeWO()], total: 3 });
    expect(screen.getByText('狀態')).toBeInTheDocument();
    expect(screen.getByText('搜尋（編號 / 標題 / 風機）')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理列表' })).toHaveTextContent('重新整理');
    // counter：顯示 items.length / total
    expect(screen.getByText('顯示 1 / 3 筆工單')).toBeInTheDocument();
  });

  it('en：標籤/按鈕/counter 走英文（且不外洩 zh 文案）', () => {
    renderPanel({ lang: 'en', items: [makeWO()], total: 5 });
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Search (key / title / turbine)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh list' })).toHaveTextContent('Refresh');
    expect(screen.getByText('Showing 1 of 5 work orders')).toBeInTheDocument();
    // negative：en 模式不應出現任何 zh 專屬文案（守住 ui() zh/en 沒倒置）
    expect(screen.queryByText('重新整理')).not.toBeInTheDocument();
    expect(screen.queryByText('狀態')).not.toBeInTheDocument();
    expect(screen.queryByText('全部狀態')).not.toBeInTheDocument();
    expect(screen.queryByText(/顯示.*筆工單/)).not.toBeInTheDocument();
  });

  // ── status filter ──────────────────────────────────────────────────────

  it('status Select：選項涵蓋「全部狀態」+ 7 個工單 status label', () => {
    renderPanel({ lang: 'zh', status: 'all' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    expect(optionTexts).toEqual([
      '全部狀態',
      '草稿',
      '已派工',
      '進行中',
      '待簽核',
      '已結案',
      '已取消',
      '重開',
    ]);
  });

  it('status Select：value 反映 status prop', () => {
    renderPanel({ status: 'in_progress' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' }) as HTMLSelectElement;
    expect(select.value).toBe('in_progress');
  });

  it('status Select：onChange → onStatusChange 帶選取值', () => {
    const { onStatusChange } = renderPanel({ status: 'all' });
    const select = screen.getByRole('combobox', { name: '依狀態過濾' });
    fireEvent.change(select, { target: { value: 'awaiting_signoff' } });
    expect(onStatusChange).toHaveBeenCalledWith('awaiting_signoff');
  });

  // ── search ───────────────────────────────────────────────────────────────

  it('search Input：value 反映 search prop', () => {
    renderPanel({ search: 'gearbox' });
    const input = screen.getByRole('textbox', { name: '搜尋工單' }) as HTMLInputElement;
    expect(input.value).toBe('gearbox');
  });

  it('search Input：onChange → onSearchChange 帶輸入值', () => {
    const { onSearchChange } = renderPanel();
    const input = screen.getByRole('textbox', { name: '搜尋工單' });
    fireEvent.change(input, { target: { value: 'WTG-01' } });
    expect(onSearchChange).toHaveBeenCalledWith('WTG-01');
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

  // ── error 態 ───────────────────────────────────────────────────────────

  it('error：顯示 warn card 帶 ⚠ 與錯誤訊息', () => {
    renderPanel({ error: '載入工單失敗（500）' });
    // 直接斷言錯誤訊息文字節點本身（不繞過 ⚠ icon，避免 icon 被抽成獨立元素時的結構耦合）
    expect(screen.getByText(/載入工單失敗（500）/)).toBeInTheDocument();
    // 另獨立守住 ⚠ 視覺提示存在
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });

  // ── empty 態 ───────────────────────────────────────────────────────────

  it('empty（items=[] 且 !loading !error）：顯示空狀態文案', () => {
    renderPanel({ items: [], total: 0 });
    expect(screen.getByText('目前沒有符合條件的工單。')).toBeInTheDocument();
  });

  it('empty 態在 loading 中不顯示（避免閃爍）', () => {
    renderPanel({ items: [], total: 0, loading: true });
    expect(screen.queryByText('目前沒有符合條件的工單。')).not.toBeInTheDocument();
  });

  it('empty 態在 error 時不顯示（讓位給錯誤卡）', () => {
    renderPanel({ items: [], total: 0, error: 'boom' });
    expect(screen.queryByText('目前沒有符合條件的工單。')).not.toBeInTheDocument();
    expect(screen.getByText(/⚠/)).toHaveTextContent('boom');
  });

  // ── 列表 row 渲染 ──────────────────────────────────────────────────────

  it('row：渲染 business_key / turbine · 類型 / 標題 / 優先級 + 狀態 label', () => {
    renderPanel({
      lang: 'zh',
      items: [
        makeWO({
          business_key: 'WO-2026-0009',
          turbine_id: 'WTG-07',
          type: 'inspection',
          title: '年度定檢',
          priority: 'critical',
          status: 'in_progress',
        }),
      ],
    });
    const row = screen.getByRole('button', { name: '開啟工單 WO-2026-0009' });
    expect(row).toHaveTextContent('WO-2026-0009');
    expect(row).toHaveTextContent('WTG-07 · 定檢'); // typeLabel(inspection, zh)
    expect(row).toHaveTextContent('年度定檢');
    expect(row).toHaveTextContent('緊急'); // priorityLabel(critical, zh)
    expect(row).toHaveTextContent('進行中'); // statusLabel(in_progress, zh)
    // 更新時間：makeWO 預設 updated_at '2026-06-02T08:30:00Z' → fmtDateTime(Asia/Taipei) = 2026-06-02 16:30
    expect(row).toHaveTextContent('更新於');
    expect(row).toHaveTextContent('2026-06-02 16:30');
  });

  it('row：estimated_hours 有值 → 顯示「預估 Nh」', () => {
    renderPanel({ items: [makeWO({ estimated_hours: 6 })] });
    const row = screen.getByRole('button', { name: /開啟工單/ });
    expect(row).toHaveTextContent('預估 6h');
  });

  it('row：estimated_hours 為 null → 不顯示「預估」', () => {
    renderPanel({ items: [makeWO({ estimated_hours: null })] });
    const row = screen.getByRole('button', { name: /開啟工單/ });
    expect(row).not.toHaveTextContent('預估');
  });

  it('多筆工單：各自渲染一張可點擊 row（以 business_key 區分）', () => {
    renderPanel({
      items: [
        makeWO({ id: 'a', business_key: 'WO-A' }),
        makeWO({ id: 'b', business_key: 'WO-B' }),
        makeWO({ id: 'c', business_key: 'WO-C' }),
      ],
      total: 3,
    });
    expect(screen.getByRole('button', { name: '開啟工單 WO-A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟工單 WO-B' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟工單 WO-C' })).toBeInTheDocument();
    // counter 與 items.length / total 對齊
    expect(screen.getByText('顯示 3 / 3 筆工單')).toBeInTheDocument();
  });

  it('counter：items 被 filter 截斷（items.length < total）時如實顯示 N / total', () => {
    renderPanel({
      items: [makeWO({ id: 'a', business_key: 'WO-A' }), makeWO({ id: 'b', business_key: 'WO-B' })],
      total: 50,
    });
    expect(screen.getByText('顯示 2 / 50 筆工單')).toBeInTheDocument();
  });

  // ── 點擊接線 ─────────────────────────────────────────────────────────────

  it('點擊 row → onSelect 帶該筆 work order', () => {
    const target = makeWO({ id: 'b', business_key: 'WO-B' });
    const { onSelect } = renderPanel({
      items: [makeWO({ id: 'a', business_key: 'WO-A' }), target],
      total: 2,
    });
    fireEvent.click(screen.getByRole('button', { name: '開啟工單 WO-B' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    // 守語意契約（傳回含正確 id 的工單）而非物件 identity，避免日後面板淺複製 items 時假紅
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: target.id, business_key: target.business_key }),
    );
  });
});

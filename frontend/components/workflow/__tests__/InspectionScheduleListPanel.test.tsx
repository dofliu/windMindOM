/**
 * InspectionScheduleListPanel component render 測試（WMOM-20260925-05）。
 *
 * `/admin/workflow`（定檢計畫 tab）的計畫列表面板。純 props 元件（無 hook /
 * 無 fetch / 無 internal state），測試範式沿用 InventoryListPanel.test.tsx：
 *
 *   - 基本渲染 + 語系（zh/en 標籤、counter；含 negative 守 zh 不外洩）
 *   - turbine Select：選項涵蓋「全部風機」+ turbineOptions；value 反映 prop；
 *     onChange → onTurbineIdChange
 *   - active-only toggle：文案 / variant 隨 activeOnly 切換；aria-pressed 反映狀態；
 *     onClick → onActiveOnlyChange(取反)
 *   - Refresh 按鈕：onClick → onRefresh；loading → 文案「載入中…」
 *   - counter：顯示 items.length / total
 *   - error 態 / empty 態
 *   - 列表 row：標題 / 風機 / 週期 / 下次到期時間 / active·paused pill /
 *     custom_days 顯示自訂天數 / last_spawned_at 顯示最近派工
 *   - 點擊 row → onSelect(該筆 schedule)
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import InspectionScheduleListPanel from '../InspectionScheduleListPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type { InspectionScheduleResponse } from '../../../services/inspectionScheduleService';

function makeSchedule(
  overrides: Partial<InspectionScheduleResponse> = {},
): InspectionScheduleResponse {
  return {
    id: 'insp-1',
    farm_id: 'farm-a',
    turbine_id: 'WTG-01',
    title: '齒輪箱季度定檢',
    description: '',
    recurrence: 'quarterly',
    interval_days: null,
    next_due_at: '2026-09-01T00:00:00Z',
    active: true,
    last_spawned_at: null,
    last_spawned_work_order_id: null,
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

interface RenderOpts {
  items?: InspectionScheduleResponse[];
  total?: number;
  loading?: boolean;
  error?: string | null;
  turbineOptions?: { value: string; label: string }[];
  turbineId?: string | 'all';
  activeOnly?: boolean;
  lang?: 'en' | 'zh';
}

function renderPanel(opts: RenderOpts = {}) {
  const onTurbineIdChange = vi.fn();
  const onActiveOnlyChange = vi.fn();
  const onSelect = vi.fn();
  const onRefresh = vi.fn();
  render(
    <ThemeProvider>
      <InspectionScheduleListPanel
        items={opts.items ?? [makeSchedule()]}
        total={opts.total ?? 1}
        loading={opts.loading ?? false}
        error={opts.error ?? null}
        turbineOptions={opts.turbineOptions ?? []}
        turbineId={opts.turbineId ?? 'all'}
        onTurbineIdChange={onTurbineIdChange}
        activeOnly={opts.activeOnly ?? false}
        onActiveOnlyChange={onActiveOnlyChange}
        onSelect={onSelect}
        onRefresh={onRefresh}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onTurbineIdChange, onActiveOnlyChange, onSelect, onRefresh };
}

describe('InspectionScheduleListPanel 定檢計畫列表面板', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 基本渲染 + 語系 ─────────────────────────────────────────────────────

  it('zh：渲染風機篩選標籤、重新整理按鈕與計畫筆數', () => {
    renderPanel({ lang: 'zh', items: [makeSchedule()], total: 3 });
    expect(screen.getByText('風機')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理列表' })).toHaveTextContent('重新整理');
    expect(screen.getByText('顯示 1 / 3 個定檢計畫')).toBeInTheDocument();
  });

  it('en：標籤/按鈕/counter 走英文（且不外洩 zh 文案）', () => {
    renderPanel({ lang: 'en', items: [makeSchedule()], total: 5 });
    expect(screen.getByText('Turbine')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh list' })).toHaveTextContent('Refresh');
    expect(screen.getByText('Showing 1 of 5 inspection schedules')).toBeInTheDocument();
    expect(screen.queryByText('重新整理')).not.toBeInTheDocument();
    expect(screen.queryByText(/顯示.*個定檢計畫/)).not.toBeInTheDocument();
  });

  // ── turbine filter ────────────────────────────────────────────────────

  it('turbine Select：選項涵蓋「全部風機」+ turbineOptions', () => {
    renderPanel({
      lang: 'zh',
      turbineId: 'all',
      turbineOptions: [
        { value: 'WTG-01', label: 'WTG-01' },
        { value: 'WTG-02', label: 'WTG-02' },
      ],
    });
    const select = screen.getByRole('combobox', { name: '依風機過濾' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    expect(optionTexts).toEqual(['全部風機', 'WTG-01', 'WTG-02']);
  });

  it('turbine Select：value 反映 turbineId prop', () => {
    renderPanel({ turbineId: 'WTG-02', turbineOptions: [{ value: 'WTG-02', label: 'WTG-02' }] });
    const select = screen.getByRole('combobox', { name: '依風機過濾' }) as HTMLSelectElement;
    expect(select.value).toBe('WTG-02');
  });

  it('turbine Select：onChange → onTurbineIdChange 帶選取值', () => {
    const { onTurbineIdChange } = renderPanel({
      turbineOptions: [{ value: 'WTG-02', label: 'WTG-02' }],
    });
    const select = screen.getByRole('combobox', { name: '依風機過濾' });
    fireEvent.change(select, { target: { value: 'WTG-02' } });
    expect(onTurbineIdChange).toHaveBeenCalledWith('WTG-02');
  });

  // ── active-only toggle ──────────────────────────────────────────────────

  it('active-only toggle：未開啟時文案「全部（含暫停）」、aria-pressed=false', () => {
    renderPanel({ activeOnly: false });
    const btn = screen.getByRole('button', { name: '切換僅顯示啟用中' });
    expect(btn).toHaveTextContent('全部（含暫停）');
    expect(btn).toHaveAttribute('aria-pressed', 'false');
  });

  it('active-only toggle：開啟時文案「僅啟用中」、aria-pressed=true', () => {
    renderPanel({ activeOnly: true });
    const btn = screen.getByRole('button', { name: '切換僅顯示啟用中' });
    expect(btn).toHaveTextContent('僅啟用中');
    expect(btn).toHaveAttribute('aria-pressed', 'true');
  });

  it('active-only toggle：activeOnly=false 時 onClick → onActiveOnlyChange(true)', () => {
    const { onActiveOnlyChange } = renderPanel({ activeOnly: false });
    fireEvent.click(screen.getByRole('button', { name: '切換僅顯示啟用中' }));
    expect(onActiveOnlyChange).toHaveBeenCalledWith(true);
  });

  it('active-only toggle：activeOnly=true 時 onClick → onActiveOnlyChange(false)（守 !activeOnly 反轉）', () => {
    const { onActiveOnlyChange } = renderPanel({ activeOnly: true });
    fireEvent.click(screen.getByRole('button', { name: '切換僅顯示啟用中' }));
    expect(onActiveOnlyChange).toHaveBeenCalledWith(false);
  });

  // ── refresh ──────────────────────────────────────────────────────────────

  it('Refresh 按鈕：onClick → onRefresh', () => {
    const { onRefresh } = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '重新整理列表' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('loading=true：Refresh 按鈕文案顯示「載入中…」', () => {
    renderPanel({ loading: true });
    expect(screen.getByRole('button', { name: '重新整理列表' })).toHaveTextContent('載入中…');
  });

  // ── error / empty 態 ───────────────────────────────────────────────────

  it('error：顯示 warn card 帶錯誤訊息', () => {
    renderPanel({ error: '載入定檢計畫失敗（500）' });
    expect(screen.getByText(/載入定檢計畫失敗（500）/)).toBeInTheDocument();
  });

  it('empty（items=[] 且 !loading !error）：顯示空狀態文案', () => {
    renderPanel({ items: [], total: 0 });
    expect(screen.getByText('目前沒有符合條件的定檢計畫。')).toBeInTheDocument();
  });

  it('empty 態在 loading 中不顯示（避免閃爍）', () => {
    renderPanel({ items: [], total: 0, loading: true });
    expect(screen.queryByText('目前沒有符合條件的定檢計畫。')).not.toBeInTheDocument();
  });

  // ── 列表 row 渲染 ──────────────────────────────────────────────────────

  it('row：渲染標題 / 風機 / 週期 / 下次到期時間 / active pill', () => {
    renderPanel({
      lang: 'zh',
      items: [
        makeSchedule({
          title: '主軸承年度定檢',
          turbine_id: 'WTG-03',
          recurrence: 'annual',
          next_due_at: '2026-12-25T00:00:00Z',
          active: true,
        }),
      ],
    });
    const row = screen.getByRole('button', { name: '開啟定檢計畫 主軸承年度定檢' });
    expect(row).toHaveTextContent('主軸承年度定檢');
    expect(row).toHaveTextContent('WTG-03');
    expect(row).toHaveTextContent('每年（約 365 天）');
    // next_due_at '2026-12-25T00:00:00Z' → fmtDateTime(Asia/Taipei) = 2026-12-25 08:00
    expect(row).toHaveTextContent('2026-12-25 08:00');
    expect(row).toHaveTextContent('啟用中');
  });

  it('row：recurrence=custom_days → 額外顯示自訂天數', () => {
    renderPanel({
      items: [makeSchedule({ title: '自訂週期計畫', recurrence: 'custom_days', interval_days: 45 })],
    });
    const row = screen.getByRole('button', { name: '開啟定檢計畫 自訂週期計畫' });
    expect(row).toHaveTextContent('自訂天數');
    expect(row).toHaveTextContent('45');
    expect(row).toHaveTextContent('天');
  });

  it('row：active=false → 顯示「已暫停」pill（非「啟用中」）', () => {
    renderPanel({ items: [makeSchedule({ title: '暫停中計畫', active: false })] });
    const row = screen.getByRole('button', { name: '開啟定檢計畫 暫停中計畫' });
    expect(row).toHaveTextContent('已暫停');
    expect(row).not.toHaveTextContent('啟用中');
  });

  it('row：last_spawned_at 有值 → 顯示最近派工時間', () => {
    renderPanel({
      items: [
        makeSchedule({ title: '有派工紀錄計畫', last_spawned_at: '2026-06-01T00:00:00Z' }),
      ],
    });
    const row = screen.getByRole('button', { name: '開啟定檢計畫 有派工紀錄計畫' });
    expect(row).toHaveTextContent('最近派工');
  });

  it('row：last_spawned_at 為 null → 不顯示「最近派工」', () => {
    renderPanel({ items: [makeSchedule({ title: '無派工紀錄計畫', last_spawned_at: null })] });
    const row = screen.getByRole('button', { name: '開啟定檢計畫 無派工紀錄計畫' });
    expect(row).not.toHaveTextContent('最近派工');
  });

  // ── 點擊接線 ─────────────────────────────────────────────────────────────

  it('點擊 row → onSelect 帶該筆 schedule', () => {
    const target = makeSchedule({ id: 'b', title: '目標計畫' });
    const { onSelect } = renderPanel({
      items: [makeSchedule({ id: 'a', title: '其他計畫' }), target],
      total: 2,
    });
    fireEvent.click(screen.getByRole('button', { name: '開啟定檢計畫 目標計畫' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: target.id, title: target.title }));
  });
});

/**
 * InspectionScheduleDetailModal component render 測試（WMOM-20260925-05）。
 *
 * 檢視 / 編輯既有定檢計畫的 modal。契約：
 *
 *   - 唯讀欄位：turbine_id / next_due_at / active pill / last_spawned_at（有值才顯示）
 *   - 編輯欄位初始值取自 `schedule` prop（title/description/recurrence/interval_days）
 *   - canSave gating：title 空 / custom_days 缺合法 interval_days → Save disabled
 *   - Save → onUpdate(id, payload) 帶正確 trim 過欄位；成功後本地 state 用回傳值同步
 *     （active pill / next_due_at 等唯讀欄位可能因此變動）
 *   - Pause/Resume 按鈕：文案 + variant 隨 active 狀態切換；onClick → onDeactivate
 *     或 onActivate（依目前 active 狀態二擇一，互斥不重複觸發）
 *   - Save / toggle 失敗 → 顯示錯誤訊息
 *   - Close 路徑：✕ / 背景點擊 → onClose；Card 內容點擊不觸發（stopPropagation）
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import React from 'react';
import InspectionScheduleDetailModal from '../InspectionScheduleDetailModal';
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
    description: '原始說明',
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
  schedule?: InspectionScheduleResponse;
  lang?: 'en' | 'zh';
  onUpdate?: ReturnType<typeof vi.fn>;
  onActivate?: ReturnType<typeof vi.fn>;
  onDeactivate?: ReturnType<typeof vi.fn>;
}

function renderModal(opts: RenderOpts = {}) {
  const schedule = opts.schedule ?? makeSchedule();
  const onClose = vi.fn();
  const onUpdate = opts.onUpdate ?? vi.fn().mockResolvedValue(schedule);
  const onActivate = opts.onActivate ?? vi.fn().mockResolvedValue({ ...schedule, active: true });
  const onDeactivate =
    opts.onDeactivate ?? vi.fn().mockResolvedValue({ ...schedule, active: false });
  render(
    <ThemeProvider>
      <InspectionScheduleDetailModal
        schedule={schedule}
        onClose={onClose}
        onUpdate={onUpdate}
        onActivate={onActivate}
        onDeactivate={onDeactivate}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onClose, onUpdate, onActivate, onDeactivate, schedule };
}

describe('InspectionScheduleDetailModal 檢視/編輯定檢計畫', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 唯讀欄位渲染 ─────────────────────────────────────────────────────────

  it('渲染風機 id / 下次到期時間 / active pill', () => {
    renderModal({ schedule: makeSchedule({ turbine_id: 'WTG-07', next_due_at: '2026-12-25T00:00:00Z' }) });
    expect(screen.getByText('WTG-07')).toBeInTheDocument();
    // '2026-12-25T00:00:00Z' → Asia/Taipei 08:00
    expect(screen.getByText(/2026-12-25 08:00/)).toBeInTheDocument();
    expect(screen.getByText('啟用中')).toBeInTheDocument();
  });

  it('active=false → pill 顯示「已暫停」（非「啟用中」）', () => {
    renderModal({ schedule: makeSchedule({ active: false }) });
    expect(screen.getByText('已暫停')).toBeInTheDocument();
    expect(screen.queryByText('啟用中')).not.toBeInTheDocument();
  });

  it('last_spawned_at 有值 → 顯示最近派工工單時間', () => {
    renderModal({ schedule: makeSchedule({ last_spawned_at: '2026-06-01T00:00:00Z' }) });
    expect(screen.getByText(/最近派工工單/)).toBeInTheDocument();
  });

  it('last_spawned_at 為 null → 不顯示最近派工工單', () => {
    renderModal({ schedule: makeSchedule({ last_spawned_at: null }) });
    expect(screen.queryByText(/最近派工工單/)).not.toBeInTheDocument();
  });

  // ── 編輯欄位初始值 ───────────────────────────────────────────────────────

  it('編輯欄位初始值取自 schedule prop', () => {
    renderModal({
      schedule: makeSchedule({ title: '主軸承檢查', description: '每季檢查一次', recurrence: 'annual' }),
    });
    expect((screen.getByRole('textbox', { name: '標題' }) as HTMLInputElement).value).toBe(
      '主軸承檢查',
    );
    expect(
      (screen.getByRole('textbox', { name: '說明' }) as HTMLTextAreaElement).value,
    ).toBe('每季檢查一次');
    expect((screen.getByRole('combobox', { name: '週期' }) as HTMLSelectElement).value).toBe(
      'annual',
    );
  });

  it('recurrence=custom_days 且 interval_days 有值 → 自訂天數欄位顯示該值', () => {
    renderModal({ schedule: makeSchedule({ recurrence: 'custom_days', interval_days: 60 }) });
    expect((screen.getByRole('spinbutton', { name: '自訂天數' }) as HTMLInputElement).value).toBe(
      '60',
    );
  });

  // ── canSave gating ───────────────────────────────────────────────────────

  it('title 清空 → Save 按鈕 disabled', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), { target: { value: '' } });
    expect(screen.getByRole('button', { name: '儲存變更' })).toBeDisabled();
  });

  it('title 非空（quarterly）→ Save 按鈕啟用', () => {
    renderModal();
    expect(screen.getByRole('button', { name: '儲存變更' })).not.toBeDisabled();
  });

  it('切到 custom_days 但清空 interval_days → Save disabled', () => {
    renderModal();
    fireEvent.change(screen.getByRole('combobox', { name: '週期' }), {
      target: { value: 'custom_days' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '自訂天數' }), {
      target: { value: '' },
    });
    expect(screen.getByRole('button', { name: '儲存變更' })).toBeDisabled();
  });

  // ── Save ─────────────────────────────────────────────────────────────────

  it('Save → onUpdate(id, payload) 帶 trim 過的欄位', async () => {
    const onUpdate = vi.fn().mockResolvedValue(makeSchedule());
    const { schedule } = renderModal({ onUpdate });
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '  更新後標題  ' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));
    });
    expect(onUpdate).toHaveBeenCalledWith(schedule.id, {
      title: '更新後標題',
      description: '原始說明',
      recurrence: 'quarterly',
      interval_days: null,
    });
  });

  it('Save 成功後本地 state 以回傳值同步（next_due_at 反映更新後版本）', async () => {
    const onUpdate = vi
      .fn()
      .mockResolvedValue(makeSchedule({ next_due_at: '2027-01-01T00:00:00Z' }));
    renderModal({ onUpdate });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));
    });
    expect(screen.getByText(/2027-01-01 08:00/)).toBeInTheDocument();
  });

  it('Save 失敗 → 顯示錯誤訊息', async () => {
    const onUpdate = vi.fn().mockRejectedValue(new Error('更新失敗（422）'));
    renderModal({ onUpdate });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));
    });
    expect(screen.getByText(/更新失敗（422）/)).toBeInTheDocument();
  });

  // ── Pause / Resume 切換 ──────────────────────────────────────────────────

  it('active=true → 按鈕文案「暫停」；點擊 → onDeactivate（非 onActivate）', async () => {
    const onActivate = vi.fn().mockResolvedValue(makeSchedule({ active: true }));
    const onDeactivate = vi.fn().mockResolvedValue(makeSchedule({ active: false }));
    const { schedule } = renderModal({
      schedule: makeSchedule({ active: true }),
      onActivate,
      onDeactivate,
    });
    const btn = screen.getByRole('button', { name: '暫停計畫' });
    expect(btn).toHaveTextContent('暫停');
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(onDeactivate).toHaveBeenCalledWith(schedule.id);
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('active=false → 按鈕文案「恢復」；點擊 → onActivate（非 onDeactivate）', async () => {
    const onActivate = vi.fn().mockResolvedValue(makeSchedule({ active: true }));
    const onDeactivate = vi.fn().mockResolvedValue(makeSchedule({ active: false }));
    const { schedule } = renderModal({
      schedule: makeSchedule({ active: false }),
      onActivate,
      onDeactivate,
    });
    const btn = screen.getByRole('button', { name: '恢復計畫' });
    expect(btn).toHaveTextContent('恢復');
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(onActivate).toHaveBeenCalledWith(schedule.id);
    expect(onDeactivate).not.toHaveBeenCalled();
  });

  it('切換後本地 state 以回傳值同步（active pill 反映最新狀態）', async () => {
    const onDeactivate = vi.fn().mockResolvedValue(makeSchedule({ active: false }));
    renderModal({ schedule: makeSchedule({ active: true }), onDeactivate });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '暫停計畫' }));
    });
    expect(screen.getByText('已暫停')).toBeInTheDocument();
    // 按鈕文案也應反映新狀態（切到恢復）
    expect(screen.getByRole('button', { name: '恢復計畫' })).toBeInTheDocument();
  });

  it('切換失敗 → 顯示錯誤訊息', async () => {
    const onDeactivate = vi.fn().mockRejectedValue(new Error('切換失敗（403）'));
    renderModal({ schedule: makeSchedule({ active: true }), onDeactivate });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '暫停計畫' }));
    });
    expect(screen.getByText(/切換失敗（403）/)).toBeInTheDocument();
  });

  // ── close 路徑 ───────────────────────────────────────────────────────────

  it('點右上角 ✕ → onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點背景（dialog 本身）→ onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 Card 內容（標題文字）不觸發 onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByText('定檢計畫'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

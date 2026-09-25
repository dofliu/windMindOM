/**
 * CreateInspectionScheduleModal component render 測試（WMOM-20260925-05）。
 *
 * 建立定檢計畫的單頁表單 modal：風機 / 標題 / 說明 / 週期 / 自訂天數（僅
 * `recurrence=custom_days` 顯示）。契約：
 *
 *   - 基本渲染 + 語系
 *   - canSubmit gating：turbine 空 / title 空 / custom_days 缺合法 interval_days → disabled
 *   - recurrence=custom_days 才顯示自訂天數欄位
 *   - Submit → onSubmit 帶正確 payload（trim 過的 title/description，非 custom_days
 *     時 interval_days=null）
 *   - Submit 失敗 → 顯示錯誤訊息，modal 不關閉（onClose 不被呼叫）
 *   - Submit 成功 → onSubmit 被呼叫，但本 modal 本身不自己呼叫 onClose
 *     （比照 CreateWorkOrderWizard 慣例，由呼叫端 WorkflowPage 決定是否關閉）
 *   - Cancel / 右上角 ✕ / 背景點擊 → onClose
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import CreateInspectionScheduleModal from '../CreateInspectionScheduleModal';
import { ThemeProvider } from '../../../theme/ThemeProvider';

const TURBINE_OPTIONS = [
  { value: 'WTG-01', label: 'WTG-01' },
  { value: 'WTG-02', label: 'WTG-02' },
];

interface RenderOpts {
  lang?: 'en' | 'zh';
  preselectTurbineId?: string;
  onSubmit?: ReturnType<typeof vi.fn>;
}

function renderModal(opts: RenderOpts = {}) {
  const onClose = vi.fn();
  const onSubmit = opts.onSubmit ?? vi.fn().mockResolvedValue(undefined);
  render(
    <ThemeProvider>
      <CreateInspectionScheduleModal
        turbineOptions={TURBINE_OPTIONS}
        preselectTurbineId={opts.preselectTurbineId}
        onClose={onClose}
        onSubmit={onSubmit}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onClose, onSubmit };
}

describe('CreateInspectionScheduleModal 建立定檢計畫', () => {
  afterEach(() => {
    cleanup();
  });

  it('zh：渲染標題與各欄位標籤', () => {
    renderModal({ lang: 'zh' });
    expect(screen.getByText('建立定檢計畫')).toBeInTheDocument();
    expect(screen.getByText('風機')).toBeInTheDocument();
    expect(screen.getByText('標題')).toBeInTheDocument();
    expect(screen.getByText('說明')).toBeInTheDocument();
    expect(screen.getByText('週期')).toBeInTheDocument();
  });

  it('en：標題與欄位走英文（不外洩 zh）', () => {
    renderModal({ lang: 'en' });
    expect(screen.getByText('Create inspection schedule')).toBeInTheDocument();
    expect(screen.getByText('Turbine')).toBeInTheDocument();
    expect(screen.queryByText('建立定檢計畫')).not.toBeInTheDocument();
  });

  it('turbine Select 未帶 preselectTurbineId 時預設選第一個選項', () => {
    renderModal();
    const select = screen.getByRole('combobox', { name: '風機' }) as HTMLSelectElement;
    expect(select.value).toBe('WTG-01');
  });

  it('preselectTurbineId 有帶時預先選取該風機（TurbineDetail 深連結場景）', () => {
    renderModal({ preselectTurbineId: 'WTG-02' });
    const select = screen.getByRole('combobox', { name: '風機' }) as HTMLSelectElement;
    expect(select.value).toBe('WTG-02');
  });

  it('recurrence 預設 quarterly 時不顯示自訂天數欄位', () => {
    // 注意：不能用 getByText('自訂天數') 斷言——`recurrence` Select 本身的
    // `<option value="custom_days">自訂天數</option>` 一律存在於 DOM（select 選項
    // 不因未被選取而消失），與欄位 label 文字同名會撞成 multiple-elements 誤判。
    // 改直接查真正條件渲染的自訂天數輸入框（spinbutton）是否存在。
    renderModal();
    expect(screen.queryByRole('spinbutton', { name: '自訂天數' })).not.toBeInTheDocument();
  });

  it('切到 recurrence=custom_days → 顯示自訂天數欄位（預設值 45）', () => {
    renderModal();
    const recurrenceSelect = screen.getByRole('combobox', { name: '週期' });
    fireEvent.change(recurrenceSelect, { target: { value: 'custom_days' } });
    const intervalInput = screen.getByRole('spinbutton', { name: '自訂天數' }) as HTMLInputElement;
    expect(intervalInput.value).toBe('45');
  });

  // ── canSubmit gating ─────────────────────────────────────────────────────

  it('title 為空 → Create schedule 按鈕 disabled', () => {
    renderModal();
    const submitBtn = screen.getByRole('button', { name: '建立計畫' });
    expect(submitBtn).toBeDisabled();
  });

  it('turbineOptions 為空（turbineId 初始空字串）→ 按鈕 disabled', () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ThemeProvider>
        <CreateInspectionScheduleModal
          turbineOptions={[]}
          onClose={onClose}
          onSubmit={onSubmit}
          lang="zh"
        />
      </ThemeProvider>,
    );
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '有標題但無風機可選' },
    });
    expect(screen.getByRole('button', { name: '建立計畫' })).toBeDisabled();
  });

  it('preselectTurbineId 不在 turbineOptions 內（過期值）→ 按鈕 disabled（守 code review should-fix：不能只檢查非空字串）', () => {
    renderModal({ preselectTurbineId: 'WTG-99-已移出風場' });
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '有標題但風機值無效' },
    });
    expect(screen.getByRole('button', { name: '建立計畫' })).toBeDisabled();
  });

  it('title 填妥（quarterly，非 custom_days）→ 按鈕啟用', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '齒輪箱季度定檢' },
    });
    expect(screen.getByRole('button', { name: '建立計畫' })).not.toBeDisabled();
  });

  it('recurrence=custom_days 但 interval_days 清空 → 按鈕 disabled（守 custom_days 必填驗證）', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '自訂週期計畫' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: '週期' }), {
      target: { value: 'custom_days' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '自訂天數' }), {
      target: { value: '' },
    });
    expect(screen.getByRole('button', { name: '建立計畫' })).toBeDisabled();
  });

  it('recurrence=custom_days 且 interval_days 合法正整數 → 按鈕啟用', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '自訂週期計畫' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: '週期' }), {
      target: { value: 'custom_days' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '自訂天數' }), {
      target: { value: '20' },
    });
    expect(screen.getByRole('button', { name: '建立計畫' })).not.toBeDisabled();
  });

  // ── submit ───────────────────────────────────────────────────────────────

  it('送出（quarterly）→ onSubmit 帶正確 payload（interval_days=null，trim 過的欄位）', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { onClose } = renderModal({ onSubmit });
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '  齒輪箱季度定檢  ' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: '說明' }), {
      target: { value: '  補充說明  ' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立計畫' }));
    });
    expect(onSubmit).toHaveBeenCalledWith({
      turbine_id: 'WTG-01',
      title: '齒輪箱季度定檢',
      description: '補充說明',
      recurrence: 'quarterly',
      interval_days: null,
    });
    // 本 modal 自己不呼叫 onClose——交給呼叫端決定（比照 CreateWorkOrderWizard 慣例）
    expect(onClose).not.toHaveBeenCalled();
  });

  it('送出（custom_days）→ onSubmit 帶 interval_days 數值', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderModal({ onSubmit });
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '自訂週期計畫' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: '週期' }), {
      target: { value: 'custom_days' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: '自訂天數' }), {
      target: { value: '20' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立計畫' }));
    });
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ recurrence: 'custom_days', interval_days: 20 }),
    );
  });

  it('送出失敗 → 顯示錯誤訊息、modal 不關閉', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('建立失敗（422）'));
    const { onClose } = renderModal({ onSubmit });
    fireEvent.change(screen.getByRole('textbox', { name: '標題' }), {
      target: { value: '會失敗的計畫' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立計畫' }));
    });
    expect(screen.getByText(/建立失敗（422）/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  // ── close 路徑 ───────────────────────────────────────────────────────────

  it('點 Cancel → onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點右上角 ✕ → onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點背景（dialog 本身，非 Card 內容）→ onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 Card 內容區域（title 文字）不觸發 onClose（stopPropagation 生效）', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByText('建立定檢計畫'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

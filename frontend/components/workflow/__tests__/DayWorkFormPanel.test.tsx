/**
 * DayWorkFormPanel component render 測試（WMOM-20260926-01，`WMOM-20260505-21` 前端）。
 *
 * `/admin/workflow`（工作日誌 tab）的個人日誌面板。純 props 元件（無外部 fetch，
 * `onAppendActivity` 由呼叫端注入），測試範式沿用 CreateInspectionScheduleModal +
 * InspectionScheduleListPanel：
 *
 *   - 基本渲染 + 語系（zh/en，含 negative 守 zh 不外洩）
 *   - 日期欄位：value 反映 prop；onChange → onWorkDateChange
 *   - loading / error / 空狀態（尚未建立日誌）三態互斥渲染
 *   - 已有 form：活動筆數 + 每種 kind 的顯示內容（wo_id / item_id—result / area / topic）
 *   - 新增活動表單：kind 切換顯示對應欄位；canSubmit gating（各 kind 必填欄位）；
 *     `completed_wo` 選單為空時的提示文案 + 有資料時自動預選第一筆
 *   - 送出成功 → onAppendActivity 帶正確 payload（trim + kind-irrelevant 欄位 undefined）
 *     + 表單欄位重置（kind 保留）
 *   - 送出失敗 → 顯示錯誤訊息，欄位不重置
 *   - 送出中 → 按鈕 disabled + 文案「新增中…」
 *   - 歷史區塊：loading / error / 空 / 列表（日期格式化 + 筆數文案）
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import DayWorkFormPanel from '../DayWorkFormPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  ActivityEntryResponse,
  AppendActivityPayload,
  DayWorkFormResponse,
} from '../../../services/dayWorkFormService';

function makeActivity(overrides: Partial<ActivityEntryResponse> = {}): ActivityEntryResponse {
  return {
    id: 'act-1',
    kind: 'completed_wo',
    wo_id: 'wo-abc',
    item_id: null,
    result: null,
    area: null,
    topic: null,
    note: '',
    logged_at: '2026-09-26T02:00:00Z',
    ...overrides,
  };
}

function makeForm(overrides: Partial<DayWorkFormResponse> = {}): DayWorkFormResponse {
  return {
    id: 'form-1',
    farm_id: 'farm-a',
    employee_id: 'emp-1',
    work_date: '2026-09-26',
    activities: [],
    notes: '',
    created_at: '2026-09-26T00:00:00Z',
    created_by: 'emp-1',
    updated_at: '2026-09-26T00:00:00Z',
    ...overrides,
  };
}

const WORK_ORDER_OPTIONS = [
  { id: 'wo-1', label: 'WO-0001 — 更換齒輪箱油封' },
  { id: 'wo-2', label: 'WO-0002 — 葉片檢查' },
];

interface RenderOpts {
  workDate?: string;
  form?: DayWorkFormResponse | null;
  loading?: boolean;
  error?: string | null;
  history?: DayWorkFormResponse[];
  historyLoading?: boolean;
  historyError?: string | null;
  workOrderOptions?: { id: string; label: string }[];
  onAppendActivity?: (
    req: Omit<AppendActivityPayload, 'employee_id'>,
  ) => Promise<DayWorkFormResponse>;
  lang?: 'en' | 'zh';
}

function renderPanel(opts: RenderOpts = {}) {
  const onWorkDateChange = vi.fn();
  const onAppendActivity =
    opts.onAppendActivity ?? vi.fn().mockResolvedValue(makeForm());
  render(
    <ThemeProvider>
      <DayWorkFormPanel
        workDate={opts.workDate ?? '2026-09-26'}
        onWorkDateChange={onWorkDateChange}
        form={opts.form === undefined ? makeForm() : opts.form}
        loading={opts.loading ?? false}
        error={opts.error ?? null}
        history={opts.history ?? []}
        historyLoading={opts.historyLoading ?? false}
        historyError={opts.historyError ?? null}
        workOrderOptions={opts.workOrderOptions ?? WORK_ORDER_OPTIONS}
        onAppendActivity={onAppendActivity}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onWorkDateChange, onAppendActivity };
}

describe('DayWorkFormPanel 基本渲染 + 語系', () => {
  afterEach(() => cleanup());

  it('zh：渲染各區塊標題', () => {
    renderPanel({ lang: 'zh' });
    expect(screen.getByText('日期')).toBeInTheDocument();
    // 「新增活動」同時是區塊標題 div 與送出按鈕的文字，用 getAllByText 避免歧義。
    expect(screen.getAllByText('新增活動').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('最近日誌（本人）')).toBeInTheDocument();
  });

  it('en：走英文（不外洩 zh）', () => {
    renderPanel({ lang: 'en' });
    expect(screen.getAllByText('Add activity').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Recent logs (yours)')).toBeInTheDocument();
    expect(screen.queryByText('新增活動')).not.toBeInTheDocument();
  });

  it('日期欄位 value 反映 workDate prop，onChange 呼叫 onWorkDateChange', () => {
    const { onWorkDateChange } = renderPanel({ workDate: '2026-01-15' });
    const dateInput = screen.getByLabelText('工作日期') as HTMLInputElement;
    expect(dateInput.value).toBe('2026-01-15');
    fireEvent.change(dateInput, { target: { value: '2026-01-16' } });
    expect(onWorkDateChange).toHaveBeenCalledWith('2026-01-16');
  });
});

describe('DayWorkFormPanel 當日日誌區塊三態', () => {
  afterEach(() => cleanup());

  it('loading：顯示「載入中…」，不顯示空狀態或活動列表', () => {
    renderPanel({ loading: true, form: null });
    expect(screen.getByText('載入中…')).toBeInTheDocument();
    expect(screen.queryByText(/尚未建立日誌/)).not.toBeInTheDocument();
  });

  it('error：顯示警告卡片文字', () => {
    renderPanel({ error: '網路錯誤', form: null });
    expect(screen.getByText(/⚠ 網路錯誤/)).toBeInTheDocument();
  });

  it('form=null 且非 loading/error：顯示「尚未建立日誌」空狀態', () => {
    renderPanel({ form: null });
    expect(screen.getByText(/這天尚未建立日誌/)).toBeInTheDocument();
  });

  it('form 存在但無活動：顯示「尚無活動記錄」', () => {
    renderPanel({ form: makeForm({ activities: [] }) });
    expect(screen.getByText('尚無活動記錄。')).toBeInTheDocument();
  });

  it('completed_wo 活動：顯示 wo_id', () => {
    renderPanel({
      form: makeForm({ activities: [makeActivity({ kind: 'completed_wo', wo_id: 'wo-xyz' })] }),
    });
    expect(screen.getByText('wo-xyz')).toBeInTheDocument();
  });

  it('inspection_item 活動：顯示 item_id — result', () => {
    renderPanel({
      form: makeForm({
        activities: [
          makeActivity({ kind: 'inspection_item', wo_id: null, item_id: 'item-9', result: '正常' }),
        ],
      }),
    });
    expect(screen.getByText('item-9 — 正常')).toBeInTheDocument();
  });

  it('patrol 活動：顯示 area', () => {
    renderPanel({
      form: makeForm({ activities: [makeActivity({ kind: 'patrol', wo_id: null, area: 'B 棟機艙' })] }),
    });
    expect(screen.getByText('B 棟機艙')).toBeInTheDocument();
  });

  it('training 活動：顯示 topic + note', () => {
    renderPanel({
      form: makeForm({
        activities: [
          makeActivity({ kind: 'training', wo_id: null, topic: '消防安全複訓', note: '線上課程' }),
        ],
      }),
    });
    expect(screen.getByText('消防安全複訓')).toBeInTheDocument();
    expect(screen.getByText('線上課程')).toBeInTheDocument();
  });

  it('活動筆數文案反映 activities.length', () => {
    renderPanel({
      form: makeForm({
        activities: [makeActivity({ id: 'a1' }), makeActivity({ id: 'a2' })],
      }),
    });
    expect(screen.getByText('已記錄 2 筆活動')).toBeInTheDocument();
  });
});

describe('DayWorkFormPanel 新增活動表單 — kind 切換與 canSubmit gating', () => {
  afterEach(() => cleanup());

  it('預設 kind=completed_wo，顯示工單 Select 且預選第一筆', () => {
    renderPanel();
    const select = screen.getByRole('combobox', { name: '工單' }) as HTMLSelectElement;
    expect(select.value).toBe('wo-1');
  });

  it('workOrderOptions 為空：顯示提示文案，Add 按鈕 disabled', () => {
    renderPanel({ workOrderOptions: [] });
    expect(screen.getByText('目前沒有指派給你的工單。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
  });

  it('workOrderOptions 從空變有資料（非同步載入完成）：自動補選第一筆', () => {
    const { rerender } = render(
      <ThemeProvider>
        <DayWorkFormPanel
          workDate="2026-09-26"
          onWorkDateChange={vi.fn()}
          form={makeForm()}
          loading={false}
          error={null}
          history={[]}
          historyLoading={false}
          historyError={null}
          workOrderOptions={[]}
          onAppendActivity={vi.fn().mockResolvedValue(makeForm())}
          lang="zh"
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();

    rerender(
      <ThemeProvider>
        <DayWorkFormPanel
          workDate="2026-09-26"
          onWorkDateChange={vi.fn()}
          form={makeForm()}
          loading={false}
          error={null}
          history={[]}
          historyLoading={false}
          historyError={null}
          workOrderOptions={WORK_ORDER_OPTIONS}
          onAppendActivity={vi.fn().mockResolvedValue(makeForm())}
          lang="zh"
        />
      </ThemeProvider>,
    );

    const select = screen.getByRole('combobox', { name: '工單' }) as HTMLSelectElement;
    expect(select.value).toBe('wo-1');
    expect(screen.getByRole('button', { name: '新增活動' })).not.toBeDisabled();
  });

  it('已選 woId 從 workOrderOptions 中消失（例如被重新指派）：送出時用目前清單第一筆，不殘留過期 id（review should-fix）', async () => {
    // 注意：不能只斷言 `select.value`——原生 `<select>` 對「value 對不到任何
    // option」會自行 fallback 顯示第一個 option（瀏覽器 DOM 層行為），與 React
    // state 是否正確重新對齊是兩回事（這正是 review should-fix 指出的陷阱）。
    // 真正該鎖住的是「送出時 payload 帶的 wo_id」，因為那才是讀 React state
    // 而非讀 DOM 顯示值。
    const onAppendActivity = vi.fn().mockResolvedValue(makeForm());
    const { rerender } = render(
      <ThemeProvider>
        <DayWorkFormPanel
          workDate="2026-09-26"
          onWorkDateChange={vi.fn()}
          form={makeForm()}
          loading={false}
          error={null}
          history={[]}
          historyLoading={false}
          historyError={null}
          workOrderOptions={WORK_ORDER_OPTIONS}
          onAppendActivity={onAppendActivity}
          lang="zh"
        />
      </ThemeProvider>,
    );
    // 使用者手動選第二筆（wo-2）。
    fireEvent.change(screen.getByRole('combobox', { name: '工單' }), {
      target: { value: 'wo-2' },
    });

    // 清單 refetch 後 wo-2 已不在（例如被重新指派給別人），只剩 wo-3。
    rerender(
      <ThemeProvider>
        <DayWorkFormPanel
          workDate="2026-09-26"
          onWorkDateChange={vi.fn()}
          form={makeForm()}
          loading={false}
          error={null}
          history={[]}
          historyLoading={false}
          historyError={null}
          workOrderOptions={[{ id: 'wo-3', label: 'WO-0003 — 更換軸承' }]}
          onAppendActivity={onAppendActivity}
          lang="zh"
        />
      </ThemeProvider>,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '新增活動' }));
    });
    expect(onAppendActivity).toHaveBeenCalledWith(expect.objectContaining({ wo_id: 'wo-3' }));
  });

  it('今天已記錄過的工單從選單排除，自動改選其餘可選項（nice-to-have：避免重複記同一張工單）', () => {
    renderPanel({
      form: makeForm({
        activities: [makeActivity({ id: 'a1', kind: 'completed_wo', wo_id: 'wo-1' })],
      }),
    });
    const select = screen.getByRole('combobox', { name: '工單' }) as HTMLSelectElement;
    // wo-1 已記錄過，選單只剩 wo-2，自動改選它。
    expect(select.value).toBe('wo-2');
    expect(select).not.toHaveTextContent('WO-0001');
  });

  it('指派的工單今天都已記錄過（選單為空）：顯示提示文案，Add 按鈕 disabled', () => {
    renderPanel({
      workOrderOptions: [{ id: 'wo-1', label: 'WO-0001 — 更換齒輪箱油封' }],
      form: makeForm({
        activities: [makeActivity({ id: 'a1', kind: 'completed_wo', wo_id: 'wo-1' })],
      }),
    });
    expect(screen.getByText('指派給你的工單今天都已記錄過。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
  });

  it('切到 inspection_item：顯示 item_id + result 欄位，未填齊 disabled', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '活動類型' }), {
      target: { value: 'inspection_item' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '定檢項目 ID' }), {
      target: { value: 'a1b2c3d4-e5f6-4789-a012-3456789abcde' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '結果' }), {
      target: { value: '正常' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).not.toBeDisabled();
  });

  it('inspection_item：item_id 非合法 UUID 格式時即使 result 已填仍 disabled（review should-fix：避免送出後才收到後端 422）', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '活動類型' }), {
      target: { value: 'inspection_item' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: '定檢項目 ID' }), {
      target: { value: 'not-a-uuid' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: '結果' }), {
      target: { value: '正常' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
  });

  it('切到 patrol：area 為空 disabled，填入後 enabled', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '活動類型' }), {
      target: { value: 'patrol' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '巡視區域' }), {
      target: { value: 'B 棟機艙' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).not.toBeDisabled();
  });

  it('切到 training：topic 為空 disabled，填入後 enabled', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('combobox', { name: '活動類型' }), {
      target: { value: 'training' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '訓練主題' }), {
      target: { value: '消防安全複訓' },
    });
    expect(screen.getByRole('button', { name: '新增活動' })).not.toBeDisabled();
  });
});

describe('DayWorkFormPanel 送出行為', () => {
  afterEach(() => cleanup());

  it('送出成功：onAppendActivity 帶正確 payload（completed_wo，kind-irrelevant 欄位 undefined）', async () => {
    const onAppendActivity = vi.fn().mockResolvedValue(makeForm());
    renderPanel({ onAppendActivity });
    fireEvent.change(screen.getByRole('textbox', { name: '備註' }), {
      target: { value: '  順利完成  ' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '新增活動' }));
    });
    expect(onAppendActivity).toHaveBeenCalledWith({
      kind: 'completed_wo',
      wo_id: 'wo-1',
      item_id: undefined,
      result: undefined,
      area: undefined,
      topic: undefined,
      note: '順利完成',
    });
  });

  it('送出成功後表單欄位重置（note 清空）', async () => {
    const onAppendActivity = vi.fn().mockResolvedValue(makeForm());
    renderPanel({ onAppendActivity });
    const noteInput = screen.getByRole('textbox', { name: '備註' }) as HTMLTextAreaElement;
    fireEvent.change(noteInput, { target: { value: '備註內容' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '新增活動' }));
    });
    expect(noteInput.value).toBe('');
  });

  it('送出中：按鈕 disabled + 文案「新增中…」', async () => {
    let resolvePromise: (v: DayWorkFormResponse) => void = () => {};
    const pending = new Promise<DayWorkFormResponse>(resolve => {
      resolvePromise = resolve;
    });
    const onAppendActivity = vi.fn().mockReturnValue(pending);
    renderPanel({ onAppendActivity });

    fireEvent.click(screen.getByRole('button', { name: '新增活動' }));
    expect(await screen.findByRole('button', { name: '新增活動' })).toBeDisabled();
    expect(screen.getByText('新增中…')).toBeInTheDocument();

    await act(async () => {
      resolvePromise(makeForm());
      await pending;
    });
  });

  it('送出失敗：顯示錯誤訊息，欄位不重置', async () => {
    const onAppendActivity = vi.fn().mockRejectedValue(new Error('伺服器錯誤'));
    renderPanel({ onAppendActivity });
    const noteInput = screen.getByRole('textbox', { name: '備註' }) as HTMLTextAreaElement;
    fireEvent.change(noteInput, { target: { value: '備註內容' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '新增活動' }));
    });
    expect(screen.getByText(/⚠ 伺服器錯誤/)).toBeInTheDocument();
    expect(noteInput.value).toBe('備註內容');
  });
});

describe('DayWorkFormPanel 歷史區塊', () => {
  afterEach(() => cleanup());

  it('historyLoading：顯示「載入中…」', () => {
    renderPanel({ historyLoading: true });
    expect(screen.getAllByText('載入中…').length).toBeGreaterThan(0);
  });

  it('historyError：顯示錯誤訊息', () => {
    renderPanel({ historyError: '歷史載入失敗' });
    expect(screen.getByText(/⚠ 歷史載入失敗/)).toBeInTheDocument();
  });

  it('history 為空：顯示「尚無日誌記錄」', () => {
    renderPanel({ history: [] });
    expect(screen.getByText('尚無日誌記錄。')).toBeInTheDocument();
  });

  it('history 有資料：顯示日期（Asia/Taipei）+ 活動筆數', () => {
    renderPanel({
      history: [
        makeForm({
          id: 'h1',
          work_date: '2026-09-20',
          activities: [makeActivity({ id: 'x1' }), makeActivity({ id: 'x2' })],
        }),
      ],
    });
    expect(screen.getByText('2026-09-20')).toBeInTheDocument();
    expect(screen.getByText('2 筆活動')).toBeInTheDocument();
  });
});

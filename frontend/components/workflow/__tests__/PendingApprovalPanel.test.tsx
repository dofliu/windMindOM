/**
 * PendingApprovalPanel component render 測試（WMOM-20260605-05，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/workflow`（簽核 tab）的「我這層的待簽」列表面板（`PendingApprovalPanel.tsx`，270 行）
 * 是核心「簽核（signoff）」流程的主操作清單：員工 / 組長 / 主管 / 總務各層登入後，
 * 在此看到「輪到我簽的步驟」並按 通過 / 駁回。先前無任何測試覆蓋本面板的真實渲染
 * （level Select / subject_type filter / counter / error / empty / 每筆 row 的
 * subject summary（工單 business_key·turbine / 非工單對象 …subjectId8）+ chain progress +
 * priority·status pill + 開啟時間 + 通過/駁回 接線）。
 *
 * 本檔延續 WorkOrder/MaterialRequest/Inventory 三大列表面板已落地的 render 測試範式
 * （ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），守住面板 UX 契約：
 *
 *   - 基本渲染 + 語系（zh/en 標籤、counter；含 negative 守 zh 不外洩）
 *   - level Select：選項涵蓋 員工/組長/主管/總務；value 反映 prop；onChange → onLevelChange
 *   - subject_type Select：選項涵蓋「全部對象」+ 工單 + 領料單；value 反映 prop；onChange → onSubjectTypeChange
 *   - Refresh 按鈕：onClick → onRefresh；loading → 文案「載入中…」/「Loading…」且 disabled
 *   - counter：顯示 items.length / total + 當前 level 標籤
 *   - error 態：warn card 顯示 ⚠ + 訊息
 *   - empty 態：items=[] 且 !loading !error → 空狀態文案；loading/error 時不顯示空狀態
 *   - row（work_order 命中 cache）：business_key / turbine / title / chain progress pill /
 *     priority·status pill / 開啟時間（started_at 時區）
 *   - row（非 work_order 或 cache miss）：subjectTypeLabel + …subjectId8
 *   - 通過 / 駁回 → onApproveClick / onRejectClick(該 pending item)
 *
 * PendingApprovalPanel 是純 props 元件（無 hook / 無 fetch / 無 internal state），
 * 故測試直接以工廠 `makePending()` / `makeWO()` 結構式滿足型別（不用 `as` 強轉），
 * 透過 props 注入各情境，斷言聚焦面板自身的渲染與回呼接線。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import PendingApprovalPanel from '../PendingApprovalPanel';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  PendingSignoffItem,
  SignoffChainResponse,
  SignoffLevel,
  SignoffStepResponse,
  SignoffSubjectType,
  WorkOrderResponse,
} from '../../../services/workOrderService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 SignoffStepResponse（所有欄位齊備，不用 `as` 強轉）。 */
function makeStep(overrides: Partial<SignoffStepResponse> = {}): SignoffStepResponse {
  return {
    id: 'step-1',
    chain_id: 'chain-1',
    level: 'leader',
    sequence: 0,
    parallel_group_id: null,
    assignee_id: null,
    status: 'pending',
    decided_at: null,
    decided_by: null,
    comment: null,
    created_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

/** 產生結構完整的 SignoffChainResponse。 */
function makeChain(overrides: Partial<SignoffChainResponse> = {}): SignoffChainResponse {
  return {
    id: 'chain-1',
    subject_type: 'work_order',
    subject_id: 'wo-00000001',
    farm_id: 'farm-a',
    levels: ['leader', 'supervisor'],
    current_level_index: 0,
    overall_status: 'pending',
    started_at: '2026-06-02T08:30:00Z',
    completed_at: null,
    rejected_at_level: null,
    rejected_reason: null,
    ...overrides,
  };
}

/** 組出一筆 PendingSignoffItem（step + chain）。 */
function makePending(
  step: Partial<SignoffStepResponse> = {},
  chain: Partial<SignoffChainResponse> = {},
): PendingSignoffItem {
  return { step: makeStep(step), chain: makeChain(chain) };
}

/** 產生結構完整的 WorkOrderResponse（mirror 自 WorkOrderListPanel.test 工廠）。 */
function makeWO(overrides: Partial<WorkOrderResponse> = {}): WorkOrderResponse {
  return {
    id: 'wo-00000001',
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
  items?: PendingSignoffItem[];
  total?: number;
  loading?: boolean;
  error?: string | null;
  level?: SignoffLevel;
  subjectType?: SignoffSubjectType | 'all';
  workOrderCache?: Map<string, WorkOrderResponse>;
  lang?: 'en' | 'zh';
}

/** 渲染 PendingApprovalPanel + 回傳所有 callback spy，供斷言接線。 */
function renderPanel(opts: RenderOpts = {}) {
  const onLevelChange = vi.fn();
  const onSubjectTypeChange = vi.fn();
  const onApproveClick = vi.fn();
  const onRejectClick = vi.fn();
  const onRefresh = vi.fn();
  render(
    <ThemeProvider>
      <PendingApprovalPanel
        items={opts.items ?? [makePending()]}
        total={opts.total ?? 1}
        loading={opts.loading ?? false}
        error={opts.error ?? null}
        level={opts.level ?? 'leader'}
        onLevelChange={onLevelChange}
        subjectType={opts.subjectType ?? 'all'}
        onSubjectTypeChange={onSubjectTypeChange}
        workOrderCache={opts.workOrderCache ?? new Map()}
        onApproveClick={onApproveClick}
        onRejectClick={onRejectClick}
        onRefresh={onRefresh}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onLevelChange, onSubjectTypeChange, onApproveClick, onRejectClick, onRefresh };
}

describe('PendingApprovalPanel 待簽列表面板', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 基本渲染 + 語系 ─────────────────────────────────────────────────────

  it('zh：渲染層級/對象欄位標籤、重新整理按鈕與待簽筆數（含當前 level 標籤）', () => {
    renderPanel({ lang: 'zh', level: 'leader', items: [makePending()], total: 3 });
    expect(screen.getByText('我的簽核層級')).toBeInTheDocument();
    expect(screen.getByText('對象類型')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理待簽列表' })).toHaveTextContent('重新整理');
    // counter：items.length / total + level 標籤（leader → 組長）
    expect(screen.getByText('顯示 1 / 3 筆 組長 待簽')).toBeInTheDocument();
  });

  it('en：標籤/按鈕/counter 走英文（且不外洩 zh 文案）', () => {
    renderPanel({ lang: 'en', level: 'supervisor', items: [makePending()], total: 5 });
    expect(screen.getByText('Acting as level')).toBeInTheDocument();
    expect(screen.getByText('Subject type')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh pending list' })).toHaveTextContent(
      'Refresh',
    );
    expect(screen.getByText('Showing 1 of 5 pending steps for Supervisor')).toBeInTheDocument();
    // negative：en 模式不應出現任何 zh 專屬文案（守住 ui() zh/en 沒倒置）
    expect(screen.queryByText('重新整理')).not.toBeInTheDocument();
    expect(screen.queryByText('我的簽核層級')).not.toBeInTheDocument();
    expect(screen.queryByText(/顯示.*待簽/)).not.toBeInTheDocument();
  });

  // ── level Select ─────────────────────────────────────────────────────────

  it('level Select：選項涵蓋 員工/組長/主管/總務（zh）', () => {
    renderPanel({ lang: 'zh', level: 'leader' });
    const select = screen.getByRole('combobox', { name: '我的簽核層級' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    expect(optionTexts).toEqual(['員工', '組長', '主管', '總務']);
  });

  it('level Select：value 反映 level prop', () => {
    renderPanel({ level: 'treasury' });
    const select = screen.getByRole('combobox', { name: '我的簽核層級' }) as HTMLSelectElement;
    expect(select.value).toBe('treasury');
  });

  it('level Select：onChange → onLevelChange 帶選取值', () => {
    const { onLevelChange } = renderPanel({ level: 'leader' });
    const select = screen.getByRole('combobox', { name: '我的簽核層級' });
    fireEvent.change(select, { target: { value: 'supervisor' } });
    expect(onLevelChange).toHaveBeenCalledTimes(1);
    expect(onLevelChange).toHaveBeenCalledWith('supervisor');
  });

  // ── subject_type Select ────────────────────────────────────────────────────

  it('subject_type Select：選項涵蓋「全部對象」+ 工單 + 領料單（zh）', () => {
    renderPanel({ lang: 'zh', subjectType: 'all' });
    const select = screen.getByRole('combobox', { name: '對象類型過濾' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    expect(optionTexts).toEqual(['全部對象', '工單', '領料單']);
  });

  it('subject_type Select（en）：「全部對象」走英文「All subjects」（不外洩 zh）', () => {
    renderPanel({ lang: 'en', subjectType: 'all' });
    const select = screen.getByRole('combobox', { name: 'Subject type filter' });
    const optionTexts = within(select)
      .getAllByRole('option')
      .map(o => o.textContent);
    // 正向守住 en 選項文案（避免 ui('All subjects','全部對象') 參數倒置時僅靠 negative test 誤判通過）
    expect(optionTexts).toEqual(['All subjects', 'Work order', 'Material request']);
    expect(screen.queryByText('全部對象')).not.toBeInTheDocument();
  });

  it('subject_type Select：value 反映 subjectType prop', () => {
    renderPanel({ subjectType: 'material_request' });
    const select = screen.getByRole('combobox', { name: '對象類型過濾' }) as HTMLSelectElement;
    expect(select.value).toBe('material_request');
  });

  it('subject_type Select：onChange → onSubjectTypeChange 帶選取值', () => {
    const { onSubjectTypeChange } = renderPanel({ subjectType: 'all' });
    const select = screen.getByRole('combobox', { name: '對象類型過濾' });
    fireEvent.change(select, { target: { value: 'work_order' } });
    expect(onSubjectTypeChange).toHaveBeenCalledTimes(1);
    expect(onSubjectTypeChange).toHaveBeenCalledWith('work_order');
  });

  // ── refresh ──────────────────────────────────────────────────────────────

  it('Refresh 按鈕：onClick → onRefresh', () => {
    const { onRefresh } = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: '重新整理待簽列表' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('loading=true：Refresh 按鈕文案顯示「載入中…」且 disabled（防載入中重複點擊）', () => {
    renderPanel({ loading: true });
    const btn = screen.getByRole('button', { name: '重新整理待簽列表' });
    expect(btn).toHaveTextContent('載入中…');
    // loading 期間按鈕應 disabled（Btn loading prop → isDisabled），避免重複觸發 onRefresh
    expect(btn).toBeDisabled();
  });

  it('loading=true（en）：Refresh 按鈕文案顯示「Loading…」且 disabled', () => {
    renderPanel({ loading: true, lang: 'en' });
    const btn = screen.getByRole('button', { name: 'Refresh pending list' });
    expect(btn).toHaveTextContent('Loading…');
    expect(btn).toBeDisabled();
  });

  it('loading=true：點擊 disabled 的 Refresh 不觸發 onRefresh（守防重複觸發行為）', () => {
    const { onRefresh } = renderPanel({ loading: true });
    fireEvent.click(screen.getByRole('button', { name: '重新整理待簽列表' }));
    expect(onRefresh).not.toHaveBeenCalled();
  });

  // ── error 態 ───────────────────────────────────────────────────────────

  it('error：顯示 warn card 帶 ⚠ 與錯誤訊息', () => {
    renderPanel({ error: '載入待簽失敗（500）' });
    // ⚠ 與 error message 同在一個文字節點（component `<div>⚠ {error}</div>`），
    // 故以單一斷言同時守住「⚠ 視覺提示」+「錯誤訊息」（避免兩個指向同節點的冗餘斷言誤導維護者）。
    expect(screen.getByText(/⚠ 載入待簽失敗（500）/)).toBeInTheDocument();
  });

  // ── empty 態 ───────────────────────────────────────────────────────────

  it('empty（items=[] 且 !loading !error）：顯示空狀態文案（含當前 level）', () => {
    renderPanel({ items: [], total: 0, level: 'leader' });
    expect(screen.getByText('組長層目前沒有待簽項目。')).toBeInTheDocument();
  });

  it('empty（en）：空狀態文案走英文（不外洩 zh）', () => {
    renderPanel({ items: [], total: 0, level: 'leader', lang: 'en' });
    expect(screen.getByText('No pending approvals at Leader level.')).toBeInTheDocument();
    // 守住 ui() en/zh 沒倒置（en 模式不外洩 zh 空狀態文案）
    expect(screen.queryByText(/層目前沒有/)).not.toBeInTheDocument();
  });

  it('empty 態在 loading 中不顯示（避免閃爍）', () => {
    renderPanel({ items: [], total: 0, loading: true, level: 'leader' });
    expect(screen.queryByText('組長層目前沒有待簽項目。')).not.toBeInTheDocument();
  });

  it('empty 態在 error 時不顯示（讓位給錯誤卡）', () => {
    renderPanel({ items: [], total: 0, error: 'boom', level: 'leader' });
    expect(screen.queryByText('組長層目前沒有待簽項目。')).not.toBeInTheDocument();
    // 直接比對訊息文字（避免日後別處新增含 ⚠ 元素時 getByText(/⚠/) 命中多元素而炸）
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });

  // ── 列表 row 渲染（work_order 命中 cache）─────────────────────────────────

  it('row（work_order 命中 cache）：渲染 business_key / turbine / title / chain progress / priority·status pill / 開啟時間', () => {
    const wo = makeWO({
      id: 'wo-99',
      business_key: 'WO-2026-0042',
      turbine_id: 'WTG-07',
      title: '主軸承異音檢查',
      priority: 'high',
      status: 'dispatched',
    });
    renderPanel({
      lang: 'zh',
      items: [
        makePending(
          { level: 'leader', sequence: 0 },
          { subject_type: 'work_order', subject_id: 'wo-99', levels: ['leader', 'supervisor'] },
        ),
      ],
      workOrderCache: new Map([['wo-99', wo]]),
    });
    expect(screen.getByText('WO-2026-0042')).toBeInTheDocument();
    expect(screen.getByText('WTG-07')).toBeInTheDocument();
    expect(screen.getByText('主軸承異音檢查')).toBeInTheDocument();
    // chain progress pill：signoffLevelLabel(step.level) · {sequence+1}/{levels.length} = 組長 · 1/2
    expect(screen.getByText(/組長 · 1\/2/)).toBeInTheDocument();
    // priority / status pill（高 / 已派工）
    expect(screen.getByText('高')).toBeInTheDocument();
    expect(screen.getByText('已派工')).toBeInTheDocument();
    // 開啟時間：started_at '2026-06-02T08:30:00Z' → fmtDateTime(Asia/Taipei) = 2026-06-02 16:30
    expect(screen.getByText(/開啟於/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-02 16:30/)).toBeInTheDocument();
  });

  it('row（en，work_order）：開啟時間前綴走「Started」', () => {
    const wo = makeWO({ id: 'wo-99', business_key: 'WO-2026-0042' });
    renderPanel({
      lang: 'en',
      items: [makePending({}, { subject_type: 'work_order', subject_id: 'wo-99' })],
      workOrderCache: new Map([['wo-99', wo]]),
    });
    expect(screen.getByText(/Started/)).toBeInTheDocument();
  });

  // ── 列表 row 渲染（非 work_order / cache miss）─────────────────────────────

  it('row（material_request 對象，無 cache）：顯示 subjectTypeLabel + …subjectId8', () => {
    renderPanel({
      lang: 'zh',
      items: [
        makePending(
          {},
          { subject_type: 'material_request', subject_id: 'mr-abcd1234' },
        ),
      ],
      workOrderCache: new Map(),
    });
    // 領料單對象（subjectTypeLabel）+ subject_id 末 8 碼前綴 …（'mr-abcd1234'.slice(-8) = 'abcd1234'）。
    // row 內 subjectTypeLabel 出現恰 2 次：left col（subjectTypeLabel）+ middle col（wo?.title ?? subjectTypeLabel）。
    // 排除 subject_type 過濾 Select 的 <option>領料單</option>（非 row 渲染），精準守住「兩個 column 都顯示 fallback」。
    const labels = screen.getAllByText('領料單').filter(el => el.tagName !== 'OPTION');
    expect(labels).toHaveLength(2);
    expect(screen.getByText('…abcd1234')).toBeInTheDocument();
  });

  it('row（work_order 但 cache miss）：fallback 顯示 subjectTypeLabel + …subjectId8（不炸）', () => {
    renderPanel({
      lang: 'zh',
      items: [makePending({}, { subject_type: 'work_order', subject_id: 'wo-deadbeef' })],
      workOrderCache: new Map(), // 故意 miss
    });
    // cache miss → 不顯示 business_key，改顯示對象類型 + subjectId8（left + middle col 各一次 → 恰 2 次）。
    // 排除 subject_type 過濾 Select 的 <option>工單</option>（非 row 渲染）。
    expect(screen.getByText('…deadbeef')).toBeInTheDocument();
    const labels = screen.getAllByText('工單').filter(el => el.tagName !== 'OPTION');
    expect(labels).toHaveLength(2);
  });

  // ── 通過 / 駁回 接線 ──────────────────────────────────────────────────────

  it('每筆 row 都渲染 駁回 + 通過 兩顆按鈕', () => {
    renderPanel({ items: [makePending()] });
    expect(screen.getByRole('button', { name: '駁回' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '通過' })).toBeInTheDocument();
  });

  it('en：通過/駁回按鈕 aria-label 走英文（守 ui() 沒倒置）', () => {
    renderPanel({ lang: 'en', items: [makePending()] });
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('點「通過」→ onApproveClick 帶該 pending item', () => {
    const item = makePending({ id: 'step-A' }, { subject_id: 'wo-A' });
    const { onApproveClick } = renderPanel({ items: [item] });
    fireEvent.click(screen.getByRole('button', { name: '通過' }));
    expect(onApproveClick).toHaveBeenCalledTimes(1);
    // 守語意契約（傳回含正確 step.id 的 pending item）而非物件 identity
    expect(onApproveClick).toHaveBeenCalledWith(
      expect.objectContaining({ step: expect.objectContaining({ id: 'step-A' }) }),
    );
  });

  it('點「駁回」→ onRejectClick 帶該 pending item', () => {
    const item = makePending({ id: 'step-B' }, { subject_id: 'wo-B' });
    const { onRejectClick } = renderPanel({ items: [item] });
    fireEvent.click(screen.getByRole('button', { name: '駁回' }));
    expect(onRejectClick).toHaveBeenCalledTimes(1);
    expect(onRejectClick).toHaveBeenCalledWith(
      expect.objectContaining({ step: expect.objectContaining({ id: 'step-B' }) }),
    );
  });

  it('多筆 row：第 2 列的「通過」帶第 2 筆 pending item（按鈕順序對齊 items）', () => {
    const first = makePending({ id: 'step-1' }, { id: 'chain-1', subject_id: 'wo-1' });
    const second = makePending({ id: 'step-2' }, { id: 'chain-2', subject_id: 'wo-2' });
    const { onApproveClick } = renderPanel({ items: [first, second], total: 2 });
    const approveBtns = screen.getAllByRole('button', { name: '通過' });
    expect(approveBtns).toHaveLength(2);
    fireEvent.click(approveBtns[1]);
    expect(onApproveClick).toHaveBeenCalledTimes(1);
    expect(onApproveClick).toHaveBeenCalledWith(
      expect.objectContaining({ step: expect.objectContaining({ id: 'step-2' }) }),
    );
  });
});

/**
 * ApprovalActionDialog component render 測試（WMOM-20260605-06，EPIC-M5 測試覆蓋擴大）。
 *
 * `ApprovalActionDialog.tsx`（309 行）是 `/admin/workflow` 簽核流程的「最後一哩」對話框：
 * reviewer 從 PendingApprovalPanel 按下 通過 / 駁回 後彈出，在此確認簽核對象、填寫
 * 備註（approve 選填）/ 駁回原因（reject 必填）並送出。它與先前覆蓋的三大列表面板 +
 * PendingApprovalPanel（皆純 props 元件）不同——**本元件含 internal state（comment /
 * reason / submitting / error / warning）+ async 送出 + 樂觀關閉 / 錯誤回填**，
 * 是 workflow render 測試系列首個「有狀態 + 非同步」元件，覆蓋價值高於純展示面板。
 *
 * 本檔延續既有 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach
 * cleanup），守住對話框契約：
 *
 *   - 標題 / dialog aria-label 隨 mode（approve/reject）× lang（zh/en）切換
 *   - subject 摘要：workOrder 命中（business_key·turbine / title / priority·status pill）
 *     vs cache miss（subjectTypeLabel + …subjectId8）
 *   - step / chain context（層級 signoffLevelLabel、階段 sequence+1 / levels.length）
 *   - approve 模式：顯示「簽核備註（選填）」Input、無駁回 textarea；送出鈕一律可按
 *   - reject 模式：顯示「駁回原因 *」textarea、無備註 Input；reason 空白 → 送出鈕 disabled
 *   - 送出（approve）：onApprove(step.id, comment|null)，空備註送 null、有備註送 trim 值，成功 → onClose
 *   - 送出（reject）：onReject(step.id, reason.trim())，成功 → onClose
 *   - subject_transition_error：顯示警告卡且 **不** onClose（chain 已落地但工單 transition 失敗）
 *   - 送出拋錯：顯示 ⚠ 錯誤卡且 **不** onClose，送出鈕回復可按（submitting=false）
 *   - submitting 中：送出鈕文案「送出中…」/「Submitting…」且 disabled（防重複送出）
 *   - 關閉路徑：遮罩點擊 / ✕ / 取消 → onClose；對話框內容點擊 → 不 onClose（stopPropagation）
 *
 * 工廠以結構式滿足型別（不用 `as` 強轉）；async 送出測試以受控 Promise 斷言中間態，
 * 並一律 await 收尾（resolve + waitFor）以免 act 警告。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import ApprovalActionDialog, { type ApprovalMode } from '../ApprovalActionDialog';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  ApprovalResultResponse,
  PendingSignoffItem,
  SignoffChainResponse,
  SignoffStepResponse,
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

/** 產生結構完整的 WorkOrderResponse（mirror 自 PendingApprovalPanel.test 工廠）。 */
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

/** 產生 ApprovalResultResponse（預設成功、無 subject transition 錯誤）。 */
function makeResult(overrides: Partial<ApprovalResultResponse> = {}): ApprovalResultResponse {
  return {
    chain: makeChain(),
    chain_completed: false,
    subject_status_changed: false,
    subject_transition_error: null,
    ...overrides,
  };
}

interface RenderOpts {
  mode?: ApprovalMode;
  pending?: PendingSignoffItem;
  workOrder?: WorkOrderResponse | null;
  lang?: 'en' | 'zh';
  onApprove?: (stepId: string, comment: string | null) => Promise<ApprovalResultResponse>;
  onReject?: (stepId: string, reason: string) => Promise<ApprovalResultResponse>;
}

/** 渲染 ApprovalActionDialog + 回傳 callback spy，供斷言接線。 */
function renderDialog(opts: RenderOpts = {}) {
  const onClose = vi.fn();
  const onApprove = opts.onApprove ?? vi.fn(async () => makeResult());
  const onReject = opts.onReject ?? vi.fn(async () => makeResult());
  render(
    <ThemeProvider>
      <ApprovalActionDialog
        mode={opts.mode ?? 'approve'}
        pending={opts.pending ?? makePending()}
        workOrder={opts.workOrder ?? null}
        onClose={onClose}
        onApprove={onApprove}
        onReject={onReject}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onClose, onApprove, onReject };
}

describe('ApprovalActionDialog 簽核/駁回對話框', () => {
  afterEach(() => {
    cleanup();
  });

  // ── 標題 / dialog aria-label（mode × lang）─────────────────────────────────

  it('approve（zh）：標題「通過此階」、dialog aria-label「通過此階」', () => {
    renderDialog({ mode: 'approve', lang: 'zh' });
    expect(screen.getByRole('heading', { name: '通過此階' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '通過此階' })).toBeInTheDocument();
  });

  it('reject（zh）：標題「駁回簽核」、dialog aria-label「駁回簽核」', () => {
    renderDialog({ mode: 'reject', lang: 'zh' });
    expect(screen.getByRole('heading', { name: '駁回簽核' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '駁回簽核' })).toBeInTheDocument();
  });

  it('approve（en）：標題/aria 走英文「Approve step」（不外洩 zh）', () => {
    renderDialog({ mode: 'approve', lang: 'en' });
    expect(screen.getByRole('heading', { name: 'Approve step' })).toBeInTheDocument();
    expect(screen.queryByText('通過此階')).not.toBeInTheDocument();
  });

  it('reject（en）：標題/aria 走英文「Reject approval」（不外洩 zh）', () => {
    renderDialog({ mode: 'reject', lang: 'en' });
    expect(screen.getByRole('heading', { name: 'Reject approval' })).toBeInTheDocument();
    expect(screen.queryByText('駁回簽核')).not.toBeInTheDocument();
  });

  // ── subject 摘要 ───────────────────────────────────────────────────────────

  it('subject（workOrder 命中）：顯示 business_key·turbine / title / priority·status pill', () => {
    const wo = makeWO({
      business_key: 'WO-2026-0042',
      turbine_id: 'WTG-07',
      title: '主軸承異音檢查',
      priority: 'high',
      status: 'dispatched',
    });
    renderDialog({ workOrder: wo, lang: 'zh' });
    // 將 priority/status/type 斷言 scope 進 subject 摘要欄（避免日後別處出現「高」等字誤命中）。
    // title div 的父層即摘要欄（business_key / title / pills flex 同層 column）。
    const summary = screen.getByText('主軸承異音檢查').parentElement as HTMLElement;
    expect(within(summary).getByText('WO-2026-0042 · WTG-07')).toBeInTheDocument();
    // priority high → 高；status dispatched → 已派工
    expect(within(summary).getByText('高')).toBeInTheDocument();
    expect(within(summary).getByText('已派工')).toBeInTheDocument();
    // type corrective → 故障維修
    expect(within(summary).getByText(/故障維修/)).toBeInTheDocument();
  });

  it('subject（workOrder=null / cache miss）：fallback 顯示 subjectTypeLabel + …subjectId8', () => {
    renderDialog({
      workOrder: null,
      lang: 'zh',
      pending: makePending({}, { subject_type: 'material_request', subject_id: 'mr-abcd1234' }),
    });
    // fallback 為單一 div：「{subjectTypeLabel} · {slice}」，文字被 span 拆成多節點，
    // 故先以 monospace span（slice(-8)='abcd1234'）定位，再斷言其父 div 含完整 fallback 文字。
    const slice = screen.getByText('abcd1234');
    expect(slice.parentElement).toHaveTextContent('領料單 · abcd1234');
    // cache miss 不應出現 work_order 摘要欄位
    expect(screen.queryByText(/WO-2026-/)).not.toBeInTheDocument();
  });

  // ── step / chain context ────────────────────────────────────────────────────

  it('context：顯示層級（signoffLevelLabel）與階段（sequence+1 / levels.length）', () => {
    renderDialog({
      lang: 'zh',
      pending: makePending(
        { level: 'supervisor', sequence: 1 },
        { levels: ['leader', 'supervisor', 'treasury'] },
      ),
    });
    // 層級：supervisor → 主管
    expect(screen.getByText('層級:').parentElement).toHaveTextContent('主管');
    // 階段：sequence(1)+1 / levels.length(3) = 2 / 3
    expect(screen.getByText('階段:').parentElement).toHaveTextContent('2 / 3');
  });

  // ── approve / reject 輸入欄位互斥 ───────────────────────────────────────────

  it('approve 模式：顯示「簽核備註」Input、無「駁回原因」textarea', () => {
    renderDialog({ mode: 'approve', lang: 'zh' });
    expect(screen.getByLabelText('簽核備註')).toBeInTheDocument();
    expect(screen.queryByLabelText('駁回原因')).not.toBeInTheDocument();
  });

  it('reject 模式：顯示「駁回原因」textarea、無「簽核備註」Input', () => {
    renderDialog({ mode: 'reject', lang: 'zh' });
    expect(screen.getByLabelText('駁回原因')).toBeInTheDocument();
    expect(screen.queryByLabelText('簽核備註')).not.toBeInTheDocument();
  });

  // ── 送出鈕 disabled gating ─────────────────────────────────────────────────

  it('approve：送出鈕一律可按（備註選填，初始即 enabled）', () => {
    renderDialog({ mode: 'approve', lang: 'zh' });
    expect(screen.getByRole('button', { name: '確認通過' })).toBeEnabled();
  });

  it('reject：reason 為空 → 送出鈕 disabled；填入內容後 enabled', () => {
    renderDialog({ mode: 'reject', lang: 'zh' });
    const submit = screen.getByRole('button', { name: '確認駁回' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('駁回原因'), { target: { value: '缺工時紀錄' } });
    expect(submit).toBeEnabled();
  });

  it('reject：reason 僅空白字元 → 送出鈕仍 disabled（trim 後為空）', () => {
    renderDialog({ mode: 'reject', lang: 'zh' });
    fireEvent.change(screen.getByLabelText('駁回原因'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: '確認駁回' })).toBeDisabled();
  });

  // ── 送出 approve ───────────────────────────────────────────────────────────

  it('approve 送出（空備註）：onApprove(step.id, null) 且成功後 onClose', async () => {
    const { onApprove, onClose } = renderDialog({
      mode: 'approve',
      pending: makePending({ id: 'step-A' }),
    });
    fireEvent.click(screen.getByRole('button', { name: '確認通過' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onApprove).toHaveBeenCalledTimes(1);
    // 空備註經 `comment.trim() || null` → null
    expect(onApprove).toHaveBeenCalledWith('step-A', null);
  });

  it('approve 送出（有備註，workOrder 命中）：onApprove 帶 trim 後備註，成功 onClose', async () => {
    // 刻意以 workOrder 命中路徑跑 submit，確認 onClose happy path 與 workOrder 是否存在無關。
    const { onApprove, onClose } = renderDialog({
      mode: 'approve',
      pending: makePending({ id: 'step-A' }),
      workOrder: makeWO(),
    });
    fireEvent.change(screen.getByLabelText('簽核備註'), { target: { value: '  已現場確認  ' } });
    fireEvent.click(screen.getByRole('button', { name: '確認通過' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onApprove).toHaveBeenCalledWith('step-A', '已現場確認');
  });

  // ── 送出 reject ────────────────────────────────────────────────────────────

  it('reject 送出：onReject(step.id, reason.trim()) 且成功後 onClose', async () => {
    const { onReject, onClose } = renderDialog({
      mode: 'reject',
      pending: makePending({ id: 'step-B' }),
    });
    fireEvent.change(screen.getByLabelText('駁回原因'), { target: { value: '  材料規格不符  ' } });
    fireEvent.click(screen.getByRole('button', { name: '確認駁回' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledWith('step-B', '材料規格不符');
  });

  // ── subject_transition_error（警告但不關閉）────────────────────────────────

  it('送出回傳 subject_transition_error：顯示警告卡且不 onClose', async () => {
    const onApprove = vi.fn(async () =>
      makeResult({ subject_transition_error: 'work order not in DISPATCHED' }),
    );
    const { onClose } = renderDialog({ mode: 'approve', onApprove });
    fireEvent.click(screen.getByRole('button', { name: '確認通過' }));
    // 警告訊息（chain 已落地但工單 transition 失敗）顯示原始錯誤字串
    expect(await screen.findByText(/work order not in DISPATCHED/)).toBeInTheDocument();
    // chain 已落地 → 不算錯誤，但工單未轉態 → 留在對話框讓使用者知悉，不關閉
    expect(onClose).not.toHaveBeenCalled();
    // 半成功狀態：finally 將 submitting 設回 false → 送出鈕回復可按，
    // 使用者知情後可採取補正動作（領域：需通知 ops 補正工單狀態）。
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '確認通過' })).toBeEnabled(),
    );
  });

  // ── 送出拋錯（錯誤回填且不關閉）─────────────────────────────────────────────

  it('送出拋錯：顯示 ⚠ 錯誤卡、不 onClose、送出鈕回復可按', async () => {
    const onApprove = vi.fn(async () => {
      throw new Error('簽核失敗（409）');
    });
    const { onClose } = renderDialog({ mode: 'approve', onApprove });
    const submit = screen.getByRole('button', { name: '確認通過' });
    fireEvent.click(submit);
    expect(await screen.findByText(/⚠ 簽核失敗（409）/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    // finally 區塊把 submitting 設回 false → 按鈕回復可按（可重試）
    await waitFor(() => expect(submit).toBeEnabled());
  });

  it('拋錯後重試成功：舊 ⚠ 錯誤卡清除且 onClose（守 handleSubmit 開頭 setError(null)）', async () => {
    // 第一次拋錯、第二次成功，守住「重試前清除前次錯誤」行為——若 setError(null) 被挪到
    // finally 之外/之後，舊錯誤卡會殘留，此測試即可攔截該迴歸。
    let call = 0;
    const onApprove = vi.fn(async () => {
      call += 1;
      if (call === 1) throw new Error('暫時失敗（503）');
      return makeResult();
    });
    const { onClose } = renderDialog({ mode: 'approve', onApprove });
    const submit = screen.getByRole('button', { name: '確認通過' });
    fireEvent.click(submit);
    expect(await screen.findByText(/⚠ 暫時失敗（503）/)).toBeInTheDocument();
    await waitFor(() => expect(submit).toBeEnabled());
    // 重試：handleSubmit 開頭 setError(null) 清掉舊錯誤卡，成功後 onClose。
    fireEvent.click(submit);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/⚠ 暫時失敗（503）/)).not.toBeInTheDocument();
  });

  // ── submitting 中（防重複送出）──────────────────────────────────────────────

  it('submitting 中：送出鈕文案「送出中…」且 disabled（防重複送出）', async () => {
    // 受控 Promise：未 resolve 前停在 submitting，斷言中間態後再放行收尾。
    let resolve!: (v: ApprovalResultResponse) => void;
    const onApprove = vi.fn(
      () => new Promise<ApprovalResultResponse>(r => { resolve = r; }),
    );
    const { onClose } = renderDialog({ mode: 'approve', lang: 'zh', onApprove });
    fireEvent.click(screen.getByRole('button', { name: '確認通過' }));
    // submitting=true → 文案切換 + disabled。
    // 註：Btn 把 `ariaLabel` prop 渲染為 `aria-label` attribute（components/ui/Btn.tsx），
    // 且 submitting 中 `ariaLabel` 不變（ApprovalActionDialog 第 290-294 行），故即使 textContent
    // 切為「送出中…」，仍可用 accessible name「確認通過」定位該按鈕。
    const submit = await screen.findByRole('button', { name: '確認通過' });
    expect(submit).toHaveTextContent('送出中…');
    expect(submit).toBeDisabled();
    // 收尾：放行 Promise，待 onClose 觸發消化 pending act（避免警告）
    resolve(makeResult());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('submitting 中（en）：送出鈕文案走「Submitting…」', async () => {
    let resolve!: (v: ApprovalResultResponse) => void;
    const onApprove = vi.fn(
      () => new Promise<ApprovalResultResponse>(r => { resolve = r; }),
    );
    const { onClose } = renderDialog({ mode: 'approve', lang: 'en', onApprove });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm approve' }));
    const submit = await screen.findByRole('button', { name: 'Confirm approve' });
    expect(submit).toHaveTextContent('Submitting…');
    // 與 zh 版對稱：submitting 中送出鈕亦 disabled（防重複送出）。
    expect(submit).toBeDisabled();
    resolve(makeResult());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  // ── 關閉路徑 ───────────────────────────────────────────────────────────────

  it('點遮罩（overlay）→ onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    fireEvent.click(screen.getByRole('dialog', { name: '通過此階' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 ✕ 關閉鈕 → onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點「取消」→ onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點對話框內容（非遮罩）→ 不 onClose（stopPropagation 守住）', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    const overlay = screen.getByRole('dialog', { name: '通過此階' });
    // overlay 的直接子層即帶 stopPropagation 的內容 wrapper（ApprovalActionDialog 第 104-105 行）。
    // 直接點該節點本身 → stopPropagation 阻止冒泡到 overlay onClick（最精準守住該行為）。
    const innerWrapper = overlay.firstElementChild as HTMLElement;
    fireEvent.click(innerWrapper);
    expect(onClose).not.toHaveBeenCalled();
    // 再點更內層子孫（subject 摘要標題）亦不冒泡 → onClose 仍未觸發。
    fireEvent.click(screen.getByText('簽核對象'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

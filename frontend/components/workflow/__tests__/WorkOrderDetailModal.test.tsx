/**
 * WorkOrderDetailModal component render 測試（WMOM-20260606-03，EPIC-M5 測試覆蓋擴大）。
 *
 * `components/workflow/WorkOrderDetailModal.tsx`（933 行）是 `/admin/workflow` 工單詳情 +
 * 狀態機 transition 控制 modal：依 `work_order.status` 決定顯示哪些 action 按鈕
 *（dispatch / start_work / progress / finish / reject / cancel / reopen），點按開 collapsible
 * inline form 收集必填欄位 → 呼對應 callback → 成功後 patch 本地 WO + 收 form、失敗回填錯誤卡。
 *
 * 本系列先前覆蓋的多為「列表面板 / wizard」；本元件核心契約在 **status-driven 按鈕可見性 +
 * 7 個 transition form 的 gating / 序列化 / submitting 中態 / 成功後本地狀態更新 + 失敗錯誤回填**。
 * 先前無任何測試覆蓋。
 *
 * 延續既有 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup）。
 * 本元件依賴 `useCurrentUser`（dispatch form 顯示目前身份 + assignee fallback），故需
 * `UserProvider` 包裹；beforeEach 清 localStorage 確保 default user（Alice Chen）穩定。
 * 工廠以結構式滿足 `WorkOrderResponse`（不用 `as` 強轉）；async mutation 一律 await 收尾以免 act 警告。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within, act } from '@testing-library/react';
import React from 'react';
import WorkOrderDetailModal from '../WorkOrderDetailModal';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { UserProvider } from '../../../hooks/useCurrentUser';
import { DEFAULT_USER } from '../../../services/mockUsers';
import type {
  FollowupKind,
  WorkOrderResponse,
  WorkOrderStatus,
} from '../../../services/workOrderService';

type Lang = 'en' | 'zh';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 WorkOrderResponse（draft / 無派工 / 無進度），overrides 末尾 spread。 */
function makeWO(overrides: Partial<WorkOrderResponse> = {}): WorkOrderResponse {
  return {
    id: 'wo-1',
    business_key: 'WO-2026-001',
    farm_id: 'farm-a',
    turbine_id: 'WT-07',
    type: 'corrective',
    status: 'draft',
    priority: 'high',
    title: '齒輪箱異音檢修',
    description: '巡檢發現 NDE 側異音，需拆檢軸承。',
    source_alarm_id: null,
    source_alarm_code: null,
    assignee_id: null,
    crew_size: 2,
    estimated_hours: 6,
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
    updated_at: '2026-01-02T03:04:00Z',
    ...overrides,
  };
}

// ─── render helper ──────────────────────────────────────────────────────────

interface RenderOpts {
  workOrder?: WorkOrderResponse;
  farmIsOffshore?: boolean;
  lang?: Lang;
  onDispatch?: (id: string, assigneeId?: string) => Promise<WorkOrderResponse>;
  onStartWork?: (
    id: string,
    requireWeatherWindow: boolean,
    weatherWindowId?: string,
  ) => Promise<WorkOrderResponse>;
  onUpdateProgress?: (id: string, note: string) => Promise<WorkOrderResponse>;
  onFinish?: (
    id: string,
    payload: {
      actual_hours: number;
      followup_kind: FollowupKind;
      work_summary: string | null;
      unfinished_items: string | null;
      followup_note: string | null;
    },
  ) => Promise<WorkOrderResponse>;
  onReject?: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onCancel?: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onReopen?: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onClose?: () => void;
}

/** 預設所有 transition callback 都 resolve 回「同單但帶指定 overrides」的 WO。 */
function resolveWith(base: WorkOrderResponse, patch: Partial<WorkOrderResponse>) {
  return vi.fn().mockResolvedValue(makeWO({ ...base, ...patch }));
}

function renderModal(opts: RenderOpts = {}) {
  const wo = opts.workOrder ?? makeWO();
  const handlers = {
    onDispatch: opts.onDispatch ?? resolveWith(wo, { status: 'dispatched' }),
    onStartWork: opts.onStartWork ?? resolveWith(wo, { status: 'in_progress' }),
    onUpdateProgress: opts.onUpdateProgress ?? resolveWith(wo, {}),
    onFinish: opts.onFinish ?? resolveWith(wo, { status: 'awaiting_signoff' }),
    onReject: opts.onReject ?? resolveWith(wo, { status: 'in_progress' }),
    onCancel: opts.onCancel ?? resolveWith(wo, { status: 'cancelled' }),
    onReopen: opts.onReopen ?? resolveWith(wo, { status: 'reopened' }),
    onClose: opts.onClose ?? vi.fn(),
  };
  render(
    <ThemeProvider>
      <UserProvider>
        <WorkOrderDetailModal
          workOrder={wo}
          farmIsOffshore={opts.farmIsOffshore ?? false}
          lang={opts.lang ?? 'zh'}
          {...handlers}
        />
      </UserProvider>
    </ThemeProvider>,
  );
  return handlers;
}

/**
 * 取 footer action 按鈕（以 aria-label 精確命中）。
 *
 * ⚠ 僅可在「尚未開啟任何 inline form」時使用：form open 後 footer 開啟鈕與 form 提交鈕
 * aria-label 同字串（如 footer「開始作業」撞 form 提交「開始作業」）會讓 getByRole
 * 多重命中而拋錯。form open 後請改用下方 `formSubmit` 或 `getAllByRole` + scope。
 */
const footerBtn = (name: string) => screen.getByRole('button', { name });

/**
 * 取 inline form 內的「提交」按鈕。
 *
 * 多個 transition form 的提交按鈕 aria-label 與 footer 開啟按鈕同字串
 *（如 reject form 提交鈕「駁回」撞 footer「駁回」）→ 以 form 內 Cancel/Back 按鈕
 *（名稱皆唯一、不與 footer 撞）的同層容器 scope 提交按鈕，避免 getByRole 多重命中。
 */
const formSubmit = (cancelName: string, submitName: string) =>
  within(screen.getByRole('button', { name: cancelName }).parentElement as HTMLElement).getByRole(
    'button',
    { name: submitName },
  );

beforeEach(() => {
  // 清 localStorage 讓 UserProvider 一律 fallback 到 DEFAULT_USER（Alice Chen），
  // dispatch form 的 assignee fallback 斷言才穩定。
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 殼層 / 靜態展示 ─────────────────────────────────────────────────────────

describe('WorkOrderDetailModal — 殼層與靜態展示', () => {
  it('renders dialog 殼層：aria-label / 標題 / business_key / turbine / 類型', () => {
    renderModal({ workOrder: makeWO({ title: '齒輪箱異音檢修', business_key: 'WO-2026-009', turbine_id: 'WT-12' }) });
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-label', '工單詳情');
    expect(screen.getByRole('heading', { name: '齒輪箱異音檢修' })).toBeInTheDocument();
    expect(screen.getByText('WO-2026-009')).toBeInTheDocument();
    expect(screen.getByText('WT-12')).toBeInTheDocument();
    expect(screen.getByText('故障維修')).toBeInTheDocument(); // typeLabel corrective zh
  });

  it('detail grid：crew / est hours / 來源警報（有值 vs —）', () => {
    renderModal({ workOrder: makeWO({ crew_size: 3, estimated_hours: 8, source_alarm_code: 'ALM-42' }) });
    expect(screen.getByText('3p · 8h')).toBeInTheDocument();
    expect(screen.getByText('ALM-42')).toBeInTheDocument();
  });

  it('來源警報 / 預估工時為 null → 顯示 dash', () => {
    renderModal({ workOrder: makeWO({ estimated_hours: null, source_alarm_code: null }) });
    expect(screen.getByText('2p · —')).toBeInTheDocument(); // crew 2 default, est —
  });

  it('description 內容渲染', () => {
    renderModal({ workOrder: makeWO({ description: '更換 NDE 軸承並回填扭力值' }) });
    expect(screen.getByText('更換 NDE 軸承並回填扭力值')).toBeInTheDocument();
  });

  it('progress_notes 空時不渲染進度記錄區', () => {
    renderModal({ workOrder: makeWO({ progress_notes: [] }) });
    expect(screen.queryByText('進度記錄')).not.toBeInTheDocument();
  });

  it('progress_notes 有值 → 渲染計數 + 每筆內容', () => {
    renderModal({
      workOrder: makeWO({
        status: 'in_progress',
        progress_notes: [
          { timestamp: '2026-01-03T00:00:00Z', actor_id: 'a1', note: '已拆檢上半箱' },
          { timestamp: '2026-01-03T02:00:00Z', actor_id: 'a1', note: '訂購新軸承' },
        ],
      }),
    });
    expect(screen.getByText('進度記錄')).toBeInTheDocument();
    expect(screen.getByText('(2)')).toBeInTheDocument();
    expect(screen.getByText('已拆檢上半箱')).toBeInTheDocument();
    expect(screen.getByText('訂購新軸承')).toBeInTheDocument();
  });

  it('完工摘要區：closed 狀態顯示實際工時 / 後續處理 / 工作摘要', () => {
    renderModal({
      workOrder: makeWO({
        status: 'closed',
        actual_hours: 5.5,
        followup_kind: 'followup_needed',
        work_summary: '更換軸承完成',
        unfinished_items: '待回收舊件',
      }),
    });
    expect(screen.getByText('完工摘要')).toBeInTheDocument();
    expect(screen.getByText('實際工時:', { exact: false })).toHaveTextContent('5.5h');
    expect(screen.getByText('後續處理:', { exact: false })).toHaveTextContent('需追蹤');
    expect(screen.getByText('工作摘要:', { exact: false })).toHaveTextContent('更換軸承完成');
    expect(screen.getByText('未完事項:', { exact: false })).toHaveTextContent('待回收舊件');
  });

  it('取消 / 駁回 / 重開原因卡各自渲染', () => {
    renderModal({
      workOrder: makeWO({
        status: 'reopened',
        cancel_reason: '客戶延期',
        reject_reason: '工時填寫不符',
        reopen_reason: '異音復發',
      }),
    });
    expect(screen.getByText('客戶延期')).toBeInTheDocument();
    expect(screen.getByText('工時填寫不符')).toBeInTheDocument();
    expect(screen.getByText('異音復發')).toBeInTheDocument();
  });

  it('awaiting_signoff → 顯示待簽核提示卡', () => {
    renderModal({ workOrder: makeWO({ status: 'awaiting_signoff' }) });
    expect(screen.getByText(/等待簽核中/)).toBeInTheDocument();
  });

  it('lang=en → dialog aria-label / 狀態 pill / action 按鈕英文', () => {
    renderModal({ lang: 'en', workOrder: makeWO({ status: 'draft' }) });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Work order detail');
    expect(screen.getByText('DRAFT')).toBeInTheDocument();
    expect(screen.getByText('Corrective')).toBeInTheDocument();
    // draft footer action 按鈕英文化
    expect(screen.getByRole('button', { name: 'Dispatch' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});

// ─── status-driven 按鈕可見性 ───────────────────────────────────────────────

describe('WorkOrderDetailModal — status 驅動的 action 按鈕可見性', () => {
  it('draft → Dispatch + Cancel；無 Start work / Finish / Reopen', () => {
    renderModal({ workOrder: makeWO({ status: 'draft' }) });
    expect(footerBtn('派工')).toBeInTheDocument();
    expect(footerBtn('取消工單')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '開始作業' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完工' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重開' })).not.toBeInTheDocument();
  });

  it('dispatched → Start work + Cancel', () => {
    renderModal({ workOrder: makeWO({ status: 'dispatched' }) });
    expect(footerBtn('開始作業')).toBeInTheDocument();
    expect(footerBtn('取消工單')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '派工' })).not.toBeInTheDocument();
  });

  it('in_progress → Add progress + Finish + Cancel', () => {
    renderModal({ workOrder: makeWO({ status: 'in_progress' }) });
    expect(footerBtn('新增進度')).toBeInTheDocument();
    expect(footerBtn('完工')).toBeInTheDocument();
    expect(footerBtn('取消工單')).toBeInTheDocument();
  });

  it('awaiting_signoff → 只有 Reject（無 Cancel）', () => {
    renderModal({ workOrder: makeWO({ status: 'awaiting_signoff' }) });
    expect(footerBtn('駁回')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消工單' })).not.toBeInTheDocument();
  });

  it('closed → 只有 Reopen', () => {
    renderModal({ workOrder: makeWO({ status: 'closed' }) });
    expect(footerBtn('重開')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完工' })).not.toBeInTheDocument();
  });

  it('reopened → Start work（可重新開工）；不顯示取消工單', () => {
    renderModal({ workOrder: makeWO({ status: 'reopened' }) });
    expect(footerBtn('開始作業')).toBeInTheDocument();
    // canCancel = draft | dispatched | in_progress → reopened 不含取消
    expect(screen.queryByRole('button', { name: '取消工單' })).not.toBeInTheDocument();
  });

  it('cancelled → 無任何 action 按鈕（只剩 Close）', () => {
    renderModal({ workOrder: makeWO({ status: 'cancelled' }) });
    expect(screen.queryByRole('button', { name: '派工' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '開始作業' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增進度' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完工' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '駁回' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消工單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重開' })).not.toBeInTheDocument();
    // 僅剩 header ✕ + footer Close 兩個「關閉」鈕（無任何 transition action）
    expect(screen.getAllByRole('button', { name: '關閉' })).toHaveLength(2);
  });
});

// ─── transition forms：dispatch ─────────────────────────────────────────────

describe('WorkOrderDetailModal — dispatch form', () => {
  it('點派工 → 開 form 顯示目前身份；空 assignee → fallback currentUser.id', async () => {
    const onDispatch = resolveWith(makeWO(), { status: 'dispatched' });
    renderModal({ workOrder: makeWO({ status: 'draft', assignee_id: null }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    expect(screen.getByText(/目前身份/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(onDispatch).toHaveBeenCalledWith('wo-1', DEFAULT_USER.id));
  });

  it('已有 assignee 且 input 留空 → 用既有 assignee_id', async () => {
    const onDispatch = resolveWith(makeWO(), { status: 'dispatched' });
    renderModal({
      workOrder: makeWO({ status: 'draft', assignee_id: 'tech-existing' }),
      onDispatch,
    });
    fireEvent.click(footerBtn('派工'));
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(onDispatch).toHaveBeenCalledWith('wo-1', 'tech-existing'));
  });

  it('輸入 assignee → 帶 trim 後的值', async () => {
    const onDispatch = resolveWith(makeWO(), { status: 'dispatched' });
    renderModal({ workOrder: makeWO({ status: 'draft' }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    const input = screen.getByLabelText(/派工對象 UUID/);
    fireEvent.change(input, { target: { value: '  tech-99  ' } });
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(onDispatch).toHaveBeenCalledWith('wo-1', 'tech-99'));
  });

  it('assignee 只輸入空白 → trim 後視為空 → fallback currentUser.id', async () => {
    const onDispatch = resolveWith(makeWO(), { status: 'dispatched' });
    renderModal({ workOrder: makeWO({ status: 'draft', assignee_id: null }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    fireEvent.change(screen.getByLabelText(/派工對象 UUID/), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(onDispatch).toHaveBeenCalledWith('wo-1', DEFAULT_USER.id));
  });

  it('dispatch 成功 → 本地狀態更新為已派工（Dispatch 消失、Start work 出現）', async () => {
    renderModal({ workOrder: makeWO({ status: 'draft' }) });
    fireEvent.click(footerBtn('派工'));
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(screen.getByText('已派工')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '派工' })).not.toBeInTheDocument();
    expect(footerBtn('開始作業')).toBeInTheDocument();
  });

  it('dispatch 失敗 → 顯示錯誤卡且 form 不收合', async () => {
    const onDispatch = vi.fn().mockRejectedValue(new Error('派工後端拒絕'));
    renderModal({ workOrder: makeWO({ status: 'draft' }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(screen.getByText('⚠ 派工後端拒絕')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '確認派工' })).toBeInTheDocument();
  });

  it('dispatch 失敗後點 form 內取消 → resetForms 清除錯誤卡', async () => {
    const onDispatch = vi.fn().mockRejectedValue(new Error('派工後端拒絕'));
    renderModal({ workOrder: makeWO({ status: 'draft' }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    await waitFor(() => expect(screen.getByText('⚠ 派工後端拒絕')).toBeInTheDocument());
    // form 內取消 → resetForms() 內 setError(null) 應清掉錯誤卡並收 form
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.queryByText('⚠ 派工後端拒絕')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認派工' })).not.toBeInTheDocument();
  });

  it('submitting 中態 → 按鈕顯示「派工中…」且 disabled', async () => {
    let resolveFn: (v: WorkOrderResponse) => void = () => {};
    const onDispatch = vi.fn(
      () => new Promise<WorkOrderResponse>(r => { resolveFn = r; }),
    );
    renderModal({ workOrder: makeWO({ status: 'draft' }), onDispatch });
    fireEvent.click(footerBtn('派工'));
    fireEvent.click(screen.getByRole('button', { name: '確認派工' }));
    const submitting = await screen.findByText('派工中…');
    expect(submitting.closest('button')).toBeDisabled();
    // 收尾：resolve 觸發 setWO + resetForms 多筆 state update，包 act() 確保
    // flush 在 React 排程內完成，避免未來 renderer/scheduler 變更時冒出 act 警告。
    await act(async () => {
      resolveFn(makeWO({ status: 'dispatched' }));
    });
    expect(screen.getByText('已派工')).toBeInTheDocument();
  });
});

// ─── transition forms：start_work（onshore / offshore） ──────────────────────

describe('WorkOrderDetailModal — start_work form', () => {
  it('onshore → 確認直接 onStartWork(id, false)', async () => {
    const onStartWork = resolveWith(makeWO(), { status: 'in_progress' });
    renderModal({ workOrder: makeWO({ status: 'dispatched' }), farmIsOffshore: false, onStartWork });
    fireEvent.click(footerBtn('開始作業'));
    expect(screen.getByText(/陸上風場/)).toBeInTheDocument();
    fireEvent.click(formSubmit('取消', '開始作業'));
    await waitFor(() => expect(onStartWork).toHaveBeenCalledWith('wo-1', false));
  });

  it('offshore → 需先填 weather window，空時 Start 按鈕 disabled', () => {
    renderModal({ workOrder: makeWO({ status: 'dispatched' }), farmIsOffshore: true });
    fireEvent.click(footerBtn('開始作業'));
    expect(screen.getByText(/離岸風場/)).toBeInTheDocument();
    // footer 開啟鈕 + form 提交鈕 = 恰好 2 件「開始作業」；以 form 內唯一「取消」鈕
    // scope 出 form 提交鈕，驗其在空 weather window 時 disabled（footer 鈕則維持 enabled）。
    expect(screen.getAllByRole('button', { name: '開始作業' })).toHaveLength(2);
    expect(formSubmit('取消', '開始作業')).toBeDisabled();
  });

  it('offshore → 填 weather window 後 onStartWork(id, true, wwid)', async () => {
    const onStartWork = resolveWith(makeWO(), { status: 'in_progress' });
    renderModal({ workOrder: makeWO({ status: 'dispatched' }), farmIsOffshore: true, onStartWork });
    fireEvent.click(footerBtn('開始作業'));
    fireEvent.change(screen.getByLabelText('氣象視窗 ID'), {
      target: { value: '  ww-uuid-1  ' },
    });
    const enabled = screen
      .getAllByRole('button', { name: '開始作業' })
      .find(b => !(b as HTMLButtonElement).disabled);
    expect(enabled).toBeDefined(); // 填入 weather window 後 form 提交鈕應 enabled
    fireEvent.click(enabled!);
    await waitFor(() => expect(onStartWork).toHaveBeenCalledWith('wo-1', true, 'ww-uuid-1'));
  });
});

// ─── transition forms：progress / finish ────────────────────────────────────

describe('WorkOrderDetailModal — progress / finish form', () => {
  it('progress：空 note → Add note disabled；填入後 onUpdateProgress(id, note)', async () => {
    const onUpdateProgress = resolveWith(makeWO(), {});
    renderModal({ workOrder: makeWO({ status: 'in_progress' }), onUpdateProgress });
    fireEvent.click(footerBtn('新增進度'));
    expect(screen.getByRole('button', { name: '新增記錄' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('進度記錄'), { target: { value: '  已完成拆檢  ' } });
    const addBtn = screen.getByRole('button', { name: '新增記錄' });
    expect(addBtn).toBeEnabled();
    fireEvent.click(addBtn);
    await waitFor(() => expect(onUpdateProgress).toHaveBeenCalledWith('wo-1', '已完成拆檢'));
  });

  it('progress：只輸入空白 note → Add note 仍 disabled（與 finish 純空白守一致）', () => {
    renderModal({ workOrder: makeWO({ status: 'in_progress' }) });
    fireEvent.click(footerBtn('新增進度'));
    fireEvent.change(screen.getByLabelText('進度記錄'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: '新增記錄' })).toBeDisabled();
  });

  it('finish：actual_hours 空 → 點完成顯示驗證錯誤、不呼 onFinish', () => {
    const onFinish = resolveWith(makeWO(), { status: 'awaiting_signoff' });
    renderModal({ workOrder: makeWO({ status: 'in_progress' }), onFinish });
    fireEvent.click(footerBtn('完工'));
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    expect(screen.getByText(/實際工時必填/)).toBeInTheDocument();
    expect(onFinish).not.toHaveBeenCalled();
  });

  it('finish：actual_hours 填純空白 → 驗證錯誤、不呼 onFinish（不可當 0 工時送出）', () => {
    // 回歸測試：`Number('   ')` 會回 0 並通過 `hours < 0` 檢查，若 production 未先 trim
    // 會把「只敲空白」誤當成 0 工時送出（WMOM-20260606-03 review must-fix）。
    const onFinish = resolveWith(makeWO(), { status: 'awaiting_signoff' });
    renderModal({ workOrder: makeWO({ status: 'in_progress' }), onFinish });
    fireEvent.click(footerBtn('完工'));
    fireEvent.change(screen.getByLabelText('實際工時'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    expect(screen.getByText(/實際工時必填/)).toBeInTheDocument();
    expect(onFinish).not.toHaveBeenCalled();
  });

  it('finish：actual_hours=0 → 合法（>= 0），onFinish 帶 actual_hours: 0', async () => {
    // 「0 工時完工」是正當情境（直接關單未計工時）→ 守 production 用 `< 0` 而非 `<= 0` 的契約。
    const onFinish = resolveWith(makeWO(), { status: 'awaiting_signoff' });
    renderModal({ workOrder: makeWO({ status: 'in_progress' }), onFinish });
    fireEvent.click(footerBtn('完工'));
    fireEvent.change(screen.getByLabelText('實際工時'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    await waitFor(() =>
      expect(onFinish).toHaveBeenCalledWith('wo-1', expect.objectContaining({ actual_hours: 0 })),
    );
  });

  it('finish：填工時 → onFinish 帶完整 payload（work_summary / followup_note trim / null 空值）', async () => {
    const onFinish = resolveWith(makeWO(), { status: 'awaiting_signoff' });
    renderModal({ workOrder: makeWO({ status: 'in_progress' }), onFinish });
    fireEvent.click(footerBtn('完工'));
    fireEvent.change(screen.getByLabelText('實際工時'), { target: { value: '4.5' } });
    fireEvent.change(screen.getByLabelText('工作摘要'), { target: { value: '  更換完成  ' } });
    // followup_needed → 顯示追蹤備註欄位，一併驗其 trim
    fireEvent.change(screen.getByLabelText('後續處理'), { target: { value: 'followup_needed' } });
    fireEvent.change(screen.getByLabelText('追蹤備註'), { target: { value: '  30 天後複檢  ' } });
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    await waitFor(() =>
      expect(onFinish).toHaveBeenCalledWith('wo-1', {
        actual_hours: 4.5,
        followup_kind: 'followup_needed',
        work_summary: '更換完成',
        unfinished_items: null,
        followup_note: '30 天後複檢',
      }),
    );
  });

  it('finish：followup_kind=followup_needed → 顯示未完事項 / 追蹤備註欄位', () => {
    renderModal({ workOrder: makeWO({ status: 'in_progress' }) });
    fireEvent.click(footerBtn('完工'));
    expect(screen.queryByLabelText('未完事項')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('後續處理'), { target: { value: 'followup_needed' } });
    expect(screen.getByLabelText('未完事項')).toBeInTheDocument();
    expect(screen.getByLabelText('追蹤備註')).toBeInTheDocument();
  });
});

// ─── transition forms：reject / cancel / reopen ─────────────────────────────

describe('WorkOrderDetailModal — reject / cancel / reopen form', () => {
  it('reject：空 reason → disabled；填入後 onReject(id, reason)', async () => {
    const onReject = resolveWith(makeWO(), { status: 'in_progress' });
    renderModal({ workOrder: makeWO({ status: 'awaiting_signoff' }), onReject });
    fireEvent.click(footerBtn('駁回'));
    expect(formSubmit('取消', '駁回')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('駁回原因'), { target: { value: '工時不符' } });
    fireEvent.click(formSubmit('取消', '駁回'));
    await waitFor(() => expect(onReject).toHaveBeenCalledWith('wo-1', '工時不符'));
  });

  it('cancel：空 reason → disabled；填入後 onCancel(id, reason)', async () => {
    const onCancel = resolveWith(makeWO(), { status: 'cancelled' });
    renderModal({ workOrder: makeWO({ status: 'draft' }), onCancel });
    fireEvent.click(footerBtn('取消工單'));
    expect(formSubmit('返回', '取消工單')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '客戶延期' } });
    fireEvent.click(formSubmit('返回', '取消工單'));
    await waitFor(() => expect(onCancel).toHaveBeenCalledWith('wo-1', '客戶延期'));
  });

  it('reopen：空 reason → disabled；填入後 onReopen(id, reason)', async () => {
    const onReopen = resolveWith(makeWO(), { status: 'reopened' });
    renderModal({ workOrder: makeWO({ status: 'closed' }), onReopen });
    fireEvent.click(footerBtn('重開'));
    expect(formSubmit('取消', '重開')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('重開原因'), { target: { value: '異音復發' } });
    fireEvent.click(formSubmit('取消', '重開'));
    await waitFor(() => expect(onReopen).toHaveBeenCalledWith('wo-1', '異音復發'));
  });

  it('非 dispatch transition 失敗（cancel reject）→ 共用 error path 回填錯誤卡且 form 不收合', async () => {
    const onCancel = vi.fn().mockRejectedValue(new Error('取消後端拒絕'));
    renderModal({ workOrder: makeWO({ status: 'draft' }), onCancel });
    fireEvent.click(footerBtn('取消工單'));
    fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '客戶延期' } });
    fireEvent.click(formSubmit('返回', '取消工單'));
    await waitFor(() => expect(screen.getByText('⚠ 取消後端拒絕')).toBeInTheDocument());
    // form 未收合 → 取消原因欄位仍在
    expect(screen.getByLabelText('取消原因')).toBeInTheDocument();
  });
});

// ─── 關閉路徑 ───────────────────────────────────────────────────────────────

describe('WorkOrderDetailModal — 關閉路徑', () => {
  it('點 backdrop → onClose', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 content（標題）→ stopPropagation 不觸發 onClose', () => {
    const onClose = vi.fn();
    renderModal({ workOrder: makeWO({ title: '齒輪箱異音檢修' }), onClose });
    fireEvent.click(screen.getByRole('heading', { name: '齒輪箱異音檢修' }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('footer Close 鈕 → onClose', () => {
    const onClose = vi.fn();
    renderModal({ workOrder: makeWO({ status: 'awaiting_signoff' }), onClose });
    // header ✕ 與 footer 皆 aria-label「關閉」→ 取最後一個（footer Close 鈕）
    const closeBtns = screen.getAllByRole('button', { name: '關閉' });
    fireEvent.click(closeBtns[closeBtns.length - 1]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

/**
 * MaterialRequestDetailModal component render 測試（WMOM-20260606-04，EPIC-M5 測試覆蓋擴大）。
 *
 * `components/workflow/MaterialRequestDetailModal.tsx`（902 行）是 `/admin/workflow` 領料單詳情 +
 * 狀態機 transition 控制 modal：依 `materialRequest.status` 決定顯示哪些 footer action 按鈕
 *（submit / dispatch / receive / close / cancel / return），點按開 collapsible inline form 收集
 * 必填欄位 → 呼對應 callback → 成功後 patch 本地 MR + 收 form、失敗回填錯誤卡。
 *
 * 核心契約：**status-driven 按鈕可見性（9 態）+ 6 個 transition form 的 gating / 序列化 /
 * submitting 中態 / 成功後本地狀態更新 + 失敗錯誤回填 + receive 數量驗證 + return payload 組裝**。
 * 先前無任何測試覆蓋（前一輪 WorkOrderDetailModal 為其姊妹 detail modal）。
 *
 * 延續既有 render 測試範式（ThemeProvider + UserProvider 雙層包裹 + jest-dom matcher +
 * afterEach cleanup）。本元件依賴 `useCurrentUser`（多數 transition 以 currentUser.id 當 actor），
 * 故 beforeEach 清 localStorage 確保 default user（Alice Chen）穩定。工廠以結構式滿足
 * `MaterialRequestResponse`（不用 `as` 強轉）；async mutation 一律 await 收尾以免 act 警告。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
  within,
  act,
} from '@testing-library/react';
import React from 'react';
import MaterialRequestDetailModal from '../MaterialRequestDetailModal';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { UserProvider } from '../../../hooks/useCurrentUser';
import { DEFAULT_USER } from '../../../services/mockUsers';
import type {
  MaterialRequestItem,
  MaterialRequestResponse,
  MaterialRequestStatus,
} from '../../../services/materialService';

type Lang = 'en' | 'zh';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 MaterialRequestItem，overrides 末尾 spread。 */
function makeItem(overrides: Partial<MaterialRequestItem> = {}): MaterialRequestItem {
  return {
    id: 'item-row-1',
    request_id: 'mr-1',
    item_id: 'inv-aaaaaaaa0001',
    estimated_qty: 4,
    actual_qty: null,
    stock_kind: 'new',
    sku: 'BRG-NDE-001',
    name: 'NDE 軸承',
    unit: 'pcs',
    ...overrides,
  };
}

/** 產生結構完整的 MaterialRequestResponse（draft / 單 item / 無 timeline）。 */
function makeMR(overrides: Partial<MaterialRequestResponse> = {}): MaterialRequestResponse {
  return {
    id: 'mr-1',
    business_key: 'MR-2026-001',
    farm_id: 'farm-a',
    requester_id: 'req-1',
    work_order_id: null,
    status: 'draft',
    items: [makeItem()],
    signoff_chain_id: null,
    requested_at: '2026-01-01T00:00:00Z',
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
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T03:04:00Z',
    ...overrides,
  };
}

// ─── render helper ──────────────────────────────────────────────────────────

interface RenderOpts {
  materialRequest?: MaterialRequestResponse;
  lang?: Lang;
  onSubmitForApproval?: (id: string, actorId: string) => Promise<MaterialRequestResponse>;
  onDispatch?: (id: string, actorId: string) => Promise<MaterialRequestResponse>;
  onReceive?: (
    id: string,
    actorId: string,
    actualQuantities: Record<string, number>,
  ) => Promise<MaterialRequestResponse>;
  onClose?: (id: string, actorId: string) => Promise<MaterialRequestResponse>;
  onCancel?: (id: string, actorId: string, reason: string) => Promise<MaterialRequestResponse>;
  onCreateReturn?: (id: string, payload: unknown) => Promise<void>;
  onCloseModal?: () => void;
}

/** 預設 transition callback 都 resolve 回「同單但帶指定 status 變化」的 MR。 */
function resolveWith(base: MaterialRequestResponse, patch: Partial<MaterialRequestResponse>) {
  return vi.fn().mockResolvedValue(makeMR({ ...base, ...patch }));
}

function renderModal(opts: RenderOpts = {}) {
  const mr = opts.materialRequest ?? makeMR();
  const handlers = {
    onSubmitForApproval:
      opts.onSubmitForApproval ?? resolveWith(mr, { status: 'awaiting_approval' }),
    onDispatch: opts.onDispatch ?? resolveWith(mr, { status: 'dispatched' }),
    onReceive: opts.onReceive ?? resolveWith(mr, { status: 'received' }),
    onClose: opts.onClose ?? resolveWith(mr, { status: 'closed' }),
    onCancel: opts.onCancel ?? resolveWith(mr, { status: 'cancelled' }),
    onCreateReturn: opts.onCreateReturn ?? vi.fn().mockResolvedValue(undefined),
    onCloseModal: opts.onCloseModal ?? vi.fn(),
  };
  render(
    <ThemeProvider>
      <UserProvider>
        <MaterialRequestDetailModal
          materialRequest={mr}
          lang={opts.lang ?? 'zh'}
          {...handlers}
        />
      </UserProvider>
    </ThemeProvider>,
  );
  return handlers;
}

/**
 * 取 footer / form 內按鈕（以 aria-label 精確命中）。本元件 footer 開啟鈕與 form 提交鈕
 * aria-label **互不相同**（footer「派發」vs form「確認派發」等），故大多可直接 getByRole。
 * 唯一重複的是「關閉」（header ✕ + footer Close 共 2 件）→ 改用 getAllByRole 取最後一個（footer）。
 */
const btn = (name: string) => screen.getByRole('button', { name });
const footerClose = () => {
  const all = screen.getAllByRole('button', { name: '關閉' });
  return all[all.length - 1];
};

beforeEach(() => {
  // 清 localStorage 讓 UserProvider 一律 fallback 到 DEFAULT_USER（Alice Chen），
  // 各 transition 的 actorId fallback 斷言才穩定。
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 殼層 / 靜態展示 ─────────────────────────────────────────────────────────

describe('MaterialRequestDetailModal — 殼層與靜態展示', () => {
  it('renders dialog 殼層：aria-label / 標題 / business_key / status pill', () => {
    renderModal({ materialRequest: makeMR({ business_key: 'MR-2026-009' }) });
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-label', '領料單詳情');
    expect(screen.getByRole('heading', { name: '領料單' })).toBeInTheDocument();
    expect(screen.getByText('MR-2026-009')).toBeInTheDocument();
    expect(screen.getByText('草稿')).toBeInTheDocument(); // draft zh status pill
  });

  it('關聯工單 work_order_id → 顯示工單尾碼（slice -8）；無關聯則不顯示', () => {
    renderModal({ materialRequest: makeMR({ work_order_id: 'wo-aabbcc12345678' }) });
    // 尾碼 slice(-8) 與「工單」label 在同一 span（多個 text node）→ 用 substring regex
    expect(screen.getByText(/12345678/)).toBeInTheDocument();
    expect(screen.getByText(/工單/)).toBeInTheDocument();
  });

  it('無關聯工單 → 不渲染工單尾碼', () => {
    renderModal({ materialRequest: makeMR({ work_order_id: null }) });
    expect(screen.queryByText(/工單/)).not.toBeInTheDocument();
  });

  it('timeline grid：申請時間有值（Asia/Taipei 格式）/ 未發生時間顯示 dash', () => {
    renderModal({ materialRequest: makeMR({ requested_at: '2026-03-15T01:30:00Z' }) });
    // UTC 01:30 → Taipei +8 → 09:30
    expect(screen.getByText('2026-03-15 09:30')).toBeInTheDocument();
    // 6 個 timeline 格 + 1 個 actual_qty 格皆未發生 → 多個 dash
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(6);
  });

  it('items table：sku / 名稱 / 庫存類型 / 預估量 / 單位渲染', () => {
    renderModal({
      materialRequest: makeMR({
        items: [makeItem({ sku: 'BRG-007', name: '主軸承', estimated_qty: 3, unit: 'pcs', stock_kind: 'new' })],
      }),
    });
    expect(screen.getByText('BRG-007')).toBeInTheDocument();
    expect(screen.getByText('主軸承')).toBeInTheDocument();
    expect(screen.getByText('全新')).toBeInTheDocument(); // stock_kind new zh
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('pcs')).toBeInTheDocument();
  });

  it('item sku/name/unit 缺漏 → fallback 顯示（item_id 尾碼 / 料件已不在主檔 / dash）', () => {
    renderModal({
      materialRequest: makeMR({
        items: [makeItem({ sku: null, name: null, unit: null, item_id: 'inv-deadbeef0001' })],
      }),
    });
    // sku 缺漏 → fallback `…${item_id.slice(-12)}`（與「…」分屬不同 text node）→ substring regex
    expect(screen.getByText(/deadbeef0001/)).toBeInTheDocument();
    expect(screen.getByText('(料件已不在主檔)')).toBeInTheDocument();
  });

  it('actual_qty 有值 → 顯示實領量', () => {
    renderModal({
      materialRequest: makeMR({
        status: 'received',
        items: [makeItem({ estimated_qty: 5, actual_qty: 4 })],
      }),
    });
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('cancel_reason 有值 → 渲染取消原因卡', () => {
    renderModal({
      materialRequest: makeMR({ status: 'cancelled', cancel_reason: '重複申請' }),
    });
    expect(screen.getByText('取消原因')).toBeInTheDocument();
    expect(screen.getByText('重複申請')).toBeInTheDocument();
  });

  it('reject_reason 有值 → 渲染駁回原因卡', () => {
    renderModal({
      materialRequest: makeMR({ status: 'rejected', reject_reason: '預算超標' }),
    });
    expect(screen.getByText('駁回原因')).toBeInTheDocument();
    expect(screen.getByText('預算超標')).toBeInTheDocument();
  });

  it('lang=en：殼層標題 / status pill 英文化', () => {
    renderModal({ materialRequest: makeMR({ status: 'approved' }), lang: 'en' });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Material request detail');
    expect(screen.getByRole('heading', { name: 'Material request' })).toBeInTheDocument();
    expect(screen.getByText('APPROVED')).toBeInTheDocument();
  });
});

// ─── status-driven footer 按鈕可見性 ────────────────────────────────────────

describe('MaterialRequestDetailModal — status-driven 按鈕可見性', () => {
  it('draft：送出簽核 + 取消；無派發/簽收/結案/退料', () => {
    renderModal({ materialRequest: makeMR({ status: 'draft' }) });
    expect(btn('送出簽核')).toBeInTheDocument();
    expect(btn('取消領料單')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '派發' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '簽收' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '結案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建退料' })).not.toBeInTheDocument();
  });

  it('awaiting_approval：只有取消（無送簽 / 無退料）', () => {
    renderModal({ materialRequest: makeMR({ status: 'awaiting_approval' }) });
    expect(btn('取消領料單')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '送出簽核' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建退料' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '派發' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '簽收' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '結案' })).not.toBeInTheDocument();
  });

  it('approved：派發 + 取消', () => {
    renderModal({ materialRequest: makeMR({ status: 'approved' }) });
    expect(btn('派發')).toBeInTheDocument();
    expect(btn('取消領料單')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '簽收' })).not.toBeInTheDocument();
  });

  it('dispatched：簽收 + 退料（不可再取消）', () => {
    renderModal({ materialRequest: makeMR({ status: 'dispatched' }) });
    expect(btn('簽收')).toBeInTheDocument();
    expect(btn('建退料')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消領料單' })).not.toBeInTheDocument();
  });

  it('received：結案 + 退料', () => {
    renderModal({ materialRequest: makeMR({ status: 'received' }) });
    expect(btn('結案')).toBeInTheDocument();
    expect(btn('建退料')).toBeInTheDocument();
  });

  it('used：結案 + 退料', () => {
    renderModal({ materialRequest: makeMR({ status: 'used' }) });
    expect(btn('結案')).toBeInTheDocument();
    expect(btn('建退料')).toBeInTheDocument();
  });

  it('closed：無任何 action（只剩 header ✕ + footer Close）', () => {
    renderModal({ materialRequest: makeMR({ status: 'closed' }) });
    const actionNames = ['送出簽核', '派發', '簽收', '結案', '取消領料單', '建退料'];
    for (const n of actionNames) {
      expect(screen.queryByRole('button', { name: n })).not.toBeInTheDocument();
    }
    // header ✕ + footer Close 皆 aria-label「關閉」
    expect(screen.getAllByRole('button', { name: '關閉' })).toHaveLength(2);
  });

  it('cancelled：無任何 action 按鈕', () => {
    renderModal({ materialRequest: makeMR({ status: 'cancelled' }) });
    const actionNames = ['送出簽核', '派發', '簽收', '結案', '取消領料單', '建退料'];
    for (const n of actionNames) {
      expect(screen.queryByRole('button', { name: n })).not.toBeInTheDocument();
    }
  });

  it('rejected：無任何 action 按鈕', () => {
    renderModal({ materialRequest: makeMR({ status: 'rejected' }) });
    const actionNames = ['送出簽核', '派發', '簽收', '結案', '取消領料單', '建退料'];
    for (const n of actionNames) {
      expect(screen.queryByRole('button', { name: n })).not.toBeInTheDocument();
    }
  });
});

// ─── submit / dispatch / close form（單一確認按鈕）──────────────────────────

describe('MaterialRequestDetailModal — submit / dispatch / close 確認流程', () => {
  it('submit：開 form → 確認 → onSubmitForApproval(id, currentUser.id) + 成功後狀態更新', async () => {
    const mr = makeMR({ status: 'draft' });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('送出簽核'));
    await act(async () => {
      fireEvent.click(btn('確認送簽'));
    });
    expect(h.onSubmitForApproval).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id);
    // 成功後本地 MR → awaiting_approval：送簽鈕消失、取消仍在
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '送出簽核' })).not.toBeInTheDocument();
    });
  });

  it('dispatch：approved → 確認 → onDispatch(id, actor) + 成功後本地狀態更新（派發鈕消失、出現簽收）', async () => {
    const mr = makeMR({ status: 'approved' });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('派發'));
    await act(async () => {
      fireEvent.click(btn('確認派發'));
    });
    expect(h.onDispatch).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id);
    // setMR(updated)→dispatched：派發鈕消失、簽收出現
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '派發' })).not.toBeInTheDocument();
    });
    expect(btn('簽收')).toBeInTheDocument();
  });

  it('close：received → 確認 → onClose(id, actor) + 成功後本地狀態更新（結案鈕消失）', async () => {
    const mr = makeMR({ status: 'received' });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('結案'));
    await act(async () => {
      fireEvent.click(btn('確認結案'));
    });
    expect(h.onClose).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id);
    // setMR(updated)→closed：所有 action 按鈕消失
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '結案' })).not.toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: '建退料' })).not.toBeInTheDocument();
  });

  it('開 form 後 footer 其他開啟鈕 disabled（activeForm 鎖定）', () => {
    renderModal({ materialRequest: makeMR({ status: 'draft' }) });
    fireEvent.click(btn('送出簽核'));
    // footer 取消鈕在 form open 期間 disabled
    expect(btn('取消領料單')).toBeDisabled();
  });

  it('submit 失敗 → 錯誤卡顯示且 form 不收合', async () => {
    const mr = makeMR({ status: 'draft' });
    const onSubmitForApproval = vi.fn().mockRejectedValue(new Error('簽核 chain 建立失敗'));
    renderModal({ materialRequest: mr, onSubmitForApproval });
    fireEvent.click(btn('送出簽核'));
    await act(async () => {
      fireEvent.click(btn('確認送簽'));
    });
    expect(await screen.findByText(/簽核 chain 建立失敗/)).toBeInTheDocument();
    // form 仍開（確認送簽鈕還在）
    expect(btn('確認送簽')).toBeInTheDocument();
  });

  it('submitting 中態：確認鈕顯示「送簽中…」且 disabled（受控 Promise）', async () => {
    const mr = makeMR({ status: 'draft' });
    let resolveFn: (v: MaterialRequestResponse) => void = () => {};
    const onSubmitForApproval = vi.fn().mockReturnValue(
      new Promise<MaterialRequestResponse>(res => {
        resolveFn = res;
      }),
    );
    renderModal({ materialRequest: mr, onSubmitForApproval });
    fireEvent.click(btn('送出簽核'));
    fireEvent.click(btn('確認送簽'));
    // 中間態：用 waitFor 等 setSubmitting(true) re-render 後「進入 disabled + 文字切換」，
    // 而非 findByRole（後者元素已存在即 resolve，不保證 disabled 已生效）
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '確認送簽' })).toBeDisabled();
      expect(screen.getByText('送簽中…')).toBeInTheDocument();
    });
    // 收尾 resolve 讓 form 收合避免 act 警告
    await act(async () => {
      resolveFn(makeMR({ ...mr, status: 'awaiting_approval' }));
    });
  });

  it('form 內取消（Back/Cancel）→ 收合 form 不呼 callback', async () => {
    const mr = makeMR({ status: 'draft' });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('送出簽核'));
    expect(btn('確認送簽')).toBeInTheDocument();
    // resetForms() 連呼多個 setState → 以 act 包覆 click 確保 re-render flush 後再斷言
    await act(async () => {
      fireEvent.click(btn('取消')); // submit form 的 reset 按鈕 aria-label「取消」
    });
    expect(screen.queryByRole('button', { name: '確認送簽' })).not.toBeInTheDocument();
    expect(h.onSubmitForApproval).not.toHaveBeenCalled();
  });
});

// ─── cancel form（reason gating）─────────────────────────────────────────────

describe('MaterialRequestDetailModal — cancel form', () => {
  it('空原因 → 確認鈕 disabled；填入 → onCancel(id, currentUser.id, trimmed)', async () => {
    const mr = makeMR({ status: 'draft' });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('取消領料單'));
    const confirm = btn('確認取消');
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText('取消原因'), {
      target: { value: '  重複申請  ' },
    });
    expect(btn('確認取消')).not.toBeDisabled();
    await act(async () => {
      fireEvent.click(btn('確認取消'));
    });
    expect(h.onCancel).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id, '重複申請');
    // setMR(updated)→cancelled：所有 action 按鈕消失（含取消領料單）
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '取消領料單' })).not.toBeInTheDocument();
    });
  });

  it('純空白原因 → 確認鈕保持 disabled', () => {
    renderModal({ materialRequest: makeMR({ status: 'draft' }) });
    fireEvent.click(btn('取消領料單'));
    fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '   ' } });
    expect(btn('確認取消')).toBeDisabled();
  });

  it('submitting 中態：確認鈕顯示「取消中…」且 disabled（受控 Promise）', async () => {
    const mr = makeMR({ status: 'draft' });
    let resolveFn: (v: MaterialRequestResponse) => void = () => {};
    const onCancel = vi.fn().mockReturnValue(
      new Promise<MaterialRequestResponse>(res => {
        resolveFn = res;
      }),
    );
    renderModal({ materialRequest: mr, onCancel });
    fireEvent.click(btn('取消領料單'));
    fireEvent.change(screen.getByLabelText('取消原因'), { target: { value: '重複申請' } });
    fireEvent.click(btn('確認取消'));
    await waitFor(() => {
      expect(screen.getByText('取消中…')).toBeInTheDocument();
    });
    await act(async () => {
      resolveFn(makeMR({ ...mr, status: 'cancelled' }));
    });
  });
});

// ─── receive form（數量預填 + 驗證）─────────────────────────────────────────

describe('MaterialRequestDetailModal — receive form', () => {
  it('開 form 自動以 estimated_qty 預填，可編輯後 → onReceive(id, actor, parsed)', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    // 開 form 後預填值由 useEffect 設定（非同步）→ 用 findByDisplayValue 等 effect flush，
    // 不依賴 fireEvent 內隱 act 同步性
    fireEvent.click(btn('簽收'));
    const input = (await screen.findByDisplayValue('4')) as HTMLInputElement;
    expect(input).toHaveAttribute('aria-label', 'actual_qty inv-1111');
    fireEvent.change(input, { target: { value: '3' } });
    await act(async () => {
      fireEvent.click(btn('確認簽收'));
    });
    expect(h.onReceive).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id, { 'row-1': 3 });
    // setMR(updated)→received：簽收鈕消失、出現結案
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '簽收' })).not.toBeInTheDocument();
    });
    expect(btn('結案')).toBeInTheDocument();
  });

  it('負數 actual_qty → 顯示驗證錯誤且不呼 onReceive', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('簽收'));
    fireEvent.change(screen.getByLabelText('actual_qty inv-1111'), {
      target: { value: '-1' },
    });
    await act(async () => {
      fireEvent.click(btn('確認簽收')); // setError 同步 setState → act 包覆
    });
    expect(screen.getByText(/非負整數/)).toBeInTheDocument();
    expect(h.onReceive).not.toHaveBeenCalled();
  });

  it('空值 actual_qty（NaN）→ 顯示驗證錯誤且不呼 onReceive', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('簽收'));
    fireEvent.change(screen.getByLabelText('actual_qty inv-1111'), {
      target: { value: '' },
    });
    await act(async () => {
      fireEvent.click(btn('確認簽收')); // setError 同步 setState → act 包覆
    });
    expect(screen.getByText(/非負整數/)).toBeInTheDocument();
    expect(h.onReceive).not.toHaveBeenCalled();
  });

  it('0 actual_qty 合法（守 < 0 非 <= 0）→ onReceive 帶 0', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('簽收'));
    fireEvent.change(screen.getByLabelText('actual_qty inv-1111'), {
      target: { value: '0' },
    });
    await act(async () => {
      fireEvent.click(btn('確認簽收'));
    });
    expect(h.onReceive).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id, { 'row-1': 0 });
  });

  it('小數 actual_qty → parseInt 截斷為整數送出（記錄 production 邊界行為）', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('簽收'));
    fireEvent.change(screen.getByLabelText('actual_qty inv-1111'), {
      target: { value: '3.5' },
    });
    await act(async () => {
      fireEvent.click(btn('確認簽收'));
    });
    // parseInt('3.5', 10) === 3：不報錯、截斷送出
    expect(h.onReceive).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id, { 'row-1': 3 });
  });

  it('多 item → 各自 actual_qty 收集為 record', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [
        makeItem({ id: 'row-1', item_id: 'inv-1111', estimated_qty: 4 }),
        makeItem({ id: 'row-2', item_id: 'inv-2222', estimated_qty: 2, sku: 'GSK-002', name: '墊片' }),
      ],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('簽收'));
    fireEvent.change(screen.getByLabelText('actual_qty inv-1111'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('actual_qty inv-2222'), { target: { value: '1' } });
    await act(async () => {
      fireEvent.click(btn('確認簽收'));
    });
    expect(h.onReceive).toHaveBeenCalledWith('mr-1', DEFAULT_USER.id, {
      'row-1': 4,
      'row-2': 1,
    });
  });
});

// ─── return form（payload 組裝 + gating）────────────────────────────────────

describe('MaterialRequestDetailModal — return form', () => {
  it('未選 item → 確認退料 disabled；選 item + 數量 → onCreateReturn payload 正確', async () => {
    const mr = makeMR({
      status: 'received',
      items: [makeItem({ item_id: 'inv-1111', sku: 'BRG-007', estimated_qty: 4 })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('建退料'));
    // 未選 item → disabled
    expect(btn('確認退料')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('退料項目'), { target: { value: 'inv-1111' } });
    fireEvent.change(screen.getByLabelText('退料數量'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('退料原因'), { target: { value: 'wrong_part' } });
    fireEvent.change(screen.getByLabelText('退回庫存類型'), { target: { value: 'used' } });
    fireEvent.change(screen.getByLabelText('退料備註'), { target: { value: '  拿錯料件  ' } });
    expect(btn('確認退料')).not.toBeDisabled();
    await act(async () => {
      fireEvent.click(btn('確認退料'));
    });
    expect(h.onCreateReturn).toHaveBeenCalledWith('mr-1', {
      item_id: 'inv-1111',
      qty: 2,
      reason: 'wrong_part',
      return_to_kind: 'used',
      returned_by: DEFAULT_USER.id,
      note: '拿錯料件',
    });
    // return 成功走獨立 try/finally（非 runMutation）→ resetForms() 收合 form
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '確認退料' })).not.toBeInTheDocument();
    });
  });

  it('數量 < 1 → 確認退料 disabled', () => {
    const mr = makeMR({
      status: 'received',
      items: [makeItem({ item_id: 'inv-1111' })],
    });
    renderModal({ materialRequest: mr });
    fireEvent.click(btn('建退料'));
    fireEvent.change(screen.getByLabelText('退料項目'), { target: { value: 'inv-1111' } });
    fireEvent.change(screen.getByLabelText('退料數量'), { target: { value: '0' } });
    expect(btn('確認退料')).toBeDisabled();
  });

  it('空備註 → payload note = null（預設 surplus / new）', async () => {
    const mr = makeMR({
      status: 'dispatched',
      items: [makeItem({ item_id: 'inv-1111' })],
    });
    const h = renderModal({ materialRequest: mr });
    fireEvent.click(btn('建退料'));
    fireEvent.change(screen.getByLabelText('退料項目'), { target: { value: 'inv-1111' } });
    // 數量預設 '1'，reason 預設 surplus，kind 預設 new
    await act(async () => {
      fireEvent.click(btn('確認退料'));
    });
    expect(h.onCreateReturn).toHaveBeenCalledWith('mr-1', {
      item_id: 'inv-1111',
      qty: 1,
      reason: 'surplus',
      return_to_kind: 'new',
      returned_by: DEFAULT_USER.id,
      note: null,
    });
  });

  it('return 失敗 → 錯誤卡顯示且 form 不收合', async () => {
    const mr = makeMR({
      status: 'received',
      items: [makeItem({ item_id: 'inv-1111' })],
    });
    const onCreateReturn = vi.fn().mockRejectedValue(new Error('庫存回補失敗'));
    renderModal({ materialRequest: mr, onCreateReturn });
    fireEvent.click(btn('建退料'));
    fireEvent.change(screen.getByLabelText('退料項目'), { target: { value: 'inv-1111' } });
    await act(async () => {
      fireEvent.click(btn('確認退料'));
    });
    expect(await screen.findByText(/庫存回補失敗/)).toBeInTheDocument();
    expect(btn('確認退料')).toBeInTheDocument();
  });
});

// ─── 關閉路徑 ────────────────────────────────────────────────────────────────

describe('MaterialRequestDetailModal — 關閉路徑', () => {
  it('點 backdrop → onCloseModal', () => {
    const h = renderModal({ materialRequest: makeMR() });
    fireEvent.click(screen.getByRole('dialog'));
    expect(h.onCloseModal).toHaveBeenCalledTimes(1);
  });

  it('點 modal 內容（標題）→ stopPropagation，不觸發 onCloseModal', () => {
    const h = renderModal({ materialRequest: makeMR() });
    fireEvent.click(screen.getByRole('heading', { name: '領料單' }));
    expect(h.onCloseModal).not.toHaveBeenCalled();
  });

  it('footer Close → onCloseModal', () => {
    const h = renderModal({ materialRequest: makeMR() });
    fireEvent.click(footerClose());
    expect(h.onCloseModal).toHaveBeenCalledTimes(1);
  });

  it('header ✕ → onCloseModal', () => {
    const h = renderModal({ materialRequest: makeMR() });
    const all = screen.getAllByRole('button', { name: '關閉' });
    fireEvent.click(all[0]); // header ✕（第一個）
    expect(h.onCloseModal).toHaveBeenCalledTimes(1);
  });

  it('lang=en：footer Close / 送簽 action 按鈕英文化', () => {
    renderModal({ materialRequest: makeMR({ status: 'draft' }), lang: 'en' });
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
    // header ✕ + footer Close 皆英文「Close」
    expect(screen.getAllByRole('button', { name: 'Close' }).length).toBeGreaterThanOrEqual(2);
  });
});

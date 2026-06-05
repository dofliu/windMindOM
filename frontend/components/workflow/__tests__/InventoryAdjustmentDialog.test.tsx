/**
 * InventoryAdjustmentDialog component render 測試（WMOM-20260605-07，EPIC-M5 測試覆蓋擴大）。
 *
 * `InventoryAdjustmentDialog.tsx`（339 行）是 `/admin/workflow` 庫存頁的「手動 +/- 調整」
 * 對話框：使用者選 stock kind（全新 / 良品 / 維修中）、填整數異動量（允許負）、必填原因、
 * 選填備註，送出呼 `useInventory.adjust`。它與 ApprovalActionDialog 同屬 workflow render
 * 測試系列中**含 internal state（deltaKind / deltaRaw / reason / note / submitting / error）
 * + 即時預覽計算 + async 送出 + 樂觀關閉 / 錯誤回填**的有狀態元件，先前無任何測試。
 *
 * 與 ApprovalActionDialog 不同處：本元件依賴 `useCurrentUser`（送出 payload 帶 actor_id），
 * 故 render wrapper 需同時包 `ThemeProvider` + `UserProvider`，並在 beforeEach 清 localStorage
 * 確保 currentUser 落在 DEFAULT_USER（actor_id 斷言可預測）。
 *
 * 本檔延續既有 render 測試範式（Provider 包裹 + jest-dom matcher + afterEach cleanup），
 * 守住對話框契約：
 *
 *   - 標題 / dialog aria-label 隨 lang（zh/en）切換；header 副標題 `{sku} · {name}`
 *   - 目前 stock 三欄回顧（new / used / repairing label + qty）
 *   - 切 stock kind → 預覽 currentQty 改用對應欄位
 *   - delta 預覽：`{label}: {old} {sign}{delta} = {next}`；無效（0 / 空 / NaN）→ 顯示「—」
 *   - 扣到負數 → preview 警告卡（⚠ 409 提示）
 *   - 送出鈕 gating：delta 必須非 0 且有限、reason 必填（trim 後非空）
 *   - 送出：onAdjust 收正確 payload（delta_kind / delta / reason.trim / actor_id / note）；
 *     空備註 → note=undefined、有備註 → trim；成功 → onAdjusted(result) + onClose
 *   - 送出拋錯：⚠ 錯誤卡且 **不** onClose，送出鈕回復可按（finally → submitting=false）
 *   - submitting 中：送出鈕文案「送出中…」/「Submitting…」且 disabled（防重複送出）
 *   - 關閉路徑：遮罩 / ✕ / 取消 → onClose；對話框內容點擊 → 不 onClose（stopPropagation）
 *
 * 工廠以結構式滿足型別（不用 `as` 強轉）；async 送出測試以受控 Promise 斷言中間態，
 * 並一律 await 收尾（resolve + waitFor）以免 act 警告。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import InventoryAdjustmentDialog from '../InventoryAdjustmentDialog';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { UserProvider } from '../../../hooks/useCurrentUser';
import { DEFAULT_USER } from '../../../services/mockUsers';
import type {
  AdjustInventoryPayload,
  AdjustInventoryResult,
  AdjustmentLogResponse,
  InventoryItemResponse,
} from '../../../services/inventoryService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 InventoryItemResponse（所有欄位齊備，不用 `as` 強轉）。 */
function makeItem(overrides: Partial<InventoryItemResponse> = {}): InventoryItemResponse {
  return {
    id: 'inv-00000001',
    sku: 'BRG-MAIN-01',
    name: '主軸承',
    description: '主軸承總成',
    unit: 'pcs',
    farm_id: 'farm-a',
    warehouse_id: 'wh-1',
    stock_new: 10,
    stock_used: 4,
    stock_repairing: 2,
    safety_stock: 3,
    unit_cost: '120000.00',
    last_received_at: null,
    last_used_at: null,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-02T08:30:00Z',
    total_available: 14,
    below_safety: false,
    ...overrides,
  };
}

/** 產生 AdjustmentLogResponse（送出成功 result 的 log 部分）。 */
function makeLog(overrides: Partial<AdjustmentLogResponse> = {}): AdjustmentLogResponse {
  return {
    id: 'log-1',
    item_id: 'inv-00000001',
    delta_kind: 'new',
    delta: 1,
    reason: '盤盈',
    actor_id: DEFAULT_USER.id,
    note: null,
    occurred_at: '2026-06-05T10:00:00Z',
    ...overrides,
  };
}

/** 產生 AdjustInventoryResult（item patch + log）。 */
function makeResult(overrides: Partial<AdjustInventoryResult> = {}): AdjustInventoryResult {
  return {
    item: makeItem(),
    log: makeLog(),
    ...overrides,
  };
}

interface RenderOpts {
  item?: InventoryItemResponse;
  lang?: 'en' | 'zh';
  onAdjust?: (req: AdjustInventoryPayload) => Promise<AdjustInventoryResult>;
  onAdjusted?: (result: AdjustInventoryResult) => void;
}

/** 渲染 InventoryAdjustmentDialog + 回傳 callback spy，供斷言接線。 */
function renderDialog(opts: RenderOpts = {}) {
  const onClose = vi.fn();
  const onAdjust = opts.onAdjust ?? vi.fn(async () => makeResult());
  const onAdjusted = opts.onAdjusted ?? vi.fn();
  render(
    <ThemeProvider>
      <UserProvider>
        <InventoryAdjustmentDialog
          item={opts.item ?? makeItem()}
          onAdjust={onAdjust}
          onClose={onClose}
          onAdjusted={onAdjusted}
          lang={opts.lang ?? 'zh'}
        />
      </UserProvider>
    </ThemeProvider>,
  );
  return { onClose, onAdjust, onAdjusted };
}

// ─── 共用 query helper（以 aria-label 定位互動控制項）────────────────────────

const getDeltaInput = () => screen.getByRole('spinbutton', { name: '異動量數值' });
const getReasonInput = () => screen.getByRole('textbox', { name: '異動原因' });
const getNoteInput = () => screen.getByRole('textbox', { name: '異動備註' });
const getKindSelect = () => screen.getByRole('combobox', { name: '選擇庫存類別' });
const getSubmitBtn = () => screen.getByRole('button', { name: '送出異動' });

/** 預覽卡：以「預覽」label 的父 Card div 定位（含 deltaKind: old±delta = next 文字）。
 *  以 null-guard 取代 `as HTMLElement` 強轉（CLAUDE.md §7 不用 as）。 */
function getPreviewCard(): HTMLElement {
  const card = screen.getByText('預覽').parentElement;
  if (!card) throw new Error('預覽卡未找到');
  return card;
}

describe('InventoryAdjustmentDialog 庫存調整對話框', () => {
  beforeEach(() => {
    // currentUser 走 localStorage 持久化；清掉確保每個 test 落在 DEFAULT_USER。
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  // ── 標題 / dialog aria-label（lang）─────────────────────────────────────────

  it('zh：dialog aria-label「調整庫存」、標題「調整庫存」、副標 sku · name', () => {
    renderDialog({ lang: 'zh' });
    expect(screen.getByRole('dialog', { name: '調整庫存' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '調整庫存' })).toBeInTheDocument();
    expect(screen.getByText('BRG-MAIN-01 · 主軸承')).toBeInTheDocument();
  });

  it('en：dialog aria-label「Adjust inventory」與標題「Adjust stock」可區分（不外洩 zh）', () => {
    renderDialog({ lang: 'en' });
    // dialog aria-label 與 heading 在 en 故意不同字串（inventory vs stock）。
    expect(screen.getByRole('dialog', { name: 'Adjust inventory' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Adjust stock' })).toBeInTheDocument();
    expect(screen.queryByText('調整庫存')).not.toBeInTheDocument();
  });

  // ── 目前 stock 三欄回顧 ─────────────────────────────────────────────────────

  it('三欄回顧顯示 new/used/repairing label + 對應 qty', () => {
    renderDialog({ item: makeItem({ stock_new: 10, stock_used: 4, stock_repairing: 2 }), lang: 'zh' });
    // 「全新/良品/維修中」label 在 Select option / preview 也出現，故 scope 進三欄回顧 grid 斷言。
    // 以 grid 的 `grid-template-columns: repeat(3,1fr)` inline style 定位（全頁唯一；overlay 雖
    // display:grid 但無 grid-template-columns），取代 parentElement 鏈式 + `as` 強轉。
    const reviewGrid = screen.getByText('10').closest('[style*="grid-template-columns"]');
    if (!(reviewGrid instanceof HTMLElement)) throw new Error('三欄回顧 grid 未找到');
    expect(within(reviewGrid).getByText('全新')).toBeInTheDocument();
    expect(within(reviewGrid).getByText('良品')).toBeInTheDocument();
    expect(within(reviewGrid).getByText('維修中')).toBeInTheDocument();
    // 三欄 qty（10 / 4 / 2）皆顯示
    expect(within(reviewGrid).getByText('10')).toBeInTheDocument();
    expect(within(reviewGrid).getByText('4')).toBeInTheDocument();
    expect(within(reviewGrid).getByText('2')).toBeInTheDocument();
  });

  // ── delta 預覽 ──────────────────────────────────────────────────────────────

  it('預設（new / delta=1）：預覽顯示「全新: 10 +1 = 11」', () => {
    renderDialog({ lang: 'zh' });
    expect(getPreviewCard()).toHaveTextContent('全新: 10 +1 = 11');
  });

  it('delta 為負：預覽帶負號（良品 4 -2 = 2），不誤加 +', () => {
    renderDialog({ lang: 'zh' });
    fireEvent.change(getKindSelect(), { target: { value: 'used' } });
    fireEvent.change(getDeltaInput(), { target: { value: '-2' } });
    expect(getPreviewCard()).toHaveTextContent('良品: 4 -2 = 2');
  });

  it('切 stock kind：預覽 currentQty 改用對應欄位（維修中 2）', () => {
    renderDialog({ lang: 'zh' });
    fireEvent.change(getKindSelect(), { target: { value: 'repairing' } });
    // delta 仍預設 1 → 維修中: 2 +1 = 3
    expect(getPreviewCard()).toHaveTextContent('維修中: 2 +1 = 3');
  });

  it('delta 無效（0）：預覽尾段顯示「—」、送出鈕 disabled', () => {
    renderDialog({ lang: 'zh' });
    fireEvent.change(getDeltaInput(), { target: { value: '0' } });
    expect(getPreviewCard()).toHaveTextContent('全新: 10 —');
    expect(getSubmitBtn()).toBeDisabled();
  });

  it('delta 清空（NaN）：預覽顯示「—」、送出鈕 disabled', () => {
    renderDialog({ lang: 'zh' });
    fireEvent.change(getDeltaInput(), { target: { value: '' } });
    expect(getPreviewCard()).toHaveTextContent('全新: 10 —');
    expect(getSubmitBtn()).toBeDisabled();
  });

  // ── 扣到負數警告 ───────────────────────────────────────────────────────────

  it('扣到負數：preview 顯示 ⚠ 409 警告（但送出鈕仍可按，交由後端拒）', () => {
    renderDialog({ item: makeItem({ stock_new: 1 }), lang: 'zh' });
    fireEvent.change(getDeltaInput(), { target: { value: '-5' } });
    expect(getPreviewCard()).toHaveTextContent('全新: 1 -5 = -4');
    expect(screen.getByText(/庫存將為負數/)).toBeInTheDocument();
    // reason 填好後，負庫存不阻擋前端送出（前端只警告，由 backend 回 409）
    fireEvent.change(getReasonInput(), { target: { value: '盤虧' } });
    expect(getSubmitBtn()).not.toBeDisabled();
  });

  it('正常加庫：不顯示負數警告', () => {
    renderDialog({ lang: 'zh' });
    expect(screen.queryByText(/庫存將為負數/)).not.toBeInTheDocument();
  });

  // ── 送出鈕 gating ──────────────────────────────────────────────────────────

  it('reason 必填：空 reason → 送出鈕 disabled；填入後 enabled', () => {
    renderDialog({ lang: 'zh' });
    // 預設 reason 空 → disabled（delta 有效但 reason 缺）
    expect(getSubmitBtn()).toBeDisabled();
    fireEvent.change(getReasonInput(), { target: { value: '盤盈' } });
    expect(getSubmitBtn()).not.toBeDisabled();
  });

  it('reason 僅空白：trim 後仍視為空 → 送出鈕 disabled', () => {
    renderDialog({ lang: 'zh' });
    fireEvent.change(getReasonInput(), { target: { value: '   ' } });
    expect(getSubmitBtn()).toBeDisabled();
  });

  // ── 送出 happy path ────────────────────────────────────────────────────────

  it('送出（空備註）：onAdjust 收 delta_kind/delta/reason.trim/actor_id，note=undefined；成功 onAdjusted + onClose', async () => {
    const onAdjust = vi.fn(async () => makeResult());
    const { onClose, onAdjusted } = renderDialog({ onAdjust, lang: 'zh' });
    fireEvent.change(getReasonInput(), { target: { value: '  盤盈  ' } });
    fireEvent.click(getSubmitBtn());
    await waitFor(() => expect(onAdjust).toHaveBeenCalledTimes(1));
    expect(onAdjust).toHaveBeenCalledWith({
      delta_kind: 'new',
      delta: 1,
      reason: '盤盈', // trim
      actor_id: DEFAULT_USER.id,
      note: undefined, // 空備註 → undefined
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    // 斷言 onAdjusted 收到完整 result（item + log 具體欄位），非僅「log 存在」的弱檢查。
    expect(onAdjusted).toHaveBeenCalledWith(
      expect.objectContaining({
        item: expect.objectContaining({ id: 'inv-00000001' }),
        log: expect.objectContaining({
          delta_kind: 'new',
          delta: 1,
          reason: '盤盈',
          actor_id: DEFAULT_USER.id,
        }),
      }),
    );
  });

  it('送出（有備註 + 換 kind + 負 delta）：payload 反映選擇，note 經 trim', async () => {
    const onAdjust = vi.fn(async () => makeResult());
    const { onClose } = renderDialog({ onAdjust, lang: 'zh' });
    fireEvent.change(getKindSelect(), { target: { value: 'used' } });
    fireEvent.change(getDeltaInput(), { target: { value: '-3' } });
    fireEvent.change(getReasonInput(), { target: { value: '良品歸還' } });
    fireEvent.change(getNoteInput(), { target: { value: '  現場回收  ' } });
    fireEvent.click(getSubmitBtn());
    await waitFor(() => expect(onAdjust).toHaveBeenCalledTimes(1));
    expect(onAdjust).toHaveBeenCalledWith({
      delta_kind: 'used',
      delta: -3,
      reason: '良品歸還',
      actor_id: DEFAULT_USER.id,
      note: '現場回收', // trim
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('onAdjusted 省略：送出成功仍不拋錯、照常 onClose（optional chain `onAdjusted?.` 守住）', async () => {
    const onAdjust = vi.fn(async () => makeResult());
    const onClose = vi.fn();
    // 直接 render 不傳 onAdjusted（renderDialog 預設會塞 spy），驗 optional chain 守得住。
    render(
      <ThemeProvider>
        <UserProvider>
          <InventoryAdjustmentDialog
            item={makeItem()}
            onAdjust={onAdjust}
            onClose={onClose}
            lang="zh"
          />
        </UserProvider>
      </ThemeProvider>,
    );
    fireEvent.change(getReasonInput(), { target: { value: '盤盈' } });
    fireEvent.click(getSubmitBtn());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onAdjust).toHaveBeenCalledTimes(1);
  });

  // ── 送出拋錯 ───────────────────────────────────────────────────────────────

  it('送出拋錯：顯示 ⚠ 錯誤卡、不 onClose、送出鈕回復可按', async () => {
    const onAdjust = vi.fn(async () => {
      throw new Error('409 Insufficient Stock');
    });
    const { onClose } = renderDialog({ onAdjust, lang: 'zh' });
    fireEvent.change(getReasonInput(), { target: { value: '盤虧' } });
    fireEvent.click(getSubmitBtn());
    // 錯誤訊息回填
    await waitFor(() => expect(screen.getByText(/409 Insufficient Stock/)).toBeInTheDocument());
    // 半失敗：不關閉，讓 user 可修正重送
    expect(onClose).not.toHaveBeenCalled();
    // finally → submitting=false，送出鈕回復可按
    expect(getSubmitBtn()).not.toBeDisabled();
  });

  it('拋錯後重試成功：清除舊錯誤卡並 onClose（守 setError(null) 置於 handleSubmit 開頭）', async () => {
    const onAdjust = vi
      .fn<(req: AdjustInventoryPayload) => Promise<AdjustInventoryResult>>()
      .mockRejectedValueOnce(new Error('409 Insufficient Stock'))
      .mockResolvedValueOnce(makeResult());
    const { onClose } = renderDialog({ onAdjust, lang: 'zh' });
    fireEvent.change(getReasonInput(), { target: { value: '盤虧' } });
    fireEvent.click(getSubmitBtn());
    await waitFor(() => expect(screen.getByText(/409 Insufficient Stock/)).toBeInTheDocument());
    // 重試（改正方向）
    fireEvent.change(getDeltaInput(), { target: { value: '2' } });
    fireEvent.click(getSubmitBtn());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    // 舊錯誤卡已清
    expect(screen.queryByText(/409 Insufficient Stock/)).not.toBeInTheDocument();
  });

  // ── submitting 受控 Promise ─────────────────────────────────────────────────

  it('submitting 中（zh）：送出鈕文案「送出中…」且 disabled（防重複送出）', async () => {
    let resolveAdjust: (r: AdjustInventoryResult) => void = () => {};
    const onAdjust = vi.fn(
      () =>
        new Promise<AdjustInventoryResult>(res => {
          resolveAdjust = res;
        }),
    );
    const { onClose } = renderDialog({ onAdjust, lang: 'zh' });
    fireEvent.change(getReasonInput(), { target: { value: '盤盈' } });
    fireEvent.click(getSubmitBtn());
    // submitting 中：以 aria-label 定位（accessible name 不變），文案切「送出中…」、disabled
    await waitFor(() => expect(getSubmitBtn()).toHaveTextContent('送出中…'));
    expect(getSubmitBtn()).toBeDisabled();
    // resolve 後 await onClose 收尾——確保 promise 解析後的 state 更新（onAdjusted/onClose/
    // setSubmitting(false)）在 test 邊界內 flush，避免洩漏到下個 test 觸發 act 警告。
    resolveAdjust(makeResult());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('submitting 中（en）：送出鈕文案「Submitting…」且 disabled', async () => {
    let resolveAdjust: (r: AdjustInventoryResult) => void = () => {};
    const onAdjust = vi.fn(
      () =>
        new Promise<AdjustInventoryResult>(res => {
          resolveAdjust = res;
        }),
    );
    const { onClose } = renderDialog({ onAdjust, lang: 'en' });
    fireEvent.change(screen.getByRole('textbox', { name: 'Adjustment reason' }), {
      target: { value: 'count surplus' },
    });
    const submit = screen.getByRole('button', { name: 'Submit adjustment' });
    fireEvent.click(submit);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Submit adjustment' })).toHaveTextContent('Submitting…'),
    );
    expect(screen.getByRole('button', { name: 'Submit adjustment' })).toBeDisabled();
    resolveAdjust(makeResult());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  // ── 關閉路徑 ───────────────────────────────────────────────────────────────

  it('點遮罩（overlay = role=dialog 節點本身，onClick=onClose）→ onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    // 元件把 role="dialog" 與 onClick={onClose} 放在同一全螢幕 overlay div 上，
    // 點它（未被 content wrapper 的 stopPropagation 攔截）即觸發 onClose。
    fireEvent.click(screen.getByRole('dialog', { name: '調整庫存' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 ✕ → onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點取消 → onClose', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點對話框內容（wrapper 本身）→ 不 onClose（stopPropagation 守住）', () => {
    const { onClose } = renderDialog({ lang: 'zh' });
    const overlay = screen.getByRole('dialog', { name: '調整庫存' });
    // overlay 第一個子節點即 content wrapper（onClick stopPropagation）
    const wrapper = overlay.firstElementChild as HTMLElement;
    fireEvent.click(wrapper);
    expect(onClose).not.toHaveBeenCalled();
    // 更內層子孫（如標題）點擊一樣不冒泡到遮罩
    fireEvent.click(within(wrapper).getByRole('heading', { name: '調整庫存' }));
    expect(onClose).not.toHaveBeenCalled();
  });
});

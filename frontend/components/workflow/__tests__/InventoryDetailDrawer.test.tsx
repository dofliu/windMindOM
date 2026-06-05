/**
 * InventoryDetailDrawer component render 測試（WMOM-20260605-08，EPIC-M5 測試覆蓋擴大）。
 *
 * `InventoryDetailDrawer.tsx`（478 行）是 `/admin/workflow` 庫存頁右側滑出的「料件詳情」
 * drawer：顯示完整料件資料（identity / stocks / safety / metadata / audit log）、
 * 「+ 調整庫存」按鈕開內嵌 `InventoryAdjustmentDialog`、audit log 於 drawer 開啟時
 * lazy load（`loadAdjustments(item.id)`）並於 adjust 成功後 reload。先前無任何測試。
 *
 * 與本系列前幾支（純展示 Panel）不同處：本元件有 **async lifecycle**
 * （mount useEffect → loadAdjustments → logs / loading / error 三態）+ **內嵌另一個
 * 有狀態對話框**（adjust 成功回呼觸發 reload）。故測試需：
 *   - render wrapper 同包 `ThemeProvider` + `UserProvider`（內嵌 dialog 依賴 useCurrentUser）
 *   - 每個 test 都 await 初始 load 結算（避免 async setState 洩漏觸發 act 警告）
 *
 * 本檔延續既有 render 測試範式（Provider 包裹 + jest-dom matcher + afterEach cleanup），
 * 守住 drawer 契約：
 *
 *   - dialog aria-label / 關閉鈕 aria-label 隨 lang（zh/en）切換；header 顯示 sku + name
 *   - 庫存分項三欄（new/used/repairing label + qty）、可用總計 / 安全庫存
 *   - below_safety=true → LOW pill；false → 無 pill
 *   - metadata：unit / unit_cost / description（空 → (none)/（無））/ warehouse_id 末 8 碼 /
 *     四個時間欄走 fmtDateTime（Asia/Taipei）
 *   - audit log：mount 即呼 loadAdjustments(item.id)；空 → 「尚無異動紀錄。」、
 *     有 log → AuditRow（sign+delta + kind label + reason + note(選填) + actor 末 8 碼 + 時間）、
 *     reject → ⚠ 錯誤卡且不顯示空狀態、header 計數隨 logs.length
 *   - Refresh 鈕 → 再次呼 loadAdjustments
 *   - 「+ 調整庫存」→ 開內嵌 InventoryAdjustmentDialog（drawer dialog 與 adjust dialog
 *     同時存在，以 aria-label 區分）；內嵌 dialog 送出 → onAdjust 收 (item.id, payload)，
 *     成功觸發 onAdjusted → loadAdjustments reload
 *   - 關閉路徑：遮罩 / ✕ → onClose；drawer 內容點擊 → 不 onClose（stopPropagation）
 *
 * 工廠以結構式滿足型別（不用 `as` 強轉）。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import InventoryDetailDrawer from '../InventoryDetailDrawer';
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
    warehouse_id: 'warehouse-12345678',
    stock_new: 10,
    stock_used: 4,
    stock_repairing: 2,
    safety_stock: 3,
    unit_cost: '120000.00',
    last_received_at: '2026-06-01T00:00:00Z',
    last_used_at: null,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-02T08:30:00Z',
    total_available: 14,
    below_safety: false,
    ...overrides,
  };
}

/** 產生 AdjustmentLogResponse（audit log 一列）。 */
function makeLog(overrides: Partial<AdjustmentLogResponse> = {}): AdjustmentLogResponse {
  return {
    id: 'log-1',
    item_id: 'inv-00000001',
    delta_kind: 'new',
    delta: 5,
    reason: '盤盈',
    actor_id: 'usr-deadbeef',
    note: null,
    occurred_at: '2026-06-05T10:00:00Z',
    ...overrides,
  };
}

/** 產生 AdjustInventoryResult（內嵌 dialog 送出成功的回傳）。 */
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
  logs?: AdjustmentLogResponse[];
  onAdjust?: (itemId: string, req: AdjustInventoryPayload) => Promise<AdjustInventoryResult>;
  loadAdjustments?: (itemId: string) => Promise<AdjustmentLogResponse[]>;
}

/** 渲染 InventoryDetailDrawer + 回傳 callback spy，供斷言接線。 */
function renderDrawer(opts: RenderOpts = {}) {
  const onClose = vi.fn();
  const onAdjust = opts.onAdjust ?? vi.fn(async () => makeResult());
  const loadAdjustments =
    opts.loadAdjustments ?? vi.fn(async () => opts.logs ?? []);
  render(
    <ThemeProvider>
      <UserProvider>
        <InventoryDetailDrawer
          item={opts.item ?? makeItem()}
          onAdjust={onAdjust}
          loadAdjustments={loadAdjustments}
          onClose={onClose}
          lang={opts.lang ?? 'zh'}
        />
      </UserProvider>
    </ThemeProvider>,
  );
  return { onClose, onAdjust, loadAdjustments };
}

/** 等 mount 觸發的 lazy load 完全結算。
 *  不只等 `loadAdjustments` 被呼（call recording 同步），更等 `refreshLogs` 內部
 *  後續的 `setLogs` / `setLogsLoading(false)` flush 完——以 Refresh 鈕文案從「載入中…」
 *  回到「重新整理」為 settled 信號。集中於此確保每個 test 邊界內 async setState 不洩漏
 *  到下個 test 觸發 act 警告。 */
async function settleInitialLoad(
  loadAdjustments: (itemId: string) => Promise<AdjustmentLogResponse[]>,
  lang: 'en' | 'zh' = 'zh',
) {
  const btnName = lang === 'zh' ? '重新整理異動紀錄' : 'Refresh adjustment log';
  const idleText = lang === 'zh' ? '重新整理' : 'Refresh';
  await waitFor(() => expect(loadAdjustments).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.getByRole('button', { name: btnName })).toHaveTextContent(idleText),
  );
}

/** 庫存分項 StockTile grid：以三欄 grid 的 `grid-template-columns` inline style 定位
 *  （drawer 中唯一），scope 進三欄避免誤命中 Card 內 summary row（可用總計 / 安全庫存）
 *  的數字。沿用 InventoryAdjustmentDialog.test 的 `closest` 策略，去 `parentElement`
 *  鏈式耦合 Card DOM 結構 + 去 `as` 強轉（CLAUDE.md §7）。 */
function getStockGrid(): HTMLElement {
  const grid = screen.getByText('全新').closest('[style*="grid-template-columns"]');
  if (!(grid instanceof HTMLElement)) throw new Error('庫存分項 StockTile grid 未找到');
  return grid;
}

describe('InventoryDetailDrawer 料件詳情 drawer', () => {
  beforeEach(() => {
    // 內嵌 InventoryAdjustmentDialog 走 useCurrentUser（localStorage 持久化）；
    // 清掉確保 currentUser 落 DEFAULT_USER，actor_id 斷言可預測。
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  // ── dialog / 關閉鈕 aria-label（lang）+ header ─────────────────────────────

  it('zh：dialog aria-label「料件詳情」、關閉鈕「關閉抽屜」、header 顯示 sku + name', async () => {
    const { loadAdjustments } = renderDrawer({ lang: 'zh' });
    expect(screen.getByRole('dialog', { name: '料件詳情' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '關閉抽屜' })).toBeInTheDocument();
    expect(screen.getByText('BRG-MAIN-01')).toBeInTheDocument();
    expect(screen.getByText('主軸承')).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('en：dialog aria-label「Inventory item detail」、關閉鈕「Close drawer」，不外洩 zh', async () => {
    const { loadAdjustments } = renderDrawer({ lang: 'en' });
    expect(screen.getByRole('dialog', { name: 'Inventory item detail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close drawer' })).toBeInTheDocument();
    expect(screen.queryByText('料件詳情')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '關閉抽屜' })).not.toBeInTheDocument();
    await settleInitialLoad(loadAdjustments, 'en');
  });

  // ── 庫存分項 ───────────────────────────────────────────────────────────────

  it('庫存分項三欄顯示 new/used/repairing label + 對應 qty', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ stock_new: 10, stock_used: 4, stock_repairing: 2 }),
      lang: 'zh',
    });
    // 「全新/良品/維修中」label 在 audit row 也可能出現，故 scope 進三欄 grid 斷言；
    // grid scope 亦避開同 Card summary row 的 total_available / safety_stock 數字。
    const stockGrid = getStockGrid();
    expect(within(stockGrid).getByText('全新')).toBeInTheDocument();
    expect(within(stockGrid).getByText('良品')).toBeInTheDocument();
    expect(within(stockGrid).getByText('維修中')).toBeInTheDocument();
    expect(within(stockGrid).getByText('10')).toBeInTheDocument();
    expect(within(stockGrid).getByText('4')).toBeInTheDocument();
    expect(within(stockGrid).getByText('2')).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('可用總計 + 安全庫存顯示於庫存分項 Card', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ total_available: 14, safety_stock: 3 }),
      lang: 'zh',
    });
    // summary row 的「可用總計 / 安全庫存」label 與 total_available=14 於 drawer 中唯一，
    // 直接 screen-level 查詢即可（不需 Card scope）。
    expect(screen.getByText(/可用總計/)).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText(/安全庫存/)).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('below_safety=true → 顯示 LOW pill', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ below_safety: true }),
      lang: 'zh',
    });
    expect(screen.getByText('低於安全')).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('below_safety=false → 不顯示 LOW pill', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ below_safety: false }),
      lang: 'zh',
    });
    expect(screen.queryByText('低於安全')).not.toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  // ── metadata ──────────────────────────────────────────────────────────────

  it('metadata 顯示 unit / unit_cost / warehouse_id 末 8 碼', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ unit: 'pcs', unit_cost: '120000.00', warehouse_id: 'warehouse-12345678' }),
      lang: 'zh',
    });
    expect(screen.getByText('pcs')).toBeInTheDocument();
    expect(screen.getByText('120000.00')).toBeInTheDocument();
    // warehouse_id.slice(-8) → '12345678'，前綴省略符
    expect(screen.getByText('…12345678')).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('description 空字串 → 顯示「（無）」fallback', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ description: '' }),
      lang: 'zh',
    });
    expect(screen.getByText('（無）')).toBeInTheDocument();
    await settleInitialLoad(loadAdjustments);
  });

  it('四個時間欄走 fmtDateTime（Asia/Taipei +8 換算）', async () => {
    const { loadAdjustments } = renderDrawer({
      item: makeItem({
        last_received_at: '2026-05-30T03:00:00Z', // → 2026-05-30 11:00（與下列各欄區別）
        created_at: '2026-06-01T00:00:00Z', // → 2026-06-01 08:00
        updated_at: '2026-06-02T08:30:00Z', // → 2026-06-02 16:30
        last_used_at: null, // → —
      }),
      lang: 'zh',
    });
    expect(screen.getByText('2026-05-30 11:00')).toBeInTheDocument(); // last_received_at
    expect(screen.getByText('2026-06-01 08:00')).toBeInTheDocument(); // created_at
    expect(screen.getByText('2026-06-02 16:30')).toBeInTheDocument(); // updated_at
    // last_used_at null → fmtDateTime 回「—」
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    await settleInitialLoad(loadAdjustments);
  });

  // ── audit log lazy load ────────────────────────────────────────────────────

  it('mount 即以 item.id 呼 loadAdjustments 一次', async () => {
    const { loadAdjustments } = renderDrawer({ item: makeItem({ id: 'inv-xyz' }), lang: 'zh' });
    await waitFor(() => expect(loadAdjustments).toHaveBeenCalledTimes(1));
    expect(loadAdjustments).toHaveBeenCalledWith('inv-xyz');
    await settleInitialLoad(loadAdjustments); // flush 後續 setState，避免 act 警告洩漏
  });

  it('logs 為空 → 顯示「尚無異動紀錄。」空狀態、header 計數 (0)', async () => {
    const { loadAdjustments } = renderDrawer({ logs: [], lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    expect(await screen.findByText('尚無異動紀錄。')).toBeInTheDocument();
    expect(screen.getByText(/異動紀錄 \(0\)/)).toBeInTheDocument();
  });

  it('有 log → AuditRow 顯示 sign+delta + kind label + reason + actor 末 8 碼 + 時間；header 計數隨 logs.length', async () => {
    const { loadAdjustments } = renderDrawer({
      logs: [
        makeLog({ id: 'l1', delta: 5, delta_kind: 'new', reason: '盤盈', actor_id: 'usr-deadbeef' }),
        makeLog({ id: 'l2', delta: -2, delta_kind: 'used', reason: '盤虧', actor_id: 'usr-cafebabe' }),
      ],
      lang: 'zh',
    });
    await settleInitialLoad(loadAdjustments);
    // 正 delta 帶 + 號 + kind label
    expect(await screen.findByText('+5 全新')).toBeInTheDocument();
    // 負 delta 不誤加 +
    expect(screen.getByText('-2 良品')).toBeInTheDocument();
    expect(screen.getByText('盤盈')).toBeInTheDocument();
    expect(screen.getByText('盤虧')).toBeInTheDocument();
    // actor_id.slice(-8) → 'deadbeef' / 'cafebabe'
    expect(screen.getByText(/deadbeef/)).toBeInTheDocument();
    expect(screen.getByText(/cafebabe/)).toBeInTheDocument();
    // header 計數
    expect(screen.getByText(/異動紀錄 \(2\)/)).toBeInTheDocument();
  });

  it('log 有 note → 顯示備註列', async () => {
    const { loadAdjustments } = renderDrawer({
      logs: [makeLog({ id: 'l1', note: '現場回收' })],
      lang: 'zh',
    });
    await settleInitialLoad(loadAdjustments);
    expect(await screen.findByText(/現場回收/)).toBeInTheDocument();
  });

  it('log 無 note → 不顯示備註列', async () => {
    const { loadAdjustments } = renderDrawer({
      logs: [makeLog({ id: 'l1', note: null, reason: '無備註原因' })],
      lang: 'zh',
    });
    await settleInitialLoad(loadAdjustments);
    expect(await screen.findByText('無備註原因')).toBeInTheDocument();
    // 無 note → 不出現「備註:」label
    expect(screen.queryByText(/備註:/)).not.toBeInTheDocument();
  });

  it('loadAdjustments reject → ⚠ 錯誤卡、不顯示空狀態', async () => {
    const loadAdjustments = vi.fn(async () => {
      throw new Error('500 server error');
    });
    renderDrawer({ loadAdjustments, lang: 'zh' });
    expect(await screen.findByText(/500 server error/)).toBeInTheDocument();
    // 錯誤態下不顯示「尚無異動紀錄」空狀態（!logsError 條件守住）
    expect(screen.queryByText('尚無異動紀錄。')).not.toBeInTheDocument();
    // finally → logsLoading=false，Refresh 鈕回復可按（文案回「重新整理」），讓使用者可重試
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新整理異動紀錄' })).toHaveTextContent('重新整理'),
    );
  });

  // ── Refresh ────────────────────────────────────────────────────────────────

  it('點 Refresh 鈕 → 再次呼 loadAdjustments', async () => {
    const { loadAdjustments } = renderDrawer({ logs: [], lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    fireEvent.click(screen.getByRole('button', { name: '重新整理異動紀錄' }));
    await waitFor(() => expect(loadAdjustments).toHaveBeenCalledTimes(2));
    // 第二次 load flush 完（鈕文案回「重新整理」），避免尾段 setState 洩漏
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新整理異動紀錄' })).toHaveTextContent('重新整理'),
    );
  });

  // ── 內嵌 InventoryAdjustmentDialog ─────────────────────────────────────────

  it('點「+ 調整庫存」→ 開內嵌 InventoryAdjustmentDialog（兩 dialog 以 aria-label 區分）', async () => {
    const { loadAdjustments } = renderDrawer({ lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    // 開啟前只有 drawer 的 dialog
    expect(screen.queryByRole('dialog', { name: '調整庫存' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '開啟調整庫存對話框' }));
    // 內嵌 adjust dialog 出現（aria-label「調整庫存」），與 drawer「料件詳情」並存
    expect(screen.getByRole('dialog', { name: '調整庫存' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '料件詳情' })).toBeInTheDocument();
  });

  it('內嵌 dialog 送出 → onAdjust 收 (item.id, payload)，成功觸發 reload（loadAdjustments 再呼）', async () => {
    const onAdjust = vi.fn(async () => makeResult());
    const { loadAdjustments } = renderDrawer({
      item: makeItem({ id: 'inv-xyz' }),
      onAdjust,
      lang: 'zh',
    });
    await waitFor(() => expect(loadAdjustments).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '開啟調整庫存對話框' }));
    // 內嵌 dialog 填原因 + 送出（delta 預設 1，kind 預設 new）
    fireEvent.change(screen.getByRole('textbox', { name: '異動原因' }), {
      target: { value: '盤盈' },
    });
    fireEvent.click(screen.getByRole('button', { name: '送出異動' }));
    // adjustForItem 把 item.id 綁進去 → onAdjust 收 (itemId, payload)
    await waitFor(() => expect(onAdjust).toHaveBeenCalledTimes(1));
    expect(onAdjust).toHaveBeenCalledWith('inv-xyz', {
      delta_kind: 'new',
      delta: 1,
      reason: '盤盈',
      actor_id: DEFAULT_USER.id,
      note: undefined,
    });
    // onAdjusted → refreshLogs → loadAdjustments 第二次
    await waitFor(() => expect(loadAdjustments).toHaveBeenCalledTimes(2));
  });

  // ── 關閉路徑 ───────────────────────────────────────────────────────────────

  it('點遮罩（role=dialog overlay 節點本身）→ onClose', async () => {
    const { onClose, loadAdjustments } = renderDrawer({ lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    fireEvent.click(screen.getByRole('dialog', { name: '料件詳情' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 ✕ → onClose', async () => {
    const { onClose, loadAdjustments } = renderDrawer({ lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    fireEvent.click(screen.getByRole('button', { name: '關閉抽屜' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 drawer 內容（content wrapper）→ 不 onClose（stopPropagation 守住）', async () => {
    const { onClose, loadAdjustments } = renderDrawer({ lang: 'zh' });
    await settleInitialLoad(loadAdjustments);
    const overlay = screen.getByRole('dialog', { name: '料件詳情' });
    // overlay 第一個子節點即 content wrapper（onClick stopPropagation）
    const wrapper = overlay.firstElementChild;
    if (!(wrapper instanceof HTMLElement)) throw new Error('content wrapper 未找到');
    fireEvent.click(wrapper);
    expect(onClose).not.toHaveBeenCalled();
    // 更內層子孫（header sku）點擊一樣不冒泡到遮罩
    fireEvent.click(within(wrapper).getByText('BRG-MAIN-01'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

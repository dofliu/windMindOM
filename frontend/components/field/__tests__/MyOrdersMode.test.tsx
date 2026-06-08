/**
 * MyOrdersMode render 測試（WMOM-20260608-02，EPIC-M5 M5-5 Part B-2）。
 *
 * 守住現場完工 UX 契約：
 *   - 「我的工單」依目前登入者 assignee_id 過濾（workOrderApi.list 帶 assignee_id）
 *   - in_progress 工單顯示「完工回報」→ 點開完工表單
 *   - 完工須簽名 + 拍照 → 未備齊時 submit disabled + 顯示提示（DEC-20260608-02）
 *
 * 沿用 FieldPage / WorkflowPage render 範式：ThemeProvider 包裹 + vi.mock service /
 * hook + global.fetch mock（零真連線）。signature canvas 在 jsdom 無 2d context，
 * 元件以 null guard 容錯，故只驗 disabled 契約不驗實際繪製。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { MyOrdersMode } from '../MyOrdersMode';
import { workOrderApi } from '../../../services/workOrderService';

vi.mock('../../../services/workOrderService', () => ({
  workOrderApi: { list: vi.fn(), finish: vi.fn() },
}));

vi.mock('../../../hooks/useCurrentUser', () => ({
  useCurrentUser: () => ({
    currentUser: { id: 'user-alice', name: 'Alice Chen' },
    setCurrentUser: vi.fn(),
    users: [],
  }),
}));

const mockedList = workOrderApi.list as unknown as ReturnType<typeof vi.fn>;
const mockedFinish = workOrderApi.finish as unknown as ReturnType<typeof vi.fn>;

/** 最小 WorkOrderResponse stub（只填 render 用得到的欄位）。 */
function makeOrder(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'wo-1',
    business_key: 'WO-TAI-202606-01',
    turbine_id: 'WT001',
    title: '軸承過熱',
    status: 'in_progress',
    assignee_id: 'user-alice',
    completion_photos: [],
    ...over,
  };
}

function setFarmsFetch(activeFarmId: string | null): void {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ active_farm_id: activeFarmId }),
  }) as unknown as typeof fetch;
}

function renderMode() {
  return render(
    <ThemeProvider>
      <MyOrdersMode lang="zh" />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setFarmsFetch('farm1');
  mockedList.mockResolvedValue({ total: 1, items: [makeOrder()] });
});

afterEach(cleanup);

describe('MyOrdersMode', () => {
  it('依 active farm + 目前登入者 assignee_id 過濾我的工單', async () => {
    renderMode();
    await screen.findByText('軸承過熱');
    expect(mockedList).toHaveBeenCalledWith({ farm_id: 'farm1', assignee_id: 'user-alice' });
  });

  it('顯示目前身分名稱', async () => {
    renderMode();
    expect(await screen.findByText('Alice Chen')).toBeInTheDocument();
  });

  it('in_progress 工單顯示「完工回報」按鈕', async () => {
    renderMode();
    expect(await screen.findByLabelText(/完工回報 WO-TAI-202606-01/)).toBeInTheDocument();
  });

  it('非 in_progress 工單不顯示完工按鈕', async () => {
    mockedList.mockResolvedValue({ total: 1, items: [makeOrder({ status: 'dispatched' })] });
    renderMode();
    await screen.findByText('軸承過熱');
    expect(screen.queryByLabelText(/完工回報 WO-/)).not.toBeInTheDocument();
  });

  it('無指派工單時顯示空狀態', async () => {
    mockedList.mockResolvedValue({ total: 0, items: [] });
    renderMode();
    expect(await screen.findByText(/目前沒有指派給你的工單/)).toBeInTheDocument();
  });

  it('點「完工回報」開啟完工表單', async () => {
    renderMode();
    fireEvent.click(await screen.findByLabelText(/完工回報 WO-TAI-202606-01/));
    expect(await screen.findByText(/完工回報 · WO-TAI-202606-01/)).toBeInTheDocument();
    expect(screen.getByLabelText('簽名板')).toBeInTheDocument();
  });

  it('完工表單未填工時/未簽名/未拍照 → 送出 disabled + 顯示提示', async () => {
    renderMode();
    fireEvent.click(await screen.findByLabelText(/完工回報 WO-TAI-202606-01/));
    const submit = await screen.findByLabelText('送出完工');
    expect(submit).toBeDisabled();
    expect(screen.getByText(/完工需填工時、簽名、並至少拍一張照片/)).toBeInTheDocument();
    // 即使填了工時，缺簽名 + 照片仍 disabled。
    fireEvent.change(screen.getByLabelText('實際工時'), { target: { value: '3.5' } });
    expect(submit).toBeDisabled();
    expect(mockedFinish).not.toHaveBeenCalled();
  });
});

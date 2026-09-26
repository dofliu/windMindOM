/**
 * WorkflowPage component render 測試（WMOM-20260604-05，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/workflow/*` 是核心「庫存派工簽核」模組主入口（502 行），先前 workflow
 * 目錄只有 `statusUtils` helper 單元測試、頁面層零覆蓋。本檔延續 FieldPage /
 * ReportsPage / CostPage / FarmOverview 已落地的 render 測試範式（mock hook +
 * 子元件 marker mock + ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup +
 * async act flush），守住 WorkflowPage 的核心 UX 契約：
 *
 *   - active farm 載入三態：載入中（farmId null）/ fetch 失敗（warn card）/ 成功（header）
 *   - 四個 tab 切換（工單 / 領料單 / 庫存 / 簽核）+ aria-pressed + 主內容面板切換
 *   - Create 按鈕依 tab 切換：orders → 建立工單 / material → 建立領料單 / 其餘 → 無
 *   - 簽核 tab pending count 徽章（approvals.total > 0 才顯示）
 *   - 子面板 props wiring（items / total / loading / error 由對應 hook 注入）
 *   - 點選 row → 對應 detail modal / drawer 開啟（onSelect / onApproveClick / onRejectClick 接線）
 *   - 建立 wizard onSubmit → 對應 hook create 被呼叫 + wizard 關閉（handleCreate / handleCreateMR 接線）
 *   - 語系：lang=en → 標題 / tab 英文（zh default 反向守住）
 *
 * 五個 stateful hook（useWorkOrders / useMaterialRequests / useInventory /
 * usePendingApprovals / useCurrentUser）全 mock，11 個子面板 / wizard / modal 以
 * 輕量 marker 取代（攤平關鍵 props 到 data-* + 提供觸發回呼的按鈕），讓測試聚焦
 * WorkflowPage 自身的 tab 路由 / 接線 / 載入態，不被子元件 350~930 行內部渲染干擾。
 * active farm 經 `farmApi.list()`（→ global.fetch `/api/farms`）載入；fetch 以 stub
 * 取代，未預期的 URL 直接 reject（避免靜默吞掉新 API 呼叫）。
 *
 * 子元件 marker mock 的 onSubmit / onSelect 等回呼 prop 以**具體 payload 型別**標註
 * （非 `unknown`），讓 tsc 在真實 Props signature 漂移時編譯失敗而非靜默假綠。
 *
 * 多數測試以 `await renderWorkflow(...)`（內部 `act(async)` 包 render）flush 掉
 * farmApi.list 的 fetch effect，避免「state update not wrapped in act()」警告。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import WorkflowPage from '../WorkflowPage';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import {
  type WorkOrderResponse,
  type PendingSignoffItem,
  type CreateWorkOrderRequest,
} from '../../../services/workOrderService';
import {
  type MaterialRequestResponse,
  type CreateMaterialRequestPayload,
} from '../../../services/materialService';
import { type InventoryItemResponse } from '../../../services/inventoryService';
import { type InspectionScheduleResponse } from '../../../services/inspectionScheduleService';
import { type MockUser } from '../../../services/mockUsers';
import { useWorkOrders, type UseWorkOrdersResult } from '../../../hooks/useWorkOrders';
import { useMaterialRequests, type UseMaterialRequestsResult } from '../../../hooks/useMaterialRequests';
import { useInventory, type UseInventoryResult } from '../../../hooks/useInventory';
import {
  useInspectionSchedules,
  type UseInspectionSchedulesResult,
} from '../../../hooks/useInspectionSchedules';
import { usePendingApprovals, type UsePendingApprovalsResult } from '../../../hooks/usePendingApprovals';
import { useCurrentUser } from '../../../hooks/useCurrentUser';
import { useDayWorkForm, type UseDayWorkFormResult } from '../../../hooks/useDayWorkForm';
import { type DayWorkFormResponse } from '../../../services/dayWorkFormService';
import { type TurbineData, TurbineStatus } from '../../../types';

// ─── hook mocks ────────────────────────────────────────────────────────────

vi.mock('../../../hooks/useWorkOrders');
vi.mock('../../../hooks/useMaterialRequests');
vi.mock('../../../hooks/useInventory');
vi.mock('../../../hooks/useInspectionSchedules');
vi.mock('../../../hooks/usePendingApprovals');
vi.mock('../../../hooks/useCurrentUser');
vi.mock('../../../hooks/useDayWorkForm');

const mockedUseWorkOrders = useWorkOrders as unknown as Mock;
const mockedUseMaterialRequests = useMaterialRequests as unknown as Mock;
const mockedUseInventory = useInventory as unknown as Mock;
const mockedUseInspectionSchedules = useInspectionSchedules as unknown as Mock;
const mockedUsePendingApprovals = usePendingApprovals as unknown as Mock;
const mockedUseCurrentUser = useCurrentUser as unknown as Mock;
const mockedUseDayWorkForm = useDayWorkForm as unknown as Mock;

// useCurrentUser 的真實 return 型別（hook 被 mock 但 tsc 仍走真實 .d.ts），
// 讓 makeCurrentUserResult 結構式對齊、欄位漂移即編譯失敗。
type UserContextValue = ReturnType<typeof useCurrentUser>;

// ─── 子面板 / wizard / modal marker mocks ───────────────────────────────────
//   只渲染 marker + 攤平本測試會斷言的 props，並提供觸發 onSelect / onSubmit /
//   onApproveClick / onRejectClick 回呼的按鈕，讓測試驗 WorkflowPage 的接線而不
//   渲染子元件內部。回呼 prop 以具體型別標註（非 unknown），守住與真實 Props 對齊。

interface ListPanelMockProps<T> {
  items: T[];
  total: number;
  loading: boolean;
  error: string | null;
  onSelect: (item: T) => void;
}

vi.mock('../WorkOrderListPanel', () => ({
  default: (p: ListPanelMockProps<WorkOrderResponse>) => (
    <div
      data-testid="wo-list-panel"
      data-total={p.total}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      工單清單 ({p.items.length})
      <button onClick={() => p.items[0] && p.onSelect(p.items[0])}>選工單</button>
    </div>
  ),
}));

vi.mock('../MaterialRequestListPanel', () => ({
  default: (p: ListPanelMockProps<MaterialRequestResponse>) => (
    <div
      data-testid="mr-list-panel"
      data-total={p.total}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      領料單清單 ({p.items.length})
      <button onClick={() => p.items[0] && p.onSelect(p.items[0])}>選領料單</button>
    </div>
  ),
}));

vi.mock('../InventoryListPanel', () => ({
  default: (p: ListPanelMockProps<InventoryItemResponse>) => (
    <div
      data-testid="inv-list-panel"
      data-total={p.total}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      庫存清單 ({p.items.length})
      <button onClick={() => p.items[0] && p.onSelect(p.items[0])}>選庫存</button>
    </div>
  ),
}));

vi.mock('../InspectionScheduleListPanel', () => ({
  default: (p: ListPanelMockProps<InspectionScheduleResponse>) => (
    <div
      data-testid="insp-list-panel"
      data-total={p.total}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      定檢計畫清單 ({p.items.length})
      <button onClick={() => p.items[0] && p.onSelect(p.items[0])}>選定檢計畫</button>
    </div>
  ),
}));

interface ApprovalPanelMockProps {
  items: PendingSignoffItem[];
  total: number;
  loading: boolean;
  error: string | null;
  onApproveClick: (pending: PendingSignoffItem) => void;
  onRejectClick: (pending: PendingSignoffItem) => void;
}

vi.mock('../PendingApprovalPanel', () => ({
  default: (p: ApprovalPanelMockProps) => (
    <div
      data-testid="approval-panel"
      data-total={p.total}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      待簽清單 ({p.items.length})
      <button onClick={() => p.items[0] && p.onApproveClick(p.items[0])}>核准</button>
      <button onClick={() => p.items[0] && p.onRejectClick(p.items[0])}>駁回</button>
    </div>
  ),
}));

interface CreateWOWizardMockProps {
  onSubmit: (req: CreateWorkOrderRequest) => Promise<void>;
  onClose: () => void;
}

vi.mock('../CreateWorkOrderWizard', () => ({
  default: (p: CreateWOWizardMockProps) => (
    <div data-testid="create-wo-wizard">
      建立工單精靈
      <button onClick={() => p.onSubmit(WO_CREATE_REQ)}>送出工單</button>
    </div>
  ),
}));

interface CreateMRWizardMockProps {
  onSubmit: (req: CreateMaterialRequestPayload) => Promise<void>;
  onClose: () => void;
}

vi.mock('../CreateMaterialRequestWizard', () => ({
  default: (p: CreateMRWizardMockProps) => (
    <div data-testid="create-mr-wizard">
      建立領料單精靈
      <button onClick={() => p.onSubmit(MR_CREATE_REQ)}>送出領料單</button>
    </div>
  ),
}));

vi.mock('../WorkOrderDetailModal', () => ({
  default: () => <div data-testid="wo-detail-modal">工單詳情</div>,
}));

vi.mock('../MaterialRequestDetailModal', () => ({
  default: () => <div data-testid="mr-detail-modal">領料單詳情</div>,
}));

vi.mock('../InventoryDetailDrawer', () => ({
  default: () => <div data-testid="inv-detail-drawer">庫存詳情</div>,
}));

interface CreateInspWizardMockProps {
  onSubmit: (req: { turbine_id: string; title: string; recurrence: string }) => Promise<void>;
  onClose: () => void;
}

vi.mock('../CreateInspectionScheduleModal', () => ({
  default: (p: CreateInspWizardMockProps) => (
    <div data-testid="create-insp-modal">
      建立定檢計畫
      <button onClick={() => p.onSubmit(INSP_CREATE_REQ)}>送出定檢計畫</button>
    </div>
  ),
}));

vi.mock('../InspectionScheduleDetailModal', () => ({
  default: () => <div data-testid="insp-detail-modal">定檢計畫詳情</div>,
}));

vi.mock('../ApprovalActionDialog', () => ({
  default: () => <div data-testid="approval-dialog">簽核動作</div>,
}));

interface DayWorkFormPanelMockProps {
  workDate: string;
  onWorkDateChange: (d: string) => void;
  form: DayWorkFormResponse | null;
  loading: boolean;
  error: string | null;
  workOrderOptions: { id: string; label: string }[];
  onAppendActivity: (req: unknown) => Promise<DayWorkFormResponse>;
}

vi.mock('../DayWorkFormPanel', () => ({
  default: (p: DayWorkFormPanelMockProps) => (
    <div
      data-testid="daywork-panel"
      data-date={p.workDate}
      data-wo-options={p.workOrderOptions.map(o => o.id).join(',')}
      data-loading={String(p.loading)}
      data-error={p.error ?? ''}
    >
      工作日誌
      <button onClick={() => p.onWorkDateChange('2026-09-27')}>換日期</button>
    </div>
  ),
}));

// ─── fixtures（型別嚴格，不用 as 強轉）──────────────────────────────────────

const USER: MockUser = {
  id: 'user-leader-001',
  name: '王領班',
  email: 'leader@example.com',
  roles: ['leader'],
  is_active: true,
  dev_mode_only: false,
};

/** WorkOrderResponse 工廠：全列必填欄位（不用 as），over 覆寫個別欄位。 */
function makeWorkOrder(over: Partial<WorkOrderResponse> = {}): WorkOrderResponse {
  return {
    id: 'wo-001',
    business_key: 'WO-2026-0001',
    farm_id: 'farm-001',
    turbine_id: 'WTG-01',
    type: 'corrective',
    status: 'draft',
    priority: 'normal',
    title: '齒輪箱檢修',
    description: '',
    source_alarm_id: null,
    source_alarm_code: null,
    assignee_id: null,
    crew_size: 2,
    estimated_hours: null,
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
    created_at: '2026-06-04T00:00:00Z',
    created_by: null,
    updated_at: '2026-06-04T00:00:00Z',
    ...over,
  };
}

/** MaterialRequestResponse 工廠：全列必填欄位，over 覆寫。 */
function makeMaterialRequest(over: Partial<MaterialRequestResponse> = {}): MaterialRequestResponse {
  return {
    id: 'mr-001',
    business_key: 'MR-2026-0001',
    farm_id: 'farm-001',
    requester_id: 'user-leader-001',
    work_order_id: null,
    status: 'draft',
    items: [],
    signoff_chain_id: null,
    requested_at: '2026-06-04T00:00:00Z',
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
    created_at: '2026-06-04T00:00:00Z',
    updated_at: '2026-06-04T00:00:00Z',
    ...over,
  };
}

/** InventoryItemResponse 工廠：全列必填 + computed 欄位，over 覆寫。 */
function makeInventoryItem(over: Partial<InventoryItemResponse> = {}): InventoryItemResponse {
  return {
    id: 'inv-001',
    sku: 'BRG-6201',
    name: '主軸承',
    description: '',
    unit: '顆',
    farm_id: 'farm-001',
    warehouse_id: 'wh-001',
    stock_new: 5,
    stock_used: 0,
    stock_repairing: 0,
    safety_stock: 2,
    unit_cost: '1200.00',
    last_received_at: null,
    last_used_at: null,
    created_at: '2026-06-04T00:00:00Z',
    updated_at: '2026-06-04T00:00:00Z',
    total_available: 5,
    below_safety: false,
  };
}

/** InspectionScheduleResponse 工廠：全列必填欄位，over 覆寫。 */
function makeInspectionSchedule(
  over: Partial<InspectionScheduleResponse> = {},
): InspectionScheduleResponse {
  return {
    id: 'insp-001',
    farm_id: 'farm-001',
    turbine_id: 'WTG-01',
    title: '齒輪箱季度定檢',
    description: '',
    recurrence: 'quarterly',
    interval_days: null,
    next_due_at: '2026-09-01T00:00:00Z',
    active: true,
    last_spawned_at: null,
    last_spawned_work_order_id: null,
    created_at: '2026-06-04T00:00:00Z',
    created_by: null,
    updated_at: '2026-06-04T00:00:00Z',
    ...over,
  };
}

/** PendingSignoffItem 工廠：step + chain 全列必填欄位，over 覆寫。 */
function makePending(over: Partial<PendingSignoffItem> = {}): PendingSignoffItem {
  return {
    step: {
      id: 'step-001',
      chain_id: 'chain-001',
      level: 'leader',
      sequence: 0,
      parallel_group_id: null,
      assignee_id: null,
      status: 'pending',
      decided_at: null,
      decided_by: null,
      comment: null,
      created_at: '2026-06-04T00:00:00Z',
    },
    chain: {
      id: 'chain-001',
      subject_type: 'work_order',
      subject_id: 'wo-001',
      farm_id: 'farm-001',
      levels: ['leader'],
      current_level_index: 0,
      overall_status: 'pending',
      started_at: '2026-06-04T00:00:00Z',
      completed_at: null,
      rejected_at_level: null,
      rejected_reason: null,
    },
    ...over,
  };
}

const WO_CREATE_REQ: CreateWorkOrderRequest = {
  farm_id: 'farm-001',
  turbine_id: 'WTG-01',
  type: 'corrective',
  priority: 'normal',
  title: '新工單',
  description: '',
  crew_size: 1,
};

const MR_CREATE_REQ: CreateMaterialRequestPayload = {
  farm_id: 'farm-001',
  requester_id: 'user-leader-001',
  items: [],
};

const INSP_CREATE_REQ = {
  turbine_id: 'WTG-01',
  title: '新定檢計畫',
  recurrence: 'quarterly',
};

// turbines 只作為 prop 傳進被 mock 的 CreateWorkOrderWizard，本測試不對其內容斷言。
const TURBINES: TurbineData[] = [
  {
    id: 1,
    name: 'WTG-01',
    status: TurbineStatus.OPERATING,
    powerOutput: 2.1,
    windSpeed: 8,
    rotorSpeed: 12,
    bladeAngle: 4,
    temperature: 45,
    vibration: 1.2,
    voltage: 690,
    current: 100,
    history: [],
  },
];

// ─── hook return 工廠（結構式滿足 Result 介面，欄位漂移 tsc 即失敗）──────────

function makeWO(over: Partial<UseWorkOrdersResult> = {}): UseWorkOrdersResult {
  return {
    items: [],
    total: 0,
    loading: false,
    error: null,
    refresh: vi.fn(),
    create: vi.fn(),
    dispatch: vi.fn(),
    startWork: vi.fn(),
    updateProgress: vi.fn(),
    finish: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    cancel: vi.fn(),
    reopen: vi.fn(),
    ...over,
  };
}

function makeMR(over: Partial<UseMaterialRequestsResult> = {}): UseMaterialRequestsResult {
  return {
    items: [],
    rawItems: [],
    total: 0,
    loading: false,
    error: null,
    refresh: vi.fn(),
    create: vi.fn(),
    submitForApproval: vi.fn(),
    dispatch: vi.fn(),
    receive: vi.fn(),
    close: vi.fn(),
    cancel: vi.fn(),
    createReturn: vi.fn(),
    ...over,
  };
}

function makeInv(over: Partial<UseInventoryResult> = {}): UseInventoryResult {
  return {
    items: [],
    rawItems: [],
    total: 0,
    loading: false,
    error: null,
    refresh: vi.fn(),
    warehouses: [],
    warehousesLoading: false,
    adjust: vi.fn(),
    listAdjustments: vi.fn(),
    ...over,
  };
}

function makeInspectionSchedules(
  over: Partial<UseInspectionSchedulesResult> = {},
): UseInspectionSchedulesResult {
  return {
    items: [],
    total: 0,
    loading: false,
    error: null,
    refresh: vi.fn(),
    create: vi.fn(),
    updateMetadata: vi.fn(),
    activate: vi.fn(),
    deactivate: vi.fn(),
    runScheduler: vi.fn().mockResolvedValue({ spawned: [] }),
    ...over,
  };
}

function makeApprovals(over: Partial<UsePendingApprovalsResult> = {}): UsePendingApprovalsResult {
  return {
    items: [],
    total: 0,
    loading: false,
    error: null,
    workOrderCache: new Map(),
    refresh: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    ...over,
  };
}

function makeCurrentUserResult(over: Partial<UserContextValue> = {}): UserContextValue {
  return {
    currentUser: USER,
    setCurrentUser: vi.fn(),
    availableUsers: [USER] as ReadonlyArray<MockUser>,
    ...over,
  };
}

function makeDayWorkForm(over: Partial<UseDayWorkFormResult> = {}): UseDayWorkFormResult {
  return {
    form: null,
    loading: false,
    error: null,
    history: [],
    historyLoading: false,
    historyError: null,
    refresh: vi.fn(),
    refreshHistory: vi.fn(),
    appendActivity: vi.fn(),
    ...over,
  };
}

// ─── fetch stub（active farm 載入）─────────────────────────────────────────

let fetchMock: ReturnType<typeof vi.fn>;

/** 成功 Response-like，含 ok / status 對齊 getJSON 的 `resp.ok` 檢查。 */
function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** 失敗 Response-like；把唯一的 `as unknown as Response` cast 集中在 helper 內。 */
function errorResponse(status: number): Response {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({}),
  } as unknown as Response;
}

const FARMS_OK = {
  active_farm_id: 'farm-001',
  farms: [
    {
      farm_id: 'farm-001',
      name: '彰化外海風場',
      turbine_count: 12,
      is_active: true,
      location: '台灣海峽',
      description: '',
      created_at: '2026-01-01T00:00:00Z',
      turbine_spec: {},
      is_offshore: true,
    },
  ],
};

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  // 預設 /api/farms 回成功；未預期 URL reject 不靜默吞掉。
  fetchMock.mockImplementation((input: string) => {
    const url = String(input);
    if (url.includes('/api/farms')) return Promise.resolve(jsonResponse(FARMS_OK));
    return Promise.reject(new Error(`Unexpected fetch in test: ${url}`));
  });

  mockedUseWorkOrders.mockReturnValue(makeWO());
  mockedUseMaterialRequests.mockReturnValue(makeMR());
  mockedUseInventory.mockReturnValue(makeInv());
  mockedUseInspectionSchedules.mockReturnValue(makeInspectionSchedules());
  mockedUsePendingApprovals.mockReturnValue(makeApprovals());
  mockedUseCurrentUser.mockReturnValue(makeCurrentUserResult());
  mockedUseDayWorkForm.mockReturnValue(makeDayWorkForm());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

/**
 * render WorkflowPage 並 flush farmApi.list 的 fetch effect。
 * 回傳後 active farm 已載入（除非 fetchMock 被改成 reject）。
 */
async function renderWorkflow(lang: 'zh' | 'en' = 'zh'): Promise<void> {
  await act(async () => {
    render(
      <ThemeProvider>
        <WorkflowPage lang={lang} turbines={TURBINES} />
      </ThemeProvider>,
    );
  });
}

// ─── tests ───────────────────────────────────────────────────────────────

describe('WorkflowPage — active farm 載入態', () => {
  it('初次 render（farmId=null，fetch 尚未 settle）顯示「載入風場中…」引導', () => {
    // farmId 初始為 null；第一次 render 即 loading card，毋須阻斷 fetch
    // （act flush 前 effect 的 await farmApi.list 還沒排回 setFarmId）。
    render(
      <ThemeProvider>
        <WorkflowPage lang="zh" turbines={TURBINES} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/載入風場中/)).toBeInTheDocument();
    // 載入態不渲染 tab / 主面板
    expect(screen.queryByTestId('wo-list-panel')).not.toBeInTheDocument();
  });

  it('fetch 失敗顯示 warn card + 錯誤訊息', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(errorResponse(500)));
    await renderWorkflow();
    expect(screen.getByText(/無法載入目前風場/)).toBeInTheDocument();
    expect(screen.queryByTestId('wo-list-panel')).not.toBeInTheDocument();
  });

  it('成功載入後 header 顯示風場名 + 目前身份 + 中文標題，預設停在工單 tab', async () => {
    await renderWorkflow();
    expect(screen.getByText('彰化外海風場')).toBeInTheDocument();
    expect(screen.getByText(USER.name)).toBeInTheDocument();
    // zh default：tab 顯示中文（反向守住 ui() 的 zh/en 映射未對調）
    expect(screen.getByRole('button', { name: '工單頁籤' })).toBeInTheDocument();
    expect(screen.getByTestId('wo-list-panel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '工單頁籤' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('WorkflowPage — tab 切換', () => {
  it('預設工單 tab：渲染工單面板 + 顯示建立工單按鈕', async () => {
    await renderWorkflow();
    expect(screen.getByTestId('wo-list-panel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '建立工單' })).toBeInTheDocument();
    expect(screen.queryByTestId('mr-list-panel')).not.toBeInTheDocument();
  });

  it('切到領料單 tab：面板切換 + aria-pressed 翻轉 + 建立領料單按鈕', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '領料單頁籤' }));
    expect(screen.getByTestId('mr-list-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('wo-list-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '領料單頁籤' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '工單頁籤' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '建立領料單' })).toBeInTheDocument();
    // 領料單 / 庫存 / 簽核 tab 無「建立工單」按鈕
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
  });

  it('切到庫存 tab：渲染庫存面板 + 無 create 按鈕', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '庫存頁籤' }));
    expect(screen.getByTestId('inv-list-panel')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立領料單' })).not.toBeInTheDocument();
  });

  it('切到定檢計畫 tab：渲染定檢計畫面板 + 顯示執行排程檢查/建立計畫按鈕', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    expect(screen.getByTestId('insp-list-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('inv-list-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '定檢計畫頁籤' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '執行排程檢查' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '建立定檢計畫' })).toBeInTheDocument();
    // 其餘 tab 的 create 按鈕不應出現
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立領料單' })).not.toBeInTheDocument();
  });

  it('切到簽核 tab：渲染待簽面板 + 無 create 按鈕', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '簽核頁籤' }));
    expect(screen.getByTestId('approval-panel')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
  });

  it('切到工作日誌 tab：渲染工作日誌面板 + 無 create 按鈕', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '工作日誌頁籤' }));
    expect(screen.getByTestId('daywork-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('insp-list-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '工作日誌頁籤' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立定檢計畫' })).not.toBeInTheDocument();
  });
});

describe('WorkflowPage — 簽核 pending 徽章', () => {
  it('approvals.total > 0 時簽核 tab 顯示數量徽章', async () => {
    mockedUsePendingApprovals.mockReturnValue(makeApprovals({ total: 3, items: [makePending()] }));
    await renderWorkflow();
    const approvalTab = screen.getByRole('button', { name: '簽核頁籤' });
    expect(within(approvalTab).getByText('3')).toBeInTheDocument();
  });

  it('approvals.total = 0 時不顯示徽章', async () => {
    await renderWorkflow();
    const approvalTab = screen.getByRole('button', { name: '簽核頁籤' });
    expect(within(approvalTab).queryByText('0')).not.toBeInTheDocument();
  });
});

describe('WorkflowPage — 子面板 props wiring', () => {
  it('工單面板收到 useWorkOrders 的 total / loading / error', async () => {
    mockedUseWorkOrders.mockReturnValue(
      makeWO({ items: [makeWorkOrder()], total: 7, loading: true, error: '工單載入失敗' }),
    );
    await renderWorkflow();
    const panel = screen.getByTestId('wo-list-panel');
    expect(panel).toHaveAttribute('data-total', '7');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '工單載入失敗');
  });

  it('領料單面板收到 useMaterialRequests 的 total / loading / error', async () => {
    mockedUseMaterialRequests.mockReturnValue(
      makeMR({ total: 4, loading: true, error: '領料單載入失敗' }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '領料單頁籤' }));
    const panel = screen.getByTestId('mr-list-panel');
    expect(panel).toHaveAttribute('data-total', '4');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '領料單載入失敗');
  });

  it('庫存面板收到 useInventory 的 total / loading / error', async () => {
    mockedUseInventory.mockReturnValue(makeInv({ total: 9, loading: true, error: '庫存載入失敗' }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '庫存頁籤' }));
    const panel = screen.getByTestId('inv-list-panel');
    expect(panel).toHaveAttribute('data-total', '9');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '庫存載入失敗');
  });

  it('定檢計畫面板收到 useInspectionSchedules 的 total / loading / error', async () => {
    mockedUseInspectionSchedules.mockReturnValue(
      makeInspectionSchedules({ total: 5, loading: true, error: '定檢計畫載入失敗' }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    const panel = screen.getByTestId('insp-list-panel');
    expect(panel).toHaveAttribute('data-total', '5');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '定檢計畫載入失敗');
  });

  it('待簽面板收到 usePendingApprovals 的 total / loading / error', async () => {
    mockedUsePendingApprovals.mockReturnValue(
      makeApprovals({ total: 2, loading: true, error: '簽核載入失敗' }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '簽核頁籤' }));
    const panel = screen.getByTestId('approval-panel');
    expect(panel).toHaveAttribute('data-total', '2');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '簽核載入失敗');
  });

  it('工作日誌面板收到 useDayWorkForm 的 loading / error', async () => {
    mockedUseDayWorkForm.mockReturnValue(makeDayWorkForm({ loading: true, error: '日誌載入失敗' }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '工作日誌頁籤' }));
    const panel = screen.getByTestId('daywork-panel');
    expect(panel).toHaveAttribute('data-loading', 'true');
    expect(panel).toHaveAttribute('data-error', '日誌載入失敗');
  });

  it('工作日誌面板的 workOrderOptions 只含 assignee_id 等於目前使用者的工單（非全部工單）', async () => {
    mockedUseWorkOrders.mockReturnValue(
      makeWO({
        items: [
          makeWorkOrder({ id: 'wo-mine', assignee_id: USER.id }),
          makeWorkOrder({ id: 'wo-others', assignee_id: 'someone-else' }),
          makeWorkOrder({ id: 'wo-unassigned', assignee_id: null }),
        ],
        total: 3,
      }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '工作日誌頁籤' }));
    const panel = screen.getByTestId('daywork-panel');
    expect(panel).toHaveAttribute('data-wo-options', 'wo-mine');
  });

  it('工作日誌面板的工單選單走獨立 useWorkOrders instance，不帶 Orders tab 的 status/search filter（review should-fix：避免跨 tab 過濾污染）', async () => {
    // Orders tab 自己的 useWorkOrders({ farmId, status, search }) 呼叫（三個 key）
    // 與工作日誌 tab 專用、無 filter 的 useWorkOrders({ farmId }) 呼叫（僅一個 key）
    // 必須是兩次「不同形狀參數」的獨立呼叫——若未來有人「優化」成共用同一個 hook
    // instance，這裡的呼叫參數形狀斷言會先紅，而非等到使用者在 Orders tab 篩選後
    // 才發現完成工單選單悄悄變空。
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '工作日誌頁籤' }));

    const callArgs = mockedUseWorkOrders.mock.calls.map(([opts]) => opts as Record<string, unknown>);
    const unfilteredCall = callArgs.find(
      opts => Object.keys(opts).length === 1 && opts.farmId === 'farm-001',
    );
    const ordersTabCall = callArgs.find(opts => 'status' in opts && 'search' in opts);

    expect(unfilteredCall).toBeDefined();
    expect(ordersTabCall).toBeDefined();
  });

  it('切換工作日誌面板日期 → onWorkDateChange 呼叫時 WorkflowPage 更新 workDate state（重渲染面板 data-date）', async () => {
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '工作日誌頁籤' }));
    const panel = screen.getByTestId('daywork-panel');
    const initialDate = panel.getAttribute('data-date');
    expect(initialDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    fireEvent.click(screen.getByRole('button', { name: '換日期' }));
    expect(screen.getByTestId('daywork-panel')).toHaveAttribute('data-date', '2026-09-27');
  });
});

describe('WorkflowPage — row 點選開 modal / drawer', () => {
  it('點工單 row → WorkOrderDetailModal 開啟', async () => {
    mockedUseWorkOrders.mockReturnValue(makeWO({ items: [makeWorkOrder()], total: 1 }));
    await renderWorkflow();
    expect(screen.queryByTestId('wo-detail-modal')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '選工單' }));
    expect(screen.getByTestId('wo-detail-modal')).toBeInTheDocument();
  });

  it('點領料單 row → MaterialRequestDetailModal 開啟', async () => {
    mockedUseMaterialRequests.mockReturnValue(
      makeMR({ items: [makeMaterialRequest()], rawItems: [makeMaterialRequest()], total: 1 }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '領料單頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '選領料單' }));
    expect(screen.getByTestId('mr-detail-modal')).toBeInTheDocument();
  });

  it('點庫存 row → InventoryDetailDrawer 開啟', async () => {
    const item = makeInventoryItem();
    mockedUseInventory.mockReturnValue(makeInv({ items: [item], rawItems: [item], total: 1 }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '庫存頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '選庫存' }));
    expect(screen.getByTestId('inv-detail-drawer')).toBeInTheDocument();
  });

  it('點定檢計畫 row → InspectionScheduleDetailModal 開啟', async () => {
    const sched = makeInspectionSchedule();
    mockedUseInspectionSchedules.mockReturnValue(
      makeInspectionSchedules({ items: [sched], total: 1 }),
    );
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    expect(screen.queryByTestId('insp-detail-modal')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '選定檢計畫' }));
    expect(screen.getByTestId('insp-detail-modal')).toBeInTheDocument();
  });

  it('點核准 → ApprovalActionDialog 開啟（approve 接線）', async () => {
    mockedUsePendingApprovals.mockReturnValue(makeApprovals({ items: [makePending()], total: 1 }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '簽核頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '核准' }));
    expect(screen.getByTestId('approval-dialog')).toBeInTheDocument();
  });

  it('點駁回 → ApprovalActionDialog 開啟（reject 接線，對稱守住）', async () => {
    mockedUsePendingApprovals.mockReturnValue(makeApprovals({ items: [makePending()], total: 1 }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '簽核頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '駁回' }));
    expect(screen.getByTestId('approval-dialog')).toBeInTheDocument();
  });
});

describe('WorkflowPage — 建立 wizard 接線', () => {
  it('點建立工單 → wizard 開啟；送出 → wo.create 帶正確 req + wizard 關閉', async () => {
    const create = vi.fn().mockResolvedValue(makeWorkOrder());
    mockedUseWorkOrders.mockReturnValue(makeWO({ create }));
    await renderWorkflow();
    expect(screen.queryByTestId('create-wo-wizard')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));
    expect(screen.getByTestId('create-wo-wizard')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByText('送出工單'));
    });
    expect(create).toHaveBeenCalledWith(WO_CREATE_REQ);
    // handleCreate 第二半契約：create 成功後 wizard 應關閉
    expect(screen.queryByTestId('create-wo-wizard')).not.toBeInTheDocument();
  });

  it('點建立領料單 → wizard 開啟；送出 → mrHook.create 帶正確 req + wizard 關閉', async () => {
    const create = vi.fn().mockResolvedValue(makeMaterialRequest());
    mockedUseMaterialRequests.mockReturnValue(makeMR({ create }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '領料單頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '建立領料單' }));
    expect(screen.getByTestId('create-mr-wizard')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByText('送出領料單'));
    });
    expect(create).toHaveBeenCalledWith(MR_CREATE_REQ);
    expect(screen.queryByTestId('create-mr-wizard')).not.toBeInTheDocument();
  });

  it('點建立定檢計畫 → modal 開啟；送出 → inspHook.create 帶正確 req + modal 關閉', async () => {
    const create = vi.fn().mockResolvedValue(makeInspectionSchedule());
    mockedUseInspectionSchedules.mockReturnValue(makeInspectionSchedules({ create }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    fireEvent.click(screen.getByRole('button', { name: '建立定檢計畫' }));
    expect(screen.getByTestId('create-insp-modal')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByText('送出定檢計畫'));
    });
    expect(create).toHaveBeenCalledWith(INSP_CREATE_REQ);
    // handleCreateInsp 第二半契約：create 成功後 modal 應關閉（比照 handleCreate/handleCreateMR）
    expect(screen.queryByTestId('create-insp-modal')).not.toBeInTheDocument();
  });
});

describe('WorkflowPage — 定檢計畫「執行排程檢查」接線', () => {
  it('點擊 → 呼叫 inspHook.runScheduler()', async () => {
    const runScheduler = vi.fn().mockResolvedValue({ spawned: [] });
    mockedUseInspectionSchedules.mockReturnValue(makeInspectionSchedules({ runScheduler }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '執行排程檢查' }));
    });
    expect(runScheduler).toHaveBeenCalledTimes(1);
  });

  it('spawn 成功顯示筆數訊息', async () => {
    const runScheduler = vi.fn().mockResolvedValue({
      spawned: [
        {
          schedule_id: 'insp-001',
          work_order_id: 'wo-999',
          turbine_id: 'WTG-01',
          next_due_at: '2026-12-01T00:00:00Z',
        },
      ],
    });
    mockedUseInspectionSchedules.mockReturnValue(makeInspectionSchedules({ runScheduler }));
    await renderWorkflow();
    fireEvent.click(screen.getByRole('button', { name: '定檢計畫頁籤' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '執行排程檢查' }));
    });
    expect(screen.getByText('已建立 1 張工單')).toBeInTheDocument();
  });
});

describe('WorkflowPage — 語系', () => {
  it('lang=en：標題與 tab 顯示英文、不出現中文 tab 名', async () => {
    await renderWorkflow('en');
    expect(screen.getByRole('button', { name: 'Work orders tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Material requests tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inventory tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inspection schedules tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approval tab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create work order' })).toBeInTheDocument();
    // negative：en 模式不應出現中文 tab 名（守住 ui() 映射未對調）
    expect(screen.queryByRole('button', { name: '工單頁籤' })).not.toBeInTheDocument();
  });
});

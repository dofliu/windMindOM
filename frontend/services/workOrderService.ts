/**
 * Work Order API client — TypeScript wrappers for /api/workflow/* endpoints.
 *
 * Backend: modules/workflow/routers/work_order_router.py（WMOM-20260504-17）
 * Schemas: modules/workflow/schemas/work_order_schemas.py
 *
 * Note：
 *  - 所有 endpoint 都要 farm_id 當 query param
 *  - 所有 transition 後端會回完整工單 → 前端 hook 直接 patch local state
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Enums（與後端 string Enum 對齊） ─────────────────────────────────────

export const WorkOrderStatusValues = [
  'draft',
  'dispatched',
  'in_progress',
  'awaiting_signoff',
  'closed',
  'cancelled',
  'reopened',
] as const;
export type WorkOrderStatus = (typeof WorkOrderStatusValues)[number];

export const WorkOrderTypeValues = [
  'corrective',
  'preventive',
  'inspection',
  'commissioning',
] as const;
export type WorkOrderType = (typeof WorkOrderTypeValues)[number];

export const PriorityValues = ['low', 'normal', 'high', 'critical'] as const;
export type Priority = (typeof PriorityValues)[number];

export const FollowupKindValues = ['none', 'followup_needed'] as const;
export type FollowupKind = (typeof FollowupKindValues)[number];

// ─── Sub-models ──────────────────────────────────────────────────────────

export interface ProgressNote {
  timestamp: string;
  actor_id: string;
  note: string;
}

// ─── Request bodies ──────────────────────────────────────────────────────

export interface CreateWorkOrderRequest {
  farm_id: string;
  turbine_id: string;
  type: WorkOrderType;
  title: string;
  description: string;
  priority?: Priority;
  source_alarm_id?: string | null;
  source_alarm_code?: string | null;
  assignee_id?: string | null;
  crew_size?: number;
  estimated_hours?: number | null;
  created_by?: string | null;
}

export interface DispatchRequest {
  actor_id: string;
}

export interface StartWorkRequest {
  require_weather_window?: boolean;
}

export interface UpdateProgressRequest {
  actor_id: string;
  note: string;
}

export interface FinishRequest {
  actual_hours: number;
  followup_kind: FollowupKind;
  work_summary?: string | null;
  unfinished_items?: string | null;
  followup_note?: string | null;
}

export interface RejectRequest {
  reject_reason: string;
}

export interface CancelRequest {
  cancel_reason: string;
}

export interface ReopenRequest {
  reopen_reason: string;
}

// ─── Response ─────────────────────────────────────────────────────────────

export interface WorkOrderResponse {
  // identity
  id: string;
  business_key: string;

  // core
  farm_id: string;
  turbine_id: string;
  type: WorkOrderType;
  status: WorkOrderStatus;
  priority: Priority;
  title: string;
  description: string;

  // 來源
  source_alarm_id: string | null;
  source_alarm_code: string | null;

  // 派工
  assignee_id: string | null;
  crew_size: number;
  estimated_hours: number | null;
  dispatched_at: string | null;
  dispatched_by: string | null;

  // offshore
  vessel_id: string | null;
  weather_window_id: string | null;
  logistic_hours: number | null;

  // 進行
  started_at: string | null;
  progress_notes: ProgressNote[];

  // 完工
  finished_at: string | null;
  actual_hours: number | null;
  work_summary: string | null;
  unfinished_items: string | null;
  followup_kind: FollowupKind;
  followup_note: string | null;

  // 簽核
  signoff_chain_id: string | null;

  // 取消 / 駁回 / 結案 / 重開
  closed_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  rejected_at: string | null;
  reject_reason: string | null;
  reopened_at: string | null;
  reopen_reason: string | null;

  // audit
  created_at: string;
  created_by: string | null;
  updated_at: string;
}

export interface WorkOrderListResponse {
  total: number;
  items: WorkOrderResponse[];
}

export interface WorkOrderListQuery {
  farm_id: string;
  turbine_id?: string;
  status?: WorkOrderStatus;
  only_open?: boolean;
  limit?: number;
  offset?: number;
}

// ─── Fetch helpers ────────────────────────────────────────────────────────

async function readError(resp: Response): Promise<string> {
  try {
    const err = await resp.json();
    if (err.detail) {
      return typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
    }
  } catch {
    /* ignore */
  }
  return `HTTP ${resp.status}`;
}

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`GET ${path} failed: ${await readError(resp)}`);
  }
  return resp.json() as Promise<T>;
}

async function postJSON<TReq, TResp>(path: string, body: TReq): Promise<TResp> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${await readError(resp)}`);
  }
  return resp.json() as Promise<TResp>;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}

// ─── API surface ──────────────────────────────────────────────────────────

export const workOrderApi = {
  // CRUD
  create: (req: CreateWorkOrderRequest) =>
    postJSON<CreateWorkOrderRequest, WorkOrderResponse>('/api/workflow/work-orders', req),

  list: (q: WorkOrderListQuery) =>
    getJSON<WorkOrderListResponse>(
      `/api/workflow/work-orders${buildQuery({
        farm_id: q.farm_id,
        turbine_id: q.turbine_id,
        status: q.status,
        only_open: q.only_open,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),

  get: (workOrderId: string, farmId: string) =>
    getJSON<WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}${buildQuery({ farm_id: farmId })}`,
    ),

  // State transitions（11 個 endpoint 的 8 個 transition）
  dispatch: (workOrderId: string, farmId: string, req: DispatchRequest) =>
    postJSON<DispatchRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/dispatch${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  startWork: (workOrderId: string, farmId: string, req: StartWorkRequest = {}) =>
    postJSON<StartWorkRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/start-work${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  updateProgress: (workOrderId: string, farmId: string, req: UpdateProgressRequest) =>
    postJSON<UpdateProgressRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/update-progress${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  finish: (workOrderId: string, farmId: string, req: FinishRequest) =>
    postJSON<FinishRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/finish${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  /** ⚠ 通常不直接叫 — approve 走 /api/workflow/approvals/{step_id}/approve（WMOM-20）。
   *  此 endpoint 後端會檢查 signoff chain；只在 chain 全 approved 才放行。 */
  approve: (workOrderId: string, farmId: string) =>
    postJSON<Record<string, never>, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/approve${buildQuery({ farm_id: farmId })}`,
      {},
    ),

  reject: (workOrderId: string, farmId: string, req: RejectRequest) =>
    postJSON<RejectRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/reject${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  cancel: (workOrderId: string, farmId: string, req: CancelRequest) =>
    postJSON<CancelRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/cancel${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  reopen: (workOrderId: string, farmId: string, req: ReopenRequest) =>
    postJSON<ReopenRequest, WorkOrderResponse>(
      `/api/workflow/work-orders/${workOrderId}/reopen${buildQuery({ farm_id: farmId })}`,
      req,
    ),
};

// ─── Helper：取得目前 active farm_id（同 FarmSelector 用法） ────────────────

export interface FarmInfo {
  farm_id: string;
  name: string;
  turbine_count: number;
  is_active: boolean;
  location: string;
  description: string;
  created_at: string;
  turbine_spec: Record<string, unknown>;
}

export interface FarmsResponse {
  farms: FarmInfo[];
  active_farm_id: string | null;
}

export const farmApi = {
  list: () => getJSON<FarmsResponse>('/api/farms'),
};

// ─── Dev placeholder actor — 等 user system 上線後抽掉 ─────────────────────

/** TODO: replace with authenticated user UUID when auth lands (M5+). */
export const DEV_ACTOR_ID = '00000000-0000-0000-0000-000000000001';

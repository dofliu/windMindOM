/**
 * Material Request + Inventory API client（WMOM-20260509-06）。
 *
 * Backend：
 *  - modules/workflow/routers/material_request_router.py（9 endpoints）
 *  - modules/workflow/routers/inventory_router.py（給 picker 用的 GET list）
 *
 * Schemas：
 *  - modules/workflow/schemas/material_request_schemas.py
 *  - modules/workflow/schemas/inventory_schemas.py
 *
 * 共用 fetch helpers 已在 workOrderService.ts；這裡複製最小私有版本避免循環 import
 * 與耦合（讓 material 與 work order client 兩個檔互不需 patch 一起改）。
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Enums（與後端 string Enum 對齊） ─────────────────────────────────────

export const MaterialRequestStatusValues = [
  'draft',
  'awaiting_approval',
  'approved',
  'dispatched',
  'received',
  'used',
  'closed',
  'cancelled',
  'rejected',
] as const;
export type MaterialRequestStatus = (typeof MaterialRequestStatusValues)[number];

export const StockKindValues = ['new', 'used', 'repairing'] as const;
export type StockKind = (typeof StockKindValues)[number];

export const ReturnReasonValues = [
  'surplus',
  'wrong_part',
  'failed_install',
  'other',
] as const;
export type ReturnReason = (typeof ReturnReasonValues)[number];

// ─── Sub-models ──────────────────────────────────────────────────────────

export interface MaterialRequestItem {
  id: string;
  request_id: string;
  item_id: string;
  estimated_qty: number;
  actual_qty: number | null;
  stock_kind: StockKind;
}

export interface MaterialReturnResponse {
  id: string;
  request_id: string;
  item_id: string;
  qty: number;
  reason: ReturnReason;
  return_to_kind: StockKind;
  returned_by: string;
  note: string | null;
  returned_at: string;
}

// ─── Request bodies ──────────────────────────────────────────────────────

export interface CreateMaterialRequestItemPayload {
  item_id: string;
  estimated_qty: number;
  stock_kind: StockKind;
}

export interface CreateMaterialRequestPayload {
  farm_id: string;
  requester_id: string;
  items: CreateMaterialRequestItemPayload[];
  work_order_id?: string | null;
}

export interface SubmitForApprovalPayload {
  actor_id: string;
  escalate_to_supervisor?: boolean;
}

export interface DispatchMaterialRequestPayload {
  actor_id?: string | null;
}

export interface ReceiveMaterialRequestPayload {
  actor_id: string;
  /** key = MaterialRequestItem.id, value = actual_qty */
  actual_quantities: Record<string, number>;
}

export interface CloseMaterialRequestPayload {
  actor_id: string;
}

export interface CancelMaterialRequestPayload {
  actor_id: string;
  cancel_reason: string;
}

export interface CreateMaterialReturnPayload {
  item_id: string;
  qty: number;
  reason: ReturnReason;
  return_to_kind: StockKind;
  returned_by: string;
  note?: string | null;
}

// ─── Response ─────────────────────────────────────────────────────────────

export interface MaterialRequestResponse {
  // identity
  id: string;
  business_key: string;

  // core
  farm_id: string;
  requester_id: string;
  work_order_id: string | null;
  status: MaterialRequestStatus;

  // items
  items: MaterialRequestItem[];

  // 簽核
  signoff_chain_id: string | null;

  // timeline
  requested_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  dispatched_at: string | null;
  received_at: string | null;
  used_at: string | null;
  closed_at: string | null;
  cancelled_at: string | null;
  rejected_at: string | null;

  // reasons
  cancel_reason: string | null;
  reject_reason: string | null;

  // audit
  created_at: string;
  updated_at: string;
}

export interface MaterialRequestListResponse {
  total: number;
  items: MaterialRequestResponse[];
}

export interface MaterialRequestListQuery {
  farm_id: string;
  work_order_id?: string;
  status?: MaterialRequestStatus;
  limit?: number;
  offset?: number;
}

// ─── Inventory picker subset（A7 庫存頁會做完整版） ───────────────────────

export interface InventoryItemSummary {
  id: string;
  sku: string;
  name: string;
  description: string;
  unit: string;
  farm_id: string;
  warehouse_id: string;
  stock_new: number;
  stock_used: number;
  stock_repairing: number;
  safety_stock: number;
  unit_cost: string; // pydantic Decimal → JSON string
  last_received_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  // computed
  total_available: number;
  below_safety: boolean;
}

export interface InventoryItemListResponse {
  total: number;
  items: InventoryItemSummary[];
}

export interface InventoryItemListQuery {
  farm_id: string;
  warehouse_id?: string;
  below_safety_only?: boolean;
  limit?: number;
  offset?: number;
}

// ─── Fetch helpers（與 workOrderService 同 pattern） ─────────────────────

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

function buildQuery(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}

// ─── Material Request API surface ─────────────────────────────────────────

export const materialRequestApi = {
  create: (req: CreateMaterialRequestPayload) =>
    postJSON<CreateMaterialRequestPayload, MaterialRequestResponse>(
      '/api/workflow/material-requests',
      req,
    ),

  list: (q: MaterialRequestListQuery) =>
    getJSON<MaterialRequestListResponse>(
      `/api/workflow/material-requests${buildQuery({
        farm_id: q.farm_id,
        work_order_id: q.work_order_id,
        status: q.status,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),

  get: (materialRequestId: string, farmId: string) =>
    getJSON<MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}${buildQuery({ farm_id: farmId })}`,
    ),

  submitForApproval: (materialRequestId: string, farmId: string, req: SubmitForApprovalPayload) =>
    postJSON<SubmitForApprovalPayload, MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}/submit-for-approval${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  dispatch: (materialRequestId: string, farmId: string, req: DispatchMaterialRequestPayload) =>
    postJSON<DispatchMaterialRequestPayload, MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}/dispatch${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  receive: (materialRequestId: string, farmId: string, req: ReceiveMaterialRequestPayload) =>
    postJSON<ReceiveMaterialRequestPayload, MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}/receive${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  close: (materialRequestId: string, farmId: string, req: CloseMaterialRequestPayload) =>
    postJSON<CloseMaterialRequestPayload, MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}/close${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  cancel: (materialRequestId: string, farmId: string, req: CancelMaterialRequestPayload) =>
    postJSON<CancelMaterialRequestPayload, MaterialRequestResponse>(
      `/api/workflow/material-requests/${materialRequestId}/cancel${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  createReturn: (materialRequestId: string, farmId: string, req: CreateMaterialReturnPayload) =>
    postJSON<CreateMaterialReturnPayload, MaterialReturnResponse>(
      `/api/workflow/material-requests/${materialRequestId}/returns${buildQuery({ farm_id: farmId })}`,
      req,
    ),
};

// ─── Inventory item API（picker subset） ─────────────────────────────────

export const inventoryApi = {
  listItems: (q: InventoryItemListQuery) =>
    getJSON<InventoryItemListResponse>(
      `/api/workflow/inventory${buildQuery({
        farm_id: q.farm_id,
        warehouse_id: q.warehouse_id,
        below_safety_only: q.below_safety_only,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),
};

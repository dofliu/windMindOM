/**
 * Inventory + Warehouse API client（WMOM-20260509-07，A7 完整版）。
 *
 * Backend：
 *  - modules/workflow/routers/inventory_router.py（8 endpoints：6 inventory + 2 warehouse）
 *
 * Schemas：
 *  - modules/workflow/schemas/inventory_schemas.py
 *
 * 與 A6 `materialService.ts` 內 picker subset 並存：A6 picker 只用 `listItems`，
 * 不依賴 mutations；A7 提供完整 CRUD + adjustment audit。後續 nice-to-have follow-up
 * 可考慮統一（讓 materialService re-export inventoryService 型別），暫不做避免 scope creep.
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Enums ─────────────────────────────────────────────────────────────────

export const StockKindValues = ['new', 'used', 'repairing'] as const;
export type StockKind = (typeof StockKindValues)[number];

export const WarehouseLocationKindValues = [
  'onshore_base',
  'vessel_storage',
  'offshore_platform',
] as const;
export type WarehouseLocationKind = (typeof WarehouseLocationKindValues)[number];

// ─── Warehouse types ──────────────────────────────────────────────────────

export interface WarehouseResponse {
  id: string;
  farm_id: string;
  name: string;
  location_kind: WarehouseLocationKind;
  is_default: boolean;
}

export interface WarehouseListResponse {
  items: WarehouseResponse[];
}

export interface CreateWarehousePayload {
  farm_id: string;
  name: string;
  location_kind?: WarehouseLocationKind;
  is_default?: boolean;
}

// ─── Inventory item types ─────────────────────────────────────────────────

export interface InventoryItemResponse {
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
  /** pydantic Decimal → JSON string，UI 顯示時轉 Number / fmtMoney */
  unit_cost: string;
  last_received_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  // computed fields（backend `@computed_field`）
  total_available: number;
  below_safety: boolean;
}

export interface InventoryItemListResponse {
  total: number;
  items: InventoryItemResponse[];
}

export interface CreateInventoryItemPayload {
  sku: string;
  name: string;
  description?: string;
  unit: string;
  farm_id: string;
  warehouse_id: string;
  unit_cost: string;
  stock_new?: number;
  stock_used?: number;
  stock_repairing?: number;
  safety_stock?: number;
}

export interface UpdateInventoryMetadataPayload {
  sku?: string;
  name?: string;
  description?: string;
  unit?: string;
  safety_stock?: number;
  unit_cost?: string;
}

export interface AdjustInventoryPayload {
  delta_kind: StockKind;
  delta: number;
  reason: string;
  actor_id: string;
  note?: string;
}

export interface AdjustmentLogResponse {
  id: string;
  item_id: string;
  delta_kind: StockKind;
  delta: number;
  reason: string;
  actor_id: string;
  note: string | null;
  occurred_at: string;
}

export interface AdjustmentLogListResponse {
  items: AdjustmentLogResponse[];
}

export interface AdjustInventoryResult {
  item: InventoryItemResponse;
  log: AdjustmentLogResponse;
}

export interface InventoryListQuery {
  farm_id: string;
  warehouse_id?: string;
  below_safety_only?: boolean;
  limit?: number;
  offset?: number;
}

// ─── Fetch helpers（與 materialService / workOrderService 同 pattern） ────

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

async function patchJSON<TReq, TResp>(path: string, body: TReq): Promise<TResp> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`PATCH ${path} failed: ${await readError(resp)}`);
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

// ─── Inventory API ─────────────────────────────────────────────────────────

export const inventoryApi = {
  create: (req: CreateInventoryItemPayload) =>
    postJSON<CreateInventoryItemPayload, InventoryItemResponse>(
      '/api/workflow/inventory',
      req,
    ),

  list: (q: InventoryListQuery) =>
    getJSON<InventoryItemListResponse>(
      `/api/workflow/inventory${buildQuery({
        farm_id: q.farm_id,
        warehouse_id: q.warehouse_id,
        below_safety_only: q.below_safety_only,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),

  get: (itemId: string, farmId: string) =>
    getJSON<InventoryItemResponse>(
      `/api/workflow/inventory/${itemId}${buildQuery({ farm_id: farmId })}`,
    ),

  updateMetadata: (
    itemId: string,
    farmId: string,
    req: UpdateInventoryMetadataPayload,
  ) =>
    patchJSON<UpdateInventoryMetadataPayload, InventoryItemResponse>(
      `/api/workflow/inventory/${itemId}${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  adjust: (itemId: string, farmId: string, req: AdjustInventoryPayload) =>
    postJSON<AdjustInventoryPayload, AdjustInventoryResult>(
      `/api/workflow/inventory/${itemId}/adjust${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  listAdjustments: (
    itemId: string,
    farmId: string,
    limit = 100,
    offset = 0,
  ) =>
    getJSON<AdjustmentLogListResponse>(
      `/api/workflow/inventory/${itemId}/adjustments${buildQuery({
        farm_id: farmId,
        limit,
        offset,
      })}`,
    ),
};

// ─── Warehouse API ─────────────────────────────────────────────────────────

export const warehouseApi = {
  list: (farmId: string) =>
    getJSON<WarehouseListResponse>(
      `/api/workflow/warehouses${buildQuery({ farm_id: farmId })}`,
    ),

  create: (req: CreateWarehousePayload) =>
    postJSON<CreateWarehousePayload, WarehouseResponse>(
      '/api/workflow/warehouses',
      req,
    ),
};

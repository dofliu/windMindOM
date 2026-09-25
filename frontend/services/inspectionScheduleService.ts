/**
 * InspectionSchedule API client（WMOM-20260925-05，`WMOM-20260505-22` 前端）。
 *
 * Backend：
 *  - modules/workflow/routers/inspection_router.py（7 endpoints）
 *
 * Schemas：
 *  - modules/workflow/schemas/inspection_schemas.py
 *
 * 沿用 inventoryService.ts 的 fetch helper pattern（authFetch + readError + buildQuery）。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Enums ─────────────────────────────────────────────────────────────────

export const RecurrenceValues = [
  'monthly',
  'quarterly',
  'semi_annual',
  'annual',
  'custom_days',
] as const;
export type Recurrence = (typeof RecurrenceValues)[number];

// ─── Types ─────────────────────────────────────────────────────────────────

export interface InspectionScheduleResponse {
  id: string;
  farm_id: string;
  turbine_id: string;
  title: string;
  description: string;
  recurrence: Recurrence;
  interval_days: number | null;
  next_due_at: string;
  active: boolean;
  last_spawned_at: string | null;
  last_spawned_work_order_id: string | null;
  created_at: string;
  created_by: string | null;
  updated_at: string;
}

export interface InspectionScheduleListResponse {
  total: number;
  items: InspectionScheduleResponse[];
}

export interface CreateInspectionSchedulePayload {
  farm_id: string;
  turbine_id: string;
  title: string;
  description?: string;
  recurrence: Recurrence;
  interval_days?: number | null;
  first_due_at?: string | null;
  created_by?: string | null;
}

export interface UpdateInspectionSchedulePayload {
  title?: string;
  description?: string;
  recurrence?: Recurrence;
  interval_days?: number | null;
}

export interface SpawnedInspectionResponse {
  schedule_id: string;
  work_order_id: string;
  turbine_id: string;
  next_due_at: string;
}

export interface RunSchedulerResponse {
  spawned: SpawnedInspectionResponse[];
}

export interface InspectionScheduleListQuery {
  farm_id: string;
  turbine_id?: string;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}

// ─── Fetch helpers（與 inventoryService / materialService 同 pattern） ──────

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
  const resp = await authFetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`GET ${path} failed: ${await readError(resp)}`);
  }
  return resp.json() as Promise<T>;
}

async function postJSON<TReq, TResp>(path: string, body: TReq): Promise<TResp> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${await readError(resp)}`);
  }
  return resp.json() as Promise<TResp>;
}

/** 給 activate/deactivate/run-scheduler 這類無 request body 的 POST 用。 */
async function postAction<TResp>(path: string): Promise<TResp> {
  const resp = await authFetch(`${API_BASE}${path}`, { method: 'POST' });
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${await readError(resp)}`);
  }
  return resp.json() as Promise<TResp>;
}

async function patchJSON<TReq, TResp>(path: string, body: TReq): Promise<TResp> {
  const resp = await authFetch(`${API_BASE}${path}`, {
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
    if (v === undefined || v === null || v === '' || v === false) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}

// ─── API ─────────────────────────────────────────────────────────────────

export const inspectionScheduleApi = {
  create: (req: CreateInspectionSchedulePayload) =>
    postJSON<CreateInspectionSchedulePayload, InspectionScheduleResponse>(
      '/api/workflow/inspection-schedules',
      req,
    ),

  list: (q: InspectionScheduleListQuery) =>
    getJSON<InspectionScheduleListResponse>(
      `/api/workflow/inspection-schedules${buildQuery({
        farm_id: q.farm_id,
        turbine_id: q.turbine_id,
        active_only: q.active_only,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),

  get: (scheduleId: string, farmId: string) =>
    getJSON<InspectionScheduleResponse>(
      `/api/workflow/inspection-schedules/${scheduleId}${buildQuery({ farm_id: farmId })}`,
    ),

  updateMetadata: (
    scheduleId: string,
    farmId: string,
    req: UpdateInspectionSchedulePayload,
  ) =>
    patchJSON<UpdateInspectionSchedulePayload, InspectionScheduleResponse>(
      `/api/workflow/inspection-schedules/${scheduleId}${buildQuery({ farm_id: farmId })}`,
      req,
    ),

  activate: (scheduleId: string, farmId: string) =>
    postAction<InspectionScheduleResponse>(
      `/api/workflow/inspection-schedules/${scheduleId}/activate${buildQuery({ farm_id: farmId })}`,
    ),

  deactivate: (scheduleId: string, farmId: string) =>
    postAction<InspectionScheduleResponse>(
      `/api/workflow/inspection-schedules/${scheduleId}/deactivate${buildQuery({ farm_id: farmId })}`,
    ),

  runScheduler: (farmId: string) =>
    postAction<RunSchedulerResponse>(
      `/api/workflow/inspection-schedules/run-scheduler${buildQuery({ farm_id: farmId })}`,
    ),
};

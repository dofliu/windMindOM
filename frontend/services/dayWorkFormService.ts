/**
 * DayWorkForm API client（WMOM-20260926-01，`WMOM-20260505-21` 前端）。
 *
 * Backend：
 *  - modules/workflow/routers/day_work_form_router.py（5 endpoints）
 *
 * Schemas：
 *  - modules/workflow/schemas/day_work_form_schemas.py
 *
 * 沿用 inspectionScheduleService.ts 的 fetch helper pattern（authFetch + readError + buildQuery）。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Enums ─────────────────────────────────────────────────────────────────

export const ActivityKindValues = [
  'completed_wo',
  'inspection_item',
  'patrol',
  'training',
] as const;
export type ActivityKind = (typeof ActivityKindValues)[number];

// ─── Types ─────────────────────────────────────────────────────────────────

export interface ActivityEntryResponse {
  id: string;
  kind: ActivityKind;
  wo_id: string | null;
  item_id: string | null;
  result: string | null;
  area: string | null;
  topic: string | null;
  note: string;
  logged_at: string;
}

export interface DayWorkFormResponse {
  id: string;
  farm_id: string;
  employee_id: string;
  work_date: string;
  activities: ActivityEntryResponse[];
  notes: string;
  created_at: string;
  created_by: string | null;
  updated_at: string;
}

export interface DayWorkFormListResponse {
  total: number;
  items: DayWorkFormResponse[];
}

export interface GetOrCreateDayWorkFormPayload {
  farm_id: string;
  work_date: string;
  employee_id?: string;
}

export interface AppendActivityPayload {
  kind: ActivityKind;
  wo_id?: string | null;
  item_id?: string | null;
  result?: string | null;
  area?: string | null;
  topic?: string | null;
  note?: string;
  employee_id?: string;
}

export interface DayWorkFormListQuery {
  farm_id: string;
  employee_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

// ─── Fetch helpers（與 inspectionScheduleService 同 pattern） ──────────────

/**
 * 解析 backend 錯誤回應（FastAPI HTTPException 的 `detail`）成可讀字串。
 *
 * - `detail` 為字串（HTTPException）→ 直接回。
 * - `detail` 為陣列（Pydantic v2 422 validation error，例如 `item_id` 不是合法
 *   UUID）→ 抽每筆的 `msg` 串接，避免把 `[{"type":"uuid_parsing",...}]` 原始
 *   JSON 丟給現場工程師看（review should-fix，同 `knowledgeService.ts` 手法）。
 * - 其餘 / 無 body → fallback `HTTP {status}`。
 */
async function readError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { msg?: string }) => (typeof d?.msg === 'string' ? d.msg : JSON.stringify(d)))
        .join('；');
    }
    if (detail) return JSON.stringify(detail);
  } catch {
    /* fall through */
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

/** 給 `by-date` 用：404（尚未建立過）回傳 `null`，非例外——呼叫端據此決定是否顯示「尚未建立」空狀態。 */
async function getJSONOrNull<T>(path: string): Promise<T | null> {
  const resp = await authFetch(`${API_BASE}${path}`);
  if (resp.status === 404) return null;
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

export const dayWorkFormApi = {
  getOrCreate: (req: GetOrCreateDayWorkFormPayload) =>
    postJSON<GetOrCreateDayWorkFormPayload, DayWorkFormResponse>(
      '/api/workflow/day-work-forms',
      req,
    ),

  list: (q: DayWorkFormListQuery) =>
    getJSON<DayWorkFormListResponse>(
      `/api/workflow/day-work-forms${buildQuery({
        farm_id: q.farm_id,
        employee_id: q.employee_id,
        date_from: q.date_from,
        date_to: q.date_to,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),

  getByDate: (farmId: string, employeeId: string, workDate: string) =>
    getJSONOrNull<DayWorkFormResponse>(
      `/api/workflow/day-work-forms/by-date${buildQuery({
        farm_id: farmId,
        employee_id: employeeId,
        work_date: workDate,
      })}`,
    ),

  get: (formId: string, farmId: string) =>
    getJSON<DayWorkFormResponse>(
      `/api/workflow/day-work-forms/${formId}${buildQuery({ farm_id: farmId })}`,
    ),

  appendActivity: (formId: string, farmId: string, req: AppendActivityPayload) =>
    postJSON<AppendActivityPayload, DayWorkFormResponse>(
      `/api/workflow/day-work-forms/${formId}/activities${buildQuery({ farm_id: farmId })}`,
      req,
    ),
};

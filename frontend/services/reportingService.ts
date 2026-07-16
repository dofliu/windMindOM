/**
 * Reporting API client — TypeScript wrappers for /api/reporting/* endpoints。
 *
 * Backend：modules/reporting/routers/reporting_router.py（WMOM-20260509-08）。
 * 3 endpoints：
 *   - GET  /api/reporting/templates                                 → 可用 template 列表
 *   - POST /api/reporting/monthly?farm_id&year&month&format=...     → PDF binary / HTML / JSON
 *   - POST /api/reporting/annual-budget?farm_id&year&format=...     → PDF / JSON
 *
 * PDF blob 處理：服務層回 `Blob`；UI 層 createObjectURL → `<a download>`。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Schema types（對齊 backend Pydantic）──────────────────────────────────

export interface CostBreakdownItem {
  category: 'material' | 'labour' | 'equipment' | 'revenue_loss';
  estimated: string;     // Decimal serialised as string
  confirmed: string;
  total: string;
}

export interface CostSummary {
  by_category: CostBreakdownItem[];
  estimated_total: string;
  confirmed_total: string;
  grand_total: string;
}

export interface WorkOrderTypeStats {
  type: string;
  finished: number;
  closed: number;
  in_progress: number;
}

export interface WorkOrderSummary {
  by_type: WorkOrderTypeStats[];
  total_finished: number;
  total_closed: number;
  total_in_progress: number;
  total_actual_hours: number;
}

export interface AvailabilityMetrics {
  time_availability: number;
  energy_availability: number;
  total_hours_in_period: number;
  downtime_hours: number;
  source: string;
}

export interface KpiHighlights {
  grand_total_cost: string;
  confirmed_cost_ratio: number;
  work_orders_finished: number;
  average_repair_hours: number;
  time_availability: number;
}

export interface NotableEvent {
  occurred_at: string;
  event_type: string;
  title: string;
  detail?: string | null;
}

export interface MonthlyReportData {
  farm_id: string;
  farm_name?: string | null;
  year: number;
  month: number;
  period_start: string;
  period_end: string;
  generated_at: string;
  kpi: KpiHighlights;
  cost: CostSummary;
  work_orders: WorkOrderSummary;
  availability: AvailabilityMetrics;
  notable_events: NotableEvent[];
}

export interface MonthlyBudgetEntry {
  month: number;
  forecast_total: string;
  forecast_by_category: Record<string, string>;
  actual_total?: string | null;
  method: string;
}

export interface AnnualBudgetData {
  farm_id: string;
  farm_name?: string | null;
  year: number;
  generated_at: string;
  months: MonthlyBudgetEntry[];
  annual_forecast_total: string;
  annual_actual_total: string;
  method: string;
  notes?: string | null;
}

export interface ReportTemplate {
  id: string;
  name: string;
  name_zh: string;
  description: string;
  sections: string[];
  formats: string[];
}

export interface ReportTemplateListResponse {
  total: number;
  items: ReportTemplate[];
}

// ─── Query types ──────────────────────────────────────────────────────────

export interface MonthlyQuery {
  farm_id: string;
  year: number;
  month: number;
  farm_name?: string;
}

export interface AnnualQuery {
  farm_id: string;
  year: number;
  farm_name?: string;
  method?: string;
  history_window?: number;
  current_month?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function buildQuery(params: Record<string, string | number | null | undefined>): string {
  // Review fix (must-fix #2)：型別簽章對齊 runtime guard，包含 `null`，
  // 避免 caller 傳入 nullable 欄位被 TS 誤判為型別錯誤。
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}

async function readError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    if (body?.detail) {
      return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    /* fall through */
  }
  return `HTTP ${resp.status}`;
}

async function postRaw(
  path: string,
  acceptable: 'application/pdf' | 'text/html' | 'application/json',
): Promise<Response> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { Accept: acceptable },
  });
  if (!resp.ok) {
    throw new Error(`POST ${path} failed: ${await readError(resp)}`);
  }
  return resp;
}

async function getJSON<T>(path: string): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: ${await readError(resp)}`);
  return resp.json() as Promise<T>;
}

// ─── API surface ──────────────────────────────────────────────────────────

export const reportingApi = {
  /** GET /api/reporting/templates */
  listTemplates: () => getJSON<ReportTemplateListResponse>('/api/reporting/templates'),

  /** POST /api/reporting/monthly?...&format=json — 給 KPI / chart 用 */
  monthlyJson: async (q: MonthlyQuery): Promise<MonthlyReportData> => {
    const path = `/api/reporting/monthly${buildQuery({ ...q, format: 'json' })}`;
    const resp = await postRaw(path, 'application/json');
    return resp.json() as Promise<MonthlyReportData>;
  },

  /** POST /api/reporting/monthly?...&format=html — 給 iframe preview 用 */
  monthlyHtml: async (q: MonthlyQuery): Promise<string> => {
    const path = `/api/reporting/monthly${buildQuery({ ...q, format: 'html' })}`;
    const resp = await postRaw(path, 'text/html');
    return resp.text();
  },

  /** POST /api/reporting/monthly?...&format=pdf — 回 Blob 給 download flow */
  monthlyPdf: async (q: MonthlyQuery): Promise<Blob> => {
    const path = `/api/reporting/monthly${buildQuery({ ...q, format: 'pdf' })}`;
    const resp = await postRaw(path, 'application/pdf');
    return resp.blob();
  },

  /** POST /api/reporting/annual-budget?...&format=json */
  annualJson: async (q: AnnualQuery): Promise<AnnualBudgetData> => {
    const path = `/api/reporting/annual-budget${buildQuery({ ...q, format: 'json' })}`;
    const resp = await postRaw(path, 'application/json');
    return resp.json() as Promise<AnnualBudgetData>;
  },

  /** POST /api/reporting/annual-budget?...&format=pdf */
  annualPdf: async (q: AnnualQuery): Promise<Blob> => {
    const path = `/api/reporting/annual-budget${buildQuery({ ...q, format: 'pdf' })}`;
    const resp = await postRaw(path, 'application/pdf');
    return resp.blob();
  },
};

// ─── Browser download helper ──────────────────────────────────────────────

/**
 * 觸發瀏覽器下載一個 Blob（用 createObjectURL + 隱形 anchor click）。
 * 用完後 revokeObjectURL 釋放記憶體（即使 download 失敗）。
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } finally {
    // 略延遲再 revoke：anchor click 是非同步觸發，過早 revoke 會打斷下載
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

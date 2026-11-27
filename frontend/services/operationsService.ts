/**
 * 仿真風場的營運：收支與可用率、自動運轉（故障產生器、模擬維修班）、實測風況（WMOM-20261127-01）。
 *
 * 端點（都在後端，這裡只包裝）：
 *   - `GET /api/operations/finance`（主管）：收入、停機少收、帳本的支出、淨額、每台機組（DEC-20261127-02）
 *   - `GET /api/operations/availability`（登入）：可用率、停機時數、發電量（DEC-20261126-04）
 *   - `GET/PUT /api/operations/fault-generator`、`/crew`（主管）：自動運轉的設定（DEC-20261126-08）
 *   - `GET/PUT /api/operations/inspection-plan`（主管）：自動定檢計畫（DEC-20261127-05）
 *   - `/api/config/wind`、`/api/config/wind/series[...]`（主管）：實測風況（DEC-20261127-03）
 *
 * 時間一律是風場時鐘（即時模擬的模擬時鐘）；不給 start / end 時後端用風場時鐘的現在。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

/** 後端回的錯誤：帶 HTTP 狀態碼，畫面依 401 / 403 / 409 給不同的說明。 */
export class OperationsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'OperationsApiError';
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const resp = await authFetch(`${API_BASE}${path}`, init);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as { detail?: unknown };
      if (typeof data.detail === 'string') detail = data.detail;
      else if (data.detail !== undefined) detail = JSON.stringify(data.detail);
    } catch {
      // 不是 JSON：留 HTTP 狀態碼
    }
    throw new OperationsApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function rangeQuery(start?: string, end?: string): string {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const q = params.toString();
  return q ? `?${q}` : '';
}

// ─── 收支與可用率 ─────────────────────────────────────────────────────────

export interface FinanceRates {
  farm_id: string;
  currency: string;
  kwh_price: number;
  hourly_labour_rate: number;
  /** 參數從哪裡來：farm_overlay（風場自己的成本設定）/ registry_derived / k13_fallback */
  source: string;
}

export interface FinanceTurbine {
  turbine_id: string;
  energy_kwh: number;
  revenue: number;
  lost_planned: number;
  lost_unplanned: number;
}

export interface FinanceResponse {
  start: string;
  end: string;
  enabled: boolean;
  rates: FinanceRates;
  energy_kwh: number;
  revenue: number;
  lost_revenue: { planned: number; unplanned: number };
  /** 人工、設備含固定成本（WMOM-20261127-02）；設備另含大件修復的吊車動員 */
  expenses: { material: number; labour: number; equipment: number; total: number };
  /** 固定成本依運轉狀態紀錄涵蓋的天數攤的明細；舊版後端沒有 */
  fixed_costs?: FinanceFixedCosts | null;
  /** 工單上的工時換算的人工：技師領年薪，已含在人員固定成本裡（counted=false 時不另算） */
  work_order_labour?: { amount: number; counted: boolean };
  net: number;
  turbines: FinanceTurbine[];
}

export interface FinanceFixedCosts {
  days: number;
  staff: number;
  equipment: number;
  total: number;
  technicians: number;
  yearly_salary: number;
  staff_per_year: number;
  equipment_per_year: number;
  equipment_items: { name: string; per_year: number }[];
  /** 人員的部分：farm_overlay（人數與年薪都是風場的設定）、onshore_default（陸域假設值）或 mixed（一部分是）；設備年費都是陸域假設值 */
  source: string;
}

export interface AvailabilityMetrics {
  turbine_id?: string;
  recorded_hours: number;
  producing_hours: number;
  ready_hours: number;
  planned_downtime_hours: number;
  unplanned_downtime_hours: number;
  energy_kwh: number;
  lost_planned_kwh: number;
  lost_unplanned_kwh: number;
  time_availability: number | null;
  energy_availability: number | null;
}

export interface AvailabilityResponse {
  start: string;
  end: string;
  enabled: boolean;
  turbines: AvailabilityMetrics[];
  farm: AvailabilityMetrics;
}

export function fetchFinance(start?: string, end?: string): Promise<FinanceResponse> {
  return request<FinanceResponse>('GET', `/api/operations/finance${rangeQuery(start, end)}`);
}

export function fetchAvailability(start?: string, end?: string): Promise<AvailabilityResponse> {
  return request<AvailabilityResponse>('GET', `/api/operations/availability${rangeQuery(start, end)}`);
}

// ─── 自動運轉 ─────────────────────────────────────────────────────────────

export interface FaultGeneratorConfig {
  enabled: boolean;
  mean_days_between_faults: number;
  scenario_weights: Record<string, number>;
  turbine_weights: Record<string, number>;
  wear_gain: number;
  min_hours_to_full: number;
  max_hours_to_full: number;
  max_active_per_turbine: number;
  seed: number;
  fatigue_reference: number;
  fouling_reference: number;
}

export interface FaultGeneratorState {
  config: FaultGeneratorConfig;
  /** 開始以來產生了幾個故障 */
  generated: number;
  /** 各故障情境的預設權重（0＝預設不產生） */
  scenarios: Record<string, number>;
}

export interface CrewConfig {
  enabled: boolean;
  response_minutes: number;
  repair_minutes: number;
  inspection_minutes: number;
  crews: number;
  close_after_finish: boolean;
}

export function fetchFaultGenerator(): Promise<FaultGeneratorState> {
  return request<FaultGeneratorState>('GET', '/api/operations/fault-generator');
}

/** 後端沒給的欄位會用預設值：一律送完整的設定（畫面上沒列的欄位沿用目前的值）。 */
export function saveFaultGenerator(config: FaultGeneratorConfig): Promise<FaultGeneratorState> {
  return request<FaultGeneratorState>('PUT', '/api/operations/fault-generator', config);
}

export function fetchCrew(): Promise<{ config: CrewConfig }> {
  return request<{ config: CrewConfig }>('GET', '/api/operations/crew');
}

export function saveCrew(config: CrewConfig): Promise<{ config: CrewConfig }> {
  return request<{ config: CrewConfig }>('PUT', '/api/operations/crew', config);
}

export interface InspectionPlanConfig {
  enabled: boolean;
  /** 每台機組幾天（風場時鐘）定檢一次 */
  interval_days: number;
}

export interface InspectionPlanSchedule {
  turbine_id: string;
  active: boolean;
  next_due_at: string;
  last_spawned_at: string | null;
  last_work_order_id: string | null;
  /** 到期了還沒開單（每 15 分鐘看一次，超過就是那台機組的未結案工單滿了） */
  overdue: boolean;
}

export interface InspectionPlanState {
  config: InspectionPlanConfig;
  /** 風場時鐘；即時模擬沒在跑時為 null */
  clock: string | null;
  /** 各機組的排程（啟用的在前、依下一次到期排序） */
  schedules: InspectionPlanSchedule[];
}

export function fetchInspectionPlan(): Promise<InspectionPlanState> {
  return request<InspectionPlanState>('GET', '/api/operations/inspection-plan');
}

/** 排程由即時模擬在下一批讀值寫進歷史時整理：回傳的排程可能還是改之前的。 */
export function saveInspectionPlan(config: InspectionPlanConfig): Promise<InspectionPlanState> {
  return request<InspectionPlanState>('PUT', '/api/operations/inspection-plan', config);
}

// ─── 實測風況 ─────────────────────────────────────────────────────────────

export type WindAlignment = 'replay' | 'absolute';
export type WindAtEnd = 'loop' | 'hold' | 'auto';

export interface MeasuredWindStatus {
  series_id: number | null;
  name: string;
  alignment: WindAlignment;
  at_end: WindAtEnd;
  start_offset_s: number;
  started_at: string | null;
  quantities: string[];
  /** 已經送出、下一步才套用 */
  pending: boolean;
}

export interface WindStatus {
  mode: 'auto' | 'manual' | 'measured';
  profile: string | null;
  override_wind_speed: number | null;
  turbulence_intensity: number;
  time_scale: number;
  measured: MeasuredWindStatus | null;
}

export interface WindSeriesSummary {
  rows: number;
  start: string;
  end: string;
  step_s: number;
  quantities: string[];
  missing: Record<string, number>;
  out_of_range: Record<string, number>;
  duplicates_dropped: number;
  unreadable_times: number;
  long_gaps: number;
  longest_gap_s: number;
  max_gap_s: number;
  height_scale: number;
  wind_speed_mean: number;
  wind_speed_max: number;
  timezone: string;
  warnings?: string[];
  height_m?: number | null;
  hub_height_m?: number | null;
}

export interface WindSeriesItem {
  id: number;
  name: string;
  created_at: string;
  summary: WindSeriesSummary;
}

export interface WindSeriesImportRequest {
  name: string;
  csv: string;
  columns?: Record<string, string>;
  timezone?: string;
  heightM?: number;
  hubHeightM?: number;
  shearExponent?: number;
  maxGapMinutes?: number;
}

export interface WindSeriesApplyRequest {
  alignment: WindAlignment;
  atEnd: WindAtEnd;
  startOffsetHours: number;
}

export function fetchWindStatus(): Promise<WindStatus> {
  return request<WindStatus>('GET', '/api/config/wind');
}

export function listWindSeries(): Promise<{ series: WindSeriesItem[] }> {
  return request<{ series: WindSeriesItem[] }>('GET', '/api/config/wind/series');
}

export function importWindSeries(req: WindSeriesImportRequest): Promise<WindSeriesItem> {
  return request<WindSeriesItem>('POST', '/api/config/wind/series', req);
}

export function applyWindSeries(id: number, req: WindSeriesApplyRequest): Promise<WindStatus> {
  return request<WindStatus>('POST', `/api/config/wind/series/${id}/apply`, req);
}

export function deleteWindSeries(id: number): Promise<{ status: string; id: number }> {
  return request<{ status: string; id: number }>('DELETE', `/api/config/wind/series/${id}`);
}

/** 停掉實測序列與手動設定，回到模型的風況。 */
export function clearWind(): Promise<{ status: string; mode: string }> {
  return request<{ status: string; mode: string }>('POST', '/api/config/wind/clear');
}

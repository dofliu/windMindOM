/**
 * Cost API client — TypeScript wrappers for /api/cost/* endpoints.
 *
 * Backend: modules/cost/routers/cost_router.py（WMOM-20260504-07）
 * Schemas: modules/cost/schemas/cost_schemas.py
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Request types ────────────────────────────────────────────────────────

/** Dataset 字串：'k13' 或 'farm:{farm_id}'（WMOM-20260504-10）。 */
export type DatasetName = string;

export interface CostForecastRequest {
  dataset?: DatasetName;
}

export interface LCOERequest {
  dataset?: DatasetName;
  capex_per_kw?: number;
  discount_rate?: number;
}

export interface MonteCarloRequest {
  dataset?: DatasetName;
  n_simulations?: number;
  seed?: number;
}

export interface BathtubConfig {
  beta_early: number;
  beta_late: number;
  early_life_years: number;
  late_life_start: number;
  early_peak: number;
  late_peak: number;
}

export interface VarFluctRequest {
  dataset?: DatasetName;
  failure_rate_model?: 'bathtub' | 'constant' | 'custom';
  bathtub?: BathtubConfig;
  cost_escalation_rate?: number;
  capacity_degradation_rate?: number;
  discount_rate?: number;
}

// ─── Response types ───────────────────────────────────────────────────────

/** Cost API response 共用的 dataset 透明度資訊（WMOM-20260504-10）。 */
export interface DatasetMeta {
  dataset_used: string;
  farm_id: string | null;
  is_fallback: boolean;
  source: 'k13_baseline' | 'farm_overlay' | 'registry_derived' | 'k13_fallback';
  warning: string | null;
}

export interface SeasonalCostBreakdown {
  season: 'winter' | 'spring' | 'summer' | 'autumn';
  corrective_wt_material: number;
  corrective_wt_labour: number;
  corrective_wt_equipment: number;
  corrective_wt_mob: number;
  corrective_wt_revenue_loss: number;
  corrective_wt_downtime: number;
  corrective_bop_total: number;
  preventive_total: number;
  preventive_material: number;
  preventive_revenue_loss: number;
  preventive_downtime: number;
  fixed_cost: number;
  total_effort: number;
  total_downtime: number;
}

export interface CostForecastResponse {
  availability_time: number;
  availability_energy: number;
  total_revenue_loss: number;
  total_repair_cost: number;
  total_effort: number;
  cost_per_kwh: number;
  seasonal: Record<string, SeasonalCostBreakdown>;
  dataset_meta?: DatasetMeta | null;
}

export interface LCOEResponse {
  lcoe: number;
  capex_total: number;
  opex_total_npv: number;
  energy_total_npv: number;
  total_cost_npv: number;
  dataset_meta?: DatasetMeta | null;
}

export interface PercentileStats {
  p10: number;
  p50: number;
  p90: number;
  mean: number;
  std: number;
}

export interface MonteCarloPercentiles {
  cost: PercentileStats;
  availability_time: PercentileStats;
  availability_energy: PercentileStats;
}

export interface MonteCarloResponse {
  n_simulations: number;
  seed: number;
  deterministic: CostForecastResponse;
  percentiles: MonteCarloPercentiles;
  dataset_meta?: DatasetMeta | null;
}

export interface YearResultResponse {
  year: number;
  failure_multiplier: number;
  cost_escalation_factor: number;
  kwh_price: number;
  capacity_factor_multiplier: number;
  total_repair_cost: number;
  total_effort: number;
  revenue_loss: number;
  fixed: number;
  availability_time: number;
  availability_energy: number;
}

export interface VarFluctSummaryResponse {
  npv_total_effort: number;
  npv_total_repair: number;
  npv_total_revenue_loss: number;
  avg_annual_effort: number;
  min_year_effort: number;
  max_year_effort: number;
  min_year_index: number;
  max_year_index: number;
  lifetime_availability_time: number;
  lifetime_availability_energy: number;
}

export interface VarFluctResponse {
  yearly: YearResultResponse[];
  summary: VarFluctSummaryResponse;
  dataset_meta?: DatasetMeta | null;
}

// ─── Fetch helpers ────────────────────────────────────────────────────────

async function postJSON<TReq, TResp>(
  path: string,
  body: TReq,
  signal?: AbortSignal,
): Promise<TResp> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      if (err.detail) detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
    } catch {
      /* ignore body parse error */
    }
    throw new Error(`POST ${path} failed: ${detail}`);
  }
  return resp.json() as Promise<TResp>;
}

export const costApi = {
  forecast: (req: CostForecastRequest = {}, signal?: AbortSignal) =>
    postJSON<CostForecastRequest, CostForecastResponse>('/api/cost/forecast', req, signal),

  lcoe: (req: LCOERequest = {}, signal?: AbortSignal) =>
    postJSON<LCOERequest, LCOEResponse>('/api/cost/lcoe', req, signal),

  monteCarlo: (req: MonteCarloRequest = {}, signal?: AbortSignal) =>
    postJSON<MonteCarloRequest, MonteCarloResponse>('/api/cost/monte-carlo', req, signal),

  varFluct: (req: VarFluctRequest = {}, signal?: AbortSignal) =>
    postJSON<VarFluctRequest, VarFluctResponse>('/api/cost/var-fluct', req, signal),
};

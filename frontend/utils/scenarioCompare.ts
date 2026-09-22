/**
 * scenarioCompare — A1「同情境內比較」的純邏輯（WMOM-20260720-10, DEC-20260720-02）。
 *
 * 消費 A0 `GET /api/scenarios/{id}/summary` 的回傳（後端 camelCase `ScenarioSummary`，此處型別
 * 一對一鏡射、不轉換）。把「判別 faulted vs healthy、分群平均、取比較用序列」抽成純函式，便於單元
 * 測試（比照 utils/farmHeader / chartAxes；ScenarioCompareView 難以整體 render 測）。
 *
 * faulted 判別**主用情境的 `fault_schedule`（session 隔離、ground truth「哪些機組被排定注入故障」）**，
 * 而非 summary 的 `faultEvents`——後者走情境 sim 時間窗（`eventsByTimeWindow`），短時間內連續生成的
 * 情境時間窗會重疊、可能混入其他情境的事件。`faultEvents` 仍並列顯示為「實際觀測到的故障次數」，
 * 且「排定卻 faultEvents===0」是有價值的提示（排了但未觸發），非矛盾。
 */

// ── 後端 ScenarioSummary 鏡射（camelCase）─────────────────────────────────────

export interface ComponentLoads {
  towerFa: number | null;
  towerSs: number | null;
  bladeFlap: number | null;
  bladeEdge: number | null;
}

export interface ScenarioTurbineSummary {
  turbineId: string;
  samples: number;
  avgPowerKw: number;
  maxPowerKw: number;
  energyKwh: number;
  capacityFactor: number;
  productionRate: number;
  estopSteps: number;
  productionHours: number | null;
  cumulativeDamage: ComponentLoads;
  worstDamage: number | null;
  rulHours: number | null;
  extremeLoad: ComponentLoads;
  damageEquivalentLoad: ComponentLoads;
  faultEvents: number;
}

export interface ScenarioFarmSummary {
  turbineCount: number;
  totalEnergyKwh: number;
  avgCapacityFactor: number;
  avgProductionRate: number;
  totalFaultEvents: number;
  maxTurbinePowerKw: number;
  worstDamage: number | null;
  worstDamageTurbineId: string | null;
  minRulHours: number | null;
  minRulTurbineId: string | null;
}

export interface ScenarioSummary {
  scenarioId: number;
  name: string | null;
  status: string | null;
  windProfile: string | null;
  durationHours: number | null;
  timeStepSeconds: number;
  ratedPowerKw: number;
  faultsInjected: number | null;
  eventsByTimeWindow: boolean;
  farm: ScenarioFarmSummary;
  turbines: ScenarioTurbineSummary[];
}

/** 可比較的每台機組數值指標鍵（皆為 number | null）。 */
export type CompareMetricKey =
  | 'capacityFactor'
  | 'energyKwh'
  | 'avgPowerKw'
  | 'worstDamage'
  | 'rulHours'
  | 'faultEvents'
  | 'productionRate'
  | 'estopSteps';

// ── 純函式 ────────────────────────────────────────────────────────────────────

/** 情境排定注入故障的機組 id 集合（session 隔離、可靠）。無排程 / 缺欄位 → 空集合。 */
export function faultedTurbineIds(
  faultSchedule?: Array<{ turbine_id?: string }> | null,
): Set<string> {
  const ids = new Set<string>();
  for (const f of faultSchedule ?? []) {
    if (f && f.turbine_id) ids.add(f.turbine_id);
  }
  return ids;
}

/** 一台機組的比較列：faulted 標記 + 各比較指標。 */
export interface TurbineComparisonRow {
  turbineId: string;
  faulted: boolean; // 由 fault_schedule 判定（排定注入）
  scheduledNotTriggered: boolean; // 排定注入但 faultEvents===0（排了未觸發）
  faultEvents: number;
  capacityFactor: number;
  energyKwh: number;
  avgPowerKw: number;
  worstDamage: number | null;
  rulHours: number | null;
  productionRate: number;
  estopSteps: number;
}

/** 把 summary 的機組清單 + faulted 集合 → 比較列（保留 turbine 原序）。 */
export function classifyTurbines(
  turbines: ScenarioTurbineSummary[],
  faultedIds: Set<string>,
): TurbineComparisonRow[] {
  return turbines.map((t) => {
    const faulted = faultedIds.has(t.turbineId);
    return {
      turbineId: t.turbineId,
      faulted,
      scheduledNotTriggered: faulted && t.faultEvents === 0,
      faultEvents: t.faultEvents,
      capacityFactor: t.capacityFactor,
      energyKwh: t.energyKwh,
      avgPowerKw: t.avgPowerKw,
      worstDamage: t.worstDamage,
      rulHours: t.rulHours,
      productionRate: t.productionRate,
      estopSteps: t.estopSteps,
    };
  });
}

/** 取某列某指標的數值（null 代表缺值，如未估出的 RUL / 無損傷）。 */
export function metricValue(
  row: TurbineComparisonRow,
  metric: CompareMetricKey,
): number | null {
  const v = row[metric];
  return typeof v === 'number' ? v : null;
}

/** 比較長條圖的一筆：缺值以 0 呈現但標記 missing（供 UI 區分「真的是 0」與「沒有值」）。 */
export interface CompareBar {
  turbineId: string;
  value: number;
  faulted: boolean;
  missing: boolean;
}

/** 產生某指標跨機組的比較序列（保留 turbine 原序）。 */
export function compareBars(
  rows: TurbineComparisonRow[],
  metric: CompareMetricKey,
): CompareBar[] {
  return rows.map((r) => {
    const raw = metricValue(r, metric);
    return {
      turbineId: r.turbineId,
      value: raw ?? 0,
      faulted: r.faulted,
      missing: raw === null,
    };
  });
}

/** faulted 與 healthy 兩群在某指標的平均（各群無有效值 → null）。這是 A1 的核心：量化
 * 「有故障 vs 健康機組的差異」。缺值不計入平均。 */
export function groupMeans(
  rows: TurbineComparisonRow[],
  metric: CompareMetricKey,
): { faulted: number | null; healthy: number | null } {
  const meanOf = (subset: TurbineComparisonRow[]): number | null => {
    const vals = subset
      .map((r) => metricValue(r, metric))
      .filter((v): v is number => v !== null);
    if (vals.length === 0) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  return {
    faulted: meanOf(rows.filter((r) => r.faulted)),
    healthy: meanOf(rows.filter((r) => !r.faulted)),
  };
}

/** 計數 faulted / healthy 機組數（供 headline）。 */
export function faultedHealthyCounts(rows: TurbineComparisonRow[]): {
  faulted: number;
  healthy: number;
} {
  let faulted = 0;
  for (const r of rows) if (r.faulted) faulted += 1;
  return { faulted, healthy: rows.length - faulted };
}

// ── A2「跨情境比較」純邏輯（WMOM-20260922-04, DEC-20260720-02）─────────────────
//
// 消費 A2 Part 1 `GET /api/scenarios/compare?ids=...` 的回傳（`ScenarioSummary[]`，與 A0/A1
// 同一鏡射型別）。比較單位是**風場層 rollup**（`ScenarioSummary.farm`），而非個別機組——跨情境比較
// 關心的是「這個情境整體 vs 那個情境整體」，機組數量/id 在不同情境間可能不同，逐機組比較無意義。

/** 可比較的風場層數值指標鍵（皆為 number | null）。 */
export type FarmCompareMetricKey =
  | 'avgCapacityFactor'
  | 'totalEnergyKwh'
  | 'avgProductionRate'
  | 'totalFaultEvents'
  | 'worstDamage'
  | 'minRulHours';

/** 情境顯示標籤：優先用使用者命名，未命名回退 `#{id}`。 */
export function scenarioLabel(s: ScenarioSummary): string {
  return s.name || `#${s.scenarioId}`;
}

/** 取某情境風場層某指標的數值（null 代表缺值）。 */
export function farmMetricValue(
  farm: ScenarioFarmSummary,
  metric: FarmCompareMetricKey,
): number | null {
  const v = farm[metric];
  return typeof v === 'number' ? v : null;
}

/** 跨情境比較長條圖的一筆：缺值以 0 呈現但標記 missing（比照 compareBars 的缺值語意）。 */
export interface ScenarioCompareBar {
  scenarioId: number;
  label: string;
  value: number;
  missing: boolean;
}

/** 產生某指標跨情境的比較序列（保留請求 ids 的原序，與 /compare 回傳順序一致）。 */
export function scenarioCompareBars(
  scenarios: ScenarioSummary[],
  metric: FarmCompareMetricKey,
): ScenarioCompareBar[] {
  return scenarios.map((s) => {
    const raw = farmMetricValue(s.farm, metric);
    return {
      scenarioId: s.scenarioId,
      label: scenarioLabel(s),
      value: raw ?? 0,
      missing: raw === null,
    };
  });
}

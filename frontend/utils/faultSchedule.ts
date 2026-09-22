/**
 * faultSchedule — 前端排定故障 ⇄ 後端 `fault_schedule` 的**單一轉換點**
 * （WMOM-20260720-13(4)，A1 follow-up）。
 *
 * 由來：`ScenarioPage.handleGenerate` 原本把同一份排程映射**兩次、形狀還不同**——
 * 送 generate-bulk 用 `at_hour`，就地組 `lastScenario.config` 用 `offset_seconds`。
 * 兩份映射各自演化正是「A1 看不到 faulted 機組」那個 bug 的成因模式（漂移風險）。
 *
 * 後端 `_parse_fault_schedule` **優先吃 `offset_seconds`**（其次才 `at_hour × 3600`），
 * 且落地進 `config_json.fault_schedule` 的形狀就是
 * `{scenario_id, turbine_id, offset_seconds, severity_rate}`
 * （見 `modules/monitoring/server/routers/config.py`）。故此處一律產出該形狀：
 * request body 與就地組的情境 config 共用同一份，與後端落地結果**逐欄位對齊**。
 */

/**
 * 一列排定故障的**領域欄位**（不含 UI 記帳用的 `key`）。
 *
 * 定義放這裡而非 ScenarioPage：`ScenarioPage.ScheduledFault` 反過來 extend 本介面，
 * 共用欄位因此只有一份定義——否則兩份手刻同形狀 interface 正是本模組想消除的漂移風險。
 * 型別住在 utils（不 import 任何 component）故無循環依賴之虞。
 */
export interface ScheduledFaultInput {
  scenarioId: string;
  turbineId: string;
  atHour: number;
  severityRate: number;
}

/**
 * 後端 `fault_schedule` 條目（送出 + 落地共用形狀）。
 *
 * `severity_rate` 設為選填是為了讀取端：#125 之前產生的舊情境其
 * `config_json.fault_schedule` 可能沒有這欄；本模組產出時一律帶上。
 */
export interface FaultScheduleEntry {
  scenario_id: string;
  turbine_id: string;
  offset_seconds: number;
  severity_rate?: number;
}

/** 一小時的秒數（at_hour → offset_seconds 換算）。 */
const SECONDS_PER_HOUR = 3600;

/**
 * 把前端排定故障列轉成後端 `fault_schedule` 條目。
 *
 * Args:
 *     faults: 前端排程列（`ScenarioPage` 的 `faults` 狀態）。
 *
 * Returns:
 *     後端形狀的條目陣列；輸入空陣列時回空陣列（**不是** undefined——空排程是
 *     「刻意的純風況基準情境」這個有意義的狀態，與「沒帶排程」必須可區分，
 *     見 ScenarioCompareView 的 `scheduleMissing`）。
 */
export function toFaultScheduleEntries(
  faults: readonly ScheduledFaultInput[],
): FaultScheduleEntry[] {
  return faults.map(f => ({
    scenario_id: f.scenarioId,
    turbine_id: f.turbineId,
    offset_seconds: f.atHour * SECONDS_PER_HOUR,
    severity_rate: f.severityRate,
  }));
}

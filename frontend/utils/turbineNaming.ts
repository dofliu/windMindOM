/**
 * turbineNaming — WT-id ↔ TurbineData.id 換算（PR C Phase 1，WMOM-20260926-03）。
 *
 * 後端機組 id 是 `WT{n:03d}`（見 `modules/monitoring/simulator/engine.py` 的
 * `f"WT{i:03d}"`），前端 `TurbineData.id` 則是該筆在 `/api/turbines`（或情境
 * `/api/scenarios/{id}/turbines`）回傳陣列中的 `index + 1`（見
 * `hooks/useRealtimeData.ts::apiToTurbineData`）。兩者對應成立的前提是回傳陣列
 * 依 `turbine_id` 排序、無缺號（scenario 端點與即時端點皆維持此不變量）。
 *
 * `ScenarioDetail`「以此情境瀏覽機組細節」入口需要把使用者當下選取的 WT-id（如
 * `"WT002"`）換算成 `TurbineData.id`（`2`），才能在情境資料到位後於陣列中找到
 * 對應的那一筆（App.tsx 沒有自己的 render 測試，故把這段換算抽成純函式獨立測試）。
 */

/**
 * 把 `WT{n}` 格式的機組 id 換算成對應的 `TurbineData.id`（`n` 本身，去除零填補）。
 *
 * @param wtId 後端機組 id，如 `"WT002"`。
 * @returns 對應的數字 id；格式不符或非正整數時回傳 `null`（呼叫端不應嘗試選取）。
 */
export function wtIdToTurbineIndex(wtId: string): number | null {
  const match = /^WT(\d+)$/.exec(wtId);
  if (!match) return null;
  const n = Number(match[1]);
  return Number.isFinite(n) && n > 0 ? n : null;
}

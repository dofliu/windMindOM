/**
 * scenarioTimeline — A2 Part 3「跨情境相對時間對齊時序疊圖」的純邏輯（DEC-20260720-02）。
 *
 * 各情境的 sim clock 皆從生成當下的 wall-clock 起算（見 decision_log DEC-20260720-02
 * caveat：「跨情境時間軸重疊，需用相對時間 t − sim_start 對齊」）。本模組把「情境資料的後端
 * timestamp」換算成「相對於該情境 sim_start 的經過毫秒數」，讓不同情境的序列能疊在同一張圖的
 * 同一條時間軸上比較，而非各自落在生成當下的絕對時間、彼此不重疊或誤重疊。
 *
 * 刻意重用既有單情境端點 `GET /api/scenarios/{id}/turbines/{turbineId}/history`（A1 的
 * `ScenarioTrendView` 已在用）而非開新後端端點——`sim_start` 已隨情境 config 落地
 * （`SavedScenario.config.sim_start`），相對時間對齊純粹是「拿現有兩份資料算差」，不需要後端
 * 新聚合邏輯。
 */

export interface HistPointLike {
  timestamp: string;
  scada?: Record<string, number>;
  scada_json?: string;
}

export interface TimelinePoint {
  /** 相對 sim_start（或對齊基準）的經過毫秒數。理論上不應為負，缺值/裁切一律保留原值不做夾範圍。 */
  t: number;
  value: number | null;
}

/** 解析情境 `sim_start`（ISO 字串）為 epoch ms；缺值或無法解析回 `null`。 */
export function simStartMs(simStart?: string | null): number | null {
  if (!simStart) return null;
  const t = new Date(simStart).getTime();
  return Number.isFinite(t) ? t : null;
}

/**
 * 把某情境某機組的原始讀數（後端 `ORDER BY timestamp DESC`）換算成「相對時間序列」（舊到新）。
 *
 * @param rows 後端 `/api/scenarios/{id}/turbines/{id}/history` 回傳的 `readings`（timestamp DESC）。
 * @param tag 要取的 SCADA tag（如 `WTUR_TotPwrAt`）。
 * @param baseMs 對齊基準（相對時間 0 點）的 epoch ms——通常是該情境的 `sim_start`；呼叫端對缺
 *   `sim_start` 的情境（未回填的舊情境）可傳入該情境自己最早一筆讀數的時間當退而求其次的基準，
 *   序列仍能疊圖看形狀，只是無法跟其他情境對齊「情境開始後第幾秒」這個絕對意義。
 */
export function buildTimelinePoints(
  rows: HistPointLike[],
  tag: string,
  baseMs: number,
): TimelinePoint[] {
  const points: TimelinePoint[] = [];
  for (const row of [...rows].reverse()) {
    const ts = row.timestamp ? new Date(row.timestamp).getTime() : NaN;
    if (!Number.isFinite(ts)) continue;
    let scada = row.scada;
    if (!scada && row.scada_json) {
      try {
        scada = JSON.parse(row.scada_json);
      } catch {
        scada = undefined;
      }
    }
    points.push({ t: ts - baseMs, value: scada?.[tag] ?? null });
  }
  return points;
}

/**
 * 相對經過時間的可讀刻度格式：小於一天顯示 `1h05m`，滿一天後顯示 `2d03h`（省略分鐘，維持刻度精簡，
 * 比照長情境常見跨度 1 小時～1 週）。負值（理論上不該出現，防禦夾到 0）視為 0。
 */
export function formatElapsed(ms: number): string {
  const totalMin = Math.max(0, Math.round(ms / 60000));
  const days = Math.floor(totalMin / 1440);
  const hours = Math.floor((totalMin % 1440) / 60);
  const minutes = totalMin % 60;
  if (days > 0) return `${days}d${String(hours).padStart(2, '0')}h`;
  return `${hours}h${String(minutes).padStart(2, '0')}m`;
}

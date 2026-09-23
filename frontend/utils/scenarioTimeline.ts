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

// ─── A2 Part 4：差異圖的分桶重採樣（DEC-20260720-02，decision_log 提到留給本階段依實作探勘判斷）──
//
// 多個情境的原始讀數取樣時間點通常不完全對齊：不同情境 `time_step` 可能不同，起點也不會剛好落在
// 同一個相對時間刻度上。若不處理，逐點相減（`series[i].t === series[j].t`）幾乎永遠找不到精確
// 相等的 `t`，算不出任何差異。本模組採「分桶重採樣」：把時間軸切成固定寬度的桶，桶內用平均值代表
// 該桶，兩個情境都有值的桶才算得出差異；桶寬選「所有選取情境中最粗的取樣間隔」（median interval
// 的最大值），刻意不選最細的，是為了不對取樣較粗的情境資料插值/捏造出超過其實際解析度的假精度。

/**
 * 序列相鄰時間點間距的中位數（毫秒）。只用相鄰點的正向間距（理論上 `buildTimelinePoints` 輸出已依
 * `t` 遞增排序），少於 2 個點或全部時間點重複（間距皆為 0）時回傳 `null`。
 */
export function medianInterval(points: TimelinePoint[]): number | null {
  if (points.length < 2) return null;
  const deltas: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const d = points[i].t - points[i - 1].t;
    if (d > 0) deltas.push(d);
  }
  if (deltas.length === 0) return null;
  deltas.sort((a, b) => a - b);
  const mid = Math.floor(deltas.length / 2);
  return deltas.length % 2 === 0 ? (deltas[mid - 1] + deltas[mid]) / 2 : deltas[mid];
}

/**
 * 依多個序列的取樣間隔決定分桶寬度：取各序列 `medianInterval` 中的**最大值**（最粗的取樣間隔）。
 * 全部序列都不足以算出間隔（例如每個都只有 0-1 個點）時回退 `fallbackMs`（預設 1 分鐘）。
 */
export function pickBinMs(seriesList: TimelinePoint[][], fallbackMs = 60_000): number {
  const intervals = seriesList
    .map(medianInterval)
    .filter((v): v is number => v !== null && v > 0);
  if (intervals.length === 0) return fallbackMs;
  return Math.max(...intervals);
}

/** 把序列分桶（桶邊界 = `Math.floor(t / binMs) * binMs`），桶內數值一律取平均。忽略 `value === null`。 */
export function binSeries(points: TimelinePoint[], binMs: number): Map<number, number> {
  const acc = new Map<number, { sum: number; count: number }>();
  for (const p of points) {
    if (p.value === null || !Number.isFinite(p.value)) continue;
    const bin = Math.floor(p.t / binMs) * binMs;
    const entry = acc.get(bin);
    if (entry) {
      entry.sum += p.value;
      entry.count += 1;
    } else {
      acc.set(bin, { sum: p.value, count: 1 });
    }
  }
  const out = new Map<number, number>();
  for (const [bin, { sum, count }] of acc) out.set(bin, sum / count);
  return out;
}

/**
 * 算兩個情境序列的差異：`compare - baseline`，逐桶比較（見上方分桶重採樣說明）。
 * 只有兩邊該桶都有值才算得出差異，否則該桶 `value` 為 `null`（渲染端應視為缺口，不插補連線，
 * 因為「差異算不出來」跟「兩邊剛好都是 0」是不同意思）。輸出依桶時間遞增排序。
 */
export function buildDiffSeries(
  baseline: TimelinePoint[],
  compare: TimelinePoint[],
  binMs: number,
): TimelinePoint[] {
  const baseBinned = binSeries(baseline, binMs);
  const compareBinned = binSeries(compare, binMs);
  const bins = Array.from(new Set([...baseBinned.keys(), ...compareBinned.keys()])).sort((a, b) => a - b);
  return bins.map((t) => {
    const b = baseBinned.get(t);
    const c = compareBinned.get(t);
    return { t, value: b !== undefined && c !== undefined ? c - b : null };
  });
}

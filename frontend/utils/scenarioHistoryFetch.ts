/**
 * scenarioHistoryFetch — 單一情境單一機組 raw history 抓取 + 對齊基準計算（A2 Part 4 抽出）。
 *
 * 邏輯完全比照 `ScenarioCompareTimelineView`（A2 Part 3）既有的 fetch effect：打既有單情境端點
 * `GET /api/scenarios/{id}/turbines/{turbineId}/history`，算出對齊基準（`config.sim_start` 有值即
 * 用它，否則退回該情境自己最早一筆讀數的時間）。`ScenarioCompareDiffView`（Part 4）需要同一份邏輯，
 * 故抽成獨立函式共用；`ScenarioCompareTimelineView` 本身維持既有寫法不動，避免無謂改動已測試過的
 * 程式碼、擴大這次的改動範圍。
 */

import { authFetch } from '../services/authClient';
import { simStartMs } from './scenarioTimeline';

export interface RawHistPoint {
  timestamp: string;
  scada?: Record<string, number>;
  scada_json?: string;
}

export interface RawScenarioData {
  rows: RawHistPoint[];
  /** 對齊基準（epoch ms）：`config.sim_start` 有值即用它，否則退回本情境自己最早一筆讀數的時間。 */
  baseMs: number;
  truncated: boolean;
  /** 該情境缺 `config.sim_start`（未回填的舊情境）→ 改以自己最早一筆讀數當對齊基準。 */
  usedFallbackAlign: boolean;
  /** 該情境的 history 請求本身失敗（HTTP 非 2xx 或例外），與「請求成功但真的沒有資料」不同情況。 */
  failed: boolean;
}

/**
 * @param apiBase API base URL。
 * @param scenarioId 情境 id。
 * @param turbineId 機組 id（如 `WT001`）。
 * @param simStart 該情境 `config.sim_start`（ISO 字串），缺值時走 fallback 對齊。
 * @param limit 單次抓取上限（對應後端 `?limit=`）。
 * @param signal 供呼叫端中止請求（元件 unmount / 依賴變更時取消過期請求）。
 */
export async function fetchScenarioHistory(
  apiBase: string,
  scenarioId: number,
  turbineId: string,
  simStart: string | null | undefined,
  limit: number,
  signal?: AbortSignal,
): Promise<RawScenarioData> {
  try {
    const r = await authFetch(
      `${apiBase}/api/scenarios/${scenarioId}/turbines/${turbineId}/history?limit=${limit}`,
      { signal },
    );
    const failed = !r.ok;
    // HTTP 非 ok 時 res 視為空 readings（無法解析 body），但仍照下方邏輯算 usedFallbackAlign——
    // 與原本內嵌於 ScenarioCompareTimelineView 的寫法一致（該版本即使 fetch 失敗也會走到同一段
    // 算 declaredBase/usedFallbackAlign 的程式碼），避免抽出後與原寫法產生行為分歧。
    const res = failed ? { readings: [] } : await r.json();
    const raw: RawHistPoint[] = Array.isArray(res.readings) ? res.readings : [];
    const declaredBase = simStartMs(simStart);
    const usedFallbackAlign = declaredBase === null;
    // 退而求其次：無 sim_start 時用該情境自己最早一筆讀數當基準（raw 為 DESC，最後一筆最舊）。
    const fallbackBase = raw.length > 0 ? new Date(raw[raw.length - 1].timestamp).getTime() : 0;
    return {
      rows: raw,
      baseMs: declaredBase ?? fallbackBase,
      truncated: raw.length >= limit,
      usedFallbackAlign,
      failed,
    };
  } catch {
    return { rows: [], baseMs: 0, truncated: false, usedFallbackAlign: false, failed: true };
  }
}

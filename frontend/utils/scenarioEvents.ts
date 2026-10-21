/**
 * scenarioEvents — 情境趨勢圖要標的「故障事件」判定（WMOM-20261021-04）。
 *
 * 情境自 -04 起記下批次的所有可觀測事件：PLC 警報成立 / 解除、跳機 / 解除、資訊（切出風速 I201）、
 * 以及運轉狀態轉換（停機原因 `plc:xxx` 的轉換也是 `event_type: "fault"`）。全部標成「故障」參考線會
 * 一個情境畫出數十條線、健康機組也滿是故障，所以只標：
 *
 * - PLC 的警報成立與跳機（`source: "plc"`、`payload.kind` 為 `alarm_raised` / `trip`）
 * - 其他來源的 `fault` 事件（情境 / 測試計畫的注入與跳機標記、舊情境的故障事件）
 *
 * 不標：PLC 的解除 / 資訊 / 復位，以及狀態轉換（跳機本身已由 PLC 事件標出）。
 */

export interface ScenarioEventLike {
  event_type: string;
  source?: string;
  payload?: Record<string, unknown> | null;
}

const PLC_ONSET_KINDS = new Set(['alarm_raised', 'trip']);

/** 事件是否要在情境趨勢圖 / 故障清單上標出。 */
export function isScenarioFaultMarker(e: ScenarioEventLike): boolean {
  if (e.event_type !== 'fault') return false;
  if (e.source === 'plc') return PLC_ONSET_KINDS.has(String(e.payload?.kind ?? ''));
  return !(e.payload && 'fromState' in e.payload);
}

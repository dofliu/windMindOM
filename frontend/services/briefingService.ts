/**
 * 出發前準備卡（WMOM-20261125-05）：故障出勤卡（故障維修工單）與例行巡檢卡（定檢 / 預防保養工單，WMOM-20261126-05）。
 *
 * 故障維修工單建立時，後端把出發前該看的證據整理成一張卡：本次事件、近 7 天的事件、相關訊號與同場
 * 對照、過往工單、手冊（警報目錄）列的原因與處置。卡片只含看得到的資料，不判定根因。
 *
 * 端點：`GET /api/operations/work-orders/{id}/briefing?farm_id=`（只讀）。沒有卡片（定檢工單、對不到
 * 機組、工單建立時閉環沒開）回 404，這裡轉成 `null`。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

export type SignalDeviation = 'high' | 'low' | 'normal' | 'unknown';
export type SignalRole = 'primary' | 'related' | 'context';

export interface BriefingSignal {
  name: string;
  label_zh: string;
  label_en: string;
  unit: string;
  role: SignalRole;
  turbine_mean: number | null;
  farm_median: number | null;
  farm_min: number | null;
  farm_max: number | null;
  peer_count: number;
  deviation: SignalDeviation;
  /** 最近 10 分鐘的平均：最後才飆高的訊號在 1 小時平均裡會被稀釋 */
  recent_mean: number | null;
  /** 截止點前最後一筆讀值（卡片 1.1 起；舊卡沒有）。 */
  last_value?: number | null;
  recent_farm_median: number | null;
  baseline_mean: number | null;
  change_from_baseline: number | null;
}

export interface BriefingEvent {
  ts?: string;
  code?: number;
  level?: string;
  text?: string;
  event_id?: string;
  event_type?: string;
  turbine_state: number | null;
  /** 這個狀態取自哪一筆讀值（讀值每 10 秒一筆，跳機當下的卡可能還是跳機前的狀態）。 */
  turbine_state_ts?: string | null;
}

export interface BriefingOtherCode {
  code: number;
  level: string;
  text: string;
  count: number;
  last_ts: string | null;
}

export interface BriefingPastOrder {
  business_key: string;
  type: string;
  status: string;
  /** 開單依據的事件碼；工單上沒填、或填的不是數字時為 null。 */
  source_alarm_code: number | null;
  created_at: string | null;
  finished_at: string | null;
}

export interface BriefingManual {
  status: 'ok' | 'no_alarm_code' | 'not_in_catalog';
  code?: number;
  level?: string;
  text?: string;
  cause?: string | null;
  rectification?: string | null;
  max_per_hour?: string | number | null;
  manual_page?: string | number | null;
  source?: string;
}

export interface BriefingCard {
  card_version: string;
  kind: 'fault_dispatch';
  work_order: {
    business_key: string;
    turbine_id: string;
    type: string;
    priority: string;
    source_alarm_code: number | null;
  };
  data_cutoff: string;
  generated_late: boolean;
  event: BriefingEvent;
  recent_events: {
    window: { start: string; end: string };
    same_code: { count: number; first_ts: string | null; last_ts: string | null; recent: string[] };
    other_codes: BriefingOtherCode[];
    farm_same_code: { window_minutes: number; turbines: { turbine_id: string; ts: string }[] };
  };
  signals: {
    window: { start: string; end: string };
    samples: number;
    /** 拿來比的同場機組數（只算發電中的） */
    peers: number;
    items: BriefingSignal[];
  };
  past_work_orders: BriefingPastOrder[];
  manual: BriefingManual;
  inventory: { status: string; note: string };
  data_quality: { flags: string[]; degraded: boolean };
  notes: string[];
}

// ─── 例行巡檢卡（WMOM-20261126-05，卡片 1.2 起）─────────────────────────────

export type InspectionEvidence =
  | { type: 'events'; code: number; level: string; text: string; event_type: string; count: number; last_ts: string }
  | {
      type: 'signal';
      name: string;
      label_zh: string;
      label_en: string;
      unit: string;
      deviation: SignalDeviation;
      turbine_mean: number | null;
      recent_mean: number | null;
      farm_median: number | null;
    }
  | { type: 'open_work_order'; business_key: string; source_alarm_code: number | null; status: string };

export interface InspectionItem {
  id: string;
  label_zh: string;
  label_en: string;
  /** 原訂第幾（技師上塔的路線） */
  default_position: number;
  /** 卡上排第幾：有證據的往前 */
  position: number;
  attention: boolean;
  score: number;
  evidence: InspectionEvidence[];
  signals: string[];
}

export interface InspectionBriefingCard {
  card_version: string;
  kind: 'routine_inspection';
  work_order: BriefingCard['work_order'];
  data_cutoff: string;
  generated_late: boolean;
  checklist: { order_changed: boolean; items: InspectionItem[] };
  recent_events: {
    window: { start: string; end: string };
    by_code: {
      code: number;
      level: string;
      text: string;
      event_type: string;
      count: number;
      first_ts: string;
      last_ts: string;
      checklist_item: string | null;
    }[];
  };
  signals: BriefingCard['signals'];
  past_work_orders: BriefingPastOrder[];
  data_quality: { flags: string[]; degraded: boolean };
  notes: string[];
}

export type AnyBriefingCard = BriefingCard | InspectionBriefingCard;

export function isInspectionCard(card: AnyBriefingCard): card is InspectionBriefingCard {
  return card.kind === 'routine_inspection';
}

export interface BriefingResponse {
  work_order_id: string;
  business_key: string;
  turbine_id: string;
  created_at: string;
  data_cutoff: string;
  card: AnyBriefingCard;
}

/** 讀一張工單的出發前準備卡；沒有卡片回 null。 */
export async function fetchBriefing(workOrderId: string, farmId: string): Promise<BriefingResponse | null> {
  const path = `/api/operations/work-orders/${encodeURIComponent(workOrderId)}/briefing?farm_id=${encodeURIComponent(farmId)}`;
  const resp = await authFetch(`${API_BASE}${path}`);
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`GET ${path} failed: HTTP ${resp.status}`);
  }
  return (await resp.json()) as BriefingResponse;
}

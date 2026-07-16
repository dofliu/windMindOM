/**
 * Knowledge / RAG API client — TypeScript wrappers for /api/knowledge/* endpoints。
 *
 * Backend：modules/knowledge/routers/knowledge_router.py（WMOM-20260603-01，EPIC-M5 M5-6）。
 * 3 endpoints：
 *   - POST /api/knowledge/alert  → AlertEvent → AlertRagResult（警報自動檢索，killer feature）
 *   - POST /api/knowledge/query  → RetrievalQuery → KnowledgeQueryResponse（手動查手冊）
 *   - GET  /api/knowledge/info   → KnowledgeInfoResponse（前端標示 RAG 來源 / baseline 模式）
 *
 * 給 M5-5 `/field/` mobile 現場工程師頁面用：警報跳出 → 30 秒內手機看到手冊處置段落。
 * 型別嚴格對齊 backend pydantic schema（modules/knowledge/schemas.py）。
 */

import { authFetch } from './authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── Schema types（對齊 backend Pydantic）──────────────────────────────────

/** 告警等級：A=警示、T1=一級跳機、T2=二級跳機。對齊 schemas.AlarmLevel。 */
export type AlarmLevel = 'A' | 'T1' | 'T2';

/** 知識庫的一塊（手冊段落 / SOP）。對齊 schemas.KnowledgeChunk。 */
export interface KnowledgeChunk {
  id: string;
  document_source: string;
  section?: string | null;
  page?: number | null;
  chunk_text: string;
  oem: string;
  model: string;
  alarm_codes: number[];
  keywords: string[];
  embedding_vector_id?: string | null;
}

/** 檢索結果單筆（chunk + 相關度 + 可解釋原因）。對齊 schemas.RetrievedChunk。 */
export interface RetrievedChunk {
  chunk: KnowledgeChunk;
  score: number; // 0..1
  match_reason: string; // 繁中可解釋命中原因
}

/** 一次檢索請求。對齊 schemas.RetrievalQuery。 */
export interface RetrievalQuery {
  text: string;
  oem?: string | null;
  model?: string | null;
  alarm_codes?: number[];
  top_k?: number | null;
}

/** SCADA 警報事件。對齊 schemas.AlertEvent。 */
export interface AlertEvent {
  alarm_code: number;
  alarm_level?: AlarmLevel;
  turbine_id: string;
  oem?: string;
  model?: string;
  scenario_id?: string | null;
  abnormal_tags?: string[];
  description?: string | null;
  severity?: number | null;
  // ISO-8601 **須帶時區 offset**（例 "2026-06-03T10:00:00Z"）；backend 強制 UTC-aware，
  // naive datetime 會被 schema validator 擋成 422。Part B 串警報時建議用
  // `new Date().toISOString()`（永遠帶 Z）避免踩時區陷阱（CLAUDE.md §B：SCADA 一律 UTC）。
  timestamp?: string | null;
}

/** POST /api/knowledge/alert 回傳。對齊 schemas.AlertRagResult。 */
export interface AlertRagResult {
  alert: AlertEvent;
  query: RetrievalQuery;
  chunks: RetrievedChunk[];
  strategy_name: string;
  retriever: string;
  is_baseline: boolean;
}

/** POST /api/knowledge/query 回傳。對齊 schemas.KnowledgeQueryResponse。 */
export interface KnowledgeQueryResponse {
  items: RetrievedChunk[];
  retriever: string;
  is_baseline: boolean;
  total: number; // backend computed_field（= items.length）
}

/** GET /api/knowledge/info 回傳。對齊 schemas.KnowledgeInfoResponse。 */
export interface KnowledgeInfoResponse {
  strategy_name: string;
  oem: string;
  model: string;
  retriever: string;
  is_baseline: boolean;
  top_k: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────

/**
 * 解析 backend 錯誤回應（FastAPI HTTPException 的 `detail`）成現場工程師可讀字串。
 *
 * - `detail` 為字串（HTTPException）→ 直接回（例：503「知識庫 RAG 服務暫時不可用」）。
 * - `detail` 為陣列（Pydantic v2 422 validation error）→ 抽每筆的 `msg` 串接，
 *   避免把 `[{"type":"missing",...}]` 原始 JSON 丟給現場工程師看（review should-fix）。
 * - 其餘 / 無 body → fallback `HTTP {status}`。
 */
async function readError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { msg?: string }) => (typeof d?.msg === 'string' ? d.msg : JSON.stringify(d)))
        .join('；');
    }
    if (detail) return JSON.stringify(detail);
  } catch {
    /* fall through */
  }
  return `HTTP ${resp.status}`;
}

async function getJSON<T>(path: string): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: ${await readError(resp)}`);
  return resp.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`POST ${path} failed: ${await readError(resp)}`);
  return resp.json() as Promise<T>;
}

// ─── API surface ──────────────────────────────────────────────────────────

export const knowledgeApi = {
  /** GET /api/knowledge/info — RAG 來源 / baseline 模式 badge。 */
  info: (): Promise<KnowledgeInfoResponse> =>
    getJSON<KnowledgeInfoResponse>('/api/knowledge/info'),

  /** POST /api/knowledge/query — 現場工程師手動打關鍵字 / 告警碼查手冊。 */
  query: (q: RetrievalQuery): Promise<KnowledgeQueryResponse> =>
    postJSON<KnowledgeQueryResponse>('/api/knowledge/query', q),

  /** POST /api/knowledge/alert — 警報事件自動檢索 top-k 手冊處置段落。 */
  queryByAlert: (event: AlertEvent): Promise<AlertRagResult> =>
    postJSON<AlertRagResult>('/api/knowledge/alert', event),
};

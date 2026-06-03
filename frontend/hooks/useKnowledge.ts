/**
 * useKnowledge — 現場工程師知識檢索 state hook（WMOM-20260603-03/-04，EPIC-M5 M5-5）。
 *
 * 給 `/field/` mobile 頁面用，包三條獨立資料流：
 *   - info：載入一次 RAG 來源 / baseline 模式（前端標示 badge）
 *   - search：手動關鍵字 / 告警碼查手冊（POST /api/knowledge/query，Part A）
 *   - alert：警報事件自動檢索 top-k 手冊處置段落（POST /api/knowledge/alert，Part B killer feature）
 *
 * race 防護：每條流各自用單調遞增 requestId（reqRef / alertReqRef）守住「較慢的舊查詢
 * 後到不蓋掉較新結果」—— 現場工程師連續送查時的 stale-overwrites-fresh，與 useCostData
 * 同精神，但這裡用單調遞增序號而非 AbortController（fetch 已送出就讓它跑完，只丟棄過期回應）。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  type AlertEvent,
  type AlertRagResult,
  type KnowledgeInfoResponse,
  type KnowledgeQueryResponse,
  type RetrievalQuery,
  knowledgeApi,
} from '../services/knowledgeService';

interface InfoState {
  loading: boolean;
  error: string | null;
  data: KnowledgeInfoResponse | null;
}

interface SearchState {
  loading: boolean;
  error: string | null;
  data: KnowledgeQueryResponse | null;
}

interface AlertState {
  loading: boolean;
  error: string | null;
  data: AlertRagResult | null;
}

const INITIAL_INFO: InfoState = { loading: false, error: null, data: null };
const INITIAL_SEARCH: SearchState = { loading: false, error: null, data: null };
const INITIAL_ALERT: AlertState = { loading: false, error: null, data: null };

export function useKnowledge() {
  const [info, setInfo] = useState<InfoState>(INITIAL_INFO);
  const [search, setSearch] = useState<SearchState>(INITIAL_SEARCH);
  const [alert, setAlert] = useState<AlertState>(INITIAL_ALERT);

  // 單調遞增的查詢序號；只接受「目前最新一筆」的回應。search / alert 各自獨立守門。
  const reqRef = useRef(0);
  const alertReqRef = useRef(0);

  // ── info：mount 載入一次（baseline 模式 badge）──
  const loadInfo = useCallback(async (): Promise<void> => {
    setInfo({ loading: true, error: null, data: null });
    try {
      const data = await knowledgeApi.info();
      setInfo({ loading: false, error: null, data });
    } catch (e) {
      setInfo({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        data: null,
      });
    }
  }, []);

  useEffect(() => {
    void loadInfo();
  }, [loadInfo]);

  // ── search：手動檢索 ──
  const runSearch = useCallback(async (q: RetrievalQuery): Promise<void> => {
    const myReq = ++reqRef.current;
    setSearch({ loading: true, error: null, data: null });
    try {
      const data = await knowledgeApi.query(q);
      // 只有最新一筆查詢的回應才寫進 state（防 stale-overwrites-fresh）。
      if (myReq !== reqRef.current) return;
      setSearch({ loading: false, error: null, data });
    } catch (e) {
      if (myReq !== reqRef.current) return;
      setSearch({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        data: null,
      });
    }
  }, []);

  // ── 清空檢索結果（含中止「接受 in-flight 回應」）──
  const clearSearch = useCallback((): void => {
    // 推進序號 → 任何 in-flight 查詢的回應都會被當成 stale 丟棄。
    reqRef.current++;
    setSearch(INITIAL_SEARCH);
  }, []);

  // ── alert：警報事件自動檢索（killer feature，Part B）──
  // backend 依 AlertEvent 自動構造 query（告警碼 + 機型 + 異常 tag）→ retrieve top-k，
  // 回傳含 auto-built query（透明標示「系統據此檢索」）+ chunks + retriever 來源。
  const runAlert = useCallback(async (event: AlertEvent): Promise<void> => {
    const myReq = ++alertReqRef.current;
    setAlert({ loading: true, error: null, data: null });
    try {
      const data = await knowledgeApi.queryByAlert(event);
      if (myReq !== alertReqRef.current) return;
      setAlert({ loading: false, error: null, data });
    } catch (e) {
      if (myReq !== alertReqRef.current) return;
      setAlert({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        data: null,
      });
    }
  }, []);

  const clearAlert = useCallback((): void => {
    alertReqRef.current++;
    setAlert(INITIAL_ALERT);
  }, []);

  return {
    info,
    search,
    alert,
    loadInfo,
    runSearch,
    clearSearch,
    runAlert,
    clearAlert,
  };
}

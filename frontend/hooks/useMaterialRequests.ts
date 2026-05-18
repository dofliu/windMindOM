/**
 * useMaterialRequests — material request 列表 + 6 個 transition 的 stateful hook。
 *
 * 設計（沿用 useWorkOrders 模式）：
 *   - farmId 為 driver；變動 / filter 改變 → 自動 refetch
 *   - mutations 成功後 patch local items（替換對應 id 的 row）
 *   - 失敗 throw；caller try/catch 顯示 UI 錯誤
 *   - race-guard via AbortController（同 useWorkOrders）
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  materialRequestApi,
  type CancelMaterialRequestPayload,
  type CloseMaterialRequestPayload,
  type CreateMaterialRequestPayload,
  type CreateMaterialReturnPayload,
  type DispatchMaterialRequestPayload,
  type MaterialRequestListResponse,
  type MaterialRequestResponse,
  type MaterialRequestStatus,
  type MaterialReturnResponse,
  type ReceiveMaterialRequestPayload,
  type SubmitForApprovalPayload,
} from '../services/materialService';

interface UseMaterialRequestsOptions {
  farmId: string | null;
  status?: MaterialRequestStatus;
  workOrderId?: string;
  /** business_key / work_order linkage 子字串 client-side filter */
  search?: string;
  limit?: number;
  offset?: number;
}

export interface UseMaterialRequestsResult {
  items: MaterialRequestResponse[];
  /** 未經 client-side search filter 的完整 list；供 detail-modal sync effect 用，
   *  避免 search 啟用時把已選 row filter 掉導致 selectedMR 停在 stale 版本。 */
  rawItems: MaterialRequestResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;

  // mutations
  create: (req: CreateMaterialRequestPayload) => Promise<MaterialRequestResponse>;
  submitForApproval: (
    id: string,
    req: SubmitForApprovalPayload,
  ) => Promise<MaterialRequestResponse>;
  dispatch: (
    id: string,
    req: DispatchMaterialRequestPayload,
  ) => Promise<MaterialRequestResponse>;
  receive: (
    id: string,
    req: ReceiveMaterialRequestPayload,
  ) => Promise<MaterialRequestResponse>;
  close: (id: string, req: CloseMaterialRequestPayload) => Promise<MaterialRequestResponse>;
  cancel: (id: string, req: CancelMaterialRequestPayload) => Promise<MaterialRequestResponse>;
  createReturn: (
    id: string,
    req: CreateMaterialReturnPayload,
  ) => Promise<MaterialReturnResponse>;
}

export function useMaterialRequests(
  opts: UseMaterialRequestsOptions,
): UseMaterialRequestsResult {
  const { farmId, status, workOrderId, search, limit = 200, offset = 0 } = opts;
  const [items, setItems] = useState<MaterialRequestResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    if (!farmId) {
      setItems([]);
      setTotal(0);
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const resp: MaterialRequestListResponse = await materialRequestApi.list({
        farm_id: farmId,
        status,
        work_order_id: workOrderId,
        limit,
        offset,
      });
      if (ctrl.signal.aborted) return;
      setItems(resp.items);
      setTotal(resp.total);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof Error ? e.message : String(e));
      setItems([]);
      setTotal(0);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [farmId, status, workOrderId, limit, offset]);

  useEffect(() => {
    fetchList();
    return () => abortRef.current?.abort();
  }, [fetchList]);

  // local search filter（list 已 server-side status / work_order filter；
  // business_key / work_order_id substring client-side）
  const filteredItems = useMemo(() => {
    if (!search || !search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter(
      mr =>
        mr.business_key.toLowerCase().includes(needle) ||
        (mr.work_order_id ?? '').toLowerCase().includes(needle),
    );
  }, [items, search]);

  // ── mutation helper ──
  const patchLocal = useCallback((updated: MaterialRequestResponse) => {
    setItems(prev => {
      const idx = prev.findIndex(x => x.id === updated.id);
      if (idx === -1) return [updated, ...prev];
      const next = prev.slice();
      next[idx] = updated;
      return next;
    });
  }, []);

  const create = useCallback(async (req: CreateMaterialRequestPayload) => {
    const mr = await materialRequestApi.create(req);
    setItems(prev => [mr, ...prev]);
    setTotal(t => t + 1);
    return mr;
  }, []);

  const submitForApproval = useCallback(
    async (id: string, req: SubmitForApprovalPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const mr = await materialRequestApi.submitForApproval(id, farmId, req);
      patchLocal(mr);
      return mr;
    },
    [farmId, patchLocal],
  );

  const dispatchMR = useCallback(
    async (id: string, req: DispatchMaterialRequestPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const mr = await materialRequestApi.dispatch(id, farmId, req);
      patchLocal(mr);
      return mr;
    },
    [farmId, patchLocal],
  );

  const receive = useCallback(
    async (id: string, req: ReceiveMaterialRequestPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const mr = await materialRequestApi.receive(id, farmId, req);
      patchLocal(mr);
      return mr;
    },
    [farmId, patchLocal],
  );

  const close = useCallback(
    async (id: string, req: CloseMaterialRequestPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const mr = await materialRequestApi.close(id, farmId, req);
      patchLocal(mr);
      return mr;
    },
    [farmId, patchLocal],
  );

  const cancel = useCallback(
    async (id: string, req: CancelMaterialRequestPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const mr = await materialRequestApi.cancel(id, farmId, req);
      patchLocal(mr);
      return mr;
    },
    [farmId, patchLocal],
  );

  /**
   * 建退料記錄；backend 同 transaction 加回 stock。
   * 退料**不會改變 MR status**，只新增 MaterialReturn 紀錄並 patch stock。
   * caller 若要看 MR 最新 audit timestamps，可呼 refresh() 重抓。
   */
  const createReturn = useCallback(
    async (id: string, req: CreateMaterialReturnPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const ret = await materialRequestApi.createReturn(id, farmId, req);
      return ret;
    },
    [farmId],
  );

  return {
    items: filteredItems,
    rawItems: items,
    total,
    loading,
    error,
    refresh: fetchList,
    create,
    submitForApproval,
    dispatch: dispatchMR,
    receive,
    close,
    cancel,
    createReturn,
  };
}

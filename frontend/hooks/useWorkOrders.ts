/**
 * useWorkOrders — work order 列表 + 8 個 transition 的 stateful hook。
 *
 * 設計：
 *   - farm_id 由外部傳入（通常是 active farm id）；變動時自動重 fetch list
 *   - filter（status / only_open / search）也驅動 list 重 fetch
 *   - mutation（create / dispatch / start / progress / finish / approve / reject / cancel / reopen）
 *     成功後 patch local items（替換對應 id 的 row）— 失敗 throw（呼叫端 try/catch UI）
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  workOrderApi,
  type CreateWorkOrderRequest,
  type DispatchRequest,
  type FinishRequest,
  type RejectRequest,
  type CancelRequest,
  type ReopenRequest,
  type StartWorkRequest,
  type UpdateProgressRequest,
  type WorkOrderListResponse,
  type WorkOrderResponse,
  type WorkOrderStatus,
} from '../services/workOrderService';

interface UseWorkOrdersOptions {
  farmId: string | null;
  status?: WorkOrderStatus;
  onlyOpen?: boolean;
  /** business_key / title 子字串 search（client-side filter，配 server list 過濾後再 client filter） */
  search?: string;
  limit?: number;
  offset?: number;
}

export interface UseWorkOrdersResult {
  items: WorkOrderResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  /** 手動 reload list（建立 / 改完想拉新版本時呼叫） */
  refresh: () => Promise<void>;

  // ── Mutations ──
  create: (req: CreateWorkOrderRequest) => Promise<WorkOrderResponse>;
  dispatch: (id: string, req: DispatchRequest) => Promise<WorkOrderResponse>;
  startWork: (id: string, req?: StartWorkRequest) => Promise<WorkOrderResponse>;
  updateProgress: (id: string, req: UpdateProgressRequest) => Promise<WorkOrderResponse>;
  finish: (id: string, req: FinishRequest) => Promise<WorkOrderResponse>;
  approve: (id: string) => Promise<WorkOrderResponse>;
  reject: (id: string, req: RejectRequest) => Promise<WorkOrderResponse>;
  cancel: (id: string, req: CancelRequest) => Promise<WorkOrderResponse>;
  reopen: (id: string, req: ReopenRequest) => Promise<WorkOrderResponse>;
}

export function useWorkOrders(opts: UseWorkOrdersOptions): UseWorkOrdersResult {
  const { farmId, status, onlyOpen, search, limit = 200, offset = 0 } = opts;
  const [items, setItems] = useState<WorkOrderResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // race-guard：farm 切換 / filter 改變時取消舊請求結果寫回
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
      // workOrderApi.list 內部不知道 abort signal — 簡化：靠 ref 比對
      const resp: WorkOrderListResponse = await workOrderApi.list({
        farm_id: farmId,
        status,
        only_open: onlyOpen,
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
  }, [farmId, status, onlyOpen, limit, offset]);

  useEffect(() => {
    fetchList();
    return () => abortRef.current?.abort();
  }, [fetchList]);

  // local search filter（list 已經 server-side status filter；business_key / title client filter）
  const filteredItems = useMemo(() => {
    if (!search || !search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter(
      wo =>
        wo.business_key.toLowerCase().includes(needle) ||
        wo.title.toLowerCase().includes(needle) ||
        wo.turbine_id.toLowerCase().includes(needle),
    );
  }, [items, search]);

  // ── Mutation helpers ──
  const patchLocal = useCallback((updated: WorkOrderResponse) => {
    setItems(prev => {
      const idx = prev.findIndex(x => x.id === updated.id);
      if (idx === -1) return [updated, ...prev];
      const next = prev.slice();
      next[idx] = updated;
      return next;
    });
  }, []);

  const create = useCallback(
    async (req: CreateWorkOrderRequest) => {
      const wo = await workOrderApi.create(req);
      setItems(prev => [wo, ...prev]);
      setTotal(t => t + 1);
      return wo;
    },
    [],
  );

  const dispatchWO = useCallback(
    async (id: string, req: DispatchRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.dispatch(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const startWork = useCallback(
    async (id: string, req: StartWorkRequest = {}) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.startWork(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const updateProgress = useCallback(
    async (id: string, req: UpdateProgressRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.updateProgress(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const finish = useCallback(
    async (id: string, req: FinishRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.finish(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const approve = useCallback(
    async (id: string) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.approve(id, farmId);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const reject = useCallback(
    async (id: string, req: RejectRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.reject(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const cancel = useCallback(
    async (id: string, req: CancelRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.cancel(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  const reopen = useCallback(
    async (id: string, req: ReopenRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const wo = await workOrderApi.reopen(id, farmId, req);
      patchLocal(wo);
      return wo;
    },
    [farmId, patchLocal],
  );

  return {
    items: filteredItems,
    total,
    loading,
    error,
    refresh: fetchList,
    create,
    dispatch: dispatchWO,
    startWork,
    updateProgress,
    finish,
    approve,
    reject,
    cancel,
    reopen,
  };
}

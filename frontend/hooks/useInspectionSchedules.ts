/**
 * useInspectionSchedules — 定檢計畫管理頁主 hook（WMOM-20260925-05）。
 *
 * 設計（沿用 useInventory 模式）：
 *   - farmId 為 driver，turbineId / activeOnly 為 server-side filter；變化 → 自動 refetch
 *   - create / activate / deactivate / runScheduler 完成後皆 refetch 整個列表 ——
 *     列表依 `next_due_at` 升冪排序（後端排序），local patch 無法正確插入新排序位置，
 *     refetch 才能保證顯示順序與後端一致（與 useWorkOrders 的 local-patch 模式不同，
 *     這裡 correctness 優先於少一次 network round-trip）
 *   - updateMetadata 只改文字欄位不影響排序，維持 local patch 即可
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  inspectionScheduleApi,
  type CreateInspectionSchedulePayload,
  type InspectionScheduleResponse,
  type RunSchedulerResponse,
  type UpdateInspectionSchedulePayload,
} from '../services/inspectionScheduleService';

interface UseInspectionSchedulesOptions {
  farmId: string | null;
  turbineId?: string;
  activeOnly?: boolean;
  limit?: number;
  offset?: number;
}

export interface UseInspectionSchedulesResult {
  items: InspectionScheduleResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;

  create: (
    req: Omit<CreateInspectionSchedulePayload, 'farm_id'>,
  ) => Promise<InspectionScheduleResponse>;
  updateMetadata: (
    id: string,
    req: UpdateInspectionSchedulePayload,
  ) => Promise<InspectionScheduleResponse>;
  activate: (id: string) => Promise<InspectionScheduleResponse>;
  deactivate: (id: string) => Promise<InspectionScheduleResponse>;
  runScheduler: () => Promise<RunSchedulerResponse>;
}

export function useInspectionSchedules(
  opts: UseInspectionSchedulesOptions,
): UseInspectionSchedulesResult {
  const { farmId, turbineId, activeOnly, limit = 200, offset = 0 } = opts;

  const [items, setItems] = useState<InspectionScheduleResponse[]>([]);
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
      const resp = await inspectionScheduleApi.list({
        farm_id: farmId,
        turbine_id: turbineId,
        active_only: activeOnly,
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
  }, [farmId, turbineId, activeOnly, limit, offset]);

  useEffect(() => {
    fetchList();
    return () => abortRef.current?.abort();
  }, [fetchList]);

  const patchLocal = useCallback((updated: InspectionScheduleResponse) => {
    setItems(prev => {
      const idx = prev.findIndex(x => x.id === updated.id);
      if (idx === -1) return prev;
      const next = prev.slice();
      next[idx] = updated;
      return next;
    });
  }, []);

  const create = useCallback(
    async (req: Omit<CreateInspectionSchedulePayload, 'farm_id'>) => {
      if (!farmId) throw new Error('farm_id required');
      const created = await inspectionScheduleApi.create({ ...req, farm_id: farmId });
      await fetchList();
      return created;
    },
    [farmId, fetchList],
  );

  const updateMetadata = useCallback(
    async (id: string, req: UpdateInspectionSchedulePayload) => {
      if (!farmId) throw new Error('farm_id required');
      const updated = await inspectionScheduleApi.updateMetadata(id, farmId, req);
      patchLocal(updated);
      return updated;
    },
    [farmId, patchLocal],
  );

  const activate = useCallback(
    async (id: string) => {
      if (!farmId) throw new Error('farm_id required');
      const updated = await inspectionScheduleApi.activate(id, farmId);
      patchLocal(updated);
      return updated;
    },
    [farmId, patchLocal],
  );

  const deactivate = useCallback(
    async (id: string) => {
      if (!farmId) throw new Error('farm_id required');
      const updated = await inspectionScheduleApi.deactivate(id, farmId);
      patchLocal(updated);
      return updated;
    },
    [farmId, patchLocal],
  );

  const runScheduler = useCallback(async () => {
    if (!farmId) throw new Error('farm_id required');
    const result = await inspectionScheduleApi.runScheduler(farmId);
    if (result.spawned.length > 0) {
      await fetchList();
    }
    return result;
  }, [farmId, fetchList]);

  return {
    items,
    total,
    loading,
    error,
    refresh: fetchList,
    create,
    updateMetadata,
    activate,
    deactivate,
    runScheduler,
  };
}

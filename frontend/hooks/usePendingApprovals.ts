/**
 * usePendingApprovals — 「我這層的待簽」list + approve/reject mutations。
 *
 * 設計：
 *   - farm_id + level 是 driver；變動 → 重 fetch
 *   - 額外副作用：list 拉到後，自動 fetch 對應 work_order subject 的 detail
 *     存進 workOrderCache（給 UI 顯示工單 title / turbine / priority 用）
 *   - approve / reject 成功 → 從 local items 移除該 step（chain 結束 / 推進下一階都
 *     代表這層 user 不再看到該 step），再失效對應 cache
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  signoffApi,
  workOrderApi,
  type ApprovalResultResponse,
  type ApproveStepRequest,
  type PendingSignoffItem,
  type RejectStepRequest,
  type SignoffLevel,
  type SignoffSubjectType,
  type WorkOrderResponse,
} from '../services/workOrderService';

interface UsePendingApprovalsOptions {
  farmId: string | null;
  level: SignoffLevel;
  subjectType?: SignoffSubjectType;
  limit?: number;
  offset?: number;
}

export interface UsePendingApprovalsResult {
  items: PendingSignoffItem[];
  total: number;
  loading: boolean;
  error: string | null;
  /** subject_id (UUID) → WorkOrderResponse；只填 work_order subject */
  workOrderCache: Map<string, WorkOrderResponse>;
  refresh: () => Promise<void>;

  approve: (stepId: string, req: ApproveStepRequest) => Promise<ApprovalResultResponse>;
  reject: (stepId: string, req: RejectStepRequest) => Promise<ApprovalResultResponse>;
}

export function usePendingApprovals(
  opts: UsePendingApprovalsOptions,
): UsePendingApprovalsResult {
  const { farmId, level, subjectType, limit = 200, offset = 0 } = opts;

  const [items, setItems] = useState<PendingSignoffItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workOrderCache, setWorkOrderCache] = useState<Map<string, WorkOrderResponse>>(
    new Map(),
  );

  // race guard：farm/level 變化取消舊請求
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
      const resp = await signoffApi.listPending({
        farm_id: farmId,
        level,
        subject_type: subjectType,
        limit,
        offset,
      });
      if (ctrl.signal.aborted) return;
      setItems(resp.items);
      setTotal(resp.total);

      // 後續：拉所有 work_order subject 的 detail 進 cache（並行）
      const workOrderIds = Array.from(
        new Set(
          resp.items
            .filter(it => it.chain.subject_type === 'work_order')
            .map(it => it.chain.subject_id),
        ),
      );
      if (workOrderIds.length > 0) {
        const fetched = await Promise.allSettled(
          workOrderIds.map(id => workOrderApi.get(id, farmId)),
        );
        if (ctrl.signal.aborted) return;
        const next = new Map<string, WorkOrderResponse>();
        fetched.forEach((res, i) => {
          if (res.status === 'fulfilled') {
            next.set(workOrderIds[i], res.value);
          }
        });
        setWorkOrderCache(next);
      } else {
        setWorkOrderCache(new Map());
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof Error ? e.message : String(e));
      setItems([]);
      setTotal(0);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [farmId, level, subjectType, limit, offset]);

  useEffect(() => {
    fetchList();
    return () => abortRef.current?.abort();
  }, [fetchList]);

  // ── Mutations ──
  const removeStep = useCallback((stepId: string) => {
    setItems(prev => prev.filter(it => it.step.id !== stepId));
    setTotal(t => Math.max(0, t - 1));
  }, []);

  const approve = useCallback(
    async (stepId: string, req: ApproveStepRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const result = await signoffApi.approve(stepId, farmId, req);
      removeStep(stepId);
      return result;
    },
    [farmId, removeStep],
  );

  const reject = useCallback(
    async (stepId: string, req: RejectStepRequest) => {
      if (!farmId) throw new Error('farm_id required');
      const result = await signoffApi.reject(stepId, farmId, req);
      removeStep(stepId);
      return result;
    },
    [farmId, removeStep],
  );

  // useMemo guard：返回新 ref 確保 React 偵測到 cache 變動
  const cacheReadonly = useMemo(() => workOrderCache, [workOrderCache]);

  return {
    items,
    total,
    loading,
    error,
    workOrderCache: cacheReadonly,
    refresh: fetchList,
    approve,
    reject,
  };
}

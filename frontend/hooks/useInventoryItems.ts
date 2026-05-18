/**
 * useInventoryItems — minimal picker hook for material request wizard。
 *
 * 設計（WMOM-20260509-06，A6 內最小可行；完整版在 A7 庫存頁）：
 *   - farmId 為 driver，僅供 picker 用，不做 mutations
 *   - 客戶端 search filter（name / sku 子字串）— search 改變不重新 fetch
 *   - 與 useWorkOrders 一致用 AbortController 做 state-update guard（fetch
 *     底層 signal 未串入；race 不會把舊回應寫進 state，但 request 仍會發出）
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  inventoryApi,
  type InventoryItemSummary,
} from '../services/materialService';

interface UseInventoryItemsOptions {
  farmId: string | null;
  /** below_safety_only filter — picker UI 「只顯示低於安全庫存」toggle 用 */
  belowSafetyOnly?: boolean;
  /** sku / name 子字串 client-side filter */
  search?: string;
  limit?: number;
}

export interface UseInventoryItemsResult {
  items: InventoryItemSummary[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useInventoryItems(
  opts: UseInventoryItemsOptions,
): UseInventoryItemsResult {
  const { farmId, belowSafetyOnly, search, limit = 200 } = opts;
  const [items, setItems] = useState<InventoryItemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const fetchItems = useCallback(async () => {
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
      const resp = await inventoryApi.listItems({
        farm_id: farmId,
        below_safety_only: belowSafetyOnly,
        limit,
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
  }, [farmId, belowSafetyOnly, limit]);

  useEffect(() => {
    fetchItems();
    return () => abortRef.current?.abort();
  }, [fetchItems]);

  const filteredItems = useMemo(() => {
    if (!search || !search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter(
      it =>
        it.sku.toLowerCase().includes(needle) ||
        it.name.toLowerCase().includes(needle),
    );
  }, [items, search]);

  return {
    items: filteredItems,
    total,
    loading,
    error,
    refresh: fetchItems,
  };
}

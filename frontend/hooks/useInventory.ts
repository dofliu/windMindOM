/**
 * useInventory — A7 庫存頁主 hook（WMOM-20260509-07）。
 *
 * 設計（沿用 useWorkOrders / useMaterialRequests 模式）：
 *   - farmId 為 driver，warehouseId / belowSafetyOnly 為 filter；變化 → 自動 refetch
 *   - mutations 成功 patch local list（替換 row）
 *   - search 客戶端 sku / name 子字串 filter
 *   - rawItems 提供未經 filter 的 list（給 detail drawer sync effect 用，
 *     與 useMaterialRequests 同 pattern，避免 search 中 selected row stale）
 *   - listAdjustments + warehouses fetch 為獨立子 helper（drawer / filter 各自呼叫）
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  inventoryApi,
  warehouseApi,
  type AdjustInventoryPayload,
  type AdjustInventoryResult,
  type AdjustmentLogResponse,
  type InventoryItemResponse,
  type WarehouseResponse,
} from '../services/inventoryService';

interface UseInventoryOptions {
  farmId: string | null;
  warehouseId?: string;
  belowSafetyOnly?: boolean;
  /** sku / name 子字串 client-side filter */
  search?: string;
  limit?: number;
  offset?: number;
}

export interface UseInventoryResult {
  items: InventoryItemResponse[];
  rawItems: InventoryItemResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;

  warehouses: WarehouseResponse[];
  warehousesLoading: boolean;

  adjust: (
    itemId: string,
    req: AdjustInventoryPayload,
  ) => Promise<AdjustInventoryResult>;
  listAdjustments: (itemId: string) => Promise<AdjustmentLogResponse[]>;
}

export function useInventory(opts: UseInventoryOptions): UseInventoryResult {
  const {
    farmId,
    warehouseId,
    belowSafetyOnly,
    search,
    limit = 200,
    offset = 0,
  } = opts;

  const [items, setItems] = useState<InventoryItemResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [warehouses, setWarehouses] = useState<WarehouseResponse[]>([]);
  const [warehousesLoading, setWarehousesLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const whAbortRef = useRef<AbortController | null>(null);

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
      const resp = await inventoryApi.list({
        farm_id: farmId,
        warehouse_id: warehouseId,
        below_safety_only: belowSafetyOnly,
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
  }, [farmId, warehouseId, belowSafetyOnly, limit, offset]);

  useEffect(() => {
    fetchList();
    return () => abortRef.current?.abort();
  }, [fetchList]);

  // warehouses 隨 farmId 變化重抓（filter dropdown / 建料件 dialog 用）
  useEffect(() => {
    if (!farmId) {
      setWarehouses([]);
      return;
    }
    whAbortRef.current?.abort();
    const ctrl = new AbortController();
    whAbortRef.current = ctrl;
    setWarehousesLoading(true);
    warehouseApi
      .list(farmId)
      .then(resp => {
        if (ctrl.signal.aborted) return;
        setWarehouses(resp.items);
      })
      .catch(() => {
        // warehouse fetch 失敗不阻斷主 list；filter 退化為「全部倉」
        if (ctrl.signal.aborted) return;
        setWarehouses([]);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setWarehousesLoading(false);
      });
    return () => ctrl.abort();
  }, [farmId]);

  // client-side search filter
  const filteredItems = useMemo(() => {
    if (!search || !search.trim()) return items;
    const needle = search.trim().toLowerCase();
    return items.filter(
      it =>
        it.sku.toLowerCase().includes(needle) ||
        it.name.toLowerCase().includes(needle),
    );
  }, [items, search]);

  const patchLocal = useCallback((updated: InventoryItemResponse) => {
    setItems(prev => {
      const idx = prev.findIndex(x => x.id === updated.id);
      if (idx === -1) return prev;
      const next = prev.slice();
      next[idx] = updated;
      return next;
    });
  }, []);

  const adjust = useCallback(
    async (itemId: string, req: AdjustInventoryPayload) => {
      if (!farmId) throw new Error('farm_id required');
      const result = await inventoryApi.adjust(itemId, farmId, req);
      patchLocal(result.item);
      return result;
    },
    [farmId, patchLocal],
  );

  const listAdjustments = useCallback(
    async (itemId: string) => {
      if (!farmId) throw new Error('farm_id required');
      const resp = await inventoryApi.listAdjustments(itemId, farmId);
      return resp.items;
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
    warehouses,
    warehousesLoading,
    adjust,
    listAdjustments,
  };
}

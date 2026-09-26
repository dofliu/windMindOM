/**
 * useDayWorkForm — 個人「工作日誌」頁主 hook（WMOM-20260926-01，`WMOM-20260505-21` 前端）。
 *
 * 設計（自填日誌，範圍限於「本人」——讀取端點的角色可見性設計仍是 open decision，
 * 見 `day_work_form_router.py` docstring 與該 issue 第 3 項，本次不處理，本 hook 一律只
 * 查詢呼叫者本人的 `employee_id`）：
 *   - `workDate` 為 driver：切換日期 → 自動查該日日誌（`by-date`，尚未建立回 `null`，
 *     非錯誤，前端顯示空狀態即可，不預先呼叫 get-or-create）
 *   - `appendActivity` 一律先呼叫 `getOrCreate`（natural-key idempotent）取得該日
 *     `form.id`，不信任本地 `form` state 是否仍對應目前 `workDate`（避免快速切換日期
 *     期間的 race condition 誤把活動寫進錯的一天——寫入目標一律正確）。**讀取端**
 *     另有一道獨立防護（review must-fix）：`appendActivity` 完成後套用 `setForm(updated)`
 *     前，比對 `latestWorkDateRef`（隨每次 render 同步最新 `workDate`）與送出當下捕捉
 *     的 `workDate` 是否一致——不一致（使用者在等待送出結果期間已切到別天）就跳過
 *     `setForm`，避免畫面卡在「日期選擇器顯示別天，但 `form` 內容其實是舊那天」且
 *     不會自我修正的錯誤狀態（`fetchForm` 本身已用 `abortRef` 防同款 race，這裡是
 *     對稱的第二道防線，非重複）
 *   - `history`：最近 N 筆本人日誌（依 `work_date` 降冪，後端排序），append 完成後
 *     一併 refetch 保持與主表同步
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  dayWorkFormApi,
  type AppendActivityPayload,
  type DayWorkFormResponse,
} from '../services/dayWorkFormService';

interface UseDayWorkFormOptions {
  farmId: string | null;
  employeeId: string | null;
  workDate: string;
  historyLimit?: number;
}

export interface UseDayWorkFormResult {
  form: DayWorkFormResponse | null;
  loading: boolean;
  error: string | null;

  history: DayWorkFormResponse[];
  historyLoading: boolean;
  historyError: string | null;

  refresh: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  appendActivity: (
    req: Omit<AppendActivityPayload, 'employee_id'>,
  ) => Promise<DayWorkFormResponse>;
}

export function useDayWorkForm(opts: UseDayWorkFormOptions): UseDayWorkFormResult {
  const { farmId, employeeId, workDate, historyLimit = 14 } = opts;

  const [form, setForm] = useState<DayWorkFormResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<DayWorkFormResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // 永遠反映「目前最新」的 workDate（每次 render 同步），供 appendActivity 完成時
  // 比對送出當下捕捉的日期是否仍是目前使用者正在看的那天。
  const latestWorkDateRef = useRef(workDate);
  useEffect(() => {
    latestWorkDateRef.current = workDate;
  }, [workDate]);

  const fetchForm = useCallback(async () => {
    if (!farmId || !employeeId) {
      setForm(null);
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const found = await dayWorkFormApi.getByDate(farmId, employeeId, workDate);
      if (ctrl.signal.aborted) return;
      setForm(found);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof Error ? e.message : String(e));
      setForm(null);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [farmId, employeeId, workDate]);

  useEffect(() => {
    fetchForm();
    return () => abortRef.current?.abort();
  }, [fetchForm]);

  const fetchHistory = useCallback(async () => {
    if (!farmId || !employeeId) {
      setHistory([]);
      return;
    }
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const resp = await dayWorkFormApi.list({
        farm_id: farmId,
        employee_id: employeeId,
        limit: historyLimit,
      });
      setHistory(resp.items);
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : String(e));
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [farmId, employeeId, historyLimit]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const appendActivity = useCallback(
    async (req: Omit<AppendActivityPayload, 'employee_id'>) => {
      if (!farmId || !employeeId) throw new Error('farm_id/employee_id required');
      const issuedForDate = workDate;
      const ensured = await dayWorkFormApi.getOrCreate({
        farm_id: farmId,
        work_date: issuedForDate,
        employee_id: employeeId,
      });
      const updated = await dayWorkFormApi.appendActivity(ensured.id, farmId, req);
      // 使用者可能在等待這兩趟 await 期間已切換日期選擇器——只有仍停留在送出當下
      // 那天才套用到 `form` state，否則畫面會顯示「別天日期 + 舊那天資料」且不會
      // 自我修正（見上方 docstring）。
      if (latestWorkDateRef.current === issuedForDate) {
        setForm(updated);
      }
      await fetchHistory();
      return updated;
    },
    [farmId, employeeId, workDate, fetchHistory],
  );

  return {
    form,
    loading,
    error,
    history,
    historyLoading,
    historyError,
    refresh: fetchForm,
    refreshHistory: fetchHistory,
    appendActivity,
  };
}

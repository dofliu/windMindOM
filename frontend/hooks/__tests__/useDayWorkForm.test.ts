/**
 * useDayWorkForm 回歸測試（WMOM-20260926-01，`WMOM-20260505-21` 前端）。
 *
 * 核心情境（review must-fix）：`fetchForm` 已用 `abortRef` 守住「較慢的舊 by-date
 * 查詢後到不得蓋掉較新的結果」，但 `appendActivity` 的 `setForm(updated)` 原本沒有
 * 對稱防護——使用者送出活動期間若切換日期選擇器，較慢的 append 回應後到時會把
 * `form` state 蓋回舊那天的資料，且不會自我修正（`workDate` 已經變了，不會再觸發
 * `fetchForm`）。本檔鎖住修法：`appendActivity` 完成時比對送出當下捕捉的 `workDate`
 * 與目前最新 `workDate` 是否一致，不一致就跳過 `setForm`。
 */

import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDayWorkForm } from '../useDayWorkForm';
import { dayWorkFormApi, type DayWorkFormResponse } from '../../services/dayWorkFormService';

vi.mock('../../services/dayWorkFormService', () => ({
  dayWorkFormApi: {
    getOrCreate: vi.fn(),
    list: vi.fn(),
    getByDate: vi.fn(),
    get: vi.fn(),
    appendActivity: vi.fn(),
  },
}));

const getByDateMock = dayWorkFormApi.getByDate as unknown as Mock;
const getOrCreateMock = dayWorkFormApi.getOrCreate as unknown as Mock;
const appendActivityMock = dayWorkFormApi.appendActivity as unknown as Mock;
const listMock = dayWorkFormApi.list as unknown as Mock;

/** 建一個可由外部 resolve/reject 的 deferred promise。 */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeForm(overrides: Partial<DayWorkFormResponse> = {}): DayWorkFormResponse {
  return {
    id: 'form-1',
    farm_id: 'farm-a',
    employee_id: 'emp-1',
    work_date: '2026-09-25',
    activities: [],
    notes: '',
    created_at: '2026-09-25T00:00:00Z',
    created_by: 'emp-1',
    updated_at: '2026-09-25T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  getByDateMock.mockReset();
  getOrCreateMock.mockReset();
  appendActivityMock.mockReset();
  listMock.mockReset();
  listMock.mockResolvedValue({ total: 0, items: [] });
});

describe('useDayWorkForm / 當日日誌（by-date）', () => {
  it('happy path：載入成功寫進 form，loading 收尾', async () => {
    const form = makeForm();
    getByDateMock.mockResolvedValue(form);

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.form).toEqual(form);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('尚未建立過（404 → null）：form 為 null，非錯誤', async () => {
    getByDateMock.mockResolvedValue(null);

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.form).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('查詢失敗：error 設定，form 為 null', async () => {
    getByDateMock.mockRejectedValue(new Error('網路錯誤'));

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.form).toBeNull();
    expect(result.current.error).toBe('網路錯誤');
  });

  it('farmId/employeeId 缺一：不查詢，form 為 null', () => {
    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: null, employeeId: 'emp-1', workDate: '2026-09-25' }),
    );
    expect(getByDateMock).not.toHaveBeenCalled();
    expect(result.current.form).toBeNull();
  });
});

describe('useDayWorkForm / history（最近日誌，僅本人）', () => {
  it('happy path：載入成功寫進 history', async () => {
    getByDateMock.mockResolvedValue(null);
    listMock.mockResolvedValue({ total: 2, items: [makeForm({ id: 'h1' }), makeForm({ id: 'h2' })] });

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.history).toHaveLength(2);
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ farm_id: 'farm-a', employee_id: 'emp-1' }),
    );
  });

  it('查詢失敗：historyError 設定，history 清空', async () => {
    getByDateMock.mockResolvedValue(null);
    listMock.mockRejectedValue(new Error('歷史載入失敗'));

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.history).toEqual([]);
    expect(result.current.historyError).toBe('歷史載入失敗');
  });
});

describe('useDayWorkForm / appendActivity', () => {
  it('happy path：一律先呼叫 getOrCreate 取得 form.id，再 appendActivity，最後 refetch history', async () => {
    getByDateMock.mockResolvedValue(null);
    const ensured = makeForm({ id: 'form-ensured' });
    const updated = makeForm({ id: 'form-ensured', activities: [] });
    getOrCreateMock.mockResolvedValue(ensured);
    appendActivityMock.mockResolvedValue(updated);

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );
    await act(async () => {
      await Promise.resolve();
    });
    listMock.mockClear();

    await act(async () => {
      await result.current.appendActivity({ kind: 'patrol', area: 'B 棟機艙' });
    });

    expect(getOrCreateMock).toHaveBeenCalledWith({
      farm_id: 'farm-a',
      work_date: '2026-09-25',
      employee_id: 'emp-1',
    });
    expect(appendActivityMock).toHaveBeenCalledWith('form-ensured', 'farm-a', {
      kind: 'patrol',
      area: 'B 棟機艙',
    });
    expect(result.current.form).toEqual(updated);
    expect(listMock).toHaveBeenCalledTimes(1); // history refetch
  });

  it('farmId/employeeId 缺一：throw，不呼叫 API', async () => {
    getByDateMock.mockResolvedValue(null);
    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: null, employeeId: 'emp-1', workDate: '2026-09-25' }),
    );

    await expect(result.current.appendActivity({ kind: 'patrol', area: 'x' })).rejects.toThrow(
      'farm_id/employee_id required',
    );
    expect(getOrCreateMock).not.toHaveBeenCalled();
  });

  // ── review must-fix：跨日期切換的 race condition ─────────────────────────

  it('race：送出期間切換日期，較慢的 append 回應後到不得蓋掉已切換到的新日期資料', async () => {
    // day A：getByDate 立即回 null（尚未建立）。
    getByDateMock.mockImplementation((_farm: string, _emp: string, date: string) => {
      if (date === '2026-09-25') return Promise.resolve(null);
      if (date === '2026-09-26') return Promise.resolve(makeForm({ id: 'form-B', work_date: '2026-09-26' }));
      throw new Error(`unexpected date ${date}`);
    });

    const getOrCreateDeferred = deferred<DayWorkFormResponse>();
    getOrCreateMock.mockReturnValue(getOrCreateDeferred.promise);
    const appendDeferred = deferred<DayWorkFormResponse>();
    appendActivityMock.mockReturnValue(appendDeferred.promise);

    const { result, rerender } = renderHook(
      ({ workDate }) => useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate }),
      { initialProps: { workDate: '2026-09-25' } },
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.form).toBeNull(); // day A：尚未建立

    // 使用者在 day A 送出一筆活動（getOrCreate + appendActivity 都還在等待中）。
    let appendPromise!: Promise<DayWorkFormResponse>;
    act(() => {
      appendPromise = result.current.appendActivity({ kind: 'patrol', area: 'A 區' });
    });

    // 送出結果還沒回來之前，使用者已經把日期切到 day B。
    rerender({ workDate: '2026-09-26' });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.form?.work_date).toBe('2026-09-26'); // day B 資料已正確載入

    // day A 的送出這時候才回應（較慢）。
    await act(async () => {
      getOrCreateDeferred.resolve(makeForm({ id: 'form-A', work_date: '2026-09-25' }));
      await Promise.resolve();
      appendDeferred.resolve(makeForm({ id: 'form-A', work_date: '2026-09-25', notes: '舊資料' }));
      await appendPromise;
    });

    // must-fix 修法：day A 的（過期）回應不得蓋掉已顯示的 day B 資料。
    expect(result.current.form?.work_date).toBe('2026-09-26');
    expect(result.current.form?.notes).not.toBe('舊資料');
  });

  it('非 race 控制組：同一天送出活動，正常套用到 form（防止過度修正）', async () => {
    getByDateMock.mockResolvedValue(null);
    const ensured = makeForm({ id: 'form-1' });
    getOrCreateMock.mockResolvedValue(ensured);
    const updated = makeForm({ id: 'form-1', notes: '新內容' });
    appendActivityMock.mockResolvedValue(updated);

    const { result } = renderHook(() =>
      useDayWorkForm({ farmId: 'farm-a', employeeId: 'emp-1', workDate: '2026-09-25' }),
    );
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      await result.current.appendActivity({ kind: 'patrol', area: 'x' });
    });

    expect(result.current.form).toEqual(updated);
  });
});

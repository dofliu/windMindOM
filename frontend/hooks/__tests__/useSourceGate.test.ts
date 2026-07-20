/**
 * useSourceGate 測試（WMOM-20260719-05，補 code review 指出「gate 邏輯無測試」）。
 *
 * 守住：status 三態（active/inactive/非 ok）、selectMode 成功/失敗、以及登出防呆
 * （登出 true→false 不得重查 status，避免 enforce 下 401 把主動登出誤標成 session 過期）。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useSourceGate } from '../useSourceGate';

function jsonRes(body: unknown, ok = true, status = 200): Promise<Response> {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

function installFetch(
  statusBody: unknown = { active: false },
  opts: { statusOk?: boolean; selectOk?: boolean; selectStatus?: number } = {},
) {
  const statusOk = opts.statusOk ?? true;
  const selectOk = opts.selectOk ?? true;
  const selectStatus = opts.selectStatus ?? (selectOk ? 200 : 401);
  fetchMock = vi.fn((url: string) => {
    if (url.includes('/api/source/status')) return jsonRes(statusBody, statusOk, statusOk ? 200 : 401);
    if (url.includes('/api/source/select')) return jsonRes({ status: 'ok' }, selectOk, selectStatus);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

const statusCalls = () => fetchMock.mock.calls.filter(c => String(c[0]).includes('/api/source/status'));
const selectCalls = () => fetchMock.mock.calls.filter(c => String(c[0]).includes('/api/source/select'));

beforeEach(() => installFetch());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('useSourceGate', () => {
  it('status active:true → sourceActive true', async () => {
    installFetch({ active: true });
    const { result } = renderHook(() => useSourceGate(true));
    await waitFor(() => expect(result.current.sourceActive).toBe(true));
  });

  it('status active:false → sourceActive false（顯示選擇頁）', async () => {
    installFetch({ active: false });
    const { result } = renderHook(() => useSourceGate(true));
    await waitFor(() => expect(result.current.sourceActive).toBe(false));
  });

  it('status 非 ok → sourceActive false（不卡在 null 載入中）', async () => {
    installFetch({}, { statusOk: false });
    const { result } = renderHook(() => useSourceGate(true));
    await waitFor(() => expect(result.current.sourceActive).toBe(false));
  });

  it('初次掛載即未登入（過渡期）→ 仍查 status', async () => {
    installFetch({ active: false });
    const { result } = renderHook(() => useSourceGate(false));
    await waitFor(() => expect(result.current.sourceActive).toBe(false));
    expect(statusCalls().length).toBe(1);
  });

  it('selectMode 成功 → POST select、sourceActive=true、回 {ok:true}', async () => {
    const { result } = renderHook(() => useSourceGate(true));
    await waitFor(() => expect(result.current.sourceActive).toBe(false));
    let ret: { ok: boolean; status?: number } = { ok: false };
    await act(async () => {
      ret = await result.current.selectMode('view');
    });
    expect(ret.ok).toBe(true);
    expect(result.current.sourceActive).toBe(true);
    expect(selectCalls().length).toBe(1);
  });

  it('selectMode 失敗（403）→ 回 {ok:false, status:403}、不誤設 active', async () => {
    installFetch({ active: false }, { selectOk: false, selectStatus: 403 });
    const { result } = renderHook(() => useSourceGate(true));
    await waitFor(() => expect(result.current.sourceActive).toBe(false));
    let ret: { ok: boolean; status?: number } = { ok: true };
    await act(async () => {
      ret = await result.current.selectMode('live');
    });
    expect(ret.ok).toBe(false);
    expect(ret.status).toBe(403);
    expect(result.current.sourceActive).toBe(false);
  });

  it('登出（true→false）不重查 status；重新登入才重查', async () => {
    const { rerender } = renderHook(({ auth }) => useSourceGate(auth), {
      initialProps: { auth: true },
    });
    await waitFor(() => expect(statusCalls().length).toBe(1));

    rerender({ auth: false }); // 登出 → 不得重查
    expect(statusCalls().length).toBe(1);

    rerender({ auth: true }); // 重新登入 → 應重查
    await waitFor(() => expect(statusCalls().length).toBe(2));
  });
});

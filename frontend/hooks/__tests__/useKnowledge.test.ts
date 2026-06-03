/**
 * useKnowledge 回歸測試（WMOM-20260603-03，EPIC-M5 M5-5）。
 *
 * 守住 `/field/` 現場查詢頁的 state hook 契約：
 *   - mount 自動 loadInfo（baseline 模式 badge）
 *   - runSearch happy path：寫進 data、清 loading/error
 *   - race：較慢的舊查詢後到不得蓋掉較新結果（reqRef 單調遞增守門）
 *   - error：失敗寫 error 字串、data 維持 null
 *   - clearSearch：清空 + 推進序號（in-flight 回應視為 stale 丟棄）
 *
 * 把整個 knowledgeService 換成可控 mock（與 useCostData.test 同精神：零真連線）。
 */

import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useKnowledge } from '../useKnowledge';
import { knowledgeApi } from '../../services/knowledgeService';

vi.mock('../../services/knowledgeService', () => ({
  knowledgeApi: {
    info: vi.fn(),
    query: vi.fn(),
    queryByAlert: vi.fn(),
  },
}));

const infoMock = knowledgeApi.info as unknown as Mock;
const queryMock = knowledgeApi.query as unknown as Mock;

/** 可由外部 resolve 的 deferred promise（同 useCostData.test 工具）。 */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const INFO_FIXTURE = {
  strategy_name: 'baseline',
  oem: 'Bachmann',
  model: 'Z72',
  retriever: 'baseline_keyword',
  is_baseline: true,
  top_k: 5,
};

function searchResult(tag: string) {
  return {
    items: [
      {
        chunk: {
          id: tag,
          document_source: 'Z72UserManual.pdf',
          chunk_text: `段落 ${tag}`,
          oem: 'Bachmann',
          model: 'Z72',
          alarm_codes: [],
          keywords: [],
        },
        score: 0.5,
        match_reason: 'mock',
      },
    ],
    retriever: 'baseline_keyword',
    is_baseline: true,
    total: 1,
  };
}

describe('useKnowledge', () => {
  beforeEach(() => {
    infoMock.mockReset();
    queryMock.mockReset();
    // 預設 info 成功（避免每個 test 都要設）。
    infoMock.mockResolvedValue(INFO_FIXTURE);
  });

  it('mount 自動 loadInfo → info.data 填入', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.data).toEqual(INFO_FIXTURE));
    expect(result.current.info.loading).toBe(false);
    expect(result.current.info.error).toBeNull();
  });

  it('info 失敗 → error 寫入、data 維持 null', async () => {
    infoMock.mockReset();
    infoMock.mockRejectedValueOnce(new Error('info boom'));
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.error).toBe('info boom'));
    expect(result.current.info.data).toBeNull();
  });

  it('runSearch happy path：寫進 data、清 loading/error', async () => {
    queryMock.mockResolvedValueOnce(searchResult('A'));
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.data).not.toBeNull());

    await act(async () => {
      await result.current.runSearch({ text: '變頻器' });
    });

    expect(result.current.search.data?.items[0].chunk.id).toBe('A');
    expect(result.current.search.loading).toBe(false);
    expect(result.current.search.error).toBeNull();
  });

  it('race：較慢的舊查詢後到不得蓋掉較新結果', async () => {
    const slow = deferred<ReturnType<typeof searchResult>>();
    const fast = deferred<ReturnType<typeof searchResult>>();
    queryMock.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise);

    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.data).not.toBeNull());

    let p1!: Promise<void>;
    let p2!: Promise<void>;
    await act(async () => {
      p1 = result.current.runSearch({ text: 'A' });
      p2 = result.current.runSearch({ text: 'B' });
    });

    // 較新的查詢 #2 先 resolve → data = B。
    await act(async () => {
      fast.resolve(searchResult('B'));
      await p2;
    });
    expect(result.current.search.data?.items[0].chunk.id).toBe('B');

    // 較舊的查詢 #1 後到 → reqRef 已前進，被當 stale 丟棄，data 維持 B。
    await act(async () => {
      slow.resolve(searchResult('A'));
      await p1;
    });
    expect(result.current.search.data?.items[0].chunk.id).toBe('B');
    expect(result.current.search.loading).toBe(false);
  });

  it('runSearch 失敗 → error 寫入、data 維持 null', async () => {
    queryMock.mockRejectedValueOnce(new Error('query boom'));
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.data).not.toBeNull());

    await act(async () => {
      await result.current.runSearch({ text: 'x' });
    });

    expect(result.current.search.error).toBe('query boom');
    expect(result.current.search.data).toBeNull();
  });

  it('clearSearch：清空結果 + 推進序號使 in-flight 回應被丟棄', async () => {
    const pending = deferred<ReturnType<typeof searchResult>>();
    queryMock.mockReturnValueOnce(pending.promise);
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.info.data).not.toBeNull());

    let p1!: Promise<void>;
    await act(async () => {
      p1 = result.current.runSearch({ text: 'A' });
    });
    expect(result.current.search.loading).toBe(true);

    // 查詢還在 in-flight 時 clearSearch → 推進 reqRef、清回 initial。
    act(() => {
      result.current.clearSearch();
    });
    expect(result.current.search.loading).toBe(false);
    expect(result.current.search.data).toBeNull();

    // in-flight 回應後到 → 被當 stale 丟棄，data 仍 null。
    await act(async () => {
      pending.resolve(searchResult('A'));
      await p1;
    });
    expect(result.current.search.data).toBeNull();
  });
});

/**
 * knowledgeService 回歸測試（WMOM-20260603-03，EPIC-M5 M5-5）。
 *
 * 鎖住 `/field/` 知識查詢的 API client 契約：
 *   - 3 endpoint 打對的 method / path / body（GET info、POST query、POST alert）
 *   - 成功回應原樣 parse 回傳
 *   - 失敗時把 FastAPI HTTPException 的 `detail` 抽進 Error message（現場可讀錯誤）
 *   - detail 非字串 / 無 body 時 fallback 成 `HTTP {status}`
 *
 * 全程 mock `global.fetch`，零真連線、零新依賴（與 mockUsers.test 同精神：純邏輯層）。
 */

import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { knowledgeApi } from '../knowledgeService';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 建一個 ok 的 Response-like 物件（只需 ok / status / json）。 */
function okResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

/** 建一個失敗的 Response-like 物件。 */
function errResponse(status: number, body: unknown): Response {
  return {
    ok: false,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe('knowledgeApi.info', () => {
  it('GET /api/knowledge/info 並原樣回傳', async () => {
    const payload = {
      strategy_name: 'baseline',
      oem: 'Bachmann',
      model: 'Z72',
      retriever: 'baseline_keyword',
      is_baseline: true,
      top_k: 5,
    };
    fetchMock.mockResolvedValueOnce(okResponse(payload));

    const result = await knowledgeApi.info();

    expect(result).toEqual(payload);
    const [url, init] = (fetchMock as Mock).mock.calls[0];
    expect(url).toContain('/api/knowledge/info');
    // GET：沒有 method 或 method 非 POST。
    expect(init?.method ?? 'GET').toBe('GET');
  });

  it('500 回應 → 丟含 detail 的 Error', async () => {
    fetchMock.mockResolvedValueOnce(errResponse(503, { detail: '知識庫 RAG 服務暫時不可用' }));
    await expect(knowledgeApi.info()).rejects.toThrow('知識庫 RAG 服務暫時不可用');
  });
});

describe('knowledgeApi.query', () => {
  it('POST /api/knowledge/query 帶 JSON body 並回傳 items', async () => {
    const payload = {
      items: [
        {
          chunk: {
            id: 'c1',
            document_source: 'Z72UserManual.pdf',
            section: '§4.3',
            page: 42,
            chunk_text: '檢查變頻器冷卻水流量',
            oem: 'Bachmann',
            model: 'Z72',
            alarm_codes: [21],
            keywords: ['變頻器', '冷卻'],
            embedding_vector_id: null,
          },
          score: 0.82,
          match_reason: '告警碼 21 命中 + 關鍵字「變頻器」命中',
        },
      ],
      retriever: 'baseline_keyword',
      is_baseline: true,
      total: 1,
    };
    fetchMock.mockResolvedValueOnce(okResponse(payload));

    const result = await knowledgeApi.query({ text: '變頻器冷卻', alarm_codes: [21] });

    expect(result.total).toBe(1);
    expect(result.items[0].chunk.id).toBe('c1');
    const [url, init] = (fetchMock as Mock).mock.calls[0];
    expect(url).toContain('/api/knowledge/query');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ text: '變頻器冷卻', alarm_codes: [21] });
  });

  it('detail 非字串時 fallback 成 JSON 字串（不丟 [object Object]）', async () => {
    fetchMock.mockResolvedValueOnce(errResponse(422, { detail: [{ msg: 'field required' }] }));
    await expect(knowledgeApi.query({ text: '' })).rejects.toThrow('field required');
  });

  it('無 JSON body 時 fallback 成 HTTP {status}', async () => {
    const noBody = {
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not json');
      },
    } as unknown as Response;
    fetchMock.mockResolvedValueOnce(noBody);
    await expect(knowledgeApi.query({ text: 'x' })).rejects.toThrow('HTTP 500');
  });
});

describe('knowledgeApi.queryByAlert', () => {
  it('POST /api/knowledge/alert 帶 AlertEvent body 並回傳 AlertRagResult', async () => {
    const payload = {
      alert: { alarm_code: 21, turbine_id: 'T01' },
      query: { text: '變頻器跳機', alarm_codes: [21] },
      chunks: [],
      strategy_name: 'baseline',
      retriever: 'baseline_keyword',
      is_baseline: true,
    };
    fetchMock.mockResolvedValueOnce(okResponse(payload));

    const result = await knowledgeApi.queryByAlert({ alarm_code: 21, turbine_id: 'T01' });

    expect(result.strategy_name).toBe('baseline');
    const [url, init] = (fetchMock as Mock).mock.calls[0];
    expect(url).toContain('/api/knowledge/alert');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ alarm_code: 21, turbine_id: 'T01' });
  });
});

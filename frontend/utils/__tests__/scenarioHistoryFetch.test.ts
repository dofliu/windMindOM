/**
 * scenarioHistoryFetch 測試（A2 Part 4 抽出）。
 *
 * 邏輯與 `ScenarioCompareTimelineView`（A2 Part 3）既有的 fetch effect 完全一致，此處直接單元
 * 測試抽出後的函式：ok/非 ok/例外三種 fetch 結果、sim_start 有值 vs 缺值走 fallback 對齊、
 * 命中 limit 時的 truncated 判定。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { fetchScenarioHistory } from '../scenarioHistoryFetch';

function jsonRes(body: unknown, ok = true): Promise<Response> {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchScenarioHistory', () => {
  it('成功 + 有 sim_start → 用 sim_start 當對齊基準，truncated=false', async () => {
    const readings = [{ timestamp: '2026-03-01T00:00:10Z', scada: { P: 2 } }, { timestamp: '2026-03-01T00:00:00Z', scada: { P: 1 } }];
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({ readings })));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', '2026-03-01T00:00:00Z', 100);
    expect(data).toEqual({
      rows: readings,
      baseMs: Date.parse('2026-03-01T00:00:00Z'),
      truncated: false,
      usedFallbackAlign: false,
      failed: false,
    });
  });

  it('缺 sim_start → usedFallbackAlign=true，baseMs 取最早一筆讀數的時間', async () => {
    const readings = [
      { timestamp: '2026-03-01T00:00:10Z', scada: { P: 2 } },
      { timestamp: '2026-03-01T00:00:00Z', scada: { P: 1 } }, // DESC 排序，最後一筆最舊
    ];
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({ readings })));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', undefined, 100);
    expect(data.usedFallbackAlign).toBe(true);
    expect(data.baseMs).toBe(Date.parse('2026-03-01T00:00:00Z'));
  });

  it('無讀數且缺 sim_start → fallbackBase 為 0（不丟例外）', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({ readings: [] })));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', undefined, 100);
    expect(data).toEqual({ rows: [], baseMs: 0, truncated: false, usedFallbackAlign: true, failed: false });
  });

  it('讀數筆數命中 limit → truncated=true', async () => {
    const readings = Array.from({ length: 5 }, (_, i) => ({ timestamp: `2026-03-01T00:00:0${i}Z`, scada: { P: i } }));
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({ readings })));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', '2026-03-01T00:00:00Z', 5);
    expect(data.truncated).toBe(true);
  });

  it('HTTP 非 ok + 有 sim_start → failed=true，baseMs 仍照 sim_start 算（rows 空不影響 baseMs 判定），不丟例外', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({}, false)));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', '2026-03-01T00:00:00Z', 100);
    expect(data).toEqual({
      rows: [],
      baseMs: Date.parse('2026-03-01T00:00:00Z'),
      truncated: false,
      usedFallbackAlign: false,
      failed: true,
    });
  });

  it('HTTP 非 ok + 缺 sim_start → failed 與 usedFallbackAlign 各自獨立判定（皆為 true，比照原本內嵌於 ScenarioCompareTimelineView 的寫法，避免抽出後行為分歧）', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({}, false)));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', undefined, 100);
    expect(data).toEqual({ rows: [], baseMs: 0, truncated: false, usedFallbackAlign: true, failed: true });
  });

  it('fetch 拋例外（網路錯誤）→ failed=true，不外洩例外', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network error'))));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', '2026-03-01T00:00:00Z', 100);
    expect(data).toEqual({ rows: [], baseMs: 0, truncated: false, usedFallbackAlign: false, failed: true });
  });

  it('res.readings 非陣列（意外格式）→ rows 空陣列，不崩潰', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonRes({ readings: null })));
    const data = await fetchScenarioHistory('http://api', 3, 'WT001', '2026-03-01T00:00:00Z', 100);
    expect(data.rows).toEqual([]);
  });
});

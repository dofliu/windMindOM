/**
 * scenarioTimeline 純函式測試（A2 Part 3，DEC-20260720-02）。
 *
 * 守住「相對時間對齊」的核心換算：`buildTimelinePoints` 依 sim_start 基準把絕對 timestamp
 * 轉成相對經過毫秒數並排序回舊到新；`simStartMs` 對缺值/壞資料的容錯；`formatElapsed` 的
 * 天/小時/分鐘刻度格式邊界。
 */

import { describe, it, expect } from 'vitest';
import { buildTimelinePoints, formatElapsed, simStartMs } from '../scenarioTimeline';

describe('simStartMs', () => {
  it('合法 ISO 字串 → 對應 epoch ms', () => {
    expect(simStartMs('2026-03-01T00:00:00Z')).toBe(Date.parse('2026-03-01T00:00:00Z'));
  });

  it('缺值（undefined/null/空字串）→ null', () => {
    expect(simStartMs(undefined)).toBeNull();
    expect(simStartMs(null)).toBeNull();
    expect(simStartMs('')).toBeNull();
  });

  it('無法解析的字串 → null（不丟例外）', () => {
    expect(simStartMs('not-a-date')).toBeNull();
  });
});

describe('buildTimelinePoints', () => {
  const base = Date.parse('2026-03-01T00:00:00Z');

  it('DESC 輸入換算後回傳 ASC（舊到新）且時間相對 baseMs', () => {
    const rows = [
      { timestamp: '2026-03-01T00:00:20Z', scada: { P: 30 } }, // +20s
      { timestamp: '2026-03-01T00:00:10Z', scada: { P: 20 } }, // +10s
      { timestamp: '2026-03-01T00:00:00Z', scada: { P: 10 } }, // +0s
    ];
    const points = buildTimelinePoints(rows, 'P', base);
    expect(points).toEqual([
      { t: 0, value: 10 },
      { t: 10000, value: 20 },
      { t: 20000, value: 30 },
    ]);
  });

  it('scada 缺該 tag → value null（不省略該筆，保留時間軸連續性）', () => {
    const rows = [{ timestamp: '2026-03-01T00:00:00Z', scada: { OTHER: 1 } }];
    expect(buildTimelinePoints(rows, 'P', base)).toEqual([{ t: 0, value: null }]);
  });

  it('走 scada_json 字串（非已解析的 scada 物件）也能取值', () => {
    const rows = [{ timestamp: '2026-03-01T00:00:00Z', scada_json: JSON.stringify({ P: 42 }) }];
    expect(buildTimelinePoints(rows, 'P', base)).toEqual([{ t: 0, value: 42 }]);
  });

  it('scada_json 壞掉（非合法 JSON）→ value null，不丟例外', () => {
    const rows = [{ timestamp: '2026-03-01T00:00:00Z', scada_json: '{not json' }];
    expect(buildTimelinePoints(rows, 'P', base)).toEqual([{ t: 0, value: null }]);
  });

  it('timestamp 缺值/無法解析的列直接跳過', () => {
    const rows = [
      { timestamp: '', scada: { P: 1 } },
      { timestamp: 'garbage', scada: { P: 2 } },
      { timestamp: '2026-03-01T00:00:00Z', scada: { P: 3 } },
    ];
    expect(buildTimelinePoints(rows, 'P', base)).toEqual([{ t: 0, value: 3 }]);
  });

  it('空輸入 → 空陣列', () => {
    expect(buildTimelinePoints([], 'P', base)).toEqual([]);
  });
});

describe('formatElapsed', () => {
  it('未滿一小時 → 0h + 分鐘', () => {
    expect(formatElapsed(5 * 60000)).toBe('0h05m');
  });

  it('數小時（未滿一天）→ 小時 + 分鐘，不顯示天', () => {
    expect(formatElapsed((3 * 60 + 15) * 60000)).toBe('3h15m');
  });

  it('滿一天 → 天 + 小時，省略分鐘', () => {
    expect(formatElapsed((25 * 60 + 30) * 60000)).toBe('1d01h');
  });

  it('負值夾在 0', () => {
    expect(formatElapsed(-1000)).toBe('0h00m');
  });

  it('剛好整天邊界（1440 分鐘）→ 1d00h', () => {
    expect(formatElapsed(1440 * 60000)).toBe('1d00h');
  });
});

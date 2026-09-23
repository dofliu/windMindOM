/**
 * scenarioTimeline 純函式測試（A2 Part 3/4，DEC-20260720-02）。
 *
 * 守住「相對時間對齊」的核心換算：`buildTimelinePoints` 依 sim_start 基準把絕對 timestamp
 * 轉成相對經過毫秒數並排序回舊到新；`simStartMs` 對缺值/壞資料的容錯；`formatElapsed` 的
 * 天/小時/分鐘刻度格式邊界。另守住 A2 Part 4 差異圖的分桶重採樣：`medianInterval`/`pickBinMs`
 * 的取樣間隔判定、`binSeries` 的分桶平均、`buildDiffSeries` 的逐桶相減與「只有一邊有值即為
 * null 缺口」規則。
 */

import { describe, it, expect } from 'vitest';
import {
  binSeries,
  buildDiffSeries,
  buildTimelinePoints,
  formatElapsed,
  medianInterval,
  pickBinMs,
  simStartMs,
  type TimelinePoint,
} from '../scenarioTimeline';

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

describe('medianInterval', () => {
  const pt = (t: number): TimelinePoint => ({ t, value: 1 });

  it('少於 2 個點 → null', () => {
    expect(medianInterval([])).toBeNull();
    expect(medianInterval([pt(0)])).toBeNull();
  });

  it('等間距序列 → 該間距', () => {
    expect(medianInterval([pt(0), pt(10), pt(20), pt(30)])).toBe(10);
  });

  it('奇數個間距 → 中位數（排序後取中間值，不受順序影響）', () => {
    // 間距序列：10, 30, 5 → 排序 5,10,30 → 中位數 10
    expect(medianInterval([pt(0), pt(10), pt(40), pt(45)])).toBe(10);
  });

  it('偶數個間距 → 中間兩者平均', () => {
    // 間距：10, 20 → 平均 15
    expect(medianInterval([pt(0), pt(10), pt(30)])).toBe(15);
  });

  it('重複時間點（間距為 0）不計入 → 全為 0 時視為無法判定，回傳 null', () => {
    expect(medianInterval([pt(5), pt(5), pt(5)])).toBeNull();
  });

  it('非遞增輸入的負間距被忽略（只採正向間距）', () => {
    // 間距：-5（忽略）, 10 → 只剩一個樣本 10
    expect(medianInterval([pt(10), pt(5), pt(15)])).toBe(10);
  });
});

describe('pickBinMs', () => {
  it('取多個序列 medianInterval 中的最大值（最粗的取樣間隔）', () => {
    const fine: TimelinePoint[] = [{ t: 0, value: 1 }, { t: 5, value: 1 }, { t: 10, value: 1 }]; // interval 5
    const coarse: TimelinePoint[] = [{ t: 0, value: 1 }, { t: 20, value: 1 }, { t: 40, value: 1 }]; // interval 20
    expect(pickBinMs([fine, coarse])).toBe(20);
  });

  it('全部序列都無法判定間隔 → 回退 fallbackMs（預設 60000）', () => {
    expect(pickBinMs([[], [{ t: 0, value: 1 }]])).toBe(60_000);
  });

  it('可自訂 fallbackMs', () => {
    expect(pickBinMs([[]], 5000)).toBe(5000);
  });
});

describe('binSeries', () => {
  it('同一桶內取平均', () => {
    const points: TimelinePoint[] = [
      { t: 0, value: 10 },
      { t: 5, value: 20 },
      { t: 10, value: 30 },
    ];
    // binMs=10 → bin 0 涵蓋 t=0,5（平均 15），bin 10 涵蓋 t=10（30）
    expect(binSeries(points, 10)).toEqual(new Map([[0, 15], [10, 30]]));
  });

  it('同一桶內 3 個以上的點也正確取平均（非只驗 2 點的特例）', () => {
    const points: TimelinePoint[] = [
      { t: 0, value: 10 },
      { t: 2, value: 20 },
      { t: 4, value: 30 },
      { t: 6, value: 40 },
    ];
    // binMs=10 → 全部落在 bin 0，平均 (10+20+30+40)/4 = 25
    expect(binSeries(points, 10)).toEqual(new Map([[0, 25]]));
  });

  it('忽略 value === null 的點', () => {
    const points: TimelinePoint[] = [
      { t: 0, value: 10 },
      { t: 2, value: null },
    ];
    expect(binSeries(points, 10)).toEqual(new Map([[0, 10]]));
  });

  it('全為 null → 空 Map', () => {
    expect(binSeries([{ t: 0, value: null }], 10)).toEqual(new Map());
  });

  it('負的 t 值分桶正確（Math.floor 向下取整，非無條件捨去小數）', () => {
    // t=-5, binMs=10 → floor(-5/10)*10 = floor(-0.5)*10 = -1*10 = -10
    expect(binSeries([{ t: -5, value: 1 }], 10)).toEqual(new Map([[-10, 1]]));
  });
});

describe('buildDiffSeries', () => {
  it('兩邊都有值的桶 → compare - baseline', () => {
    const baseline: TimelinePoint[] = [{ t: 0, value: 100 }];
    const compare: TimelinePoint[] = [{ t: 0, value: 130 }];
    expect(buildDiffSeries(baseline, compare, 10)).toEqual([{ t: 0, value: 30 }]);
  });

  it('只有一邊有值的桶 → value null（缺口，非 0）', () => {
    const baseline: TimelinePoint[] = [{ t: 0, value: 100 }];
    const compare: TimelinePoint[] = [{ t: 20, value: 50 }];
    expect(buildDiffSeries(baseline, compare, 10)).toEqual([
      { t: 0, value: null },
      { t: 20, value: null },
    ]);
  });

  it('輸出依桶時間遞增排序（即使輸入桶集合來源順序不同）', () => {
    const baseline: TimelinePoint[] = [{ t: 20, value: 1 }, { t: 0, value: 1 }];
    const compare: TimelinePoint[] = [{ t: 10, value: 1 }];
    const out = buildDiffSeries(baseline, compare, 10);
    expect(out.map((p) => p.t)).toEqual([0, 10, 20]);
  });

  it('兩邊皆空 → 空陣列', () => {
    expect(buildDiffSeries([], [], 10)).toEqual([]);
  });
});

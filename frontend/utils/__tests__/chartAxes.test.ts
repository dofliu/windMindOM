/**
 * rightAxisTags 純函式測試（WMOM-20260718-06）。
 *
 * 守住「量級差一個數量級以上的 tag 移右軸」的分軸邏輯——功率 vs 風速能同時看清、
 * 量級相近則單軸、無資料/全 0 不亂分、負值以絕對值計。
 */

import { describe, it, expect } from 'vitest';
import { rightAxisTags } from '../chartAxes';

const powerWind = [
  { WTUR_TotPwrAt: 300, WMET_WSpeedNac: 6 },
  { WTUR_TotPwrAt: 500, WMET_WSpeedNac: 8 },
  { WTUR_TotPwrAt: 375, WMET_WSpeedNac: 7 },
];

describe('rightAxisTags', () => {
  it('功率 vs 風速：風速移右軸、功率留左軸', () => {
    const right = rightAxisTags(['WTUR_TotPwrAt', 'WMET_WSpeedNac'], powerWind);
    expect(right.has('WMET_WSpeedNac')).toBe(true);
    expect(right.has('WTUR_TotPwrAt')).toBe(false);
  });

  it('量級相近（多條溫度）→ 全走左軸（右軸空）', () => {
    const temps = [
      { A: 60, B: 80, C: 120 },
      { A: 65, B: 85, C: 130 },
    ];
    expect(rightAxisTags(['A', 'B', 'C'], temps).size).toBe(0);
  });

  it('量級最大的 tag 永遠留左軸', () => {
    expect(rightAxisTags(['WTUR_TotPwrAt', 'WMET_WSpeedNac'], powerWind).has('WTUR_TotPwrAt')).toBe(false);
  });

  it('無資料 → 空 Set（單軸）', () => {
    expect(rightAxisTags(['A', 'B'], []).size).toBe(0);
  });

  it('全 0 值 → 空 Set（不亂分）', () => {
    expect(rightAxisTags(['A', 'B'], [{ A: 0, B: 0 }]).size).toBe(0);
  });

  it('全 null/缺值的 tag → 留左軸（maxAbs 0 不移右）', () => {
    const data: Array<Record<string, unknown>> = [{ A: 400, B: null }, { A: 500, B: undefined }];
    expect(rightAxisTags(['A', 'B'], data).has('B')).toBe(false);
  });

  it('ratio 可調', () => {
    const data = [{ A: 500, B: 200 }];
    // ratio=2 → threshold 250；B(200) < 250 → 右軸
    expect(rightAxisTags(['A', 'B'], data, 2).has('B')).toBe(true);
    // 預設 ratio=10 → threshold 50；B(200) >= 50 → 左軸
    expect(rightAxisTags(['A', 'B'], data).has('B')).toBe(false);
  });

  it('負值以絕對值計量級', () => {
    const data = [{ A: -480, B: -6 }, { A: -500, B: -7 }];
    const right = rightAxisTags(['A', 'B'], data);
    expect(right.has('B')).toBe(true);
    expect(right.has('A')).toBe(false);
  });
});

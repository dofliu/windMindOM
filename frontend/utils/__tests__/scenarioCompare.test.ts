/**
 * scenarioCompare 純函式測試（WMOM-20260720-10, A1）。
 *
 * 守住 A1 的核心邏輯：faulted 判別（由 fault_schedule）、分群平均（有故障 vs 健康的差異）、
 * 比較序列的缺值處理。這些是比較視圖正確性的根，抽純函式單測 + mutation-verify。
 */

import { describe, it, expect } from 'vitest';
import {
  faultedTurbineIds,
  classifyTurbines,
  compareBars,
  groupMeans,
  metricValue,
  faultedHealthyCounts,
  type ScenarioTurbineSummary,
} from '../scenarioCompare';

const LOADS = { towerFa: null, towerSs: null, bladeFlap: null, bladeEdge: null };

function turbine(
  id: string,
  over: Partial<ScenarioTurbineSummary> = {},
): ScenarioTurbineSummary {
  return {
    turbineId: id,
    samples: 100,
    avgPowerKw: 1000,
    maxPowerKw: 1500,
    energyKwh: 2000,
    capacityFactor: 0.5,
    productionRate: 0.9,
    estopSteps: 0,
    productionHours: 1.0,
    cumulativeDamage: LOADS,
    worstDamage: 0.001,
    rulHours: 10000,
    extremeLoad: LOADS,
    damageEquivalentLoad: LOADS,
    faultEvents: 0,
    ...over,
  };
}

describe('faultedTurbineIds', () => {
  it('由 fault_schedule 取 turbine_id 集合', () => {
    const ids = faultedTurbineIds([
      { turbine_id: 'WT002' },
      { turbine_id: 'WT005' },
      { turbine_id: 'WT002' }, // 重複去重
    ]);
    expect([...ids].sort()).toEqual(['WT002', 'WT005']);
  });

  it('無排程 / undefined / 缺 turbine_id → 空集合（不炸）', () => {
    expect(faultedTurbineIds().size).toBe(0);
    expect(faultedTurbineIds(null).size).toBe(0);
    expect(faultedTurbineIds([{}, { turbine_id: '' }]).size).toBe(0);
  });
});

describe('classifyTurbines', () => {
  it('faulted 由集合判定；排定注入但 faultEvents===0 標記 scheduledNotTriggered', () => {
    const rows = classifyTurbines(
      [
        turbine('WT001', { faultEvents: 0 }), // 健康
        turbine('WT002', { faultEvents: 3 }), // 排定 + 有觸發
        turbine('WT003', { faultEvents: 0 }), // 排定但未觸發
      ],
      new Set(['WT002', 'WT003']),
    );
    expect(rows.map((r) => r.faulted)).toEqual([false, true, true]);
    expect(rows.map((r) => r.scheduledNotTriggered)).toEqual([false, false, true]);
    expect(rows[1].faultEvents).toBe(3);
  });
});

describe('metricValue / compareBars', () => {
  it('缺值（null）→ bar value 0 且 missing=true；有值 → missing=false', () => {
    const rows = classifyTurbines(
      [
        turbine('WT001', { worstDamage: 0.004 }),
        turbine('WT002', { worstDamage: null }), // 無損傷資料
      ],
      new Set(['WT002']),
    );
    const bars = compareBars(rows, 'worstDamage');
    expect(bars[0]).toMatchObject({ turbineId: 'WT001', value: 0.004, faulted: false, missing: false });
    expect(bars[1]).toMatchObject({ turbineId: 'WT002', value: 0, faulted: true, missing: true });
    expect(metricValue(rows[1], 'worstDamage')).toBeNull();
  });
});

describe('groupMeans — 有故障 vs 健康的差異（A1 核心）', () => {
  it('分別平均 faulted / healthy 兩群，缺值不計入', () => {
    const rows = classifyTurbines(
      [
        turbine('WT001', { capacityFactor: 0.6 }), // healthy
        turbine('WT002', { capacityFactor: 0.4 }), // healthy
        turbine('WT003', { capacityFactor: 0.2 }), // faulted
        turbine('WT004', { capacityFactor: 0.1 }), // faulted
      ],
      new Set(['WT003', 'WT004']),
    );
    const m = groupMeans(rows, 'capacityFactor');
    expect(m.healthy).toBeCloseTo(0.5); // (0.6+0.4)/2
    expect(m.faulted).toBeCloseTo(0.15); // (0.2+0.1)/2
  });

  it('某群全缺值 → 該群 null；某群無成員 → null', () => {
    const rows = classifyTurbines(
      [
        turbine('WT001', { rulHours: null }), // faulted，RUL 缺
        turbine('WT002', { rulHours: 5000 }), // healthy
      ],
      new Set(['WT001']),
    );
    const m = groupMeans(rows, 'rulHours');
    expect(m.faulted).toBeNull(); // faulted 群唯一成員 RUL 缺
    expect(m.healthy).toBeCloseTo(5000);

    const noFaulted = groupMeans(classifyTurbines([turbine('WT001')], new Set()), 'capacityFactor');
    expect(noFaulted.faulted).toBeNull(); // 無 faulted 成員
  });
});

describe('faultedHealthyCounts', () => {
  it('計數兩群機組數', () => {
    const rows = classifyTurbines(
      [turbine('WT001'), turbine('WT002'), turbine('WT003')],
      new Set(['WT002']),
    );
    expect(faultedHealthyCounts(rows)).toEqual({ faulted: 1, healthy: 2 });
  });
});

/**
 * farmHeader 純函式測試（WMOM-20260718-04 follow-up）。
 *
 * 補上 App.tsx header strip 邏輯的回歸保護——原本零測試，導致 code review 才抓到
 * `dataSourceLabel` 把 `MODBUS_TCP` 誤標成「模擬」。這裡守住全 4 個 DataSourceType 的
 * 正確標籤，以及 parseActiveFarm 的各種容錯。
 */

import { describe, it, expect } from 'vitest';
import { DataSourceType } from '../../types';
import { dataSourceLabel, parseActiveFarm } from '../farmHeader';

describe('dataSourceLabel — 全 4 個 DataSourceType', () => {
  it('MOCK → Demo（zh/en）', () => {
    expect(dataSourceLabel(DataSourceType.MOCK, 'zh')).toBe('Demo 資料');
    expect(dataSourceLabel(DataSourceType.MOCK, 'en')).toBe('Demo data');
  });

  it('SIMULATION → 模擬 / Simulation', () => {
    expect(dataSourceLabel(DataSourceType.SIMULATION, 'zh')).toBe('模擬');
    expect(dataSourceLabel(DataSourceType.SIMULATION, 'en')).toBe('Simulation');
  });

  it('OPC_DA → OPC-DA（真實資料源，不標模擬）', () => {
    expect(dataSourceLabel(DataSourceType.OPC_DA, 'zh')).toBe('OPC-DA');
  });

  it('MODBUS_TCP → Modbus TCP（真實資料源，**不可**誤標成模擬）', () => {
    const label = dataSourceLabel(DataSourceType.MODBUS_TCP, 'zh');
    expect(label).toBe('Modbus TCP');
    expect(label).not.toBe('模擬');
  });
});

describe('parseActiveFarm — 解析 + 容錯', () => {
  it('正常：回傳 active farm 的 name + turbine_count', () => {
    const data = {
      farms: [
        { farm_id: 'f1', name: '彰化離岸', turbine_count: 14 },
        { farm_id: 'f2', name: '雲林陸域', turbine_count: 8 },
      ],
      active_farm_id: 'f2',
    };
    expect(parseActiveFarm(data)).toEqual({ name: '雲林陸域', turbine_count: 8 });
  });

  it('active_farm_id 對不到任何 farm → null', () => {
    expect(parseActiveFarm({ farms: [{ farm_id: 'f1', name: 'A', turbine_count: 3 }], active_farm_id: 'zzz' })).toBeNull();
  });

  it('空 farms 清單 → null', () => {
    expect(parseActiveFarm({ farms: [], active_farm_id: null })).toBeNull();
  });

  it('缺 farms 欄位 → null', () => {
    expect(parseActiveFarm({ active_farm_id: 'f1' })).toBeNull();
  });

  it('null / 非物件 → null（不 crash）', () => {
    expect(parseActiveFarm(null)).toBeNull();
    expect(parseActiveFarm('nope')).toBeNull();
    expect(parseActiveFarm(undefined)).toBeNull();
  });

  it('active farm 缺 name → null（strip 不顯示殘缺資料）', () => {
    expect(parseActiveFarm({ farms: [{ farm_id: 'f1', turbine_count: 3 }], active_farm_id: 'f1' })).toBeNull();
  });
});

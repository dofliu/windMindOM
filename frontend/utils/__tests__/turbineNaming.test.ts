/**
 * turbineNaming 純函式測試（PR C Phase 1，WMOM-20260926-03）。
 *
 * `wtIdToTurbineIndex` 把 ScenarioDetail「以此情境瀏覽機組細節」帶出的 WT-id 換算成
 * `TurbineData.id`（App.tsx 用它在情境資料到位後找到對應機組並自動選取）。抽出這段
 * 純函式獨立測試——App.tsx 本身無 render 測試基礎設施（需 mock ~15 個子元件，既有
 * 限制），這是本次唯一能鎖住該換算邏輯正確性的測試層。
 */

import { describe, it, expect } from 'vitest';
import { wtIdToTurbineIndex } from '../turbineNaming';

describe('wtIdToTurbineIndex', () => {
  it('三位數零填補格式 → 去除零填補後的數字', () => {
    expect(wtIdToTurbineIndex('WT001')).toBe(1);
    expect(wtIdToTurbineIndex('WT002')).toBe(2);
    expect(wtIdToTurbineIndex('WT010')).toBe(10);
    expect(wtIdToTurbineIndex('WT099')).toBe(99);
  });

  it('三位數以上不受零填補寬度限制（情境機組數超過 999 的邊界防呆，理論不會發生但不應誤算）', () => {
    expect(wtIdToTurbineIndex('WT100')).toBe(100);
    expect(wtIdToTurbineIndex('WT999')).toBe(999);
  });

  it('WT000（無此機組，id 從 1 起算）→ null', () => {
    expect(wtIdToTurbineIndex('WT000')).toBeNull();
  });

  it('格式不符（缺 WT 前綴 / 非數字 / 空字串）→ null，不拋錯', () => {
    expect(wtIdToTurbineIndex('001')).toBeNull();
    expect(wtIdToTurbineIndex('WTabc')).toBeNull();
    expect(wtIdToTurbineIndex('')).toBeNull();
    expect(wtIdToTurbineIndex('WT')).toBeNull();
  });
});

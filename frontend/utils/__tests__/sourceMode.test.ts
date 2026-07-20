/**
 * sourceMode 純函式測試（PR #147 review follow-up）。
 *
 * 補上 App.tsx `handleSelectSource` 的 id→mode 對應的回歸保護——原本零測試，導致把
 * 'scenario' 卡的 mode mutate 回 'simulation'（舊 bug）時全前端 937 測無一轉紅。這裡守住
 * 每張卡送出的 mode 正確，尤其 scenario 卡**必須**送 'scenario'（不自由跑），不可退回 'simulation'。
 */

import { describe, it, expect } from 'vitest';
import { sourceCardToMode } from '../sourceMode';

describe('sourceCardToMode — 全 4 張來源卡片 → mode', () => {
  it('scenario 卡 → scenario（產生新情境不自由跑；**不可**退回 simulation）', () => {
    // 這是 DEC-20260720-01 整條 PR 鏈的關鍵斷言：退回 'simulation' 即重新引入自由跑 + Modbus bug。
    expect(sourceCardToMode('scenario')).toBe('scenario');
    expect(sourceCardToMode('scenario')).not.toBe('simulation');
  });

  it('simulation 卡 → simulation（即時模擬自由跑）', () => {
    expect(sourceCardToMode('simulation')).toBe('simulation');
  });

  it('live 卡 → live（實接 OPC/Modbus）', () => {
    expect(sourceCardToMode('live')).toBe('live');
  });

  it('observe 卡（調閱過去情境）→ view（不啟動任何來源）', () => {
    expect(sourceCardToMode('observe')).toBe('view');
  });
});

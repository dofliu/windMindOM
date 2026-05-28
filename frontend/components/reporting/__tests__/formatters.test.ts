/**
 * reporting formatters 純函式回歸測試（WMOM-20260528-01）。
 *
 * 守月報 / 年度預算面板的金額與百分比顯示契約。fmtMoneyDecimal 在 WMOM-20260509-09
 * code review should-fix #1 因「兩 panel 重複定義 + null 行為分歧」被抽成共用；本檔
 * 鎖定其文件化的 edge-case 行為（null / undefined / 空字串 / 非數字 / 無限大 → '—'，
 * 以及 M / k / 整數三段門檻與負值），避免日後改動時悄悄退化。
 */

import { describe, it, expect } from 'vitest';
import { fmtMoneyDecimal, fmtPct } from '../formatters';

describe('fmtMoneyDecimal — Decimal 字串/數字 → 貨幣顯示', () => {
  it('null / undefined / 空字串 → 破折號', () => {
    expect(fmtMoneyDecimal(null)).toBe('—');
    expect(fmtMoneyDecimal(undefined)).toBe('—');
    expect(fmtMoneyDecimal('')).toBe('—');
  });

  it('非數字 / 無限大 → 破折號', () => {
    expect(fmtMoneyDecimal('abc')).toBe('—');
    expect(fmtMoneyDecimal('Infinity')).toBe('—');
    expect(fmtMoneyDecimal(Infinity)).toBe('—');
    expect(fmtMoneyDecimal(-Infinity)).toBe('—');
    expect(fmtMoneyDecimal(NaN)).toBe('—');
  });

  it('小額（< 1k）→ €xxx.xx 兩位小數', () => {
    expect(fmtMoneyDecimal('450.00')).toBe('€450.00');
    expect(fmtMoneyDecimal('0')).toBe('€0.00');
    expect(fmtMoneyDecimal('999.99')).toBe('€999.99');
  });

  it('接受 number 與 string 兩型，結果一致', () => {
    expect(fmtMoneyDecimal(450)).toBe('€450.00');
    expect(fmtMoneyDecimal('450')).toBe('€450.00');
  });

  it('千級（≥ 1e3）→ €x.xxk', () => {
    expect(fmtMoneyDecimal('1000')).toBe('€1.00k');
    expect(fmtMoneyDecimal('1234.5')).toBe('€1.23k');
    expect(fmtMoneyDecimal('12345.67')).toBe('€12.35k');
    // 門檻下方最大值：999,999.99 仍走 k 段（< 1e6），(/1e3).toFixed(2) 進位成 1000.00
    expect(fmtMoneyDecimal('999999.99')).toBe('€1000.00k');
  });

  it('百萬級（≥ 1e6）→ €x.xxM', () => {
    expect(fmtMoneyDecimal('1000000')).toBe('€1.00M');
    expect(fmtMoneyDecimal('2345678')).toBe('€2.35M');
  });

  it('負值保留符號，門檻用絕對值判斷', () => {
    // 刻意設計：負號在 € 之後（€-450.00），非標準 locale 的 -€450.00；改動需同步本測試。
    expect(fmtMoneyDecimal('-450')).toBe('€-450.00');
    expect(fmtMoneyDecimal('-1500000')).toBe('€-1.50M');
  });
});

describe('fmtPct — 0-1 浮點 → 百分比（1 位小數）', () => {
  it('代表值正確', () => {
    expect(fmtPct(0)).toBe('0.0%');
    expect(fmtPct(0.5)).toBe('50.0%');
    expect(fmtPct(1)).toBe('100.0%');
  });

  it('四捨五入到 1 位小數', () => {
    expect(fmtPct(0.1234)).toBe('12.3%');
    expect(fmtPct(0.999)).toBe('99.9%');
  });
});

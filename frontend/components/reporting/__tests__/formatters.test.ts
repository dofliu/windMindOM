/**
 * reporting/formatters 純函式回歸測試。
 *
 * 這兩個 formatter 是 WMOM-20260509-09 code review Should-fix #1 抽出的共用層
 * （原本 MonthlyReportPanel / AnnualBudgetPanel 各自定義、null 行為分歧）。本檔鎖住
 * 抽出後的單一行為，特別是 null / undefined / 空字串 / 非有限值一律回「—」這條
 * 「不顯示 0 或 NaN」的契約 —— 月報金額欄位的正確性關鍵。
 */

import { describe, it, expect } from 'vitest';
import { fmtMoneyDecimal, fmtPct } from '../formatters';

describe('fmtMoneyDecimal', () => {
  it('null / undefined / 空字串 → 「—」', () => {
    expect(fmtMoneyDecimal(null)).toBe('—');
    expect(fmtMoneyDecimal(undefined)).toBe('—');
    expect(fmtMoneyDecimal('')).toBe('—');
  });

  it('非數字 / 非有限值 → 「—」', () => {
    expect(fmtMoneyDecimal('abc')).toBe('—');
    expect(fmtMoneyDecimal(Number.NaN)).toBe('—');
    expect(fmtMoneyDecimal(Number.POSITIVE_INFINITY)).toBe('—');
  });

  it('小額（|n| < 1e3）→ €N.NN', () => {
    expect(fmtMoneyDecimal(450)).toBe('€450.00');
    expect(fmtMoneyDecimal('450')).toBe('€450.00');
    expect(fmtMoneyDecimal(0)).toBe('€0.00');
    expect(fmtMoneyDecimal(999.99)).toBe('€999.99');
  });

  it('千級（|n| ≥ 1e3）→ €N.NNk（含 1e3 下界）', () => {
    expect(fmtMoneyDecimal(1000)).toBe('€1.00k'); // 恰好 1e3 → 進 k 級
    expect(fmtMoneyDecimal(12340)).toBe('€12.34k');
    expect(fmtMoneyDecimal('45678')).toBe('€45.68k');
    // 上界鄰值：999_999.99 仍 < 1e6 → 留 k 級（四捨五入後顯示 1000.00k，非 M 級），
    // 鎖住 k/M 分級「以 1e6 為門檻」的方向，防未來把判斷改成顯示值四捨五入後比較。
    expect(fmtMoneyDecimal(999_999.99)).toBe('€1000.00k');
  });

  it('百萬級（|n| ≥ 1e6）→ €N.NNM（含 1e6 下界）', () => {
    expect(fmtMoneyDecimal(1_000_000)).toBe('€1.00M'); // 恰好 1e6 → 進 M 級
    expect(fmtMoneyDecimal(1_230_000)).toBe('€1.23M');
  });

  it('負值依絕對值分級、保留負號（含 1e3 邊界）', () => {
    expect(fmtMoneyDecimal(-450)).toBe('€-450.00');
    expect(fmtMoneyDecimal(-1000)).toBe('€-1.00k'); // |−1000| = 1e3 → k 級
    expect(fmtMoneyDecimal(-1500)).toBe('€-1.50k');
    expect(fmtMoneyDecimal(-2_000_000)).toBe('€-2.00M');
  });

  it('字串帶前綴數字由 parseFloat 寬鬆解析（顯示用途）', () => {
    // 此為 parseFloat 的寬鬆副作用（'12.5abc' → 12.5），非刻意設計；測試鎖住它，
    // 若未來改用嚴格 parse（Number()）行為會改變，此測試會提醒同步評估。
    expect(fmtMoneyDecimal('12.5abc')).toBe('€12.50');
  });
});

describe('fmtPct', () => {
  it('0-1 浮點 → 一位小數百分比', () => {
    expect(fmtPct(0)).toBe('0.0%');
    expect(fmtPct(0.5)).toBe('50.0%');
    expect(fmtPct(1)).toBe('100.0%');
    expect(fmtPct(0.1234)).toBe('12.3%');
  });

  it('NaN → 「NaN%」（source 未防禦缺值，鎖住現況）', () => {
    // fmtPct 簽章為 `v: number`，呼叫端（MonthlyReportPanel KPI ratio）型別已保證傳
    // 有限數，故無真實 null/undefined 風險。但 NaN 仍是 number，會輸出 'NaN%'。
    // 此處刻意鎖住目前未防禦行為：若未來於 source 加 guard（回 '—'），此測試會紅 →
    // 提醒同步更新，而非靜默改變使用者可見輸出。
    expect(fmtPct(Number.NaN)).toBe('NaN%');
  });
});

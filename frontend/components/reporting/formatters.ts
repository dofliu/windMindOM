/**
 * Formatters shared by reporting panels（review fix — should-fix dedup）。
 */

/**
 * 把 Decimal 字串（後端 Pydantic 序列化）格式化為人類可讀貨幣。
 *
 * - null / undefined / 非數字 → `'—'`
 * - |n| ≥ 1e6 → `€1.23M`
 * - |n| ≥ 1e3 → `€12.34k`
 * - 否則 → `€450.00`
 *
 * Note：用 `parseFloat` 對「金額顯示」夠用（顯示 2 位小數）；若未來要做精算（加總、
 * 分帳）必須改用 decimal.js 或 BigInt，避免 IEEE 754 精度漂失。
 */
export function fmtMoneyDecimal(s: string | number | null | undefined): string {
  if (s === null || s === undefined || s === '') return '—';
  const n = typeof s === 'number' ? s : parseFloat(s);
  if (!isFinite(n)) return '—';
  if (Math.abs(n) >= 1e6) return `€${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `€${(n / 1e3).toFixed(2)}k`;
  return `€${n.toFixed(2)}`;
}

/** 格式化 0-1 浮點為百分比（1 位小數）。 */
export function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

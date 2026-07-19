/**
 * chartAxes — 依量級把趨勢圖的 tags 分到左/右兩個 Y 軸（WMOM-20260718-06）。
 *
 * 問題：功率（數百 kW）與風速（個位數 m/s）畫在同一個 Y 軸時，風速被壓到貼底、完全看不見。
 * 解法：量級比「全體最大值」還小一個數量級以上（預設 < 1/10）的 tag 移到右軸，兩軸各自
 * auto-scale，兩個尺度差很大的物理量就能同時看清楚。量級相近（如多條溫度）則全走左軸、
 * 不渲染右軸，避免無謂複雜。
 */

/**
 * 回傳應放在「右軸」的 tag 集合（其餘走左軸）。
 *
 * @param tags   目前圖上的 tag 清單。
 * @param data   趨勢資料列（每列是 `{ tag: value, ... }`）。
 * @param ratio  量級門檻：maxAbs < globalMax / ratio 的 tag 放右軸（預設 10 ＝一個數量級）。
 * @returns 右軸 tag 的 Set；無資料或所有 tag 量級相近時為空（＝單軸）。
 */
export function rightAxisTags(
  tags: string[],
  data: Array<Record<string, unknown>>,
  ratio = 10,
): Set<string> {
  const maxAbs = new Map<string, number>();
  for (const tag of tags) {
    let m = 0;
    for (const row of data) {
      const v = row[tag];
      if (typeof v === 'number' && Number.isFinite(v)) {
        const a = Math.abs(v);
        if (a > m) m = a;
      }
    }
    maxAbs.set(tag, m);
  }

  const globalMax = Math.max(0, ...tags.map(t => maxAbs.get(t) ?? 0));
  const right = new Set<string>();
  if (globalMax <= 0) return right; // 無資料 → 單軸

  const threshold = globalMax / ratio;
  for (const tag of tags) {
    const m = maxAbs.get(tag) ?? 0;
    // m > 0 才移右軸（全 0/缺值的 tag 留左軸）；量級最大的 tag 恆 >= threshold → 永遠留左軸。
    if (m > 0 && m < threshold) right.add(tag);
  }
  return right;
}

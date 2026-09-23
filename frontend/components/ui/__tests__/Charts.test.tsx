/**
 * `MiniSparkline`/`BigChart`/`HealthBar` 測試（WMOM-20260923-04，EPIC-M5 測試覆蓋擴大）。
 *
 * 三支元件都是純 SVG path 數學（正規化座標、`range=0` 除以零防呆、`Math.max(len-1,1)`
 * 防呆、`HealthBar` 的 clamp + 顏色門檻）——這類邊界條件是最容易被日後小重構悄悄破壞、卻
 * 沒有任何頁面層測試會剛好命中的分支（全部數值相同、只有一筆資料、clamp 到 0/100 邊界）。
 *
 * 不斷言真實視覺渲染（jsdom 無法驗證），只驗證 DOM 結構（`<path>`/`<line>`/`<circle>`/
 * `<text>` 數量與 `d`/`style` 屬性內容）是否符合預期計算結果。
 */

import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';
import { MiniSparkline, BigChart, HealthBar } from '../Charts';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { palettes } from '../../../theme/themes';

afterEach(cleanup);

const C = palettes.light;

/** jsdom 會把 inline style 的 hex 正規化成 `rgb(r, g, b)`，比對前需先轉換。 */
function hexToRgb(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}

function renderWithTheme(node: React.ReactElement) {
  return render(<ThemeProvider>{node}</ThemeProvider>);
}

describe('MiniSparkline', () => {
  it('空陣列 → 只渲染 placeholder div，無 svg', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[]} />);
    expect(container.querySelector('svg')).toBeNull();
    expect(container.querySelector('div')).toBeInTheDocument();
  });

  it('單一數值 → 不崩潰、path d 不含 NaN', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[42]} />);
    const path = container.querySelector('path');
    expect(path).not.toBeNull();
    expect(path?.getAttribute('d')).not.toContain('NaN');
  });

  it('多筆數值 → 正常路徑，不含 NaN', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[1, 5, 3, 8, 2]} />);
    const path = container.querySelector('path');
    expect(path?.getAttribute('d')).not.toContain('NaN');
  });

  it('全部數值相同（range=0）→ fallback range=1，不產生 NaN', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[7, 7, 7, 7]} />);
    const path = container.querySelector('path');
    expect(path?.getAttribute('d')).not.toContain('NaN');
  });

  it('fill=false（預設）→ 只有 1 條 path，無 linearGradient', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[1, 2, 3]} />);
    expect(container.querySelectorAll('path').length).toBe(1);
    expect(container.querySelector('linearGradient')).toBeNull();
  });

  it('fill=true → 多渲染 1 條 area path + linearGradient', () => {
    const { container } = renderWithTheme(<MiniSparkline values={[1, 2, 3]} fill />);
    expect(container.querySelectorAll('path').length).toBe(2);
    expect(container.querySelector('linearGradient')).not.toBeNull();
  });
});

describe('BigChart', () => {
  it('無 series → 渲染 — placeholder，無 svg', () => {
    const { container, getByText } = renderWithTheme(<BigChart series={[]} />);
    expect(container.querySelector('svg')).toBeNull();
    expect(getByText('—')).toBeInTheDocument();
  });

  it('series 內都是空陣列 → 同樣視為無資料', () => {
    const { container } = renderWithTheme(
      <BigChart series={[{ values: [], color: C.accent }]} />,
    );
    expect(container.querySelector('svg')).toBeNull();
  });

  it('單一 series 無 upper/lower/fill → 只有 1 條 line path', () => {
    const { container } = renderWithTheme(
      <BigChart series={[{ values: [1, 2, 3], color: C.accent }]} grid={false} />,
    );
    expect(container.querySelectorAll('path').length).toBe(1);
  });

  it('upper/lower 長度相等 → 多渲染 1 條 band path', () => {
    const { container } = renderWithTheme(
      <BigChart
        series={[
          { values: [1, 2, 3], color: C.accent, upper: [2, 3, 4], lower: [0, 1, 2] },
        ]}
        grid={false}
      />,
    );
    expect(container.querySelectorAll('path').length).toBe(2);
  });

  it('upper/lower 長度不等 → 不渲染 band（守長度檢查分支）', () => {
    const { container } = renderWithTheme(
      <BigChart
        series={[
          { values: [1, 2, 3], color: C.accent, upper: [2, 3, 4], lower: [0, 1] },
        ]}
        grid={false}
      />,
    );
    expect(container.querySelectorAll('path').length).toBe(1);
  });

  it('fill=true 且有 band → band + area + line 共 3 條 path', () => {
    const { container } = renderWithTheme(
      <BigChart
        series={[
          {
            values: [1, 2, 3],
            color: C.accent,
            fill: true,
            upper: [2, 3, 4],
            lower: [0, 1, 2],
          },
        ]}
        grid={false}
      />,
    );
    expect(container.querySelectorAll('path').length).toBe(3);
  });

  it('grid=true（預設）→ 5 條格線 line；grid=false → 0 條', () => {
    const series = [{ values: [1, 2, 3], color: C.accent }];
    const withGrid = renderWithTheme(<BigChart series={series} />);
    expect(withGrid.container.querySelectorAll('line').length).toBe(5);

    const withoutGrid = renderWithTheme(<BigChart series={series} grid={false} />);
    expect(withoutGrid.container.querySelectorAll('line').length).toBe(0);
  });

  it('events 帶 label → 渲染對應 circle + text', () => {
    const { container, getByText } = renderWithTheme(
      <BigChart
        series={[{ values: [1, 2, 3], color: C.accent }]}
        grid={false}
        events={[{ position: 0.5, color: C.warn, label: 'FAULT' }]}
      />,
    );
    expect(container.querySelector('circle')).not.toBeNull();
    // position=0.5、W=800（BigChart 固定寬度）→ cx 應精確落在 400，而非只驗證「有畫」
    expect(container.querySelector('circle')?.getAttribute('cx')).toBe('400');
    expect(getByText('FAULT')).toBeInTheDocument();
  });
});

describe('HealthBar', () => {
  it('value=110 → clamp 顯示 100%', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={110} />);
    expect(getByText('100%')).toBeInTheDocument();
  });

  it('value=-10 → clamp 顯示 0%', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={-10} />);
    expect(getByText('0%')).toBeInTheDocument();
  });

  it('value=90（>85）→ ok 色', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={90} />);
    const bar = getByText('90%').previousElementSibling?.firstElementChild;
    const style = bar?.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.ok));
  });

  it('value=80（>75 且 <=85）→ amber 色', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={80} />);
    const bar = getByText('80%').previousElementSibling?.firstElementChild;
    const style = bar?.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.amber));
  });

  it('value=50（<=75）→ warn 色', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={50} />);
    const bar = getByText('50%').previousElementSibling?.firstElementChild;
    const style = bar?.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.warn));
  });

  it('邊界值 85（不大於 85）→ 非 ok 色，走 amber 分支', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={85} />);
    const bar = getByText('85%').previousElementSibling?.firstElementChild;
    const style = bar?.getAttribute('style') ?? '';
    expect(style).not.toContain(hexToRgb(C.ok));
    expect(style).toContain(hexToRgb(C.amber));
  });

  it('邊界值 75（不大於 75）→ 非 amber 色，走 warn 分支', () => {
    const { getByText } = renderWithTheme(<HealthBar label="Gearbox" value={75} />);
    const bar = getByText('75%').previousElementSibling?.firstElementChild;
    const style = bar?.getAttribute('style') ?? '';
    expect(style).not.toContain(hexToRgb(C.amber));
    expect(style).toContain(hexToRgb(C.warn));
  });
});

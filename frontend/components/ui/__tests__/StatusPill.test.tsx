/**
 * StatusPill component + tone-mapper 純函式測試（WMOM-20260923-04，EPIC-M5 測試覆蓋擴大）。
 *
 * `StatusPill` 是全站狀態顏色語意的單一來源：`turbineStatusTone`/`workOrderStatusTone`/
 * `technicianStatusTone` 三支匯出純函式決定風機/工單/技師狀態該套哪種顏色，先前只被呼叫端
 * 頁面測試間接命中，覆蓋不保證涵蓋每個分支（尤其是 default fallback）。本檔直接測完整分支。
 *
 * 元件本體不斷言 `getComputedStyle`（jsdom 不會做 CSS 簡寫展開/計算），改讀 inline `style`
 * 屬性字串是否包含預期 hex 值，比照專案內未見對計算後樣式斷言的既有慣例。
 */

import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';
import {
  StatusPill,
  turbineStatusTone,
  workOrderStatusTone,
  technicianStatusTone,
} from '../StatusPill';
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

function renderPill(props: React.ComponentProps<typeof StatusPill>) {
  return render(
    <ThemeProvider>
      <StatusPill {...props} />
    </ThemeProvider>,
  );
}

describe('StatusPill — 元件渲染', () => {
  it('顯示 children', () => {
    const { getByText } = renderPill({ children: 'OPERATING' });
    expect(getByText('OPERATING')).toBeInTheDocument();
  });

  it.each([
    ['ok', C.okSoft, C.ok],
    ['warn', C.warnSoft, C.warn],
    ['amber', C.amberSoft, C.amber],
    ['info', C.infoSoft, C.info],
    ['accent', C.accentSoft, C.accent],
    ['muted', C.panelMuted, C.faint],
    ['danger', C.dangerSoft, C.danger],
  ] as const)('tone=%s 套用對應 theme 顏色（bg/fg）', (tone, bg, fg) => {
    const { getByText } = renderPill({ children: 'x', tone });
    const style = getByText('x').getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(bg));
    expect(style).toContain(hexToRgb(fg));
  });

  it('未指定 tone 時預設 muted', () => {
    const { getByText } = renderPill({ children: 'x' });
    const style = getByText('x').getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.panelMuted));
    expect(style).toContain(hexToRgb(C.faint));
  });

  it('colorBg/colorFg 覆蓋 tone 對照表', () => {
    const { getByText } = renderPill({
      children: 'x',
      tone: 'ok',
      colorBg: '#123456',
      colorFg: '#abcdef',
    });
    const style = getByText('x').getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb('#123456'));
    expect(style).toContain(hexToRgb('#abcdef'));
    // 不應殘留被覆蓋掉的 tone 顏色
    expect(style).not.toContain(hexToRgb(C.okSoft));
  });

  it('size 預設 sm，padding/fontSize 較小', () => {
    const { getByText } = renderPill({ children: 'x' });
    const style = getByText('x').getAttribute('style') ?? '';
    expect(style).toContain('padding: 2px 8px');
    expect(style).toContain('font-size: 10px');
  });

  it('size=md 時 padding/fontSize 較大', () => {
    const { getByText } = renderPill({ children: 'x', size: 'md' });
    const style = getByText('x').getAttribute('style') ?? '';
    expect(style).toContain('padding: 4px 10px');
    expect(style).toContain('font-size: 11px');
  });

  it('title 屬性透傳', () => {
    const { getByText } = renderPill({ children: 'x', title: '提示文字' });
    expect(getByText('x')).toHaveAttribute('title', '提示文字');
  });
});

describe('turbineStatusTone', () => {
  it.each([
    ['OPERATING', 'ok'],
    ['FAULT', 'warn'],
    ['IDLE', 'amber'],
    ['OFFLINE', 'muted'],
    ['UNKNOWN_STATUS', 'muted'],
  ] as const)('%s → %s', (status, tone) => {
    expect(turbineStatusTone(status)).toBe(tone);
  });
});

describe('workOrderStatusTone', () => {
  it.each([
    ['IN_PROGRESS', 'amber'],
    ['COMPLETED', 'ok'],
    ['OPEN', 'accent'],
    ['UNKNOWN_STATUS', 'accent'],
  ] as const)('%s → %s', (status, tone) => {
    expect(workOrderStatusTone(status)).toBe(tone);
  });
});

describe('technicianStatusTone', () => {
  it.each([
    ['ON_DUTY', 'ok'],
    ['ON DUTY', 'ok'],
    ['DISPATCHED', 'accent'],
    ['OFF_DUTY', 'muted'],
    ['UNKNOWN_STATUS', 'muted'],
  ] as const)('%s → %s', (status, tone) => {
    expect(technicianStatusTone(status)).toBe(tone);
  });
});

/**
 * Logo 品牌風車圖示的 render 測試。
 *
 * 契約（見 Logo.tsx）：render 一個 <svg>（風車：1 圓心 circle + 3 葉片 ellipse）；
 * size 控制 svg 寬高（預設 18）；color 控制 fill（預設 'currentColor'）；
 * viewBox 固定 0 0 24 24；aria-hidden（純裝飾）。
 * Logo **不使用 useTheme**，故毋須包 ThemeProvider。
 * 測試策略同 Btn.test.tsx（RTL + jsdom + 原生 DOM 斷言）。
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { Logo } from '../Logo';

afterEach(cleanup);

/** render Logo 並回傳其 <svg> 根節點。 */
function renderLogo(ui: React.ReactElement): SVGSVGElement {
  const { container } = render(ui);
  const svg = container.querySelector('svg');
  if (svg === null) throw new Error('Logo 未 render 出 <svg>');
  return svg;
}

describe('Logo', () => {
  it('render 風車 <svg>：1 個圓心 circle + 3 片 ellipse 葉片', () => {
    const svg = renderLogo(<Logo />);
    expect(svg.querySelectorAll('circle').length).toBe(1);
    expect(svg.querySelectorAll('ellipse').length).toBe(3);
  });

  it('預設 size=18：svg 寬高皆為 18', () => {
    const svg = renderLogo(<Logo />);
    expect(svg.getAttribute('width')).toBe('18');
    expect(svg.getAttribute('height')).toBe('18');
  });

  it('自訂 size：svg 寬高跟著改變', () => {
    const svg = renderLogo(<Logo size={32} />);
    expect(svg.getAttribute('width')).toBe('32');
    expect(svg.getAttribute('height')).toBe('32');
  });

  it('viewBox 固定為 0 0 24 24（保持縮放比例）', () => {
    const svg = renderLogo(<Logo />);
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
  });

  it('預設 color=currentColor：圓心 fill 為 currentColor', () => {
    const svg = renderLogo(<Logo />);
    expect(svg.querySelector('circle')?.getAttribute('fill')).toBe('currentColor');
  });

  it('自訂 color：所有葉片與圓心 fill 套用該色', () => {
    // 刻意用與 theme palette 無關的測試色，凸顯 Logo 是純 prop 驅動、不吃 theme。
    const svg = renderLogo(<Logo color="#123456" />);
    expect(svg.querySelector('circle')?.getAttribute('fill')).toBe('#123456');
    svg.querySelectorAll('ellipse').forEach((el) => {
      expect(el.getAttribute('fill')).toBe('#123456');
    });
  });

  it('aria-hidden="true"：純裝飾圖示對讀屏隱藏', () => {
    const svg = renderLogo(<Logo />);
    // 布林 JSX 屬性 aria-hidden 會 render 成字串 "true"；明確驗 true 而非僅存在，
    // 避免 aria-hidden="false"（語義相反）也過關。
    expect(svg.getAttribute('aria-hidden')).toBe('true');
  });
});

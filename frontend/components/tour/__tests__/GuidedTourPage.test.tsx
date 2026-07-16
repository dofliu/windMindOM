/**
 * GuidedTourPage render 測試（app 內情境導覽模式）。
 * 範式同其他 render 測試：ThemeProvider 包裹 + jest-dom matcher。純前端、無 hook mock。
 */

import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import GuidedTourPage from '../GuidedTourPage';
import { ThemeProvider } from '../../../theme/ThemeProvider';

const renderTour = (lang: 'zh' | 'en' = 'zh') =>
  render(
    <ThemeProvider>
      <GuidedTourPage lang={lang} />
    </ThemeProvider>,
  );

afterEach(cleanup);

describe('GuidedTourPage', () => {
  it('開場顯示「開始導覽」按鈕', () => {
    renderTour();
    expect(screen.getByRole('button', { name: /開始導覽/ })).toBeInTheDocument();
  });

  it('點開始導覽 → 進到情境一（監控總覽，出現風場總覽面板）', () => {
    renderTour();
    fireEvent.click(screen.getByRole('button', { name: /開始導覽/ }));
    expect(screen.getByText('風場總覽')).toBeInTheDocument();
  });

  it('下一步推進到情境二（告警查手冊）', () => {
    renderTour();
    fireEvent.click(screen.getByRole('button', { name: /開始導覽/ }));
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }));
    expect(screen.getByText('齒輪箱軸承溫度過高')).toBeInTheDocument();
  });

  it('章節列可直接跳到月報情境', () => {
    renderTour();
    fireEvent.click(screen.getByRole('button', { name: /月報/ }));
    expect(screen.getByText(/運維月報/)).toBeInTheDocument();
  });

  it('英文 lang 顯示英文開場', () => {
    renderTour('en');
    expect(screen.getByRole('button', { name: /Start tour/ })).toBeInTheDocument();
  });
});

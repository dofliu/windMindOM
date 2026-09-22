/**
 * GuidedTourPage render 測試（app 內情境導覽模式）。
 * 範式同其他 render 測試：ThemeProvider 包裹 + jest-dom matcher。純前端、無 hook mock。
 */

import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import GuidedTourPage from '../GuidedTourPage';
import { ThemeProvider, useTheme } from '../../../theme/ThemeProvider';

const renderTour = (lang: 'zh' | 'en' = 'zh') =>
  render(
    <ThemeProvider>
      <GuidedTourPage lang={lang} />
    </ThemeProvider>,
  );

/** 額外掛一顆會讀 useTheme() 的切換鈕，用來在不改變 step 的情況下逼 GuidedTourPage 重新 render。 */
const ThemeToggleHarness: React.FC<{ lang: 'zh' | 'en' }> = ({ lang }) => {
  const { toggle } = useTheme();
  return (
    <>
      <button type="button" onClick={toggle}>toggle-theme</button>
      <GuidedTourPage lang={lang} />
    </>
  );
};

const renderTourWithThemeToggle = (lang: 'zh' | 'en' = 'zh') =>
  render(
    <ThemeProvider>
      <ThemeToggleHarness lang={lang} />
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

  it('切換主題不應讓情境敘事區（Story/Eyebrow/Beat）的 DOM node 整棵被卸載重建（PR D，避免 inline component 每次 render 重新定義）', () => {
    renderTourWithThemeToggle();
    fireEvent.click(screen.getByRole('button', { name: /開始導覽/ }));
    // 「情境一 · 監控總覽」是 Story 內 Eyebrow 渲染的 kicker，非右側 mock 面板（後者本就會隨 stage() 重繪，不是本測要鎖的對象）。
    const beforeNode = screen.getByText('情境一 · 監控總覽');
    fireEvent.click(screen.getByRole('button', { name: 'toggle-theme' }));
    const afterNode = screen.getByText('情境一 · 監控總覽');
    expect(afterNode).toBe(beforeNode);
  });
});

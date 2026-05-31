/**
 * PageHeader 頁面標題列的 render 測試（5 頁共用）。
 *
 * 契約（見 PageHeader.tsx）：title 永遠以 <h1> 顯示；sub / breadcrumb / actions 皆選填
 * （給才各自 render 一個 <div>）。
 * 測試策略同 Btn.test.tsx；PageHeader 用 useTheme，故包 ThemeProvider。
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { PageHeader } from '../PageHeader';
import { ThemeProvider } from '../../../theme/ThemeProvider';

afterEach(cleanup);

function renderHeader(ui: React.ReactElement): HTMLElement {
  const { container } = render(<ThemeProvider>{ui}</ThemeProvider>);
  return container;
}

describe('PageHeader', () => {
  it('title 永遠以 <h1> render', () => {
    renderHeader(<PageHeader title="成本總覽" />);
    const h1 = screen.getByText('成本總覽');
    expect(h1.tagName).toBe('H1');
  });

  it('title 支援 ReactNode（非字串）：仍包在 <h1> 內', () => {
    renderHeader(<PageHeader title={<span data-testid="title-node">複合標題</span>} />);
    const node = screen.getByTestId('title-node');
    expect(node.textContent).toBe('複合標題');
    expect(node.closest('h1')).not.toBeNull();
  });

  it('給 sub 時顯示副標文字', () => {
    renderHeader(<PageHeader title="X" sub="2026 年度" />);
    expect(screen.getByText('2026 年度').textContent).toBe('2026 年度');
  });

  it('未給 sub 時不顯示副標（queryByText 為 null）', () => {
    renderHeader(<PageHeader title="X" />);
    expect(screen.queryByText('2026 年度')).toBeNull();
  });

  it('給 breadcrumb 時顯示麵包屑文字', () => {
    renderHeader(<PageHeader title="X" breadcrumb="首頁 / 成本" />);
    expect(screen.getByText('首頁 / 成本').textContent).toBe('首頁 / 成本');
  });

  it('未給 breadcrumb 時不顯示麵包屑（queryByText 為 null）', () => {
    renderHeader(<PageHeader title="X" />);
    expect(screen.queryByText('首頁 / 成本')).toBeNull();
  });

  it('給 actions 時 render 自訂節點', () => {
    renderHeader(<PageHeader title="X" actions={<button>匯出</button>} />);
    expect(screen.getByText('匯出').textContent).toBe('匯出');
  });

  it('未給 actions 時不 render 任何 button', () => {
    const container = renderHeader(<PageHeader title="X" />);
    expect(container.querySelector('button')).toBeNull();
  });
});

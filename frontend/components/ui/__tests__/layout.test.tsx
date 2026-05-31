/**
 * 版面原件 render 測試：Stat / Card / PageHeader。
 *
 * 這三個是 KPI 卡、面板容器、頁首的共用骨架，遍佈 5 頁。守護重點是「可選 prop 在
 * 缺省時不該渲染多餘節點、在帶入時要出現在 DOM」，以及 Card 的 onClick 行為。
 * 同樣只驗 DOM 結構 / 文字 / 互動，不綁 theme 配色。
 */

import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithTheme } from '../../../test/renderWithTheme';
import { Stat } from '../Stat';
import { Card } from '../Card';
import { PageHeader } from '../PageHeader';

describe('Stat', () => {
  it('render label / value', () => {
    renderWithTheme(<Stat label="總發電量" value="3.55" />);
    expect(screen.getByText('總發電量')).toBeInTheDocument();
    expect(screen.getByText('3.55')).toBeInTheDocument();
  });

  it('帶 unit / hint 時顯示；缺省時不顯示', () => {
    const { rerender } = renderWithTheme(<Stat label="L" value="1" />);
    expect(screen.queryByText('MW')).not.toBeInTheDocument();
    expect(screen.queryByText('較昨日 +2%')).not.toBeInTheDocument();
    rerender(<Stat label="L" value="1" unit="MW" hint="較昨日 +2%" />);
    expect(screen.getByText('MW')).toBeInTheDocument();
    expect(screen.getByText('較昨日 +2%')).toBeInTheDocument();
  });
});

describe('Card', () => {
  it('render children', () => {
    renderWithTheme(
      <Card>
        <span>面板內容</span>
      </Card>,
    );
    expect(screen.getByText('面板內容')).toBeInTheDocument();
  });

  it('帶 onClick 時點擊觸發', () => {
    const onClick = vi.fn();
    renderWithTheme(<Card onClick={onClick}>可點卡片</Card>);
    fireEvent.click(screen.getByText('可點卡片'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('className 透傳（外部 layout 掛 class 用）', () => {
    renderWithTheme(<Card className="grid-cell">x</Card>);
    expect(screen.getByText('x')).toHaveClass('grid-cell');
  });
});

describe('PageHeader', () => {
  it('title 渲染為 <h1>', () => {
    renderWithTheme(<PageHeader title="成本分析" />);
    const h1 = screen.getByRole('heading', { level: 1, name: '成本分析' });
    expect(h1).toBeInTheDocument();
    expect(h1.tagName).toBe('H1');
  });

  it('sub / breadcrumb / actions 帶入時顯示；缺省時不顯示', () => {
    const { rerender } = renderWithTheme(<PageHeader title="T" />);
    expect(screen.queryByText('副標題')).not.toBeInTheDocument();
    expect(screen.queryByText('首頁 / 成本')).not.toBeInTheDocument();
    expect(screen.queryByText('匯出')).not.toBeInTheDocument();
    rerender(
      <PageHeader
        title="T"
        sub="副標題"
        breadcrumb="首頁 / 成本"
        actions={<button>匯出</button>}
      />,
    );
    expect(screen.getByText('副標題')).toBeInTheDocument();
    expect(screen.getByText('首頁 / 成本')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯出' })).toBeInTheDocument();
  });
});

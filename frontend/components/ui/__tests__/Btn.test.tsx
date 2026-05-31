/**
 * Btn component render 測試 —— 本 repo 第一批真 DOM render 測試之一。
 *
 * Btn 是全 app 共用的按鈕原件（dispatch / approve / 切 dataset / 表單送出都用它），
 * 互動正確性（onClick 觸發、disabled / loading 擋點擊）與無障礙屬性（aria-label /
 * aria-pressed / type）是回歸守護重點。本檔只驗「行為 + 語意 DOM」，不綁 theme 配色
 * （inline style hex 會隨主題改動而脆），以維持低脆弱度。
 */

import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithTheme } from '../../../test/renderWithTheme';
import { Btn } from '../Btn';

describe('Btn', () => {
  it('render children 並產生 <button>', () => {
    renderWithTheme(<Btn>派工</Btn>);
    const btn = screen.getByRole('button', { name: '派工' });
    expect(btn).toBeInTheDocument();
    expect(btn.tagName).toBe('BUTTON');
  });

  it('type 預設 button；可指定 submit', () => {
    const { rerender } = renderWithTheme(<Btn>送出</Btn>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
    rerender(<Btn type="submit">送出</Btn>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });

  it('點擊觸發 onClick', () => {
    const onClick = vi.fn();
    renderWithTheme(<Btn onClick={onClick}>確認</Btn>);
    fireEvent.click(screen.getByRole('button', { name: '確認' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('disabled 時按鈕 disabled 且不觸發 onClick', () => {
    const onClick = vi.fn();
    renderWithTheme(
      <Btn onClick={onClick} disabled>
        確認
      </Btn>,
    );
    const btn = screen.getByRole('button', { name: '確認' });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('loading 時同樣 disabled（isDisabled = disabled || loading）且不觸發 onClick', () => {
    const onClick = vi.fn();
    renderWithTheme(
      <Btn onClick={onClick} loading>
        確認
      </Btn>,
    );
    const btn = screen.getByRole('button', { name: '確認' });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('loading 時仍顯示 children 文字（目前無 spinner，只靠 opacity；若日後加 spinner 此 test 需更新）', () => {
    // 文件化現況：loading 不會隱藏或替換 children，使用者仍看得到按鈕文案。
    renderWithTheme(<Btn loading>派工中</Btn>);
    expect(screen.getByRole('button', { name: '派工中' })).toBeInTheDocument();
  });

  it('ariaLabel 透傳到 aria-label（無障礙：呼叫端為 icon-only 按鈕傳）', () => {
    renderWithTheme(<Btn ariaLabel="關閉對話框">✕</Btn>);
    // 用 accessible name 取得，證明 aria-label 真的掛上去
    expect(screen.getByRole('button', { name: '關閉對話框' })).toBeInTheDocument();
  });

  it('ariaPressed 透傳到 aria-pressed（toggle 按鈕語意）', () => {
    const { rerender } = renderWithTheme(
      <Btn ariaPressed={false} ariaLabel="切換">
        切
      </Btn>,
    );
    expect(screen.getByRole('button', { name: '切換' })).toHaveAttribute('aria-pressed', 'false');
    rerender(
      <Btn ariaPressed ariaLabel="切換">
        切
      </Btn>,
    );
    expect(screen.getByRole('button', { name: '切換' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('title 透傳到 title 屬性', () => {
    renderWithTheme(
      <Btn title="說明文字" ariaLabel="b">
        b
      </Btn>,
    );
    expect(screen.getByRole('button', { name: 'b' })).toHaveAttribute('title', '說明文字');
  });
});

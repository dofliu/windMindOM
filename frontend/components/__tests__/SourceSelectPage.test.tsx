/**
 * SourceSelectPage render 測試（WMOM-20260719-04, DEC-20260719-01 #3）。
 *
 * 登入後的「選擇資料來源」全屏頁：四張卡（實接 / 即時模擬 / 產生情境 / 調閱過去情境），
 * 點卡回呼 `onSelect(cardId)`。守住：四卡渲染、回呼帶正確 id、語系、忙碌禁用。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import SourceSelectPage, { type SourceCardId, type SelectOutcome } from '../SourceSelectPage';
import { ThemeProvider } from '../../theme/ThemeProvider';

type OnSelect = (id: SourceCardId) => void | SelectOutcome | Promise<void | SelectOutcome>;

function renderPage(onSelect: OnSelect, lang: 'en' | 'zh' = 'zh') {
  return render(
    <ThemeProvider>
      <SourceSelectPage lang={lang} onSelect={onSelect} onToggleLang={() => {}} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('SourceSelectPage', () => {
  it('渲染標題與四張來源卡', () => {
    renderPage(vi.fn());
    expect(screen.getByText('選擇資料來源')).toBeInTheDocument();
    expect(screen.getByText('實際資料對接')).toBeInTheDocument();
    expect(screen.getByText('即時模擬')).toBeInTheDocument();
    expect(screen.getByText('產生新情境')).toBeInTheDocument();
    expect(screen.getByText('調閱過去情境')).toBeInTheDocument();
  });

  it('點「調閱過去情境」→ onSelect("observe")', async () => {
    const onSelect = vi.fn();
    renderPage(onSelect);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '選擇：調閱過去情境' }));
    });
    expect(onSelect).toHaveBeenCalledWith('observe');
  });

  it('點「實際資料對接」→ onSelect("live")；點「產生新情境」→ onSelect("scenario")', async () => {
    const onSelect = vi.fn();
    renderPage(onSelect);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '選擇：實際資料對接' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '選擇：產生新情境' }));
    });
    expect(onSelect).toHaveBeenNthCalledWith(1, 'live');
    expect(onSelect).toHaveBeenNthCalledWith(2, 'scenario');
  });

  it('lang=en 標題 = Choose a data source', () => {
    renderPage(vi.fn(), 'en');
    expect(screen.getByText('Choose a data source')).toBeInTheDocument();
  });

  it('onSelect 回 {ok:false, status:403} → 顯示需主管權限（不靜默）', async () => {
    const onSelect = vi.fn(() => Promise.resolve({ ok: false, status: 403 }));
    renderPage(onSelect);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '選擇：實際資料對接' }));
    });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/主管以上權限/));
  });

  it('選擇進行中其他卡禁用（避免重複啟動）', async () => {
    // onSelect 卡住（pending promise）→ busy 狀態應禁用所有選擇鈕。
    let resolve!: () => void;
    const onSelect = vi.fn(() => new Promise<void>(r => (resolve = r)));
    renderPage(onSelect);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '選擇：即時模擬' }));
    });
    expect(screen.getByRole('button', { name: '選擇：實際資料對接' })).toBeDisabled();
    await act(async () => {
      resolve();
    });
  });
});

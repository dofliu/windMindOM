/**
 * ScenarioMountBanner component render 測試（WMOM-20260926-05，EPIC-M5 測試覆蓋擴大）。
 *
 * `ScenarioMountBanner`（PR C Phase 1，`WMOM-20260926-03` 新增）先前完全零 component 測試。
 * 與其餘 `components/ui/*.tsx` 純展示 primitive 不同，本元件有真正的條件邏輯（`error` 是否
 * 存在決定 `Card` tone/是否顯示錯誤說明、`loading && !error` 短路、lang 切換兩組文案），且
 * `FarmOverview.tsx`/`TurbineDetail.tsx` 既有測試只驗證「情境掛載時顯示 banner」的 happy
 * path，從未餵過 `loading`/`error` props，這兩條分支先前完全無測試涵蓋。
 *
 * 比照 `StatusPill.test.tsx` 的 `hexToRgb` 手法斷言 inline style 顏色（jsdom 會把 hex
 * 正規化成 `rgb(r, g, b)`）。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';
import { ScenarioMountBanner } from '../ScenarioMountBanner';
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

function renderBanner(props: Partial<React.ComponentProps<typeof ScenarioMountBanner>> = {}) {
  const onExit = vi.fn();
  const utils = render(
    <ThemeProvider>
      <ScenarioMountBanner scenarioName="測試情境A" onExit={onExit} {...props} />
    </ThemeProvider>,
  );
  return { ...utils, onExit };
}

describe('ScenarioMountBanner — 基本顯示', () => {
  it('role=status 容器帶 aria-label（zh 預設，含情境名稱）', () => {
    const { getByRole } = renderBanner();
    expect(getByRole('status')).toHaveAttribute('aria-label', '情境檢視中: 測試情境A');
  });

  it('顯示情境名稱（strong）與唯讀說明', () => {
    const { getByText } = renderBanner();
    expect(getByText('測試情境A').tagName).toBe('STRONG');
    expect(getByText('(唯讀)')).toBeInTheDocument();
  });
});

describe('ScenarioMountBanner — lang 切換', () => {
  it('lang=en 時 aria-label / 唯讀說明 / 退出按鈕皆改用英文', () => {
    const { getByRole, getByText, queryByText } = renderBanner({ lang: 'en' });
    expect(getByRole('status')).toHaveAttribute('aria-label', 'Scenario view: 測試情境A');
    expect(getByText('(read-only)')).toBeInTheDocument();
    expect(
      getByRole('button', { name: 'Exit scenario view, back to live data' }),
    ).toBeInTheDocument();
    expect(queryByText('(唯讀)')).not.toBeInTheDocument();
  });

  it('lang=zh（預設）退出按鈕 aria-label 為中文', () => {
    const { getByRole } = renderBanner();
    expect(getByRole('button', { name: '結束情境檢視，返回即時資料' })).toBeInTheDocument();
  });
});

describe('ScenarioMountBanner — loading 分支', () => {
  it('loading=true 且無 error 時顯示 Loading 文案（zh）', () => {
    const { getByText } = renderBanner({ loading: true });
    expect(getByText('載入中…')).toBeInTheDocument();
  });

  it('loading=true 且無 error 時顯示 Loading 文案（en）', () => {
    const { getByText } = renderBanner({ loading: true, lang: 'en' });
    expect(getByText('Loading…')).toBeInTheDocument();
  });

  it('loading=false（預設）不顯示 Loading 文案', () => {
    const { queryByText } = renderBanner();
    expect(queryByText('載入中…')).not.toBeInTheDocument();
  });

  it('loading=true 但同時有 error 時不顯示 Loading 文案（error 優先）', () => {
    const { queryByText } = renderBanner({ loading: true, error: '找不到情境' });
    expect(queryByText('載入中…')).not.toBeInTheDocument();
  });
});

describe('ScenarioMountBanner — error 分支', () => {
  it('error=null（預設）時 Card tone 為 accent，無 alert 區塊', () => {
    const { container, queryByRole } = renderBanner();
    const cardDiv = container.querySelector('[role="status"] > div') as HTMLElement;
    const style = cardDiv.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.accentSoft));
    expect(style).toContain(hexToRgb(C.accent));
    expect(queryByRole('alert')).not.toBeInTheDocument();
  });

  it('error 為空字串（falsy 但非 null）時視同無 error：tone 仍為 accent、無 alert 區塊', () => {
    // 已知/接受的行為：元件 `error ? 'warn' : 'accent'` 與 `{error && (...)}` 皆把空字串當
    // falsy 處理，等同 null。若上游把「有錯誤但訊息未帶回」表示成 `error: ''` 而非 `null`，
    // 會靜默退回無錯誤 UI——此測試明確鎖住這個既有行為，而非遺漏。
    const { container, queryByRole } = renderBanner({ error: '' });
    const cardDiv = container.querySelector('[role="status"] > div') as HTMLElement;
    const style = cardDiv.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.accentSoft));
    expect(queryByRole('alert')).not.toBeInTheDocument();
  });

  it('error 非 null 時 Card tone 變成 warn', () => {
    const { container } = renderBanner({ error: '網路錯誤' });
    const cardDiv = container.querySelector('[role="status"] > div') as HTMLElement;
    const style = cardDiv.getAttribute('style') ?? '';
    expect(style).toContain(hexToRgb(C.warnSoft));
    expect(style).toContain(hexToRgb(C.warn));
  });

  it('error 非 null 時渲染 role=alert 錯誤說明（zh）', () => {
    const { getByRole } = renderBanner({ error: '網路錯誤' });
    expect(getByRole('alert')).toHaveTextContent(
      '載入這個情境失敗（可能已被刪除，或發生網路錯誤）。下方顯示的數字可能是空的或過期。',
    );
  });

  it('error 非 null 時渲染 role=alert 錯誤說明（en）', () => {
    const { getByRole } = renderBanner({ error: '網路錯誤', lang: 'en' });
    expect(getByRole('alert')).toHaveTextContent(
      'Failed to load this scenario (it may have been deleted, or a network error occurred). ' +
        'The numbers shown below may be empty or stale.',
    );
  });
});

describe('ScenarioMountBanner — onExit 接線', () => {
  it('點擊退出按鈕（zh）觸發 onExit', () => {
    const { getByRole, onExit } = renderBanner();
    fireEvent.click(getByRole('button', { name: '結束情境檢視，返回即時資料' }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });

  it('點擊退出按鈕（en）觸發 onExit', () => {
    const { getByRole, onExit } = renderBanner({ lang: 'en' });
    fireEvent.click(getByRole('button', { name: 'Exit scenario view, back to live data' }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });

  it('有 error 時點擊退出按鈕仍觸發 onExit', () => {
    const { getByRole, onExit } = renderBanner({ error: '找不到情境' });
    fireEvent.click(getByRole('button', { name: '結束情境檢視，返回即時資料' }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});

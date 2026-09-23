/**
 * `Sidebar.tsx` component 測試（WMOM-20260923-05，EPIC-M5 測試覆蓋擴大）。
 *
 * 全站唯一主導覽入口，先前完全零 `__tests__`。涵蓋：primary/secondary 導覽項目渲染
 * （active 樣式、badge 顯示條件）、mobile drawer（依 `window.innerWidth` 切換
 * fixed/sticky + transform + 點擊遮罩關閉）、backend 健康狀態 dot、lang/theme 切換按鈕。
 *
 * `window.innerWidth` 在元件內是 render 時讀取的一次性判定（非 resize listener），
 * 故測試只需在 render 前用 `Object.defineProperty` 設定值即可，不需模擬 resize 事件；
 * 每個測試後還原成 jsdom 預設值（1024）避免同檔案內測試互相汙染。
 *
 * 本檔是本 repo 第一支實際呼叫 `ThemeProvider.toggle()` 的測試（`StatusPill.test.tsx`/
 * `Charts.test.tsx` 都沒動過 theme mode）：`toggle()` 會把 mode 寫進真實
 * `localStorage['wmom.theme']`，vitest 預設 `isolate: true` 只做 per-file 隔離，
 * 同檔案內後續測試的新 `ThemeProvider` 會讀到已寫入的值——故 `afterEach` 額外清除
 * `localStorage`，避免主題切換測試「污染」同檔案內排在它之後的其他測試。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';
import { Sidebar, type NavItem } from '../Sidebar';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { palettes } from '../../../theme/themes';

afterEach(() => {
  cleanup();
  setInnerWidth(1024);
  localStorage.clear();
});

const C = palettes.light;

/** jsdom 會把 inline style 的 hex 正規化成 `rgb(r, g, b)`，比對前需先轉換。 */
function hexToRgb(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}

function setInnerWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: width });
}

const primary: NavItem[] = [
  { id: 'overview', iconId: 'overview', labelEn: 'Overview', labelZh: '總覽' },
  { id: 'turbine', iconId: 'turbine', labelEn: 'Turbines', labelZh: '風機' },
];

const secondaryWithBadge: NavItem[] = [
  { id: 'faults', iconId: 'faults', labelEn: 'Faults', labelZh: '故障', badge: 3 },
  { id: 'settings', iconId: 'settings', labelEn: 'Settings', labelZh: '設定' },
];

function renderSidebar(props: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const onSelect = props.onSelect ?? vi.fn();
  const onToggleLang = props.onToggleLang ?? vi.fn();
  return render(
    <ThemeProvider>
      <Sidebar
        primary={primary}
        secondary={secondaryWithBadge}
        activeId="overview"
        onSelect={onSelect}
        lang="zh"
        onToggleLang={onToggleLang}
        backendHealthy
        {...props}
      />
    </ThemeProvider>,
  );
}

describe('Sidebar — primary/secondary 導覽項目', () => {
  it('渲染 primary + secondary 項目文字（預設 lang=zh）', () => {
    const { getByText } = renderSidebar();
    expect(getByText('總覽')).toBeInTheDocument();
    expect(getByText('風機')).toBeInTheDocument();
    expect(getByText('故障')).toBeInTheDocument();
    expect(getByText('設定')).toBeInTheDocument();
  });

  it('lang=en 時顯示英文 label', () => {
    const { getByText, queryByText } = renderSidebar({ lang: 'en' });
    expect(getByText('Overview')).toBeInTheDocument();
    expect(queryByText('總覽')).not.toBeInTheDocument();
  });

  it('secondary 為空陣列時不顯示「工具」標題與任何 secondary 項目', () => {
    const { queryByText } = renderSidebar({ secondary: [] });
    expect(queryByText('工具')).not.toBeInTheDocument();
    expect(queryByText('設定')).not.toBeInTheDocument();
  });

  it('activeId 對應項目有 aria-current=page，其餘沒有', () => {
    const { getByLabelText } = renderSidebar({ activeId: 'turbine' });
    expect(getByLabelText('風機')).toHaveAttribute('aria-current', 'page');
    expect(getByLabelText('總覽')).not.toHaveAttribute('aria-current');
  });

  it('active 項目套用 accent 顏色與 accentSoft 背景，非 active 項目維持一般樣式', () => {
    const { getByLabelText } = renderSidebar({ activeId: 'turbine' });
    const activeStyle = getByLabelText('風機').getAttribute('style') ?? '';
    const inactiveStyle = getByLabelText('總覽').getAttribute('style') ?? '';
    expect(activeStyle).toContain(hexToRgb(C.accentSoft));
    expect(activeStyle).toContain(hexToRgb(C.accent));
    expect(inactiveStyle).not.toContain(hexToRgb(C.accentSoft));
  });

  it('badge > 0 才顯示數字，其餘項目不顯示 badge', () => {
    const { getByText, queryByText } = renderSidebar();
    expect(getByText('3')).toBeInTheDocument();
    // '設定'（settings）沒有 badge，不應渲染出額外的數字節點
    expect(queryByText('0')).not.toBeInTheDocument();
  });

  it('badge=0 視為 falsy，不顯示', () => {
    const { queryByText } = renderSidebar({
      secondary: [{ id: 'x', iconId: 'settings', labelEn: 'X', labelZh: 'X', badge: 0 }],
    });
    expect(queryByText('0')).not.toBeInTheDocument();
  });

  it('點擊項目呼叫 onSelect 並帶正確 id（desktop 下未傳 onMobileClose 不會炸）', () => {
    const onSelect = vi.fn();
    const { getByLabelText } = renderSidebar({ onSelect, onMobileClose: undefined });
    fireEvent.click(getByLabelText('風機'));
    expect(onSelect).toHaveBeenCalledWith('turbine');
  });

  it('點擊項目同時呼叫 onMobileClose', () => {
    const onSelect = vi.fn();
    const onMobileClose = vi.fn();
    const { getByLabelText } = renderSidebar({ onSelect, onMobileClose });
    fireEvent.click(getByLabelText('故障'));
    expect(onSelect).toHaveBeenCalledWith('faults');
    expect(onMobileClose).toHaveBeenCalledTimes(1);
  });
});

describe('Sidebar — backend 健康狀態', () => {
  it('backendHealthy=true 顯示「後端正常」與 ok 色 dot', () => {
    // Sidebar 裡有兩個 aria-hidden span（health dot + theme 按鈕圖示），故從文字所在的
    // row 往下找 dot，而非對整個 container 用可能命中錯誤節點的全域 selector。
    const { getByText } = renderSidebar({ backendHealthy: true });
    const row = getByText('後端正常');
    const dot = row.querySelector('span[aria-hidden]');
    expect(dot?.getAttribute('style') ?? '').toContain(hexToRgb(C.ok));
  });

  it('backendHealthy=false 顯示「後端離線」與 warn 色 dot', () => {
    const { getByText } = renderSidebar({ backendHealthy: false });
    const row = getByText('後端離線');
    const dot = row.querySelector('span[aria-hidden]');
    expect(dot?.getAttribute('style') ?? '').toContain(hexToRgb(C.warn));
  });

  it('lang=en 時健康狀態文字改英文', () => {
    const { getByText } = renderSidebar({ lang: 'en', backendHealthy: false });
    expect(getByText('Backend offline')).toBeInTheDocument();
  });
});

describe('Sidebar — lang/theme 切換按鈕', () => {
  it('lang=zh 時語言按鈕顯示 EN，點擊呼叫 onToggleLang', () => {
    const onToggleLang = vi.fn();
    const { getByText } = renderSidebar({ lang: 'zh', onToggleLang });
    const btn = getByText('EN');
    fireEvent.click(btn);
    expect(onToggleLang).toHaveBeenCalledTimes(1);
  });

  it('lang=en 時語言按鈕顯示 中文', () => {
    const { getByText } = renderSidebar({ lang: 'en' });
    expect(getByText('中文')).toBeInTheDocument();
  });

  it('預設 light mode：主題按鈕顯示「夜」+ ☾ + aria-pressed=false，點擊後切到 dark 顯示「日」+ ☀ + aria-pressed=true', () => {
    const { getByLabelText, getByText } = renderSidebar();
    const btn = getByLabelText('切換主題');
    expect(btn).toHaveAttribute('aria-pressed', 'false');
    expect(getByText('夜')).toBeInTheDocument();
    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(getByText('日')).toBeInTheDocument();
  });
});

describe('Sidebar — footerExtra', () => {
  it('未傳 footerExtra 時不渲染額外節點', () => {
    const { queryByText } = renderSidebar();
    expect(queryByText('FARM-X')).not.toBeInTheDocument();
  });

  it('傳入 footerExtra 時渲染在 footer 區塊內', () => {
    const { getByText } = renderSidebar({ footerExtra: <div>FARM-X</div> });
    expect(getByText('FARM-X')).toBeInTheDocument();
  });
});

describe('Sidebar — mobile drawer（window.innerWidth < 768）', () => {
  it('mobileOpen=false 時 transform 收起（translateX(-100%)）、position fixed', () => {
    setInnerWidth(500);
    const { getByLabelText } = renderSidebar({ mobileOpen: false });
    const style = getByLabelText('主選單').getAttribute('style') ?? '';
    expect(style).toContain('translateX(-100%)');
    expect(style).toContain('position: fixed');
  });

  it('mobileOpen=true 時 transform 展開（translateX(0)）並渲染遮罩', () => {
    setInnerWidth(500);
    const { getByLabelText, container } = renderSidebar({ mobileOpen: true });
    const style = getByLabelText('主選單').getAttribute('style') ?? '';
    expect(style).toContain('translateX(0)');
    expect(container.querySelector('[role="presentation"]')).toBeInTheDocument();
  });

  it('mobileOpen=false 時不渲染遮罩', () => {
    setInnerWidth(500);
    const { container } = renderSidebar({ mobileOpen: false });
    expect(container.querySelector('[role="presentation"]')).not.toBeInTheDocument();
  });

  it('點擊遮罩呼叫 onMobileClose', () => {
    setInnerWidth(500);
    const onMobileClose = vi.fn();
    const { container } = renderSidebar({ mobileOpen: true, onMobileClose });
    const overlay = container.querySelector('[role="presentation"]');
    expect(overlay).not.toBeNull();
    fireEvent.click(overlay as Element);
    expect(onMobileClose).toHaveBeenCalledTimes(1);
  });
});

describe('Sidebar — desktop（window.innerWidth >= 768）', () => {
  it('desktop 下 position 為 sticky，transform 恆為 translateX(0)，即使 mobileOpen=true 也不受影響', () => {
    setInnerWidth(1024);
    const { getByLabelText } = renderSidebar({ mobileOpen: true });
    const style = getByLabelText('主選單').getAttribute('style') ?? '';
    expect(style).toContain('position: sticky');
    expect(style).toContain('translateX(0)');
  });

  it('desktop 下即使 mobileOpen=true 也不渲染遮罩（因 showAsDrawer=false）', () => {
    setInnerWidth(1024);
    const { container } = renderSidebar({ mobileOpen: true });
    expect(container.querySelector('[role="presentation"]')).not.toBeInTheDocument();
  });
});

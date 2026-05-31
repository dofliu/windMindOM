/**
 * Btn 共用按鈕的 render 測試（windMindOM 前端第一批 component render 測試之一）。
 *
 * 測試策略：
 * - 用 @testing-library/react + jsdom；刻意不引入 @testing-library/jest-dom，改用原生
 *   DOM 斷言，避免新增 devDependency。
 * - Btn 透過 useTheme() 取色，而 useTheme 不在 <ThemeProvider> 內會 throw，故所有 render
 *   都用 renderBtn() 包一層 ThemeProvider。預設 mode = 'light'（localStorage 空 →
 *   readInitial 回 'light'），因此 inline style 的色值對應 palettes.light。
 * - 顏色斷言以 palettes.light 來源色經 hexToRgb() 轉換後比對 —— jsdom CSSOM 會把 inline
 *   style 的 hex 正規化為 `rgb(r, g, b)`（已實測：'#FFFFFF' → 'rgb(255, 255, 255)'），
 *   故不能直接比 hex。透過 hexToRgb(LIGHT.xxx) 鎖定「variant → theme token」對映，
 *   色值改動會自動跟著走，不寫死 magic rgb 字串。
 * - border 用 `1px solid <color>` 的 shorthand 設定；jsdom 同樣把其中的 hex 正規化成 rgb，
 *   故以 `1px solid ${hexToRgb(...)}` 整段比對。
 *
 * 不測：dark mode 切換（屬 ThemeProvider 行為，非 Btn 職責）。
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { Btn } from '../Btn';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { palettes } from '../../../theme/themes';

afterEach(cleanup);

const LIGHT = palettes.light;

/**
 * 把 6 碼 hex（#RRGGBB）轉成 jsdom inline style 正規化後的 `rgb(r, g, b)` 字串。
 * 僅支援 #RRGGBB（本元件 theme 色值皆為此格式），不處理 3 碼縮寫或 alpha。
 */
function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff})`;
}

/** light palette 中文字疊在實心按鈕上的白色，jsdom 正規化後的 rgb。 */
const WHITE_RGB = 'rgb(255, 255, 255)';

/** 包 ThemeProvider 後 render，回傳唯一的 <button> 根節點。 */
function renderBtn(ui: React.ReactElement): HTMLButtonElement {
  const { container } = render(<ThemeProvider>{ui}</ThemeProvider>);
  const btn = container.querySelector('button');
  if (btn === null) throw new Error('Btn 未 render 出 <button>');
  return btn;
}

describe('Btn', () => {
  it('render children 並產生 <button>（type 預設 button）', () => {
    const btn = renderBtn(<Btn>送出</Btn>);
    expect(btn.tagName).toBe('BUTTON');
    expect(btn.getAttribute('type')).toBe('button');
    // children 文字直接落在 button 內
    expect(screen.getByText('送出')).toBe(btn);
  });

  it('預設 variant=secondary：背景=panel、文字=text、框線含 border 色', () => {
    const btn = renderBtn(<Btn>X</Btn>);
    expect(btn.style.background).toBe(hexToRgb(LIGHT.panel));
    expect(btn.style.color).toBe(hexToRgb(LIGHT.text));
    expect(btn.style.border).toBe(`1px solid ${hexToRgb(LIGHT.border)}`);
  });

  it('variant=primary：背景=accent、文字=accentInk、框線含 accent', () => {
    // 註：light palette 的 accentInk 恰為 '#FFFFFF'，與 danger/warn 的字面白撞值；
    //     此處鎖定的是「primary 走 accentInk token」，token 值若改動會自動跟著走。
    const btn = renderBtn(<Btn variant="primary">X</Btn>);
    expect(btn.style.background).toBe(hexToRgb(LIGHT.accent));
    expect(btn.style.color).toBe(hexToRgb(LIGHT.accentInk));
    expect(btn.style.border).toBe(`1px solid ${hexToRgb(LIGHT.accent)}`);
  });

  it('variant=ghost：背景透明、文字=sub、框線含 border', () => {
    const btn = renderBtn(<Btn variant="ghost">X</Btn>);
    // 'transparent' 不是 hex，jsdom 不轉換，直接比對
    expect(btn.style.background).toBe('transparent');
    expect(btn.style.color).toBe(hexToRgb(LIGHT.sub));
    expect(btn.style.border).toBe(`1px solid ${hexToRgb(LIGHT.border)}`);
  });

  it('variant=danger：背景=warn token、框線含 warn、light 模式文字=白色', () => {
    // danger variant 刻意使用 warn token（見 Btn.tsx palettes）
    const btn = renderBtn(<Btn variant="danger">X</Btn>);
    expect(btn.style.background).toBe(hexToRgb(LIGHT.warn));
    expect(btn.style.color).toBe(WHITE_RGB);
    expect(btn.style.border).toBe(`1px solid ${hexToRgb(LIGHT.warn)}`);
  });

  it('variant=warn：背景=amber、框線含 amber、light 模式文字=白色', () => {
    const btn = renderBtn(<Btn variant="warn">X</Btn>);
    expect(btn.style.background).toBe(hexToRgb(LIGHT.amber));
    expect(btn.style.color).toBe(WHITE_RGB);
    expect(btn.style.border).toBe(`1px solid ${hexToRgb(LIGHT.amber)}`);
  });

  it('size=sm：padding 與 fontSize 套用小尺寸值', () => {
    const btn = renderBtn(<Btn size="sm">X</Btn>);
    expect(btn.style.padding).toBe('6px 10px');
    expect(btn.style.fontSize).toBe('12px');
  });

  it('fullWidth：button width 為 100%', () => {
    const btn = renderBtn(<Btn fullWidth>X</Btn>);
    expect(btn.style.width).toBe('100%');
  });

  it('透傳 onClick：點擊觸發 handler', () => {
    const onClick = vi.fn();
    const btn = renderBtn(<Btn onClick={onClick}>X</Btn>);
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('disabled：button.disabled=true、style 反映不可用、點擊不觸發 handler', () => {
    const onClick = vi.fn();
    const btn = renderBtn(
      <Btn onClick={onClick} disabled>
        X
      </Btn>,
    );
    expect(btn.disabled).toBe(true);
    expect(btn.style.cursor).toBe('not-allowed');
    expect(btn.style.opacity).toBe('0.5');
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('loading 也視為 disabled（isDisabled = disabled || loading）', () => {
    const onClick = vi.fn();
    const btn = renderBtn(
      <Btn onClick={onClick} loading>
        X
      </Btn>,
    );
    expect(btn.disabled).toBe(true);
    expect(btn.style.opacity).toBe('0.5');
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('透傳 type=submit 與 ariaLabel', () => {
    const btn = renderBtn(
      <Btn type="submit" ariaLabel="提交表單">
        X
      </Btn>,
    );
    expect(btn.getAttribute('type')).toBe('submit');
    expect(btn.getAttribute('aria-label')).toBe('提交表單');
  });

  it('自訂 style 會 merge 進 inline style 並覆蓋同名 base 屬性', () => {
    // base borderRadius=8；自訂改成 2 應勝出（...style 在最後）
    const btn = renderBtn(<Btn style={{ borderRadius: 2, marginTop: 4 }}>X</Btn>);
    expect(btn.style.borderRadius).toBe('2px');
    expect(btn.style.marginTop).toBe('4px');
  });
});

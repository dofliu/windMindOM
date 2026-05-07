/**
 * ThemeProvider — 提供 light/dark 雙主題的 React Context。
 *
 * 用法：
 *   <ThemeProvider>...</ThemeProvider>
 *   const { mode, setMode, toggle, C } = useTheme();
 *
 * - mode 寫進 localStorage（key = 'wmom.theme'）並同步到 <html data-theme>。
 * - C 是當前 palette 物件，所有元件用 C.accent / C.bg / ... 即可。
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { applyPaletteToRoot, palettes, type Palette, type ThemeMode } from './themes';

const STORAGE_KEY = 'wmom.theme';

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  toggle: () => void;
  C: Palette;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readInitial(): ThemeMode {
  if (typeof window === 'undefined') return 'light';
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  // 預設跟交接書一致：Light（鼠尾草綠）
  return 'light';
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(readInitial);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    try {
      localStorage.setItem(STORAGE_KEY, m);
    } catch {
      // localStorage 不可用就忽略；下次開頁回到 light
    }
  }, []);

  const toggle = useCallback(() => {
    setModeState(prev => {
      const next: ThemeMode = prev === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const C = palettes[mode];

  // 同步 <html data-theme> 與 CSS variable，方便 vendor 套件吃
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode);
    applyPaletteToRoot(C);
  }, [mode, C]);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, setMode, toggle, C }),
    [mode, setMode, toggle, C],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used inside <ThemeProvider>');
  }
  return ctx;
}

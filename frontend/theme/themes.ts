/**
 * windMindOM theme palette — A · Calm Operator (light) / Glass Cockpit (dark).
 * 改版後所有元件顏色一律走這份 palette，不可再硬寫 hex。
 */

export type ThemeMode = 'light' | 'dark';

export interface Palette {
  // Surfaces
  bg: string;
  panel: string;
  panelMuted: string; // 表頭、輸入框 fill
  border: string;

  // Text
  text: string;
  sub: string;
  faint: string;

  // Brand
  accent: string;
  accentSoft: string;
  accentInk: string; // 文字疊在 accent 按鈕上的顏色

  // Semantic
  ok: string;
  okSoft: string;
  warn: string;
  warnSoft: string;
  amber: string;       // IDLE / MED 偏向
  amberSoft: string;
  danger: string;
  dangerSoft: string;
  info: string;
  infoSoft: string;

  // Chart event colors（保留 hex，按交接書 §7 例外）
  chartFault: string;
  chartGrid: string;
  chartWind: string;
  chartOperator: string;
  chartState: string;

  isDark: boolean;
}

export const lightPalette: Palette = {
  bg: '#F5F2EA',
  panel: '#FFFFFF',
  panelMuted: '#FAF7EE',
  border: '#E5E0D2',
  text: '#1F2D24',
  sub: '#6B7669',
  faint: '#9BA39A',
  accent: '#3F6B53',
  accentSoft: '#E2EBE3',
  accentInk: '#FFFFFF',
  ok: '#5C8A5F',
  okSoft: '#DEEAD9',
  warn: '#C97B5A',
  warnSoft: '#FBE8DD',
  amber: '#B8A053',
  amberSoft: '#FAF3E0',
  danger: '#B25340',
  dangerSoft: '#F5DAD0',
  info: '#5A7A98',
  infoSoft: '#E0E8F0',
  chartFault: '#C97B5A',
  chartGrid: '#B8A053',
  chartWind: '#5A7A98',
  chartOperator: '#5C8A5F',
  chartState: '#8B7AB8',
  isDark: false,
};

export const darkPalette: Palette = {
  bg: '#0E1815',
  panel: '#152320',
  panelMuted: '#1A2A26',
  border: 'rgba(255,255,255,0.10)',
  text: '#E8F0EC',
  sub: '#8FA39A',
  faint: '#566860',
  accent: '#3DDC97',
  accentSoft: 'rgba(61,220,151,0.16)',
  accentInk: '#0A0F0E',
  ok: '#3DDC97',
  okSoft: 'rgba(61,220,151,0.16)',
  warn: '#FF8E72',
  warnSoft: 'rgba(255,142,114,0.18)',
  amber: '#FFB347',
  amberSoft: 'rgba(255,179,71,0.16)',
  danger: '#FF6B5C',
  dangerSoft: 'rgba(255,107,92,0.18)',
  info: '#7AB8E8',
  infoSoft: 'rgba(122,184,232,0.16)',
  chartFault: '#FF8E72',
  chartGrid: '#FFB347',
  chartWind: '#7AB8E8',
  chartOperator: '#3DDC97',
  chartState: '#B49DE8',
  isDark: true,
};

export const palettes: Record<ThemeMode, Palette> = {
  light: lightPalette,
  dark: darkPalette,
};

/** 把 palette 寫進 :root CSS variables，方便偶有第三方需要吃 var(--wmom-...) 用。 */
export function applyPaletteToRoot(p: Palette): void {
  const root = document.documentElement;
  root.style.setProperty('--wmom-bg', p.bg);
  root.style.setProperty('--wmom-panel', p.panel);
  root.style.setProperty('--wmom-panel-muted', p.panelMuted);
  root.style.setProperty('--wmom-border', p.border);
  root.style.setProperty('--wmom-text', p.text);
  root.style.setProperty('--wmom-sub', p.sub);
  root.style.setProperty('--wmom-faint', p.faint);
  root.style.setProperty('--wmom-accent', p.accent);
  root.style.setProperty('--wmom-accent-soft', p.accentSoft);
  root.style.setProperty('--wmom-accent-ink', p.accentInk);
  root.style.setProperty('--wmom-ok', p.ok);
  root.style.setProperty('--wmom-warn', p.warn);
  root.style.setProperty('--wmom-amber', p.amber);
  root.style.setProperty('--wmom-danger', p.danger);
}

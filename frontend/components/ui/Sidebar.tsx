/**
 * Sidebar — 220px 主導覽。
 *
 * 五個主頁面（overview / turbine / maintenance / cost / history）+ 兩個 secondary
 * （faults 帶未結 badge / settings）。底部：後端狀態 + EN/中 + ☀/☾。
 *
 * 響應式：≤ 768px 折成 hamburger（mobileOpen 控制）；header 由 App 提供。
 */

import React from 'react';
import { Logo, NavIcon, type NavIconId } from './Logo';
import { useTheme } from '../../theme/ThemeProvider';

export interface NavItem {
  id: string;
  iconId: NavIconId;
  labelEn: string;
  labelZh: string;
  /** 紅色 badge（>0 才顯示）。 */
  badge?: number;
}

interface SidebarProps {
  primary: NavItem[];
  secondary: NavItem[];
  activeId: string;
  onSelect: (id: string) => void;
  lang: 'en' | 'zh';
  onToggleLang: () => void;
  /** Backend 是否健康。 */
  backendHealthy: boolean;
  /** 行動裝置：是否打開（≤ 768px 才用得到）。 */
  mobileOpen?: boolean;
  /** 行動裝置：關閉 callback。 */
  onMobileClose?: () => void;
  /** 額外右側裝飾（farm selector 等）。 */
  footerExtra?: React.ReactNode;
}

const tr = (lang: 'en' | 'zh', en: string, zh: string) => (lang === 'zh' ? zh : en);

const NavButton: React.FC<{
  item: NavItem;
  active: boolean;
  onClick: () => void;
  lang: 'en' | 'zh';
}> = ({ item, active, onClick, lang }) => {
  const { C } = useTheme();
  return (
    <button
      onClick={onClick}
      aria-label={tr(lang, item.labelEn, item.labelZh)}
      aria-current={active ? 'page' : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        borderRadius: 8,
        border: 'none',
        textAlign: 'left',
        cursor: 'pointer',
        background: active ? C.accentSoft : 'transparent',
        color: active ? C.accent : C.text,
        fontWeight: active ? 600 : 500,
        fontSize: 14,
        fontFamily: 'inherit',
        position: 'relative',
        transition: 'background 160ms ease, color 160ms ease',
      }}
    >
      <NavIcon id={item.iconId} color={active ? C.accent : C.sub} />
      <span style={{ flex: 1 }}>{tr(lang, item.labelEn, item.labelZh)}</span>
      {item.badge && item.badge > 0 ? (
        <span
          style={{
            background: C.warn,
            color: C.isDark ? '#1A0A07' : '#FFFFFF',
            fontSize: 10,
            fontWeight: 700,
            padding: '1px 6px',
            borderRadius: 999,
            minWidth: 18,
            textAlign: 'center',
          }}
        >
          {item.badge}
        </span>
      ) : null}
    </button>
  );
};

export const Sidebar: React.FC<SidebarProps> = ({
  primary,
  secondary,
  activeId,
  onSelect,
  lang,
  onToggleLang,
  backendHealthy,
  mobileOpen,
  onMobileClose,
  footerExtra,
}) => {
  const { C, mode, toggle } = useTheme();
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  const showAsDrawer = isMobile;

  const sidebar = (
    <aside
      aria-label={tr(lang, 'Primary navigation', '主選單')}
      style={{
        width: 220,
        background: C.panel,
        borderRight: `1px solid ${C.border}`,
        padding: '24px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        flexShrink: 0,
        height: '100vh',
        position: showAsDrawer ? 'fixed' : 'sticky',
        top: 0,
        left: 0,
        zIndex: showAsDrawer ? 60 : 10,
        transform: showAsDrawer && !mobileOpen ? 'translateX(-100%)' : 'translateX(0)',
        transition: 'transform 220ms ease',
        overflowY: 'auto',
      }}
    >
      {/* Logo + brand */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '0 8px 20px',
          borderBottom: `1px solid ${C.border}`,
          marginBottom: 12,
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: C.accent,
            display: 'grid',
            placeItems: 'center',
          }}
        >
          <Logo color={C.accentInk} size={18} />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>WMOM</div>
          <div style={{ fontSize: 11, color: C.sub }}>{tr(lang, 'Operations', '營運平台')}</div>
        </div>
      </div>

      {/* Primary */}
      {primary.map(item => (
        <NavButton
          key={item.id}
          item={item}
          active={activeId === item.id}
          onClick={() => {
            onSelect(item.id);
            onMobileClose?.();
          }}
          lang={lang}
        />
      ))}

      {/* Secondary group */}
      {secondary.length > 0 && (
        <>
          <div
            style={{
              fontSize: 10,
              color: C.faint,
              textTransform: 'uppercase',
              letterSpacing: 1,
              padding: '14px 12px 6px',
            }}
          >
            {tr(lang, 'Tools', '工具')}
          </div>
          {secondary.map(item => (
            <NavButton
              key={item.id}
              item={item}
              active={activeId === item.id}
              onClick={() => {
                onSelect(item.id);
                onMobileClose?.();
              }}
              lang={lang}
            />
          ))}
        </>
      )}

      {/* Footer */}
      <div
        style={{
          marginTop: 'auto',
          paddingTop: 16,
          borderTop: `1px solid ${C.border}`,
          fontSize: 12,
          color: C.sub,
        }}
      >
        {footerExtra && <div style={{ marginBottom: 12 }}>{footerExtra}</div>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: backendHealthy ? C.ok : C.warn,
              display: 'inline-block',
            }}
            aria-hidden
          />
          {backendHealthy
            ? tr(lang, 'Backend healthy', '後端正常')
            : tr(lang, 'Backend offline', '後端離線')}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={onToggleLang}
            aria-label={tr(lang, 'Toggle language', '切換語言')}
            style={{
              background: 'transparent',
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 11,
              cursor: 'pointer',
              color: C.sub,
              fontFamily: 'inherit',
            }}
          >
            {lang === 'zh' ? 'EN' : '中文'}
          </button>
          <button
            onClick={toggle}
            aria-label={tr(lang, 'Toggle theme', '切換主題')}
            aria-pressed={mode === 'dark'}
            title={tr(lang, 'Theme', '主題')}
            style={{
              background: 'transparent',
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 12,
              cursor: 'pointer',
              color: C.sub,
              fontFamily: 'inherit',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span aria-hidden>{mode === 'dark' ? '☀' : '☾'}</span>
            {mode === 'dark' ? tr(lang, 'Light', '日') : tr(lang, 'Dark', '夜')}
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <>
      {sidebar}
      {showAsDrawer && mobileOpen && (
        <div
          role="presentation"
          onClick={onMobileClose}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            zIndex: 55,
          }}
        />
      )}
    </>
  );
};

export default Sidebar;

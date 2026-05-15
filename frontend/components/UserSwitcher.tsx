/**
 * UserSwitcher — sidebar 底部 mock-login user 切換器（WMOM-20260510-01 Part B）。
 *
 * UI 樣式參考 FarmSelector：dropdown 由下方 footerExtra slot 展開（向上彈出）。
 *
 * 行為：
 *   - 顯示目前 user 名 + 主要 role pill
 *   - 點擊展開 4 個 fixture user 列表，點選即切換（同步寫 localStorage）
 *   - Owner（dev_mode_only=true）標 (dev only) 灰字 tag
 *   - 切換不需 reload — UserContext 會 propagate 給所有訂閱元件
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '../theme/ThemeProvider';
import { useCurrentUser } from '../hooks/useCurrentUser';
import type { MockUser, MockUserRole } from '../services/mockUsers';

interface Props {
  lang: 'en' | 'zh';
}

const tr = (lang: 'en' | 'zh', en: string, zh: string) => (lang === 'zh' ? zh : en);

/** 把 role enum map 成顯示字串。Owner 多角時 join 全部。 */
const formatRoles = (roles: ReadonlyArray<MockUserRole>, lang: 'en' | 'zh'): string => {
  const labels: Record<MockUserRole, [string, string]> = {
    employee: ['employee', '員工'],
    leader: ['leader', '組長'],
    treasury: ['treasury', '財務'],
    owner: ['owner', '老闆'],
  };
  return roles.map(r => tr(lang, labels[r][0], labels[r][1])).join(' / ');
};

const UserSwitcher: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const { currentUser, setCurrentUser, availableUsers } = useCurrentUser();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    // 鍵盤無障礙：Escape 關閉 dropdown（符合 WAI-ARIA listbox authoring practice）
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const handleSelect = (user: MockUser) => {
    setCurrentUser(user);
    setIsOpen(false);
  };

  return (
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      <button
        onClick={() => setIsOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={tr(lang, 'Switch user', '切換使用者')}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 6,
          padding: '8px 10px',
          background: C.panelMuted,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          fontSize: 12,
          color: C.text,
          fontFamily: 'inherit',
          cursor: 'pointer',
        }}
      >
        <span
          style={{
            flex: 1,
            textAlign: 'left',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          <span style={{ fontWeight: 600 }}>{currentUser.name}</span>
          <span style={{ fontSize: 10, color: C.sub }}>
            {formatRoles(currentUser.roles, lang)}
          </span>
        </span>
        <span aria-hidden style={{ color: C.sub, fontSize: 10 }}>▾</span>
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label={tr(lang, 'Mock users', '模擬使用者')}
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            background: C.panel,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            boxShadow: C.isDark
              ? '0 12px 40px rgba(0,0,0,0.6)'
              : '0 12px 40px rgba(31, 45, 36, 0.16)',
            zIndex: 100,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              borderBottom: `1px solid ${C.border}`,
              fontSize: 11,
              color: C.sub,
            }}
          >
            {tr(lang, 'Mock login (dev)', '模擬登入（dev）')}
          </div>
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {availableUsers
              .filter(u => u.is_active)
              .map(user => {
                const isActive = user.id === currentUser.id;
                // 用 div + role="option" 而非 button + role="option"，符合 WAI-ARIA
                // listbox children must be option role 的 implicit ownership 規定
                return (
                  <div
                    key={user.id}
                    role="option"
                    aria-selected={isActive}
                    tabIndex={0}
                    onClick={() => handleSelect(user)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSelect(user);
                      }
                    }}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '10px 12px',
                      background: isActive ? C.accentSoft : 'transparent',
                      // 注意：border shorthand 必須在 borderLeft 之前，否則 React 會
                      // 先設 borderLeft 再被 border 重置（active 高亮線會消失）
                      border: 'none',
                      borderLeft: `3px solid ${isActive ? C.accent : 'transparent'}`,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      fontFamily: 'inherit',
                      boxSizing: 'border-box',
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 600,
                          color: isActive ? C.accent : C.text,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        {user.name}
                        {user.dev_mode_only && (
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 600,
                              color: C.faint,
                              border: `1px solid ${C.border}`,
                              padding: '1px 5px',
                              borderRadius: 4,
                              textTransform: 'uppercase',
                              letterSpacing: 0.5,
                            }}
                            title={tr(
                              lang,
                              'Only works when WMOM_DEV_MODE=true',
                              '僅 WMOM_DEV_MODE=true 時可用',
                            )}
                          >
                            {tr(lang, 'dev only', 'dev')}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                        {formatRoles(user.roles, lang)}
                        {user.email ? ` · ${user.email}` : ''}
                      </div>
                    </div>
                    {isActive && (
                      <span style={{ fontSize: 10, color: C.accent, fontWeight: 600 }}>
                        {tr(lang, 'Active', '使用中')}
                      </span>
                    )}
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
};

export default UserSwitcher;

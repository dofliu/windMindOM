/**
 * PageHeader — H1 (DM Serif) + sub + actions。
 * 所有 5 頁的開頭都是這個。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

interface PageHeaderProps {
  title: React.ReactNode;
  sub?: React.ReactNode;
  /** 麵包屑（會顯示在 title 上方）。 */
  breadcrumb?: React.ReactNode;
  /** 右側按鈕區。 */
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, sub, breadcrumb, actions }) => {
  const { C } = useTheme();
  return (
    <div style={{ marginBottom: 24 }}>
      {breadcrumb && (
        <div style={{ fontSize: 12, color: C.sub, marginBottom: 8 }}>
          {breadcrumb}
        </div>
      )}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h1
            style={{
              fontFamily: '"DM Serif Display", serif',
              fontSize: 38,
              lineHeight: 1.05,
              margin: 0,
              fontWeight: 400,
              letterSpacing: -0.8,
              color: C.text,
            }}
          >
            {title}
          </h1>
          {sub && (
            <div style={{ fontSize: 14, color: C.sub, marginTop: 6 }}>
              {sub}
            </div>
          )}
        </div>
        {actions && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
};

export default PageHeader;

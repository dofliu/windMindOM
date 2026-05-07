/**
 * Card — 主面板容器（panel + 1px border + 14px radius）。
 * 顏色一律走 theme palette；外部不可傳 hex。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

interface CardProps {
  children?: React.ReactNode;
  /** 內距，預設 20。padding=0 給內含 table / list 的滿版卡片。 */
  padding?: number | string;
  /** 是否使用「警示」背景（accentSoft / warnSoft 等）疊上去用。 */
  tone?: 'default' | 'warn' | 'ok' | 'accent' | 'muted';
  /** 額外 inline style — 用來放 grid / margin 等 layout 屬性。 */
  style?: React.CSSProperties;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  children,
  padding = 20,
  tone = 'default',
  style,
  className,
  onClick,
}) => {
  const { C } = useTheme();
  const toneMap = {
    default: { bg: C.panel, border: C.border },
    muted: { bg: C.panelMuted, border: C.border },
    accent: { bg: C.accentSoft, border: C.accent },
    ok: { bg: C.okSoft, border: C.ok },
    warn: { bg: C.warnSoft, border: C.warn },
  } as const;
  const { bg, border } = toneMap[tone];
  return (
    <div
      onClick={onClick}
      className={className}
      style={{
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 14,
        padding,
        cursor: onClick ? 'pointer' : undefined,
        transition: 'border-color 160ms ease, transform 160ms ease',
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export default Card;

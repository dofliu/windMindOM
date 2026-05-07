/**
 * Btn — 三種變化：primary（accent 填充）/ secondary（panel + border）/ ghost（透明）。
 * 顏色一律走 theme，aria-label 必填以利無障礙（呼叫端傳即可）。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

export type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'warn';

interface BtnProps {
  children?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  variant?: BtnVariant;
  size?: 'sm' | 'md';
  disabled?: boolean;
  loading?: boolean;
  type?: 'button' | 'submit' | 'reset';
  fullWidth?: boolean;
  ariaLabel?: string;
  ariaPressed?: boolean;
  title?: string;
  style?: React.CSSProperties;
}

export const Btn: React.FC<BtnProps> = ({
  children,
  onClick,
  variant = 'secondary',
  size = 'md',
  disabled,
  loading,
  type = 'button',
  fullWidth,
  ariaLabel,
  ariaPressed,
  title,
  style,
}) => {
  const { C } = useTheme();
  const palettes: Record<BtnVariant, { bg: string; color: string; border: string }> = {
    primary: { bg: C.accent, color: C.accentInk, border: C.accent },
    secondary: { bg: C.panel, color: C.text, border: C.border },
    ghost: { bg: 'transparent', color: C.sub, border: C.border },
    danger: { bg: C.warn, color: C.isDark ? '#1A0A07' : '#FFFFFF', border: C.warn },
    warn: { bg: C.amber, color: C.isDark ? '#1A1207' : '#FFFFFF', border: C.amber },
  };
  const p = palettes[variant];
  const isDisabled = disabled || loading;
  const padding = size === 'sm' ? '6px 10px' : '8px 14px';
  const fontSize = size === 'sm' ? 12 : 13;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      aria-label={ariaLabel}
      aria-pressed={ariaPressed}
      title={title}
      style={{
        background: p.bg,
        color: p.color,
        border: `1px solid ${p.border}`,
        borderRadius: 8,
        padding,
        fontSize,
        fontWeight: variant === 'primary' || variant === 'danger' || variant === 'warn' ? 600 : 500,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.5 : 1,
        fontFamily: 'inherit',
        width: fullWidth ? '100%' : undefined,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        whiteSpace: 'nowrap',
        transition: 'opacity 160ms ease, transform 80ms ease',
        ...style,
      }}
    >
      {children}
    </button>
  );
};

export default Btn;

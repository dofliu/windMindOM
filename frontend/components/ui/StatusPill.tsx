/**
 * StatusPill — 通用狀態標籤。
 *
 * 內建語意：ok / warn / amber / info / accent / muted / danger
 * 也可直接傳 colorBg / colorFg 自訂（給 chart event 類型用，需要與圖表顏色對齊時）。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

export type PillTone = 'ok' | 'warn' | 'amber' | 'info' | 'accent' | 'muted' | 'danger';

interface StatusPillProps {
  children: React.ReactNode;
  tone?: PillTone;
  size?: 'sm' | 'md';
  /** 自訂顏色（蓋過 tone）。 */
  colorBg?: string;
  colorFg?: string;
  style?: React.CSSProperties;
  title?: string;
}

export const StatusPill: React.FC<StatusPillProps> = ({
  children,
  tone = 'muted',
  size = 'sm',
  colorBg,
  colorFg,
  style,
  title,
}) => {
  const { C } = useTheme();
  const map: Record<PillTone, { bg: string; fg: string }> = {
    ok: { bg: C.okSoft, fg: C.ok },
    warn: { bg: C.warnSoft, fg: C.warn },
    amber: { bg: C.amberSoft, fg: C.amber },
    info: { bg: C.infoSoft, fg: C.info },
    accent: { bg: C.accentSoft, fg: C.accent },
    muted: { bg: C.panelMuted, fg: C.faint },
    danger: { bg: C.dangerSoft, fg: C.danger },
  };
  const bg = colorBg ?? map[tone].bg;
  const fg = colorFg ?? map[tone].fg;
  const padding = size === 'md' ? '4px 10px' : '2px 8px';
  const fontSize = size === 'md' ? 11 : 10;
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        background: bg,
        color: fg,
        padding,
        borderRadius: 999,
        fontSize,
        fontWeight: 600,
        letterSpacing: 0.5,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  );
};

/** 把 turbine status 字串映射到 pill tone — 全 app 共用。 */
export function turbineStatusTone(status: string): PillTone {
  switch (status) {
    case 'OPERATING':
      return 'ok';
    case 'FAULT':
      return 'warn';
    case 'IDLE':
      return 'amber';
    case 'OFFLINE':
    default:
      return 'muted';
  }
}

export function workOrderStatusTone(status: string): PillTone {
  switch (status) {
    case 'IN_PROGRESS':
      return 'amber';
    case 'COMPLETED':
      return 'ok';
    case 'OPEN':
    default:
      return 'accent';
  }
}

export function technicianStatusTone(status: string): PillTone {
  if (status === 'ON_DUTY' || status === 'ON DUTY') return 'ok';
  if (status === 'DISPATCHED') return 'accent';
  return 'muted';
}

export default StatusPill;

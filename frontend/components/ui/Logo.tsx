/**
 * Logo / NavIcon — 改版後的 sidebar 圖示。
 * 全部 stroke 走 currentColor，外部用 color prop 控制即可（保留 hex 例外只給 chart）。
 */

import React from 'react';

export const Logo: React.FC<{ color?: string; size?: number }> = ({ color = 'currentColor', size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
    <circle cx="12" cy="12" r="2.5" fill={color} />
    <ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color} />
    <ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color} transform="rotate(120 12 12)" />
    <ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color} transform="rotate(240 12 12)" />
  </svg>
);

export type NavIconId =
  | 'overview'
  | 'turbine'
  | 'maintenance'
  | 'workflow'
  | 'cost'
  | 'reports'
  | 'history'
  | 'field'
  | 'faults'
  | 'settings';

export const NavIcon: React.FC<{ id: NavIconId; color?: string; size?: number }> = ({
  id,
  color = 'currentColor',
  size = 18,
}) => {
  const stroke = color;
  const common = { stroke, strokeWidth: 1.6, fill: 'none' } as const;
  const cap = { ...common, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  const m: Record<NavIconId, React.ReactNode> = {
    overview: (
      <g {...common}>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </g>
    ),
    turbine: (
      <g {...common}>
        <circle cx="12" cy="9" r="2" />
        <path d="M12 11v10M12 9V3M12 9l5-3M12 9l-5-3" />
      </g>
    ),
    maintenance: (
      <g {...cap}>
        <path d="M14 4l-3 3 5 5 3-3a3.5 3.5 0 1 0-5-5z" />
        <path d="M11 7L4 14l3 3 7-7" />
      </g>
    ),
    workflow: (
      <g {...cap}>
        <rect x="3" y="6" width="18" height="14" rx="2" />
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
        <path d="M3 12h18" />
        <path d="M12 12v2" />
      </g>
    ),
    cost: (
      <g {...cap}>
        <path d="M12 4v16M8 8h6a2 2 0 1 1 0 4H10a2 2 0 1 0 0 4h7" />
      </g>
    ),
    reports: (
      <g {...cap}>
        {/* document outline */}
        <path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
        <path d="M14 3v5h5" />
        {/* mini bar chart inside */}
        <path d="M9 17v-3M12 17v-6M15 17v-4" />
      </g>
    ),
    history: (
      <g {...cap}>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 7v5l3 2" />
      </g>
    ),
    field: (
      // 手機 + 放大鏡：現場 mobile 知識查詢。
      <g {...cap}>
        <rect x="5" y="3" width="9" height="18" rx="2" />
        <path d="M5 17h9" />
        <circle cx="17" cy="9" r="2.5" />
        <path d="M19 11l2 2" />
      </g>
    ),
    faults: (
      <g {...cap}>
        <path d="M12 3l9 16H3z" />
        <path d="M12 10v4M12 17h.01" />
      </g>
    ),
    settings: (
      <g {...cap}>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 0 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 0 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9A1.7 1.7 0 0 0 10 3.1V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
      </g>
    ),
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      {m[id]}
    </svg>
  );
};

export default Logo;

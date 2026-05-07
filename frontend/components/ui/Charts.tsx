/**
 * BigChart / MiniSparkline / HealthBar — Calm Operator 設計風格的 SVG 圖表元件。
 *
 * 給 overview / turbine / cost 用；HistoryPage 仍走 recharts 但用 theme 顏色。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

// ─── Mini sparkline ─────────────────────────────────────────────────

export const MiniSparkline: React.FC<{
  values: number[];
  color?: string;
  height?: number;
  fill?: boolean;
}> = ({ values, color, height = 32, fill = false }) => {
  const { C } = useTheme();
  const stroke = color ?? C.accent;
  if (!values.length) {
    return <div style={{ height }} />;
  }
  const W = 100;
  const H = height;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padY = 2;
  const points = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * W;
    const y = H - padY - ((v - min) / range) * (H - padY * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const path = `M${points[0]} L${points.slice(1).join(' L')}`;
  const area = `${path} L${W},${H} L0,${H} Z`;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
      {fill && (
        <>
          <defs>
            <linearGradient id={`spark-grad-${stroke.replace(/[^a-z0-9]/gi, '')}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#spark-grad-${stroke.replace(/[^a-z0-9]/gi, '')})`} />
        </>
      )}
      <path d={path} stroke={stroke} strokeWidth={1.5} fill="none" />
    </svg>
  );
};

// ─── Big chart (overview / cost) ───────────────────────────────────

export interface BigChartEvent {
  /** 0..1 之間的相對位置（圖表寬度）。 */
  position: number;
  color: string;
  label?: string;
}

export interface BigChartSeries {
  values: number[];
  color: string;
  fill?: boolean;
  /** Optional：上下界線（給 P10/P90 帶狀）。 */
  upper?: number[];
  lower?: number[];
}

interface BigChartProps {
  series: BigChartSeries[];
  events?: BigChartEvent[];
  height?: number;
  /** 是否畫背景格線。 */
  grid?: boolean;
}

export const BigChart: React.FC<BigChartProps> = ({ series, events = [], height = 220, grid = true }) => {
  const { C } = useTheme();
  const W = 800;
  const H = height;
  const all = series.flatMap(s => [...s.values, ...(s.upper || []), ...(s.lower || [])]);
  if (!all.length) {
    return (
      <div
        style={{
          height: H,
          display: 'grid',
          placeItems: 'center',
          color: C.sub,
          fontSize: 12,
        }}
      >
        —
      </div>
    );
  }
  const minV = Math.min(...all);
  const maxV = Math.max(...all);
  const range = maxV - minV || 1;
  const padY = 16;

  const toPath = (vals: number[]): string => {
    if (!vals.length) return '';
    const pts = vals.map((v, i) => {
      const x = (i / Math.max(vals.length - 1, 1)) * W;
      const y = H - padY - ((v - minV) / range) * (H - padY * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    return `M${pts[0]} L${pts.slice(1).join(' L')}`;
  };

  const toArea = (upper: number[], lower: number[]): string => {
    const upPts = upper.map((v, i) => {
      const x = (i / Math.max(upper.length - 1, 1)) * W;
      const y = H - padY - ((v - minV) / range) * (H - padY * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    const loPts = lower
      .map((v, i) => {
        const x = (i / Math.max(lower.length - 1, 1)) * W;
        const y = H - padY - ((v - minV) / range) * (H - padY * 2);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .reverse();
    return `M${upPts.join(' L')} L${loPts.join(' L')} Z`;
  };

  return (
    <svg
      width="100%"
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
    >
      <defs>
        {series.map((s, i) => (
          <linearGradient key={i} id={`bgrad-${i}-${s.color.replace(/[^a-z0-9]/gi, '')}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={s.color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={s.color} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>

      {/* grid */}
      {grid &&
        [0, 0.25, 0.5, 0.75, 1].map((p, i) => (
          <line
            key={i}
            x1="0"
            x2={W}
            y1={padY + p * (H - padY * 2)}
            y2={padY + p * (H - padY * 2)}
            stroke={C.border}
            strokeWidth="0.5"
          />
        ))}

      {/* P10–P90 band */}
      {series.map((s, i) =>
        s.upper && s.lower && s.upper.length === s.lower.length ? (
          <path
            key={`band-${i}`}
            d={toArea(s.upper, s.lower)}
            fill={s.color}
            fillOpacity={0.1}
          />
        ) : null,
      )}

      {/* series area + line */}
      {series.map((s, i) => {
        const path = toPath(s.values);
        const area = `${path} L${W},${H} L0,${H} Z`;
        return (
          <g key={i}>
            {s.fill && (
              <path d={area} fill={`url(#bgrad-${i}-${s.color.replace(/[^a-z0-9]/gi, '')})`} />
            )}
            <path d={path} stroke={s.color} strokeWidth="2" fill="none" />
          </g>
        );
      })}

      {/* events */}
      {events.map((e, i) => {
        const x = e.position * W;
        return (
          <g key={i}>
            <line
              x1={x}
              x2={x}
              y1="6"
              y2={H - 6}
              stroke={e.color}
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity="0.7"
            />
            <circle cx={x} cy={14} r="4" fill={e.color} />
            {e.label && (
              <text
                x={x + 6}
                y={18}
                fontSize={10}
                fill={C.sub}
                fontFamily="JetBrains Mono, monospace"
              >
                {e.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

// ─── Health bar (subsystem) ────────────────────────────────────────

export const HealthBar: React.FC<{
  label: React.ReactNode;
  value: number; // 0..100
}> = ({ label, value }) => {
  const { C } = useTheme();
  const pct = Math.max(0, Math.min(100, value));
  const color = pct > 85 ? C.ok : pct > 75 ? C.amber : C.warn;
  return (
    <div>
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 6 }}>{label}</div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: C.bg,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 3,
            transition: 'width 200ms ease',
          }}
        />
      </div>
      <div
        style={{
          fontSize: 11,
          color: C.text,
          marginTop: 4,
          fontFamily: 'JetBrains Mono, monospace',
        }}
      >
        {pct.toFixed(0)}%
      </div>
    </div>
  );
};

export default BigChart;

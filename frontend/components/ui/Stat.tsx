/**
 * Stat — 大數字 + 單位 + 副標的常見組合（hero stat / KPI 卡用）。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

interface StatProps {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  /** 額外副標 / 變化（%）。 */
  hint?: React.ReactNode;
  /** 大數字是否用 accent 色強調。 */
  highlight?: boolean;
  /** 大數字顏色覆寫（給 fault 數字變紅之類）。 */
  valueColor?: string;
  /** 大數字字級，預設 40（hero）；turbine 卡片可傳 32。 */
  size?: number;
}

export const Stat: React.FC<StatProps> = ({
  label,
  value,
  unit,
  hint,
  highlight,
  valueColor,
  size = 40,
}) => {
  const { C } = useTheme();
  const color = valueColor ?? (highlight ? C.accent : C.text);
  return (
    <div>
      <div
        style={{
          fontSize: 12,
          color: C.sub,
          letterSpacing: 1,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 6 }}>
        <span
          style={{
            fontFamily: '"DM Serif Display", serif',
            fontSize: size,
            color,
            lineHeight: 1,
            fontWeight: 400,
          }}
        >
          {value}
        </span>
        {unit && <span style={{ fontSize: 14, color: C.sub }}>{unit}</span>}
      </div>
      {hint && <div style={{ fontSize: 12, color: C.sub, marginTop: 8 }}>{hint}</div>}
    </div>
  );
};

export default Stat;

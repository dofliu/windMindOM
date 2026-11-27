/**
 * 營運頁共用的小東西：格式化、錯誤說明、表格樣式（WMOM-20261127-01）。
 */

import React from 'react';
import { Card } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import { OperationsApiError } from '../../services/operationsService';

export type Lang = 'en' | 'zh';

export const pick = (lang: Lang) => (en: string, zh: string) => (lang === 'zh' ? zh : en);

/** 金額：千分位、小數兩位。 */
export function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** 電量：1,000 kWh 以上用 MWh。 */
export function fmtEnergy(kwh: number | null | undefined): string {
  if (kwh === null || kwh === undefined || !Number.isFinite(kwh)) return '—';
  if (Math.abs(kwh) >= 1000) {
    return `${(kwh / 1000).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MWh`;
  }
  return `${kwh.toLocaleString('en-US', { maximumFractionDigits: 0 })} kWh`;
}

export function fmtPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

export function fmtHours(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toFixed(1);
}

/** 風場時鐘的時間（UTC 字串）→ 簡短顯示（UTC）。 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return `${iso.slice(0, 16).replace('T', ' ')} UTC`;
}

/** 依錯誤的狀態碼給使用者看得懂的說明。 */
export function explainError(err: unknown, lang: Lang): string {
  const ui = pick(lang);
  if (err instanceof OperationsApiError) {
    if (err.status === 401) return ui('Please sign in.', '請先登入。');
    if (err.status === 403) return ui('Supervisors only.', '這裡只有主管能看或修改，請用主管帳號登入。');
    if (err.status === 409 || err.status === 400) {
      return ui(`Not available now: ${err.message}`, `目前不能用：${err.message}`);
    }
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

export const ErrorNote: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { C } = useTheme();
  return (
    <Card tone="warn" padding={14}>
      <div role="alert" style={{ color: C.warn, fontSize: 13 }}>
        {children}
      </div>
    </Card>
  );
};

/** 表格的儲存格樣式。 */
export function useTableStyles() {
  const { C } = useTheme();
  const th: React.CSSProperties = {
    textAlign: 'left',
    padding: '8px 10px',
    fontSize: 11,
    fontWeight: 500,
    color: C.sub,
    borderBottom: `1px solid ${C.border}`,
    background: C.panelMuted,
    whiteSpace: 'nowrap',
  };
  const td: React.CSSProperties = {
    padding: '7px 10px',
    fontSize: 13,
    color: C.text,
    borderBottom: `1px solid ${C.border}`,
    whiteSpace: 'nowrap',
  };
  const num: React.CSSProperties = { ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' };
  const thNum: React.CSSProperties = { ...th, textAlign: 'right' };
  return { th, td, num, thNum };
}

/** 開關（checkbox＋文字）。 */
export const Toggle: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
  label: React.ReactNode;
  disabled?: boolean;
}> = ({ checked, onChange, label, disabled }) => {
  const { C } = useTheme();
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: C.text }}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={e => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
};

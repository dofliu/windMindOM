/**
 * Field — 表單輸入的 wrapper（label + select / input / readonly text）。
 * 顏色全走 theme，給 history / cost / settings 用。
 */

import React from 'react';
import { useTheme } from '../../theme/ThemeProvider';

interface FieldShellProps {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  fullWidth?: boolean;
}

export const Field: React.FC<FieldShellProps> = ({ label, hint, children, fullWidth }) => {
  const { C } = useTheme();
  return (
    <label style={{ display: 'block', width: fullWidth ? '100%' : undefined }}>
      {label && (
        <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>{label}</div>
      )}
      {children}
      {hint && (
        <div style={{ fontSize: 11, color: C.faint, marginTop: 4 }}>{hint}</div>
      )}
    </label>
  );
};

export interface InputBaseProps {
  value?: string | number;
  onChange?: (v: string) => void;
  placeholder?: string;
  type?: string;
  step?: string | number;
  min?: number | string;
  max?: number | string;
  disabled?: boolean;
  ariaLabel?: string;
  fullWidth?: boolean;
  monospace?: boolean;
  width?: number | string;
}

export const Input: React.FC<InputBaseProps> = ({
  value,
  onChange,
  placeholder,
  type = 'text',
  step,
  min,
  max,
  disabled,
  ariaLabel,
  fullWidth,
  monospace,
  width,
}) => {
  const { C } = useTheme();
  return (
    <input
      type={type}
      value={value ?? ''}
      step={step}
      min={min}
      max={max}
      placeholder={placeholder}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={e => onChange?.(e.target.value)}
      style={{
        background: C.panel,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 13,
        color: C.text,
        fontFamily: monospace ? 'JetBrains Mono, monospace' : 'inherit',
        width: fullWidth ? '100%' : width,
        outline: 'none',
        boxSizing: 'border-box',
      }}
    />
  );
};

interface SelectOption {
  value: string;
  // 限定 string：原生 <option> 只能顯示文字，傳 JSX 會被靜默渲染成空字串（footgun）。
  // 全 app 既有呼叫端皆傳字串，於型別層擋住非字串 label。
  label: string;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (v: string) => void;
  ariaLabel?: string;
  fullWidth?: boolean;
  width?: number | string;
}

export const Select: React.FC<SelectProps> = ({ value, options, onChange, ariaLabel, fullWidth, width }) => {
  const { C } = useTheme();
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      aria-label={ariaLabel}
      style={{
        background: C.panel,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 13,
        color: C.text,
        fontFamily: 'inherit',
        width: fullWidth ? '100%' : width,
        cursor: 'pointer',
        outline: 'none',
        boxSizing: 'border-box',
      }}
    >
      {options.map(o => (
        <option key={o.value} value={o.value} style={{ color: '#000' }}>
          {o.label}
        </option>
      ))}
    </select>
  );
};

/** Readonly value box (history filter cards 用)。 */
export const ReadOnlyBox: React.FC<{ children: React.ReactNode; monospace?: boolean }> = ({
  children,
  monospace,
}) => {
  const { C } = useTheme();
  return (
    <div
      style={{
        padding: '8px 12px',
        background: C.panelMuted,
        borderRadius: 8,
        fontSize: 13,
        color: C.text,
        fontFamily: monospace ? 'JetBrains Mono, monospace' : 'inherit',
        border: `1px solid ${C.border}`,
      }}
    >
      {children}
    </div>
  );
};

export default Field;

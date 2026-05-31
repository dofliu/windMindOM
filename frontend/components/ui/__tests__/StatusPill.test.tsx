/**
 * StatusPill 測試 —— render 行為 + 三個 status→tone 純函式。
 *
 * StatusPill 是 turbine / work order / technician 狀態標籤的共用原件；三個 tone
 * mapping 函式（turbineStatusTone / workOrderStatusTone / technicianStatusTone）
 * 決定全 app 狀態配色語意，此前零測試。本檔：
 *   1. render 層：children 顯示、title / 自訂顏色透傳、未知 tone 不炸。
 *   2. 純函式層：每個已知 status 對到預期 tone + 未知值走 default 分支（switch 無漏接）。
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithTheme } from '../../../test/renderWithTheme';
import {
  StatusPill,
  turbineStatusTone,
  workOrderStatusTone,
  technicianStatusTone,
  type PillTone,
} from '../StatusPill';

describe('StatusPill render', () => {
  it('render children 文字', () => {
    renderWithTheme(<StatusPill>運轉中</StatusPill>);
    expect(screen.getByText('運轉中')).toBeInTheDocument();
  });

  it('title 透傳到 title 屬性', () => {
    renderWithTheme(<StatusPill title="提示">OK</StatusPill>);
    expect(screen.getByText('OK')).toHaveAttribute('title', '提示');
  });

  it('colorBg / colorFg 自訂顏色蓋過 tone（給 chart 對齊用）', () => {
    renderWithTheme(
      <StatusPill colorBg="rgb(1, 2, 3)" colorFg="rgb(4, 5, 6)">
        E1
      </StatusPill>,
    );
    const el = screen.getByText('E1');
    // 只驗自訂色真的套上去（行為），不驗 theme 預設色（避免綁 palette）
    expect(el).toHaveStyle({ background: 'rgb(1, 2, 3)', color: 'rgb(4, 5, 6)' });
  });
});

describe('turbineStatusTone', () => {
  const cases: ReadonlyArray<[string, PillTone]> = [
    ['OPERATING', 'ok'],
    ['FAULT', 'warn'],
    ['IDLE', 'amber'],
    ['OFFLINE', 'muted'],
  ];
  it.each(cases)('%s → %s', (status, tone) => {
    expect(turbineStatusTone(status)).toBe(tone);
  });

  it('未知 status 走 default → muted（switch 無漏接，不回 undefined）', () => {
    expect(turbineStatusTone('SOMETHING_NEW')).toBe('muted');
  });
});

describe('workOrderStatusTone', () => {
  const cases: ReadonlyArray<[string, PillTone]> = [
    ['IN_PROGRESS', 'amber'],
    ['COMPLETED', 'ok'],
    ['OPEN', 'accent'],
  ];
  it.each(cases)('%s → %s', (status, tone) => {
    expect(workOrderStatusTone(status)).toBe(tone);
  });

  it('CANCELLED（statusUtils 真實存在的狀態但 switch 未列 case）走 default → accent', () => {
    // 'CANCELLED' 是 statusUtils.ts 定義的真實 WorkOrderStatus，workOrderStatusTone 目前
    // 沒有顯式 case → fallthrough default → 'accent'。用真實值而非虛構值當 default 樣本，
    // 將來若要給 CANCELLED 專屬 tone，此 test 會迫使刻意更新。
    expect(workOrderStatusTone('CANCELLED')).toBe('accent');
  });
});

describe('technicianStatusTone', () => {
  it('ON_DUTY / "ON DUTY"（底線與空白兩種寫法）皆 → ok', () => {
    expect(technicianStatusTone('ON_DUTY')).toBe('ok');
    expect(technicianStatusTone('ON DUTY')).toBe('ok');
  });

  it('DISPATCHED → accent', () => {
    expect(technicianStatusTone('DISPATCHED')).toBe('accent');
  });

  it('其他（含未知）→ muted', () => {
    expect(technicianStatusTone('OFF_DUTY')).toBe('muted');
    expect(technicianStatusTone('whatever')).toBe('muted');
  });
});

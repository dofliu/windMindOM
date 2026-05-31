/**
 * Field 表單欄位 wrapper 的 render 測試。
 *
 * 契約（見 Field.tsx）：根節點為 <label>；label / hint 皆為選填（給才各自 render 一個 <div>），
 * children 永遠 render 在中間；fullWidth 控制根 <label> 寬度。
 * 測試策略同 Btn.test.tsx（RTL + jsdom + 原生 DOM 斷言）；Field 用 useTheme，故包 ThemeProvider。
 * 不測：label/hint 的顏色細節（屬 theme token，非 Field 結構契約）。
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { Field } from '../Field';
import { ThemeProvider } from '../../../theme/ThemeProvider';

afterEach(cleanup);

/** 包 ThemeProvider 後 render，回傳根 <label> 節點。 */
function renderField(ui: React.ReactElement): HTMLLabelElement {
  const { container } = render(<ThemeProvider>{ui}</ThemeProvider>);
  const label = container.querySelector('label');
  if (label === null) throw new Error('Field 未 render 出 <label>');
  return label;
}

describe('Field', () => {
  it('根節點是 <label> 且 render children', () => {
    const label = renderField(
      <Field label="風場">
        <input data-testid="inp" />
      </Field>,
    );
    expect(label.tagName).toBe('LABEL');
    // getByTestId 找不到會 throw；此處取回節點確認即為傳入的 input
    expect(screen.getByTestId('inp').tagName).toBe('INPUT');
  });

  it('給 label 時顯示 label 文字', () => {
    renderField(
      <Field label="風場名稱">
        <input />
      </Field>,
    );
    expect(screen.getByText('風場名稱').textContent).toBe('風場名稱');
  });

  it('label 支援 ReactNode（非字串）', () => {
    renderField(
      <Field label={<span data-testid="label-node">複合標籤</span>}>
        <input />
      </Field>,
    );
    expect(screen.getByTestId('label-node').textContent).toBe('複合標籤');
  });

  it('給 hint 時顯示 hint 文字', () => {
    renderField(
      <Field label="X" hint="請輸入 6 碼">
        <input />
      </Field>,
    );
    expect(screen.getByText('請輸入 6 碼').textContent).toBe('請輸入 6 碼');
  });

  it('label + hint 都給：DOM 順序為 label → children → hint（3 個子節點）', () => {
    const label = renderField(
      <Field label="標籤" hint="提示">
        <input data-testid="inp" />
      </Field>,
    );
    expect(label.childElementCount).toBe(3);
    const labelDiv = screen.getByText('標籤');
    const hintDiv = screen.getByText('提示');
    const input = screen.getByTestId('inp');
    expect(labelDiv.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(input.compareDocumentPosition(hintDiv) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('未給 label 與 hint：根 <label> 只剩 children 本身（1 個子節點）', () => {
    const label = renderField(
      <Field>
        <input data-testid="inp" />
      </Field>,
    );
    expect(label.childElementCount).toBe(1);
    expect(label.firstElementChild).toBe(screen.getByTestId('inp'));
  });

  it('fullWidth：根 <label> width 為 100%', () => {
    const label = renderField(
      <Field fullWidth>
        <input />
      </Field>,
    );
    expect(label.style.width).toBe('100%');
  });

  it('未給 fullWidth：根 <label> 不設 width（反向對照，避免「永遠 100%」迴歸）', () => {
    const label = renderField(
      <Field>
        <input />
      </Field>,
    );
    expect(label.style.width).toBe('');
  });
});

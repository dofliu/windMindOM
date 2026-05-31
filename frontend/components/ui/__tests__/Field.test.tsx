/**
 * 表單原件 render 測試：Field / Input / Select / ReadOnlyBox。
 *
 * 這層是 history / cost / settings 頁的輸入控制項。守護重點是受控元件的 onChange
 * 契約（回傳的是「新值字串」而非原始 event）、aria-label 無障礙、disabled，以及
 * Select 的 option 對應。受控 callback 的型別契約一旦被改成傳 event 會直接破壞所有
 * 呼叫端，故鎖成回歸基準。
 */

import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithTheme } from '../../../test/renderWithTheme';
import { Field, Input, Select, ReadOnlyBox } from '../Field';

describe('Field', () => {
  it('render label / children / hint', () => {
    renderWithTheme(
      <Field label="折現率" hint="百分比">
        <span>內容</span>
      </Field>,
    );
    expect(screen.getByText('折現率')).toBeInTheDocument();
    expect(screen.getByText('內容')).toBeInTheDocument();
    expect(screen.getByText('百分比')).toBeInTheDocument();
  });
});

describe('Field + Input 組合（實際使用場景）', () => {
  it('Input 以 ariaLabel 與 Field label 文字一致時，可用 label 文字取得 input（無障礙關聯）', () => {
    // cost / settings 頁的真實用法：<Field label="折現率"><Input ariaLabel="折現率" .../></Field>。
    // Field 用 <label><div>文字</div>children</label> 包覆，這裡驗 AT 能由文字定位到 input。
    renderWithTheme(
      <Field label="折現率">
        <Input value="" ariaLabel="折現率" />
      </Field>,
    );
    expect(screen.getByLabelText('折現率')).toBeInTheDocument();
  });
});

describe('Input', () => {
  it('value 受控顯示、aria-label 透傳', () => {
    renderWithTheme(<Input value="abc" ariaLabel="名稱" />);
    const input = screen.getByLabelText('名稱') as HTMLInputElement;
    expect(input.value).toBe('abc');
  });

  it('value 為 undefined 時 render 空字串（避免 React uncontrolled 警告）', () => {
    renderWithTheme(<Input ariaLabel="空" />);
    expect((screen.getByLabelText('空') as HTMLInputElement).value).toBe('');
  });

  it('onChange 收到的是「新值字串」而非 event', () => {
    const onChange = vi.fn();
    renderWithTheme(<Input value="" onChange={onChange} ariaLabel="in" />);
    fireEvent.change(screen.getByLabelText('in'), { target: { value: '新值' } });
    expect(onChange).toHaveBeenCalledWith('新值');
  });

  it('disabled 透傳', () => {
    renderWithTheme(<Input value="x" disabled ariaLabel="dis" />);
    expect(screen.getByLabelText('dis')).toBeDisabled();
  });
});

describe('Select', () => {
  const options = [
    { value: 'k13', label: 'K13 範例' },
    { value: 'farm:tc', label: '台中港曲風場' },
  ];

  it('render 全部 option 且 value 受控', () => {
    renderWithTheme(
      <Select value="farm:tc" options={options} onChange={() => {}} ariaLabel="資料集" />,
    );
    const select = screen.getByLabelText('資料集') as HTMLSelectElement;
    expect(select.value).toBe('farm:tc');
    expect(screen.getByRole('option', { name: 'K13 範例' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '台中港曲風場' })).toBeInTheDocument();
  });

  it('切換 option 觸發 onChange 帶新 value', () => {
    const onChange = vi.fn();
    renderWithTheme(
      <Select value="k13" options={options} onChange={onChange} ariaLabel="資料集" />,
    );
    fireEvent.change(screen.getByLabelText('資料集'), { target: { value: 'farm:tc' } });
    expect(onChange).toHaveBeenCalledWith('farm:tc');
  });
});

describe('ReadOnlyBox', () => {
  it('render children', () => {
    renderWithTheme(<ReadOnlyBox>唯讀值</ReadOnlyBox>);
    expect(screen.getByText('唯讀值')).toBeInTheDocument();
  });
});

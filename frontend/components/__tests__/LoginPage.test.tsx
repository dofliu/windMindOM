/**
 * LoginPage render / 互動測試（WMOM-20260716-05f-b）。
 * ThemeProvider 包裹 + jest-dom matcher；登入邏輯以 onLogin prop 注入（不打真 API）。
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import LoginPage from '../LoginPage';
import { ThemeProvider } from '../../theme/ThemeProvider';

afterEach(cleanup);

type Props = React.ComponentProps<typeof LoginPage>;

function renderLogin(props: Partial<Props> = {}) {
  const onLogin = props.onLogin ?? vi.fn().mockResolvedValue(undefined);
  const utils = render(
    <ThemeProvider>
      <LoginPage lang="zh" onLogin={onLogin} {...props} />
    </ThemeProvider>,
  );
  return { ...utils, onLogin };
}

describe('LoginPage', () => {
  it('顯示帳號 / 密碼欄位 + 登入鈕', () => {
    renderLogin();
    expect(screen.getByLabelText('帳號')).toBeInTheDocument();
    expect(screen.getByLabelText('密碼')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登入' })).toBeInTheDocument();
  });

  it('填帳密送出 → 呼叫 onLogin(帳號, 密碼)', async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined);
    renderLogin({ onLogin });
    fireEvent.change(screen.getByLabelText('帳號'), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText('密碼'), { target: { value: 'pw123' } });
    fireEvent.click(screen.getByRole('button', { name: '登入' }));
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith('alice', 'pw123'));
  });

  it('onLogin reject → 顯示錯誤訊息', async () => {
    const onLogin = vi.fn().mockRejectedValue(new Error('帳號或密碼錯誤'));
    renderLogin({ onLogin });
    fireEvent.change(screen.getByLabelText('帳號'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('密碼'), { target: { value: 'y' } });
    fireEvent.click(screen.getByRole('button', { name: '登入' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('帳號或密碼錯誤');
  });

  it('空帳密送出 → 前端擋下（提示、不呼叫 onLogin）', () => {
    const onLogin = vi.fn();
    renderLogin({ onLogin });
    fireEvent.click(screen.getByRole('button', { name: '登入' }));
    expect(onLogin).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('請輸入帳號與密碼');
  });

  it('sessionExpired → 顯示過期標題', () => {
    renderLogin({ sessionExpired: true });
    expect(screen.getByText('連線階段已過期')).toBeInTheDocument();
  });

  it('有 onClose → 顯示「稍後再說」並可點', () => {
    const onClose = vi.fn();
    renderLogin({ onClose });
    fireEvent.click(screen.getByRole('button', { name: '稍後再說' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('英文 lang → 顯示英文欄位', () => {
    renderLogin({ lang: 'en' });
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});

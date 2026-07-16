/**
 * useAuth / AuthProvider 測試（WMOM-20260716-05f-b）。
 *
 * mock authClient（login / clearAuthToken / getAuthToken / onUnauthorized），
 * 用 harness 元件把 context 值投影成 DOM 來斷言。零真連線。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../useAuth';
import * as authClient from '../../services/authClient';

vi.mock('../../services/authClient', async importOriginal => {
  const actual = await importOriginal<typeof import('../../services/authClient')>();
  return {
    ...actual,
    authApi: { login: vi.fn(), me: vi.fn() },
    clearAuthToken: vi.fn(),
    getAuthToken: vi.fn(() => null),
    onUnauthorized: vi.fn(),
  };
});

function Harness() {
  const auth = useAuth();
  return (
    <div>
      <div data-testid="actor">{auth.actor ? auth.actor.name : 'none'}</div>
      <div data-testid="authed">{String(auth.isAuthenticated)}</div>
      <div data-testid="open">{String(auth.loginOpen)}</div>
      <div data-testid="expired">{String(auth.sessionExpired)}</div>
      <button onClick={() => void auth.login('u', 'p')}>do-login</button>
      <button onClick={auth.logout}>do-logout</button>
      <button onClick={auth.openLogin}>do-open</button>
      <button onClick={auth.closeLogin}>do-close</button>
    </div>
  );
}

const renderProvider = () =>
  render(
    <AuthProvider>
      <Harness />
    </AuthProvider>,
  );

/** 取回 AuthProvider 於 mount 時註冊進 onUnauthorized 的 401 handler。 */
function getRegisteredHandler(): (() => void) | undefined {
  const mock = vi.mocked(authClient.onUnauthorized);
  const call = mock.mock.calls.find(c => typeof c[0] === 'function');
  return call?.[0] as (() => void) | undefined;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(authClient.getAuthToken).mockReturnValue(null);
  vi.mocked(authClient.authApi.login).mockReset();
  vi.mocked(authClient.clearAuthToken).mockReset();
  vi.mocked(authClient.onUnauthorized).mockReset();
});

afterEach(cleanup);

describe('AuthProvider / useAuth', () => {
  it('初始未登入', () => {
    renderProvider();
    expect(screen.getByTestId('authed').textContent).toBe('false');
    expect(screen.getByTestId('actor').textContent).toBe('none');
    expect(screen.getByTestId('open').textContent).toBe('false');
  });

  it('login 成功 → set actor + 關 overlay', async () => {
    vi.mocked(authClient.authApi.login).mockResolvedValue({
      id: 'u1',
      name: 'Alice',
      role: 'employee',
    });
    renderProvider();
    fireEvent.click(screen.getByText('do-open'));
    expect(screen.getByTestId('open').textContent).toBe('true');

    fireEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('actor').textContent).toBe('Alice'));
    expect(screen.getByTestId('authed').textContent).toBe('true');
    expect(screen.getByTestId('open').textContent).toBe('false');
  });

  it('logout → 清 actor + 呼叫 clearAuthToken', async () => {
    vi.mocked(authClient.authApi.login).mockResolvedValue({
      id: 'u1',
      name: 'Alice',
      role: 'employee',
    });
    renderProvider();
    fireEvent.click(screen.getByText('do-login'));
    await waitFor(() => expect(screen.getByTestId('actor').textContent).toBe('Alice'));

    fireEvent.click(screen.getByText('do-logout'));

    expect(screen.getByTestId('actor').textContent).toBe('none');
    expect(screen.getByTestId('authed').textContent).toBe('false');
    expect(vi.mocked(authClient.clearAuthToken)).toHaveBeenCalled();
  });

  it('openLogin / closeLogin 切換 overlay', () => {
    renderProvider();
    expect(screen.getByTestId('open').textContent).toBe('false');
    fireEvent.click(screen.getByText('do-open'));
    expect(screen.getByTestId('open').textContent).toBe('true');
    fireEvent.click(screen.getByText('do-close'));
    expect(screen.getByTestId('open').textContent).toBe('false');
  });

  it('401 handler → 清 actor + 開 overlay + 標記 sessionExpired', () => {
    renderProvider();
    const handler = getRegisteredHandler();
    expect(handler).toBeTypeOf('function');

    act(() => handler!());

    expect(screen.getByTestId('authed').textContent).toBe('false');
    expect(screen.getByTestId('open').textContent).toBe('true');
    expect(screen.getByTestId('expired').textContent).toBe('true');
  });

  it('仍持有 token 時，mount 還原 localStorage 的 actor', () => {
    vi.mocked(authClient.getAuthToken).mockReturnValue('tok');
    window.localStorage.setItem(
      'wmom_auth_actor',
      JSON.stringify({ id: 'u9', name: 'Bob', role: 'leader' }),
    );
    renderProvider();
    expect(screen.getByTestId('actor').textContent).toBe('Bob');
    expect(screen.getByTestId('authed').textContent).toBe('true');
  });
});

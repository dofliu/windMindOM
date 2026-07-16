/**
 * LoginPage — 真登入表單 overlay（WMOM-20260716-05f-b）。
 *
 * themed（走 `useTheme`）+ 雙語（`lang` prop）。自管表單 state（帳密 / 送出中 / 錯誤）；
 * 登入邏輯由 `onLogin`（成功 resolve、失敗 throw）注入 → 與 AuthProvider 解耦、好測。
 *
 * 過渡期未強制登入，故 overlay **可關**（`onClose`）；`sessionExpired` 只改標題文案
 * （「連線階段已過期」）。Enter 送出（包 `<form>`）。
 */

import React, { useState } from 'react';
import { useTheme } from '../theme/ThemeProvider';
import { Btn, Field, Input } from './ui';

interface LoginPageProps {
  lang: 'zh' | 'en';
  onLogin: (username: string, password: string) => Promise<void>;
  onClose?: () => void;
  sessionExpired?: boolean;
}

const LoginPage: React.FC<LoginPageProps> = ({ lang, onLogin, onClose, sessionExpired }) => {
  const { C } = useTheme();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const t = (zh: string, en: string) => (lang === 'zh' ? zh : en);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    if (!username.trim() || !password) {
      setError(t('請輸入帳號與密碼', 'Enter username and password'));
      return;
    }
    setSubmitting(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('登入失敗', 'Login failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('登入', 'Sign in')}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: C.isDark ? 'rgba(4,10,8,0.72)' : 'rgba(20,30,25,0.42)',
        backdropFilter: 'blur(4px)',
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 380,
          background: C.bg,
          border: `1px solid ${C.border}`,
          borderRadius: 16,
          padding: 28,
          boxShadow: '0 24px 60px rgba(0,0,0,0.28)',
        }}
      >
        <div style={{ marginBottom: 4, fontSize: 19, fontWeight: 700, color: C.text }}>
          {sessionExpired
            ? t('連線階段已過期', 'Session expired')
            : t('登入 windMindOM', 'Sign in to windMindOM')}
        </div>
        <div style={{ marginBottom: 20, fontSize: 12.5, color: C.sub, lineHeight: 1.5 }}>
          {sessionExpired
            ? t('請重新登入以繼續操作。', 'Please sign in again to continue.')
            : t('離岸風場運維管理平台', 'Offshore wind O&M management platform')}
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Field label={t('帳號', 'Username')} fullWidth>
              <Input
                value={username}
                onChange={setUsername}
                placeholder={t('請輸入帳號', 'Enter username')}
                ariaLabel={t('帳號', 'Username')}
                fullWidth
              />
            </Field>
            <Field label={t('密碼', 'Password')} fullWidth>
              <Input
                value={password}
                onChange={setPassword}
                type="password"
                placeholder={t('請輸入密碼', 'Enter password')}
                ariaLabel={t('密碼', 'Password')}
                fullWidth
              />
            </Field>

            {error && (
              <div
                role="alert"
                style={{
                  fontSize: 12.5,
                  color: C.isDark ? '#FFB4A2' : '#B23A2E',
                  background: C.dangerSoft,
                  border: `1px solid ${C.danger}`,
                  borderRadius: 8,
                  padding: '8px 10px',
                }}
              >
                {error}
              </div>
            )}

            <Btn
              type="submit"
              variant="primary"
              fullWidth
              loading={submitting}
              disabled={submitting}
              ariaLabel={t('登入', 'Sign in')}
            >
              {submitting ? t('登入中…', 'Signing in…') : t('登入', 'Sign in')}
            </Btn>

            {onClose && (
              <Btn
                type="button"
                variant="ghost"
                fullWidth
                onClick={onClose}
                ariaLabel={t('稍後再說', 'Not now')}
              >
                {t('稍後再說', 'Not now')}
              </Btn>
            )}
          </div>
        </form>

        <div style={{ marginTop: 16, fontSize: 11, color: C.faint, lineHeight: 1.5 }}>
          {t(
            '過渡期未強制登入，可先「稍後再說」以現有身分操作。',
            'Login is optional during transition — you may continue with "Not now".',
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;

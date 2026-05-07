/**
 * FarmSelector — sidebar 底部風場切換器（改版後）。
 *
 * UI 走 theme palette；行為與舊版一致：
 *   - 點擊展開列表
 *   - 切換 farm 會 reload 整個 app（後端切 active farm）
 *   - 「+ 新增風場」開 modal
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '../theme/ThemeProvider';
import { Btn, Card, Field, Input } from './ui';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface Farm {
  farm_id: string;
  name: string;
  turbine_count: number;
  is_active: boolean;
  location: string;
  description: string;
  created_at: string;
  turbine_spec: Record<string, unknown>;
}

interface Preset {
  key: string;
  label: string;
}

const PRESETS: Preset[] = [
  { key: 'z72_2mw', label: 'Z72 2MW (Direct Drive)' },
  { key: 'vestas_v90_3mw', label: 'Vestas V90 3MW' },
  { key: 'sg_8mw', label: 'SG 8MW (Offshore)' },
  { key: 'goldwind_2.5mw', label: 'Goldwind 2.5MW' },
];

interface Props {
  lang: 'en' | 'zh';
}

const FarmSelector: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const [farms, setFarms] = useState<Farm[]>([]);
  const [activeFarmId, setActiveFarmId] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  useEffect(() => {
    fetchFarms();
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchFarms = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/farms`);
      if (!res.ok) return;
      const data = await res.json();
      setFarms(data.farms || []);
      setActiveFarmId(data.active_farm_id);
    } catch {
      /* Farm API not available */
    }
  };

  const switchFarm = async (farmId: string) => {
    if (farmId === activeFarmId || switching) return;
    setSwitching(true);
    try {
      const res = await fetch(`${API_BASE}/api/farms/${farmId}/activate`, { method: 'POST' });
      if (res.ok) {
        setActiveFarmId(farmId);
        setIsOpen(false);
        window.location.reload();
      }
    } catch {
      /* ignore */
    } finally {
      setSwitching(false);
    }
  };

  const activeFarm = farms.find(f => f.farm_id === activeFarmId);
  const ratedPower = activeFarm?.turbine_spec?.rated_power_kw as number | undefined;
  const label = activeFarm
    ? `${activeFarm.name}${ratedPower ? ` · ${(ratedPower / 1000).toFixed(1)} MW` : ''}`
    : ui('Select farm', '選擇風場');

  return (
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      <button
        onClick={() => setIsOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ui('Switch wind farm', '切換風場')}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 6,
          padding: '8px 10px',
          background: C.panelMuted,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          fontSize: 12,
          color: C.text,
          fontFamily: 'inherit',
          cursor: 'pointer',
        }}
      >
        <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {label}
        </span>
        <span aria-hidden style={{ color: C.sub, fontSize: 10 }}>▾</span>
      </button>

      {isOpen && (
        <div
          role="listbox"
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            background: C.panel,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            boxShadow: C.isDark
              ? '0 12px 40px rgba(0,0,0,0.6)'
              : '0 12px 40px rgba(31, 45, 36, 0.16)',
            zIndex: 100,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 11,
              color: C.sub,
            }}
          >
            <span>{ui('Wind farms', '風場專案')}</span>
            <button
              onClick={() => {
                setIsOpen(false);
                setShowCreate(true);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: C.accent,
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: 600,
              }}
            >
              + {ui('New', '新增')}
            </button>
          </div>
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {farms.length === 0 ? (
              <div style={{ padding: 12, fontSize: 12, color: C.faint }}>
                {ui('No farms', '尚未建立風場')}
              </div>
            ) : (
              farms.map(farm => {
                const isActive = farm.farm_id === activeFarmId;
                const power = farm.turbine_spec?.rated_power_kw as number | undefined;
                return (
                  <button
                    key={farm.farm_id}
                    role="option"
                    aria-selected={isActive}
                    onClick={() => switchFarm(farm.farm_id)}
                    disabled={switching}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '10px 12px',
                      background: isActive ? C.accentSoft : 'transparent',
                      borderLeft: `3px solid ${isActive ? C.accent : 'transparent'}`,
                      border: 'none',
                      cursor: switching ? 'wait' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      fontFamily: 'inherit',
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 600,
                          color: isActive ? C.accent : C.text,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {farm.name}
                      </div>
                      <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                        {farm.turbine_count} {ui('turbines', '台')}
                        {power ? ` · ${(power / 1000).toFixed(1)} MW` : ''}
                        {farm.location ? ` · ${farm.location}` : ''}
                      </div>
                    </div>
                    {isActive && (
                      <span style={{ fontSize: 10, color: C.accent, fontWeight: 600 }}>
                        {ui('Active', '使用中')}
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {showCreate && (
        <CreateFarmModal
          lang={lang}
          onClose={() => setShowCreate(false)}
          onCreated={farmId => {
            setShowCreate(false);
            fetchFarms();
            switchFarm(farmId);
          }}
        />
      )}
    </div>
  );
};

// ─── Create farm modal ────────────────────────────────────────

interface CreateModalProps {
  lang: 'en' | 'zh';
  onClose: () => void;
  onCreated: (farmId: string) => void;
}

const CreateFarmModal: React.FC<CreateModalProps> = ({ lang, onClose, onCreated }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const [name, setName] = useState('');
  const [preset, setPreset] = useState('z72_2mw');
  const [turbineCount, setTurbineCount] = useState(14);
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!name.trim()) {
      setError(ui('Farm name is required', '請輸入風場名稱'));
      return;
    }
    setCreating(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/farms`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          preset,
          turbine_count: turbineCount,
          location: location.trim(),
          description: description.trim(),
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || 'Failed to create farm');
        return;
      }
      const data = await res.json();
      onCreated(data.farm.farm_id);
    } catch {
      setError(ui('Network error', '網路錯誤'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 200,
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <Card
        padding={0}
        onClick={undefined}
        style={{ width: '100%', maxWidth: 460, overflow: 'hidden' }}
      >
        <div
          onClick={e => e.stopPropagation()}
        >
          <div
            style={{
              padding: '14px 18px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <h2
              style={{
                margin: 0,
                fontFamily: '"DM Serif Display", serif',
                fontSize: 22,
                fontWeight: 400,
                color: C.text,
              }}
            >
              {ui('Create wind farm', '建立新風場')}
            </h2>
            <button
              onClick={onClose}
              aria-label={ui('Close', '關閉')}
              style={{
                background: 'transparent',
                border: 'none',
                color: C.sub,
                fontSize: 18,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>

          <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Field label={`${ui('Farm name', '風場名稱')} *`}>
              <Input
                value={name}
                onChange={setName}
                placeholder={ui('e.g. Changhua Offshore 8MW', '例：彰化離岸 8MW 風場')}
                fullWidth
                ariaLabel={ui('Farm name', '風場名稱')}
              />
            </Field>

            <div>
              <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>
                {ui('Turbine model', '風機機型')}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                {PRESETS.map(p => {
                  const active = preset === p.key;
                  return (
                    <button
                      key={p.key}
                      onClick={() => setPreset(p.key)}
                      aria-pressed={active}
                      style={{
                        padding: '8px 10px',
                        fontSize: 12,
                        borderRadius: 8,
                        border: `1px solid ${active ? C.accent : C.border}`,
                        background: active ? C.accentSoft : C.panel,
                        color: active ? C.accent : C.text,
                        cursor: 'pointer',
                        fontFamily: 'inherit',
                        fontWeight: active ? 600 : 500,
                      }}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <Field label={ui('Number of turbines', '風機數量')}>
              <Input
                type="number"
                value={turbineCount}
                onChange={v => setTurbineCount(Math.max(1, Math.min(50, parseInt(v) || 1)))}
                min={1}
                max={50}
                width={100}
                ariaLabel={ui('Number of turbines', '風機數量')}
              />
            </Field>

            <Field label={`${ui('Location', '地點')} (${ui('optional', '選填')})`}>
              <Input
                value={location}
                onChange={setLocation}
                placeholder={ui('e.g. Taiwan Strait', '例：台灣海峽')}
                fullWidth
                ariaLabel={ui('Location', '地點')}
              />
            </Field>

            <Field label={`${ui('Description', '說明')} (${ui('optional', '選填')})`}>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={2}
                placeholder={ui('Notes about this farm...', '備註...')}
                style={{
                  background: C.panel,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: 13,
                  color: C.text,
                  fontFamily: 'inherit',
                  width: '100%',
                  resize: 'none',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </Field>

            {error && (
              <div
                style={{
                  background: C.warnSoft,
                  color: C.warn,
                  border: `1px solid ${C.warn}`,
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: 13,
                }}
              >
                {error}
              </div>
            )}
          </div>

          <div
            style={{
              padding: '12px 18px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <Btn onClick={onClose} ariaLabel={ui('Cancel', '取消')}>
              {ui('Cancel', '取消')}
            </Btn>
            <Btn
              variant="primary"
              onClick={handleCreate}
              disabled={creating || !name.trim()}
              ariaLabel={ui('Create farm', '建立風場')}
            >
              {creating ? ui('Creating…', '建立中…') : ui('Create & activate', '建立並啟用')}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default FarmSelector;

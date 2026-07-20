/**
 * SettingsPage — A · Calm Operator 改版（套新元件，所有 API 不動）。
 *
 * 條件區塊：
 *   - DataSource selector
 *   - SIMULATION：simulation params + turbine spec + wind control + grid control
 *   - OPC_DA：server / progId
 *   - MODBUS_TCP：ip / port / slaveId
 *   - API 端點資訊
 */

import React, { useEffect, useState } from 'react';
import { type AppSettings, DataSourceType } from '../types';
import { Btn, Card, Field, Input, PageHeader, Select, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import type { SourceMode } from '../hooks/useSourceGate';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

const WIND_PROFILES = [
  { id: 'auto', en: 'Auto (daily pattern)', zh: '自動（日變化）' },
  { id: 'calm', en: 'Calm (2 m/s)', zh: '平靜 (2 m/s)' },
  { id: 'moderate', en: 'Moderate (8 m/s)', zh: '中等 (8 m/s)' },
  { id: 'rated', en: 'Rated (12 m/s)', zh: '額定 (12 m/s)' },
  { id: 'strong', en: 'Strong (18 m/s)', zh: '強風 (18 m/s)' },
  { id: 'storm', en: 'Storm (26 m/s)', zh: '暴風 (26 m/s)' },
  { id: 'gusty', en: 'Gusty (10 m/s)', zh: '陣風 (10 m/s)' },
  { id: 'ramp_up', en: 'Ramp up (3→15)', zh: '漸增 (3→15)' },
  { id: 'ramp_down', en: 'Ramp down (15→3)', zh: '漸減 (15→3)' },
];

const GRID_PROFILES = [
  { id: 'auto', en: 'Auto', zh: '自動' },
  { id: 'nominal', en: 'Nominal (50 Hz / 690 V)', zh: '標稱' },
  { id: 'low_freq', en: 'Low frequency', zh: '低頻' },
  { id: 'high_freq', en: 'High frequency', zh: '高頻' },
  { id: 'undervoltage', en: 'Undervoltage', zh: '欠壓' },
  { id: 'overvoltage', en: 'Overvoltage', zh: '過壓' },
  { id: 'weak_grid', en: 'Weak grid', zh: '弱電網' },
  { id: 'recovery', en: 'Recovery ramp', zh: '電網恢復' },
];

interface SettingsPageProps {
  settings: AppSettings;
  onSave: (settings: AppSettings) => void;
  lang?: 'en' | 'zh';
}

interface WindStatus {
  mode?: string;
  profile?: string;
  override_wind_speed?: number;
}
interface GridStatus {
  mode?: string;
  profile?: string;
  override_frequency_hz?: number;
  override_voltage_v?: number;
}
interface TurbineSpec {
  rated_power_kw?: number;
  rotor_diameter?: number;
  cut_in_speed?: number;
  rated_speed?: number;
  cut_out_speed?: number;
  gear_ratio?: number;
  max_rotor_rpm?: number;
  nominal_voltage?: number;
  curtailment_kw?: number | null;
}

/**
 * Section — 卡片式區塊。**必須定義在 SettingsPage 之外**（module scope）。
 *
 * 若定義在 render body 內，每次 SettingsPage re-render（改任何設定的本地 state、或每 5 秒
 * 刷新 wind/grid 狀態）都會生出**新的元件 identity** → React 視為不同型別 → 卸載並重建整個
 * 表單 DOM → 捲動位置與輸入焦點被重置回頁頂。這正是使用者回報「改任何設定畫面就跳回 top、
 * 停不在原地」的根因（WMOM-20260720-05）。移到 module scope 後 identity 穩定，就地 reconcile、
 * 不再重建。
 */
const Section: React.FC<{
  title: React.ReactNode;
  tone?: 'accent' | 'amber' | 'info' | 'warn';
  children: React.ReactNode;
}> = ({ title, tone = 'accent', children }) => {
  const { C } = useTheme();
  const tonePalette = {
    accent: C.accent,
    amber: C.amber,
    info: C.info,
    warn: C.warn,
  };
  return (
    <Card style={{ marginBottom: 14, borderLeft: `4px solid ${tonePalette[tone]}` }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: C.text, marginBottom: 14 }}>{title}</h3>
      {children}
    </Card>
  );
};

const SettingsPage: React.FC<SettingsPageProps> = ({ settings, onSave, lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [formData, setFormData] = useState<AppSettings>(settings);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success'>('idle');
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  // 目前實際來源種類（WMOM-20260720-06 / DEC-20260720-01）：風況/電網/機組是「即時模擬」的即時
  // 調整，只在 simulation 來源下有作用。view/live/情境下應停用（情境風況於生成時就固定）。
  // undefined＝載入中；null＝查不到（fail-open，不因狀態查詢失敗就把控制藏起來）。
  const [sourceKind, setSourceKind] = useState<SourceMode | null | undefined>(undefined);

  // wind / grid state
  const [windStatus, setWindStatus] = useState<WindStatus | null>(null);
  const [windProfile, setWindProfile] = useState('auto');
  const [customWind, setCustomWind] = useState({ speed: '10', direction: '270', temp: '25', turbulence: '0.1' });
  const [windMsg, setWindMsg] = useState('');
  const [gridStatus, setGridStatus] = useState<GridStatus | null>(null);
  const [gridProfile, setGridProfile] = useState('auto');
  const [customGrid, setCustomGrid] = useState({ frequency: '50.0', voltage: '690' });
  const [gridMsg, setGridMsg] = useState('');

  // turbine spec
  const [, setTurbineSpec] = useState<TurbineSpec | null>(null);
  const [specPresets, setSpecPresets] = useState<Record<string, TurbineSpec>>({});
  const [specMsg, setSpecMsg] = useState('');
  const [editSpec, setEditSpec] = useState<Record<string, string>>({});

  useEffect(() => {
    setFormData(settings);
  }, [settings]);

  const refreshWindStatus = () => {
    fetch(`${API_BASE}/api/config/wind`)
      .then(r => {
        setApiConnected(true);
        return r.json();
      })
      .then(setWindStatus)
      .catch(() => setApiConnected(false));
  };
  const refreshGridStatus = () => {
    fetch(`${API_BASE}/api/config/grid`)
      .then(r => r.json())
      .then(setGridStatus)
      .catch(() => {});
  };
  // 隨 wind/grid 一起每 5 秒輪詢：gate 是安全網，若使用者開著本頁期間來源被別處切換（如切到
  // live），這裡要能跟上、及時擋掉即時控制，而非停在 mount 當下的過期狀態（review Should-fix）。
  const refreshSourceKind = () => {
    fetch(`${API_BASE}/api/source/status`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { kind?: SourceMode | null } | null) => setSourceKind(data ? data.kind ?? null : null))
      .catch(() => setSourceKind(null));
  };

  useEffect(() => {
    refreshWindStatus();
    refreshGridStatus();
    refreshSourceKind();
    const id = setInterval(() => {
      refreshWindStatus();
      refreshGridStatus();
      refreshSourceKind();
    }, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/config/turbine-spec`)
      .then(r => r.json())
      .then((spec: TurbineSpec) => {
        setTurbineSpec(spec);
        setEditSpec({
          rated_power_kw: String(spec.rated_power_kw ?? 5000),
          rotor_diameter: String(spec.rotor_diameter ?? 126),
          cut_in_speed: String(spec.cut_in_speed ?? 3),
          rated_speed: String(spec.rated_speed ?? 12),
          cut_out_speed: String(spec.cut_out_speed ?? 25),
          gear_ratio: String(spec.gear_ratio ?? 100),
          max_rotor_rpm: String(spec.max_rotor_rpm ?? 15),
          nominal_voltage: String(spec.nominal_voltage ?? 690),
          curtailment_kw: spec.curtailment_kw != null ? String(spec.curtailment_kw) : '',
        });
      })
      .catch(() => {});
    fetch(`${API_BASE}/api/config/turbine-spec/presets`)
      .then(r => r.json())
      .then(setSpecPresets)
      .catch(() => {});
  }, []);

  // ─── handlers (API 不動) ─────────────────────────────────

  const handleSetProfile = async (profile: string) => {
    setWindProfile(profile);
    try {
      const res = await fetch(`${API_BASE}/api/config/wind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setWindMsg(u(`Switched to: ${profile}`, `已切換: ${profile}`));
      setApiConnected(true);
    } catch {
      setWindMsg(u(`Failed (${API_BASE} not responding)`, `無法連線 (${API_BASE})`));
      setApiConnected(false);
    }
    refreshWindStatus();
    setTimeout(() => setWindMsg(''), 5000);
  };

  const handleSetCustomWind = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/config/wind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          windSpeed: parseFloat(customWind.speed) || null,
          windDirection: parseFloat(customWind.direction) || null,
          ambientTemp: parseFloat(customWind.temp) || null,
          turbulence: parseFloat(customWind.turbulence) || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setWindMsg(u('Custom wind applied', '已套用自訂風況'));
      setApiConnected(true);
    } catch {
      setWindMsg(u(`Failed (${API_BASE} not responding)`, `無法連線 (${API_BASE})`));
      setApiConnected(false);
    }
    refreshWindStatus();
    setTimeout(() => setWindMsg(''), 5000);
  };

  const handleSetGridProfile = async (profile: string) => {
    setGridProfile(profile);
    await fetch(`${API_BASE}/api/config/grid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile }),
    });
    setGridMsg(u(`Grid: ${profile}`, `電網: ${profile}`));
    refreshGridStatus();
    setTimeout(() => setGridMsg(''), 3000);
  };

  const handleSetCustomGrid = async () => {
    await fetch(`${API_BASE}/api/config/grid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        frequencyHz: parseFloat(customGrid.frequency) || null,
        voltageV: parseFloat(customGrid.voltage) || null,
      }),
    });
    setGridMsg(u('Custom grid applied', '已套用自訂電網'));
    refreshGridStatus();
    setTimeout(() => setGridMsg(''), 3000);
  };

  const handleSetPreset = async (preset: string) => {
    const res = await fetch(`${API_BASE}/api/config/turbine-spec`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset }),
    });
    if (res.ok) {
      const data = await res.json();
      setTurbineSpec(data.spec);
      setEditSpec({
        rated_power_kw: String(data.spec.rated_power_kw),
        rotor_diameter: String(data.spec.rotor_diameter),
        cut_in_speed: String(data.spec.cut_in_speed),
        rated_speed: String(data.spec.rated_speed),
        cut_out_speed: String(data.spec.cut_out_speed),
        gear_ratio: String(data.spec.gear_ratio),
        max_rotor_rpm: String(data.spec.max_rotor_rpm),
        nominal_voltage: String(data.spec.nominal_voltage),
        curtailment_kw: data.spec.curtailment_kw != null ? String(data.spec.curtailment_kw) : '',
      });
      setSpecMsg(u(`Applied: ${preset}`, `已套用: ${preset}`));
      setTimeout(() => setSpecMsg(''), 3000);
    }
  };

  const handleApplySpec = async () => {
    const payload: Record<string, number | null> = {};
    for (const [k, v] of Object.entries(editSpec)) {
      const s = String(v ?? '');
      payload[k] = s === '' ? null : parseFloat(s);
    }
    const res = await fetch(`${API_BASE}/api/config/turbine-spec`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const data = await res.json();
      setTurbineSpec(data.spec);
      setSpecMsg(u('Turbine spec updated', '已更新風機規格'));
      setTimeout(() => setSpecMsg(''), 3000);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // 防守（review Must-fix）：gate 只藏 UI，不擋「編輯到一半、來源在背景被別處切走（5 秒輪詢抓到
    // → liveTuningBlocked 翻真 → Section 隱藏）後，formData 仍留著剛才的 stale 編輯值」被儲存夾帶
    // 送出。若目前 blocked，送出時把模擬參數還原成 settings（＝未變動），避免 useSettings 偵測到
    // simChanged → POST /api/config/simulation → 後端 switch_mode 悄悄把來源切回 simulation（live
    // 時斷現場 SCADA）。註：只在送出當下還原，formData 本身保留使用者編輯值，來源切回即時模擬時
    // 編輯不遺失。
    const payload = liveTuningBlocked ? { ...formData, simulation: settings.simulation } : formData;
    onSave(payload);
    setSaveStatus('success');
    setTimeout(() => setSaveStatus('idle'), 2000);
  };

  const isSim = formData.dataSource === DataSourceType.SIMULATION;
  // 只在「明確知道」目前來源是 view / live 時才擋（fail-open：載入中/查不到就照常顯示，
  // 不因狀態查詢失敗而把即時模擬使用者的控制藏掉）。
  const liveTuningBlocked = sourceKind === 'view' || sourceKind === 'live';
  const sourceKindLabel = (kind: SourceMode | null | undefined): string => {
    if (kind === 'view') return u('a past scenario (view mode)', '調閱過去情境');
    if (kind === 'live') return u('the live data connection', '實際資料對接');
    // 防禦性 fallback：目前唯一呼叫點在 liveTuningBlocked（kind 必為 view/live），不會走到這裡。
    return u('the current source', '目前來源');
  };

  return (
    <form onSubmit={handleSubmit}>
      <PageHeader
        title={u('Settings', '系統設定')}
        sub={u(
          'Data source · simulation · wind / grid override · turbine spec',
          '資料源・模擬參數・風況/電網覆寫・風機規格',
        )}
        actions={
          <>
            {saveStatus === 'success' && <StatusPill tone="ok">{u('Saved!', '已儲存')}</StatusPill>}
            <Btn type="submit" variant="primary" ariaLabel={u('Save settings', '儲存設定')}>
              {u('Save settings', '儲存設定')}
            </Btn>
          </>
        }
      />

      {/* Backend warning */}
      {apiConnected === false && (
        <Card tone="warn" style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, color: C.warn }}>
            {u('Cannot connect to backend API', '無法連線到後端 API')}
          </div>
          <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
            {u(`Trying: ${API_BASE}`, `目前嘗試連線: ${API_BASE}`)}
          </div>
        </Card>
      )}

      {/* Data source */}
      <Section title={u('Data source', '資料源')}>
        <Field label={u('Data source', '資料源')}>
          <Select
            value={formData.dataSource}
            onChange={v => setFormData(prev => ({ ...prev, dataSource: v as DataSourceType }))}
            options={[
              { value: DataSourceType.MOCK, label: u('Mock (frontend only)', 'Mock（純前端）') },
              { value: DataSourceType.SIMULATION, label: u('Physics simulation', '物理模擬') },
              { value: DataSourceType.OPC_DA, label: u('OPC DA Server', 'OPC DA 伺服器') },
              { value: DataSourceType.MODBUS_TCP, label: u('Modbus TCP Gateway', 'Modbus TCP 閘道') },
            ]}
            ariaLabel={u('Data source', '資料源')}
            fullWidth
          />
        </Field>
        <p style={{ fontSize: 12, color: C.sub, marginTop: 8, marginBottom: 0 }}>
          {u(
            'Mock: random data; Simulation: physics model via backend; OPC DA / Modbus: real wind farm.',
            'Mock 為前端隨機資料；Simulation 走後端物理模型；OPC DA / Modbus 連線真實風場。',
          )}
        </p>
      </Section>

      {/* Simulation — 亦 gate：view/live 下按「儲存設定」若 sim 參數有變，useSettings 會
          POST /api/config/simulation → 後端 set_simulation 落到 switch_mode，把來源**悄悄切回
          simulation**（live 時等於斷現場 SCADA）。故一併藏起、不讓改（review Must-fix）。 */}
      {isSim && !liveTuningBlocked && (
        <Section title={u('Simulation', '模擬參數')} tone="accent">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
            }}
          >
            <Field label={u('Turbine count', '風機數')}>
              <Input
                type="number"
                value={formData.simulation.turbineCount}
                onChange={v =>
                  setFormData(p => ({ ...p, simulation: { ...p.simulation, turbineCount: Number(v) || 0 } }))
                }
                min={1}
                max={100}
                fullWidth
              />
            </Field>
            <Field label={u('Base wind speed (m/s)', '基準風速 (m/s)')}>
              <Input
                type="number"
                step="0.5"
                value={formData.simulation.baseWindSpeed}
                onChange={v =>
                  setFormData(p => ({ ...p, simulation: { ...p.simulation, baseWindSpeed: Number(v) || 0 } }))
                }
                min={0}
                max={30}
                fullWidth
              />
            </Field>
            <Field label={u('Turbulence intensity', '湍流強度')}>
              <Input
                type="number"
                step="0.01"
                value={formData.simulation.turbulenceIntensity}
                onChange={v =>
                  setFormData(p => ({
                    ...p,
                    simulation: { ...p.simulation, turbulenceIntensity: Number(v) || 0 },
                  }))
                }
                min={0}
                max={0.5}
                fullWidth
              />
            </Field>
          </div>
        </Section>
      )}

      {/* OPC DA */}
      {formData.dataSource === DataSourceType.OPC_DA && (
        <Section title={u('OPC DA Server', 'OPC DA 伺服器')} tone="accent">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <Field label={u('Server name / IP', '伺服器名稱 / IP')}>
              <Input
                value={formData.opcDa.server}
                onChange={v => setFormData(p => ({ ...p, opcDa: { ...p.opcDa, server: v } }))}
                placeholder="localhost"
                fullWidth
              />
            </Field>
            <Field label="ProgID">
              <Input
                value={formData.opcDa.progId}
                onChange={v => setFormData(p => ({ ...p, opcDa: { ...p.opcDa, progId: v } }))}
                placeholder="BACHMANN.OPCEnterpriseServer.2"
                fullWidth
                monospace
              />
            </Field>
          </div>
        </Section>
      )}

      {/* Modbus */}
      {formData.dataSource === DataSourceType.MODBUS_TCP && (
        <Section title={u('Modbus TCP Gateway', 'Modbus TCP 閘道')} tone="accent">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <Field label="IP">
              <Input
                value={formData.modbusTcp.ip}
                onChange={v => setFormData(p => ({ ...p, modbusTcp: { ...p.modbusTcp, ip: v } }))}
                placeholder="10.128.1.12"
                fullWidth
                monospace
              />
            </Field>
            <Field label={u('Port', '埠號')}>
              <Input
                type="number"
                value={formData.modbusTcp.port}
                onChange={v => setFormData(p => ({ ...p, modbusTcp: { ...p.modbusTcp, port: Number(v) || 0 } }))}
                fullWidth
              />
            </Field>
            <Field label="Slave ID">
              <Input
                type="number"
                value={formData.modbusTcp.slaveId}
                onChange={v => setFormData(p => ({ ...p, modbusTcp: { ...p.modbusTcp, slaveId: Number(v) || 0 } }))}
                fullWidth
              />
            </Field>
          </div>
        </Section>
      )}

      {/* view/live 下：模擬參數 / 風況 / 電網 / 機組皆以說明取代互動控制（DEC-20260720-01 + review
          Must-fix）——不只是「無作用」，改了按儲存還會把來源切回 simulation（live 時斷現場連線）。 */}
      {isSim && liveTuningBlocked && (
        <Section title={u('Simulation settings unavailable here', '模擬設定目前不可調整')} tone="info">
          <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.6 }}>
            {u(
              `You're currently on: ${sourceKindLabel(sourceKind)}. Simulation settings (parameters / wind / grid / turbine spec) apply only while the live simulation source is running — and saving a change here would switch the source back to simulation${sourceKind === 'live' ? ', disconnecting the live SCADA feed' : ''}. A scenario's wind is fixed at generation time.`,
              `目前來源：${sourceKindLabel(sourceKind)}。模擬設定（模擬參數 / 風況 / 電網 / 機組規格）只在「即時模擬」來源執行時有意義——在這裡改動並儲存會把來源切回「即時模擬」${sourceKind === 'live' ? '（實際對接時等於中斷現場 SCADA 連線）' : ''}。情境的風況於生成時就已固定。`,
            )}
          </div>
        </Section>
      )}

      {/* Turbine spec */}
      {isSim && !liveTuningBlocked && (
        <Section title={u('Turbine specification', '風機規格')} tone="info">
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
              {u('Presets', '預設機型')}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {Object.entries(specPresets).map(([name, spec]) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => handleSetPreset(name)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 6,
                    border: `1px solid ${C.border}`,
                    background: C.panelMuted,
                    color: C.sub,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  {name} ({(spec as TurbineSpec).rated_power_kw}kW)
                </button>
              ))}
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 10,
              marginBottom: 12,
            }}
          >
            {[
              { key: 'rated_power_kw', en: 'Rated kW', zh: '額定功率 kW' },
              { key: 'rotor_diameter', en: 'Rotor diameter m', zh: '葉輪直徑 m' },
              { key: 'cut_in_speed', en: 'Cut-in m/s', zh: '切入風速 m/s' },
              { key: 'rated_speed', en: 'Rated m/s', zh: '額定風速 m/s' },
              { key: 'cut_out_speed', en: 'Cut-out m/s', zh: '切出風速 m/s' },
              { key: 'gear_ratio', en: 'Gear ratio', zh: '齒輪比' },
              { key: 'max_rotor_rpm', en: 'Max RPM', zh: '最大轉速' },
              { key: 'nominal_voltage', en: 'Nominal V', zh: '額定電壓' },
            ].map(f => (
              <Field key={f.key} label={u(f.en, f.zh)}>
                <Input
                  type="number"
                  step="any"
                  value={editSpec[f.key] ?? ''}
                  onChange={v => setEditSpec(p => ({ ...p, [f.key]: v }))}
                  fullWidth
                  monospace
                />
              </Field>
            ))}
          </div>

          <Card tone="warn" padding={14}>
            <Field
              label={u('Power curtailment (kW)', '功率限載 kW')}
              hint={u(
                'Empty = no curtailment. Pitch increases automatically to limit power.',
                '留空 = 不限載；限載時 pitch 自動加大限制功率。',
              )}
            >
              <Input
                type="number"
                step="100"
                value={editSpec.curtailment_kw ?? ''}
                onChange={v => setEditSpec(p => ({ ...p, curtailment_kw: v }))}
                placeholder={u('Empty = no curtailment', '留空 = 不限載')}
                width={200}
                monospace
              />
            </Field>
          </Card>

          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Btn type="button" variant="primary" onClick={handleApplySpec} ariaLabel={u('Apply spec', '套用規格')}>
              {u('Apply turbine spec', '套用風機規格')}
            </Btn>
            {specMsg && <StatusPill tone="accent">{specMsg}</StatusPill>}
          </div>
        </Section>
      )}

      {/* Wind control */}
      {isSim && !liveTuningBlocked && (
        <Section title={u('Wind condition control', '風況控制')} tone="info">
          {windStatus && (
            <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
              {u('Mode', '模式')}: <span style={{ color: C.text, fontWeight: 600 }}>{windStatus.mode}</span>
              {windStatus.profile && <span> ({windStatus.profile})</span>}
              {windStatus.override_wind_speed != null && (
                <span style={{ marginLeft: 10 }}>
                  {u('Wind', '風速')}:{' '}
                  <span style={{ color: C.accent, fontFamily: 'JetBrains Mono, monospace' }}>
                    {windStatus.override_wind_speed} m/s
                  </span>
                </span>
              )}
            </div>
          )}

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
              {u('Quick profiles', '快速情境')}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {WIND_PROFILES.map(p => {
                const active = windProfile === p.id || windStatus?.profile === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSetProfile(p.id)}
                    aria-pressed={active}
                    style={{
                      padding: '4px 10px',
                      fontSize: 12,
                      borderRadius: 6,
                      border: `1px solid ${active ? C.info : C.border}`,
                      background: active ? C.infoSoft : C.panelMuted,
                      color: active ? C.info : C.sub,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontWeight: active ? 600 : 500,
                    }}
                  >
                    {u(p.en, p.zh)}
                  </button>
                );
              })}
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
              marginBottom: 10,
            }}
          >
            <Field label={u('Wind (m/s)', '風速 (m/s)')}>
              <Input
                type="number"
                step="0.5"
                value={customWind.speed}
                onChange={v => setCustomWind(p => ({ ...p, speed: v }))}
                fullWidth
                monospace
              />
            </Field>
            <Field label={u('Direction (°)', '風向 (°)')}>
              <Input
                type="number"
                step="5"
                value={customWind.direction}
                onChange={v => setCustomWind(p => ({ ...p, direction: v }))}
                fullWidth
                monospace
              />
            </Field>
            <Field label={u('Temp (°C)', '溫度 (°C)')}>
              <Input
                type="number"
                step="1"
                value={customWind.temp}
                onChange={v => setCustomWind(p => ({ ...p, temp: v }))}
                fullWidth
                monospace
              />
            </Field>
            <Field label={u('Turbulence', '湍流')}>
              <Input
                type="number"
                step="0.05"
                value={customWind.turbulence}
                onChange={v => setCustomWind(p => ({ ...p, turbulence: v }))}
                fullWidth
                monospace
              />
            </Field>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Btn type="button" onClick={handleSetCustomWind} variant="primary">
              {u('Apply custom wind', '套用自訂風況')}
            </Btn>
            {windMsg && <StatusPill tone="info">{windMsg}</StatusPill>}
          </div>
        </Section>
      )}

      {/* Grid control */}
      {isSim && !liveTuningBlocked && (
        <Section title={u('Grid control', '電網控制')} tone="amber">
          {gridStatus && (
            <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
              {u('Mode', '模式')}:{' '}
              <span style={{ color: C.text, fontWeight: 600 }}>{gridStatus.mode}</span>
              {gridStatus.profile && <span> ({gridStatus.profile})</span>}
              {gridStatus.override_frequency_hz != null && (
                <span style={{ marginLeft: 10 }}>
                  {u('Freq', '頻率')}:{' '}
                  <span style={{ color: C.amber, fontFamily: 'JetBrains Mono, monospace' }}>
                    {gridStatus.override_frequency_hz} Hz
                  </span>
                </span>
              )}
              {gridStatus.override_voltage_v != null && (
                <span style={{ marginLeft: 10 }}>
                  {u('Voltage', '電壓')}:{' '}
                  <span style={{ color: C.amber, fontFamily: 'JetBrains Mono, monospace' }}>
                    {gridStatus.override_voltage_v} V
                  </span>
                </span>
              )}
            </div>
          )}

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
              {u('Grid profiles', '電網情境')}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {GRID_PROFILES.map(p => {
                const active = gridProfile === p.id || gridStatus?.profile === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleSetGridProfile(p.id)}
                    aria-pressed={active}
                    style={{
                      padding: '4px 10px',
                      fontSize: 12,
                      borderRadius: 6,
                      border: `1px solid ${active ? C.amber : C.border}`,
                      background: active ? C.amberSoft : C.panelMuted,
                      color: active ? C.amber : C.sub,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontWeight: active ? 600 : 500,
                    }}
                  >
                    {u(p.en, p.zh)}
                  </button>
                );
              })}
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
              marginBottom: 10,
            }}
          >
            <Field label={u('Frequency (Hz)', '頻率 (Hz)')}>
              <Input
                type="number"
                step="0.05"
                value={customGrid.frequency}
                onChange={v => setCustomGrid(p => ({ ...p, frequency: v }))}
                fullWidth
                monospace
              />
            </Field>
            <Field label={u('Voltage (V)', '電壓 (V)')}>
              <Input
                type="number"
                step="1"
                value={customGrid.voltage}
                onChange={v => setCustomGrid(p => ({ ...p, voltage: v }))}
                fullWidth
                monospace
              />
            </Field>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Btn type="button" onClick={handleSetCustomGrid} variant="primary">
              {u('Apply custom grid', '套用自訂電網')}
            </Btn>
            {gridMsg && <StatusPill tone="amber">{gridMsg}</StatusPill>}
          </div>
        </Section>
      )}

      {/* API endpoints info */}
      <Section title={u('API endpoints', 'API 端點')} tone="accent">
        <div
          style={{
            fontSize: 12,
            color: C.sub,
            fontFamily: 'JetBrains Mono, monospace',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          <div>GET /api/turbines — All turbines</div>
          <div>GET /api/turbines/farm-status — Farm KPIs</div>
          <div>GET /api/turbines/WT001/history — Historical data</div>
          <div>GET /api/export/snapshot — Current state</div>
          <div>GET /api/export/history?turbine_id=WT001&format=csv</div>
          <div>WS /ws/realtime — Real-time stream</div>
        </div>
      </Section>
    </form>
  );
};

export default SettingsPage;

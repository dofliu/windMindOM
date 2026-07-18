/**
 * ScenarioPage — Scenario 模式的「情境設定」頁（WMOM-20260718-04, DEC-20260718-01）。
 *
 * DEC-20260718-01 把模擬主路徑定為 Scenario：使用者定義「風場 + 風況 + 時長 + 故障排程」
 * → 一次批次生成可重現資料集 → 探索 + 練運維。本頁即該「情境設定精靈」：
 *   1. 情境設定：目前風場（側邊欄切換）+ 風況 profile + 時長 + 解析度
 *   2. 故障排程：一列一支排定故障（場景 / 風機 / 第幾小時發生 / 發展速率），可增可刪
 *   3. 生成：先套風況（POST /api/config/wind）再批次生成（POST /api/config/simulation/generate-bulk
 *      帶 fault_schedule）→ 顯示結果（資料筆數 / 注入故障數 / 最終故障狀態）
 *   4. 生成後可一鍵跳去「歷史資料」探索該情境
 *
 * 全程走 `authFetch`（enforce-ready：generate-bulk / wind / faults 端點需 SUPERVISOR / 登入）。
 * free-run 即時模擬保留為預設落地（輕量看一眼），正式的情境練運維走本頁批次。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Btn, Card, Field, Input, PageHeader, Select, Stat, StatusPill, type PillTone } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface ScenarioOption {
  id: string;
  name_en: string;
  name_zh: string;
}

interface FarmLite {
  farm_id: string;
  name: string;
  turbine_count: number;
}

interface FinalFaultStatus {
  turbine_id: string;
  scenario_id?: string;
  name_en?: string;
  name_zh?: string;
  severity: number;
  phase: string;
  tripped: boolean;
}

interface GenerateResult {
  status: string;
  duration_hours: number;
  time_step: number;
  total_readings: number;
  faults_injected: number;
  final_fault_status: FinalFaultStatus[];
  storage_stats: { db_size_mb?: number };
}

/** 一列排定故障（前端狀態；送出時轉為後端 fault_schedule 條目）。 */
interface ScheduledFault {
  key: number;
  scenarioId: string;
  turbineId: string;
  atHour: number;
  severityRate: number;
}

const WIND_PROFILES: { value: string; en: string; zh: string }[] = [
  { value: 'calm', en: 'Calm (~4 m/s)', zh: '微風（~4 m/s）' },
  { value: 'moderate', en: 'Moderate (~10 m/s)', zh: '中風（~10 m/s）' },
  { value: 'rated', en: 'Rated (~13 m/s)', zh: '額定風（~13 m/s）' },
  { value: 'strong', en: 'Strong (~18 m/s)', zh: '強風（~18 m/s）' },
  { value: 'storm', en: 'Storm (>25 m/s, cut-out)', zh: '暴風（>25 m/s 停機）' },
  { value: 'gusty', en: 'Gusty', zh: '陣風' },
  { value: 'ramp_up', en: 'Ramp up', zh: '風速漸增' },
  { value: 'ramp_down', en: 'Ramp down', zh: '風速漸減' },
];

const DURATION_PRESETS: { hours: number; en: string; zh: string }[] = [
  { hours: 24, en: '1 day', zh: '1 天' },
  { hours: 168, en: '1 week', zh: '1 週' },
  { hours: 720, en: '1 month', zh: '1 月' },
];

const RESOLUTIONS: { value: number; en: string; zh: string }[] = [
  { value: 10, en: '10s (high-res)', zh: '10 秒（高解析）' },
  { value: 60, en: '60s (standard)', zh: '60 秒（標準）' },
  { value: 300, en: '300s (fast)', zh: '300 秒（快速）' },
];

const phaseTone = (phase: string): PillTone => {
  if (phase === 'critical' || phase === 'advanced') return 'warn';
  return 'amber';
};

interface Props {
  lang?: 'en' | 'zh';
  /** 生成後「查看歷史資料」的跳頁回呼（App 接到 history view）。 */
  onExplore?: () => void;
}

const ScenarioPage: React.FC<Props> = ({ lang = 'zh', onExplore }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [scenarios, setScenarios] = useState<ScenarioOption[]>([]);
  const [farm, setFarm] = useState<FarmLite | null>(null);

  const [windProfile, setWindProfile] = useState('moderate');
  const [durationHours, setDurationHours] = useState(168);
  const [timeStep, setTimeStep] = useState(60);
  const [faults, setFaults] = useState<ScheduledFault[]>([]);

  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const nextKey = useRef(1);

  useEffect(() => {
    authFetch(`${API_BASE}/api/faults/scenarios`)
      .then(r => (r.ok ? r.json() : []))
      .then((data: ScenarioOption[]) => setScenarios(Array.isArray(data) ? data : []))
      .catch(() => {});
    authFetch(`${API_BASE}/api/farms`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { farms?: FarmLite[]; active_farm_id?: string } | null) => {
        if (!data?.farms) return;
        const active = data.farms.find(f => f.farm_id === data.active_farm_id) ?? data.farms[0] ?? null;
        setFarm(active);
      })
      .catch(() => {});
  }, []);

  const turbineCount = farm?.turbine_count ?? 14;
  const turbineOptions = useMemo(
    () => Array.from({ length: turbineCount }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`),
    [turbineCount],
  );

  // 估算資料筆數（給使用者對生成量的直覺）：步數 × 風機數。
  const estimatedReadings = Math.round((durationHours * 3600) / timeStep) * turbineCount;

  const scenarioLabel = (id: string): string => {
    const s = scenarios.find(x => x.id === id);
    return s ? (lang === 'zh' ? s.name_zh : s.name_en) : id;
  };

  const addFault = () => {
    const firstScenario = scenarios[0]?.id ?? '';
    setFaults(prev => [
      ...prev,
      {
        key: nextKey.current++,
        scenarioId: firstScenario,
        turbineId: turbineOptions[0] ?? 'WT001',
        atHour: Math.max(0, Math.round(durationHours / 2)),
        severityRate: 0.002,
      },
    ]);
  };

  const removeFault = (key: number) => setFaults(prev => prev.filter(f => f.key !== key));

  const updateFault = (key: number, patch: Partial<ScheduledFault>) =>
    setFaults(prev => prev.map(f => (f.key === key ? { ...f, ...patch } : f)));

  const handleGenerate = async () => {
    setGenerating(true);
    setResult(null);
    setError('');
    setMessage(u('Applying wind & generating scenario…', '套用風況並生成情境資料集…（時長越長越久）'));
    try {
      // 1. 套風況 profile（讓批次以此風況跑）。
      await authFetch(`${API_BASE}/api/config/wind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: windProfile }),
      });

      // 2. 批次生成（帶故障排程）。
      const res = await authFetch(`${API_BASE}/api/config/simulation/generate-bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          duration_hours: durationHours,
          time_step: timeStep,
          fault_schedule: faults.map(f => ({
            scenario_id: f.scenarioId,
            turbine_id: f.turbineId,
            at_hour: f.atHour,
            severity_rate: f.severityRate,
          })),
        }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
        } catch {
          /* ignore parse error */
        }
        setError(u(`Generation failed: ${detail}`, `生成失敗：${detail}`));
        setMessage('');
        return;
      }
      const data = (await res.json()) as GenerateResult;
      setResult(data);
      setMessage(u('Scenario dataset generated.', '情境資料集已生成。'));
    } catch {
      setError(u('Network error during generation.', '生成時發生網路錯誤。'));
      setMessage('');
    } finally {
      setGenerating(false);
    }
  };

  const canGenerate = !generating && scenarios.length > 0;

  return (
    <div>
      <PageHeader
        title={u('Scenario Simulation', '情境模擬')}
        sub={u(
          'Define farm · wind · duration · scheduled faults → generate one reproducible dataset → explore & practice O&M',
          '定義風場・風況・時長・排定故障 → 一次生成可重現資料集 → 探索並演練運維',
        )}
        actions={
          <Btn
            variant="primary"
            onClick={handleGenerate}
            disabled={!canGenerate}
            ariaLabel={u('Generate scenario', '生成情境')}
          >
            {generating ? u('Generating…', '生成中…') : u('Generate scenario', '生成情境')}
          </Btn>
        }
      />

      {message && (
        <div style={{ marginBottom: 14 }}>
          <StatusPill tone="accent" size="md">
            {message}
          </StatusPill>
        </div>
      )}
      {error && (
        <div
          style={{
            marginBottom: 14,
            background: C.warnSoft,
            color: C.warn,
            border: `1px solid ${C.warn}`,
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: 13,
          }}
          role="alert"
        >
          {error}
        </div>
      )}

      {/* ── 情境設定 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.text }}>
          {u('Scenario definition', '情境設定')}
        </div>

        <div style={{ marginBottom: 14, fontSize: 13, color: C.sub }}>
          {u('Wind farm', '風場')}：
          <span style={{ color: C.text, fontWeight: 600 }}>
            {farm ? `${farm.name}（${farm.turbine_count} ${u('turbines', '台')}）` : u('loading…', '載入中…')}
          </span>
          <span style={{ color: C.faint, marginLeft: 8 }}>
            {u('· switch via the sidebar', '· 用側邊欄切換風場')}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 12,
          }}
        >
          <Field label={u('Wind profile', '風況')}>
            <Select
              value={windProfile}
              onChange={setWindProfile}
              options={WIND_PROFILES.map(p => ({ value: p.value, label: u(p.en, p.zh) }))}
              ariaLabel={u('Wind profile', '風況')}
              fullWidth
            />
          </Field>
          <Field label={u('Duration (hours)', '時長（小時）')}>
            <Input
              type="number"
              min={1}
              max={8760}
              value={String(durationHours)}
              onChange={v => setDurationHours(Math.max(1, Math.min(8760, parseInt(v) || 1)))}
              fullWidth
              monospace
              ariaLabel={u('Duration hours', '時長小時')}
            />
          </Field>
          <Field label={u('Resolution', '解析度')}>
            <Select
              value={String(timeStep)}
              onChange={v => setTimeStep(parseInt(v) || 60)}
              options={RESOLUTIONS.map(r => ({ value: String(r.value), label: u(r.en, r.zh) }))}
              ariaLabel={u('Resolution', '解析度')}
              fullWidth
            />
          </Field>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: C.sub }}>{u('Presets:', '快速設定：')}</span>
          {DURATION_PRESETS.map(p => (
            <Btn
              key={p.hours}
              size="sm"
              variant={durationHours === p.hours ? 'primary' : 'secondary'}
              onClick={() => setDurationHours(p.hours)}
              ariaLabel={u(p.en, p.zh)}
            >
              {u(p.en, p.zh)}
            </Btn>
          ))}
          <span style={{ fontSize: 11, color: C.faint, marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace' }}>
            ≈ {estimatedReadings.toLocaleString()} {u('readings', '筆資料')}
          </span>
        </div>
      </Card>

      {/* ── 故障排程 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 14,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {u('Fault schedule', '故障排程')}{' '}
            <span style={{ color: C.faint, fontWeight: 400 }}>({faults.length})</span>
          </div>
          <Btn
            size="sm"
            variant="secondary"
            onClick={addFault}
            disabled={scenarios.length === 0}
            ariaLabel={u('Add fault', '新增故障')}
          >
            + {u('Add fault', '新增故障')}
          </Btn>
        </div>

        {faults.length === 0 ? (
          <div style={{ fontSize: 13, color: C.faint, padding: '8px 0' }}>
            {u(
              'No scheduled faults — generates a clean wind-only dataset. Add a fault to practice O&M on a reproducible case.',
              '無排定故障 — 生成純風況資料集。加一支故障即可在可重現案例上演練運維。',
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {faults.map(f => {
              const outOfRange = f.atHour >= durationHours;
              return (
                <div
                  key={f.key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(160px, 2fr) minmax(110px, 1fr) minmax(120px, 1fr) minmax(120px, 1fr) auto',
                    gap: 8,
                    alignItems: 'end',
                    padding: '10px',
                    background: C.panelMuted,
                    borderRadius: 8,
                  }}
                >
                  <Field label={u('Fault scenario', '故障場景')}>
                    <Select
                      value={f.scenarioId}
                      onChange={v => updateFault(f.key, { scenarioId: v })}
                      options={scenarios.map(s => ({ value: s.id, label: lang === 'zh' ? s.name_zh : s.name_en }))}
                      ariaLabel={u('Fault scenario', '故障場景')}
                      fullWidth
                    />
                  </Field>
                  <Field label={u('Turbine', '風機')}>
                    <Select
                      value={f.turbineId}
                      onChange={v => updateFault(f.key, { turbineId: v })}
                      options={turbineOptions.map(t => ({ value: t, label: t }))}
                      ariaLabel={u('Turbine', '風機')}
                      fullWidth
                    />
                  </Field>
                  <Field label={u('At hour', '第幾小時')}>
                    <Input
                      type="number"
                      min={0}
                      max={durationHours}
                      value={String(f.atHour)}
                      onChange={v => updateFault(f.key, { atHour: Math.max(0, parseInt(v) || 0) })}
                      fullWidth
                      monospace
                      ariaLabel={u('At hour', '第幾小時')}
                    />
                  </Field>
                  <Field label={u('Severity rate', '發展速率')}>
                    <Input
                      type="number"
                      step="0.0001"
                      min={0.00001}
                      max={0.1}
                      value={String(f.severityRate)}
                      onChange={v => updateFault(f.key, { severityRate: parseFloat(v) || 0.0002 })}
                      fullWidth
                      monospace
                      ariaLabel={u('Severity rate', '發展速率')}
                    />
                  </Field>
                  <Btn
                    size="sm"
                    variant="ghost"
                    onClick={() => removeFault(f.key)}
                    ariaLabel={u('Remove fault', '移除故障')}
                  >
                    ✕
                  </Btn>
                  {outOfRange && (
                    <div style={{ gridColumn: '1 / -1', fontSize: 11, color: C.warn }}>
                      {u(
                        `At-hour ${f.atHour} ≥ duration ${durationHours}h — this fault will not be injected.`,
                        `第 ${f.atHour} 小時 ≥ 時長 ${durationHours}h — 此故障不會被注入。`,
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── 結果 ── */}
      {result && (
        <Card>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 14,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: C.accent }}>
              {u('Scenario dataset', '情境資料集')}
            </div>
            {onExplore && (
              <Btn size="sm" variant="primary" onClick={onExplore} ariaLabel={u('View history', '查看歷史資料')}>
                {u('Explore history →', '查看歷史資料 →')}
              </Btn>
            )}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 14,
              marginBottom: result.final_fault_status?.length ? 16 : 0,
            }}
          >
            <Stat label={u('Duration', '時長')} value={`${result.duration_hours}h`} size={24} />
            <Stat
              label={u('Readings', '資料筆數')}
              value={result.total_readings.toLocaleString()}
              highlight
              size={24}
            />
            <Stat label={u('Faults injected', '注入故障數')} value={result.faults_injected} size={24} />
            <Stat
              label={u('DB size', '資料庫大小')}
              value={`${result.storage_stats?.db_size_mb ?? '—'}`}
              unit="MB"
              size={24}
            />
          </div>

          {result.final_fault_status?.length > 0 && (
            <>
              <div style={{ fontSize: 12, color: C.sub, marginBottom: 6 }}>
                {u('Final fault status', '最終故障狀態')}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ color: C.sub }}>
                      {[u('Turbine', '風機'), u('Scenario', '場景'), u('Severity', '嚴重度'), u('Phase', '階段'), u('Tripped', '跳脫')].map(h => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '6px 10px',
                            fontSize: 10,
                            color: C.faint,
                            fontWeight: 500,
                            letterSpacing: 0.5,
                            textTransform: 'uppercase',
                            borderBottom: `1px solid ${C.border}`,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.final_fault_status.map((f, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td style={{ padding: '6px 10px', fontFamily: 'JetBrains Mono, monospace', color: C.text }}>
                          {f.turbine_id}
                        </td>
                        <td style={{ padding: '6px 10px', color: C.text }}>
                          {f.scenario_id ? scenarioLabel(f.scenario_id) : f.name_zh ?? f.name_en}
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          <span
                            style={{
                              fontFamily: 'JetBrains Mono, monospace',
                              color: f.severity > 0.7 ? C.warn : f.severity > 0.4 ? C.amber : C.ok,
                            }}
                          >
                            {(f.severity * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          <StatusPill tone={phaseTone(f.phase)}>{f.phase}</StatusPill>
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          {f.tripped ? (
                            <StatusPill tone="warn">TRIP</StatusPill>
                          ) : (
                            <span style={{ color: C.sub }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
};

export default ScenarioPage;

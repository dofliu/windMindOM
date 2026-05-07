/**
 * FaultInjectionPanel — A · Calm Operator 改版（套新元件，功能不動）。
 *
 * - 上半：注入控制（場景 / 風機 / 速率 / 注入 / 清除全部 + 活躍故障表）
 * - 下半：診斷測試計畫卡片 + 結果摘要
 */

import React, { useEffect, useState } from 'react';
import type { FaultScenario } from '../types';
import {
  Btn,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  StatusPill,
  Stat,
  type PillTone,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface TestPlan {
  id: string;
  name_en: string;
  name_zh: string;
  description_en: string;
  description_zh: string;
  duration_hours: number;
  fault_count: number;
  turbines_affected: string[];
  scenarios_used: string[];
}

interface ActiveFault {
  turbine_id: string;
  scenario_id?: string;
  name_en: string;
  name_zh: string;
  severity: number;
  phase: string;
  tripped: boolean;
  active_alarms?: { type: string; code: number; desc: string }[];
}

interface TestPlanResult {
  status: string;
  plan_id: string;
  duration_hours: number;
  total_readings: number;
  faults_injected: number;
  final_fault_status: ActiveFault[];
  storage_stats: { db_size_mb?: number };
}

interface Props {
  lang?: 'en' | 'zh';
}

const phaseTone = (phase: string): PillTone => {
  if (phase === 'critical') return 'warn';
  if (phase === 'advanced') return 'warn';
  if (phase === 'developing') return 'amber';
  return 'amber';
};

const planTone = (id: string): PillTone => {
  if (id === 'basic_validation') return 'ok';
  if (id === 'subtle_challenge') return 'amber';
  if (id === 'mixed_difficulty') return 'amber';
  return 'warn';
};

const FaultInjectionPanel: React.FC<Props> = ({ lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [scenarios, setScenarios] = useState<FaultScenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState('');
  const [selectedTurbine, setSelectedTurbine] = useState('WT001');
  const [severityRate, setSeverityRate] = useState('0.005');
  const [activeFaults, setActiveFaults] = useState<ActiveFault[]>([]);
  const [message, setMessage] = useState('');

  const [testPlans, setTestPlans] = useState<TestPlan[]>([]);
  const [runningPlan, setRunningPlan] = useState<string | null>(null);
  const [planResult, setPlanResult] = useState<TestPlanResult | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/faults/scenarios`)
      .then(r => r.json())
      .then(setScenarios)
      .catch(() => {});
    fetch(`${API_BASE}/api/faults/test-plans`)
      .then(r => r.json())
      .then(setTestPlans)
      .catch(() => {});
    refreshActive();
    const id = setInterval(refreshActive, 3000);
    return () => clearInterval(id);
  }, []);

  const refreshActive = () => {
    fetch(`${API_BASE}/api/faults/active`)
      .then(r => r.json())
      .then(setActiveFaults)
      .catch(() => {});
  };

  const handleInject = async () => {
    if (!selectedScenario) return;
    const res = await fetch(`${API_BASE}/api/faults/inject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenarioId: selectedScenario,
        turbineId: selectedTurbine,
        severityRate: parseFloat(severityRate),
      }),
    });
    if (res.ok) {
      setMessage(u(`Fault injected to ${selectedTurbine}`, `已注入故障到 ${selectedTurbine}`));
      refreshActive();
    }
    setTimeout(() => setMessage(''), 3000);
  };

  const handleClearAll = async () => {
    await fetch(`${API_BASE}/api/faults/clear`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    setMessage(u('All faults cleared', '已清除所有故障'));
    refreshActive();
    setTimeout(() => setMessage(''), 3000);
  };

  const handleRunPlan = async (planId: string) => {
    setRunningPlan(planId);
    setPlanResult(null);
    setMessage(
      u(`Running plan "${planId}"…`, `正在執行測試計畫「${planId}」…`),
    );
    try {
      const res = await fetch(`${API_BASE}/api/faults/test-plans/${planId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ time_step: 10 }),
      });
      const data = await res.json();
      setPlanResult(data);
      setMessage(u(`Plan "${planId}" completed`, `測試計畫「${planId}」執行完成`));
      refreshActive();
    } catch {
      setMessage(u('Test plan failed', '測試計畫執行失敗'));
    } finally {
      setRunningPlan(null);
      setTimeout(() => setMessage(''), 8000);
    }
  };

  const turbineOptions = Array.from({ length: 14 }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`);

  return (
    <div>
      <PageHeader
        title={u('Fault Injection', '故障模擬')}
        sub={u(
          'Manual injection · diagnostic test plans · simulated fault behavior',
          '手動注入故障・診斷測試計畫・模擬故障行為',
        )}
        actions={
          <>
            <Btn
              variant="warn"
              onClick={handleInject}
              disabled={!selectedScenario}
              ariaLabel={u('Inject fault', '注入故障')}
            >
              {u('Inject fault', '注入故障')}
            </Btn>
            <Btn variant="primary" onClick={handleClearAll} ariaLabel={u('Clear all', '清除全部')}>
              {u('Clear all', '清除全部')}
            </Btn>
          </>
        }
      />

      {message && (
        <div style={{ marginBottom: 14 }}>
          <StatusPill tone="accent" size="md">
            {message}
          </StatusPill>
        </div>
      )}

      {/* Inject form */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.text }}>
          {u('Inject parameters', '注入參數')}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 12,
          }}
        >
          <Field label={u('Scenario', '故障場景')}>
            <Select
              value={selectedScenario}
              onChange={setSelectedScenario}
              options={[
                { value: '', label: u('-- Select scenario --', '-- 選擇故障場景 --') },
                ...scenarios.map(s => ({
                  value: s.id,
                  label: lang === 'zh' ? s.name_zh : s.name_en,
                })),
              ]}
              ariaLabel={u('Scenario', '故障場景')}
              fullWidth
            />
          </Field>
          <Field label={u('Turbine', '風機')}>
            <Select
              value={selectedTurbine}
              onChange={setSelectedTurbine}
              options={turbineOptions.map(t => ({ value: t, label: t }))}
              ariaLabel={u('Turbine', '風機')}
              fullWidth
            />
          </Field>
          <Field label={u('Severity rate', '速率')}>
            <Input
              type="number"
              step="0.001"
              min={0.0001}
              max={0.1}
              value={severityRate}
              onChange={setSeverityRate}
              fullWidth
              monospace
              ariaLabel={u('Severity rate', '速率')}
            />
          </Field>
        </div>
      </Card>

      {/* Active faults */}
      {activeFaults.length > 0 && (
        <Card padding={0} style={{ marginBottom: 14 }}>
          <div
            style={{
              padding: '14px 18px',
              borderBottom: `1px solid ${C.border}`,
              fontSize: 14,
              fontWeight: 600,
              color: C.text,
            }}
          >
            {u('Active faults', '活躍故障')} ({activeFaults.length})
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: C.panelMuted }}>
                  {[u('Turbine', '風機'), u('Fault', '故障'), u('Severity', '嚴重度'), u('Phase', '階段'), u('Alarms', '告警')].map(h => (
                    <th
                      key={h}
                      style={{
                        textAlign: 'left',
                        padding: '10px 14px',
                        fontSize: 11,
                        color: C.sub,
                        fontWeight: 500,
                        letterSpacing: 0.5,
                        textTransform: 'uppercase',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activeFaults.map((f, i) => (
                  <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td
                      style={{
                        padding: '10px 14px',
                        fontFamily: 'JetBrains Mono, monospace',
                        color: C.text,
                      }}
                    >
                      {f.turbine_id}
                    </td>
                    <td style={{ padding: '10px 14px', color: C.text }}>
                      {lang === 'zh' ? f.name_zh : f.name_en}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div
                          style={{
                            width: 80,
                            height: 6,
                            background: C.bg,
                            borderRadius: 3,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              height: '100%',
                              width: `${f.severity * 100}%`,
                              background: f.severity > 0.7 ? C.warn : f.severity > 0.4 ? C.amber : C.ok,
                              borderRadius: 3,
                            }}
                          />
                        </div>
                        <span
                          style={{
                            fontSize: 11,
                            color: C.sub,
                            fontFamily: 'JetBrains Mono, monospace',
                          }}
                        >
                          {(f.severity * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <StatusPill tone={phaseTone(f.phase)}>
                        {f.phase}
                        {f.tripped && ' · TRIP'}
                      </StatusPill>
                    </td>
                    <td
                      style={{
                        padding: '10px 14px',
                        fontSize: 11,
                        color: C.sub,
                      }}
                    >
                      {f.active_alarms?.map(a => `[${a.type}]`).join(' ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Test plans */}
      <div style={{ marginBottom: 8, marginTop: 24 }}>
        <h2
          style={{
            margin: 0,
            fontFamily: '"DM Serif Display", serif',
            fontSize: 24,
            fontWeight: 400,
            color: C.text,
          }}
        >
          {u('Diagnostic Test Plans', '診斷測試計畫')}
        </h2>
        <p style={{ margin: '6px 0 16px', fontSize: 13, color: C.sub }}>
          {u(
            'Generate simulated historical data with pre-scheduled fault injections.',
            '產生含預排程故障注入的模擬歷史資料，用於外部診斷系統測試。',
          )}
        </p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: 14,
        }}
      >
        {testPlans.map(plan => {
          const isRunning = runningPlan === plan.id;
          const tone = planTone(plan.id);
          const labelMap: Record<string, string> = {
            basic_validation: u('Easy', '簡單'),
            subtle_challenge: u('Hard', '困難'),
            mixed_difficulty: u('Mixed', '混合'),
          };
          return (
            <Card key={plan.id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                    {lang === 'zh' ? plan.name_zh : plan.name_en}
                  </div>
                  <StatusPill tone={tone}>{labelMap[plan.id] || u('Extreme', '極限')}</StatusPill>
                </div>
                <div style={{ textAlign: 'right', fontSize: 11, color: C.sub }}>
                  <div style={{ fontFamily: 'JetBrains Mono, monospace' }}>{plan.duration_hours}h</div>
                  <div>
                    {plan.fault_count} {u('faults', '故障')}
                  </div>
                </div>
              </div>
              <p style={{ fontSize: 12, color: C.sub, margin: '10px 0' }}>
                {lang === 'zh' ? plan.description_zh : plan.description_en}
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
                {plan.turbines_affected.sort().map(t => (
                  <span
                    key={t}
                    style={{
                      fontSize: 10,
                      padding: '2px 6px',
                      borderRadius: 4,
                      background: C.panelMuted,
                      color: C.sub,
                      fontFamily: 'JetBrains Mono, monospace',
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 4,
                    fontSize: 10,
                    color: C.faint,
                  }}
                >
                  {plan.scenarios_used.slice(0, 4).map(s => (
                    <span key={s}>{s}</span>
                  ))}
                  {plan.scenarios_used.length > 4 && <span>+{plan.scenarios_used.length - 4}</span>}
                </div>
                <Btn
                  variant="primary"
                  onClick={() => handleRunPlan(plan.id)}
                  disabled={isRunning || runningPlan !== null}
                  ariaLabel={u('Run plan', '執行計畫')}
                >
                  {isRunning ? u('Running…', '執行中…') : u('Run', '執行')}
                </Btn>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Plan result */}
      {planResult && (
        <Card style={{ marginTop: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.accent }}>
            {u('Test plan result', '測試計畫結果')} — {planResult.plan_id}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 14,
              marginBottom: 16,
            }}
          >
            <Stat label={u('Duration', '時長')} value={`${planResult.duration_hours}h`} size={24} />
            <Stat
              label={u('Readings', '數據筆數')}
              value={planResult.total_readings.toLocaleString()}
              highlight
              size={24}
            />
            <Stat label={u('Faults injected', '注入故障數')} value={planResult.faults_injected} size={24} />
            <Stat
              label={u('DB size', '資料庫大小')}
              value={`${planResult.storage_stats?.db_size_mb ?? '—'}`}
              unit="MB"
              size={24}
            />
          </div>
          {planResult.final_fault_status?.length > 0 && (
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
                    {planResult.final_fault_status.map((f, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td style={{ padding: '6px 10px', fontFamily: 'JetBrains Mono, monospace', color: C.text }}>
                          {f.turbine_id}
                        </td>
                        <td style={{ padding: '6px 10px', color: C.text }}>{f.scenario_id ?? f.name_en}</td>
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

export default FaultInjectionPanel;

/**
 * ScenarioCompareView — A1「同情境內比較」（WMOM-20260720-10, DEC-20260720-02）。
 *
 * 消費 A0 `GET /api/scenarios/{id}/summary`，在**單一情境內**跨機組比較，凸顯「有故障 vs 健康機組」
 * 的差異（使用者願景 level 1–2）。呈現：風場層 headline → 指標選擇 → 有故障/健康分群平均對照 →
 * 跨機組比較長條圖（依 faulted/healthy 著色）→ 每台機組明細表。
 *
 * faulted 判別走情境 `fault_schedule`（session 隔離、可靠），非 summary 的 `faultEvents`（後者走
 * 時間窗、`eventsByTimeWindow` 提醒可能混入重疊情境）。判別/分群/序列邏輯抽在 utils/scenarioCompare。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, Stat, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { windProfileLabel } from '../utils/windProfiles';
import type { SavedScenario } from './ScenarioDetail';
import {
  classifyTurbines,
  compareBars,
  faultedHealthyCounts,
  faultedTurbineIds,
  groupMeans,
  type CompareMetricKey,
  type ScenarioSummary,
} from '../utils/scenarioCompare';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface Props {
  scenario: SavedScenario;
  lang?: 'en' | 'zh';
}

interface MetricDef {
  key: CompareMetricKey;
  en: string;
  zh: string;
  unit: string;
  fmt: (v: number) => string;
}

/** 損傷值量級極小（~1e-3 或更小）→ 極小用科學記號，其餘固定小數。 */
function fmtDamage(v: number): string {
  if (v === 0) return '0';
  return Math.abs(v) < 1e-3 ? v.toExponential(2) : v.toFixed(4);
}

const ScenarioCompareView: React.FC<Props> = ({ scenario, lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [summary, setSummary] = useState<ScenarioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<CompareMetricKey>('capacityFactor');

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    authFetch(`${API_BASE}/api/scenarios/${scenario.id}/summary`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      // 只有自己仍是最新 request（未被 abort）才套用結果 / 結束 loading——否則切情境（scenario.id
      // 變）時，被 abort 的舊 request 其 finally 會把新 request 剛設的 loading 打回，短暫閃「無摘要」。
      // 比照 hooks/useCostData 的 guard。
      .then((res: ScenarioSummary) => { if (!ctrl.signal.aborted) setSummary(res); })
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setError(u('Failed to load scenario summary.', '載入情境摘要失敗。'));
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [scenario.id]);

  const METRICS: MetricDef[] = useMemo(
    () => [
      { key: 'capacityFactor', en: 'Capacity factor', zh: '容量因數', unit: '%', fmt: (v) => (v * 100).toFixed(1) },
      { key: 'energyKwh', en: 'Energy', zh: '發電量', unit: 'kWh', fmt: (v) => Math.round(v).toLocaleString() },
      { key: 'productionRate', en: 'Production rate', zh: '生產佔比', unit: '%', fmt: (v) => (v * 100).toFixed(1) },
      { key: 'worstDamage', en: 'Worst damage', zh: '最嚴重損傷', unit: '', fmt: fmtDamage },
      { key: 'rulHours', en: 'Remaining life', zh: '剩餘壽命', unit: 'h', fmt: (v) => Math.round(v).toLocaleString() },
      { key: 'faultEvents', en: 'Fault events', zh: '故障事件', unit: '', fmt: (v) => String(v) },
    ],
    [],
  );

  const faultedIds = useMemo(
    () => faultedTurbineIds(scenario.config?.fault_schedule),
    [scenario.config],
  );
  const rows = useMemo(
    () => (summary ? classifyTurbines(summary.turbines, faultedIds) : []),
    [summary, faultedIds],
  );
  const counts = useMemo(() => faultedHealthyCounts(rows), [rows]);
  // 排程缺失防呆（Must-fix）：faultedIds 空但有機組實際觸發故障 → 很可能是這條路徑的 scenario 物件
  // 沒帶 fault_schedule。此時分群會全落在 healthy、誤導；明示提醒而非靜默呈現「全部健康」。
  const scheduleMissing = useMemo(
    () => faultedIds.size === 0 && rows.some((r) => r.faultEvents > 0),
    [faultedIds, rows],
  );
  const activeMetric = METRICS.find((m) => m.key === metric) ?? METRICS[0];
  const bars = useMemo(() => compareBars(rows, metric), [rows, metric]);
  const means = useMemo(() => groupMeans(rows, metric), [rows, metric]);

  const fmtMean = (v: number | null): string =>
    v === null ? '—' : `${activeMetric.fmt(v)}${activeMetric.unit ? ` ${activeMetric.unit}` : ''}`;

  if (loading) {
    return (
      <Card>
        <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
          {u('Loading comparison…', '載入比較資料…')}
        </div>
      </Card>
    );
  }
  if (error || !summary) {
    return (
      <Card>
        <div style={{ fontSize: 13, color: C.warn, padding: '24px 0', textAlign: 'center' }}>
          {error ?? u('No summary available.', '無摘要資料。')}
        </div>
      </Card>
    );
  }

  const farm = summary.farm;

  return (
    <div>
      {scheduleMissing && (
        <div
          style={{
            marginBottom: 14,
            fontSize: 12,
            color: C.amber,
            background: C.panelMuted,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            padding: '8px 12px',
          }}
        >
          {u(
            'Fault schedule unavailable for this scenario — faulted/healthy grouping may be inaccurate (turbines shown as healthy despite observed fault events). Open it from the saved-scenario list to load the schedule.',
            '此情境未帶故障排程——有故障/健康分群可能不準（雖有觀測到故障事件，機組仍被歸為健康）。請從「過去情境」清單開啟以載入排程。',
          )}
        </div>
      )}

      {/* ── 風場層 headline ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>
          {u('Farm-level summary', '風場層摘要')}
        </div>
        <div style={{ fontSize: 12, color: C.sub, marginBottom: 12 }}>
          {summary.windProfile
            ? `${u('wind', '風況')} ${windProfileLabel(summary.windProfile, lang)} · `
            : ''}
          {u('rated', '額定')} {Math.round(summary.ratedPowerKw).toLocaleString()} kW
          {' · '}
          <span style={{ color: C.warn }}>{counts.faulted}</span> {u('faulted', '故障')} /{' '}
          <span style={{ color: C.ok }}>{counts.healthy}</span> {u('healthy', '健康')}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 14,
          }}
        >
          <Stat label={u('Total energy', '總發電量')} value={Math.round(farm.totalEnergyKwh).toLocaleString()} unit="kWh" size={20} highlight />
          <Stat label={u('Avg capacity factor', '平均容量因數')} value={(farm.avgCapacityFactor * 100).toFixed(1)} unit="%" size={20} />
          <Stat label={u('Avg production rate', '平均生產佔比')} value={(farm.avgProductionRate * 100).toFixed(1)} unit="%" size={20} />
          <Stat label={u('Total fault events', '總故障事件')} value={farm.totalFaultEvents} size={20} />
          <Stat
            label={u('Worst damage', '最嚴重損傷')}
            value={farm.worstDamageTurbineId ?? '—'}
            hint={farm.worstDamage !== null ? fmtDamage(farm.worstDamage) : undefined}
            size={20}
            valueColor={C.warn}
          />
          <Stat
            label={u('Shortest remaining life', '最短剩餘壽命')}
            value={farm.minRulTurbineId ?? '—'}
            hint={farm.minRulHours !== null ? `${Math.round(farm.minRulHours).toLocaleString()} h` : undefined}
            size={20}
            valueColor={C.warn}
          />
        </div>
      </Card>

      {/* ── 指標選擇 + 有故障/健康分群對照 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
          {u('Compare turbines by', '依指標比較機組')}
        </div>
        <div
          style={{
            display: 'flex',
            gap: 4,
            flexWrap: 'wrap',
            marginBottom: 14,
            padding: 4,
            background: C.panelMuted,
            borderRadius: 8,
          }}
        >
          {METRICS.map((m) => {
            const active = m.key === metric;
            return (
              <button
                key={m.key}
                onClick={() => setMetric(m.key)}
                aria-pressed={active}
                style={{
                  padding: '6px 12px',
                  fontSize: 12,
                  borderRadius: 6,
                  border: 'none',
                  background: active ? C.accent : 'transparent',
                  color: active ? C.accentInk : C.sub,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  fontWeight: active ? 600 : 500,
                }}
              >
                {u(m.en, m.zh)}
              </button>
            );
          })}
        </div>

        {/* 有故障 vs 健康 平均對照（A1 核心：量化兩群差異）*/}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 14,
            marginBottom: 14,
          }}
        >
          <Stat
            label={`${u('Faulted avg', '有故障機組平均')} · ${u(activeMetric.en, activeMetric.zh)}`}
            value={fmtMean(means.faulted)}
            size={20}
            valueColor={C.warn}
          />
          <Stat
            label={`${u('Healthy avg', '健康機組平均')} · ${u(activeMetric.en, activeMetric.zh)}`}
            value={fmtMean(means.healthy)}
            size={20}
            valueColor={C.ok}
          />
        </div>

        {/* 跨機組比較長條圖（faulted=warn / healthy=accent）*/}
        <div style={{ width: '100%', height: 300 }}>
          <ResponsiveContainer>
            <BarChart data={bars} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
              <XAxis dataKey="turbineId" tick={{ fill: C.sub, fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={50} />
              <YAxis tick={{ fill: C.sub, fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.text }}
                formatter={(v: number) => [activeMetric.fmt(v), u(activeMetric.en, activeMetric.zh)]}
              />
              <Bar dataKey="value" name={u(activeMetric.en, activeMetric.zh)} isAnimationActive={false}>
                {bars.map((b) => (
                  <Cell key={b.turbineId} fill={b.faulted ? C.warn : C.ok} fillOpacity={b.missing ? 0.25 : 1} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ fontSize: 11, color: C.faint, marginTop: 6 }}>
          <span style={{ color: C.warn }}>■</span> {u('faulted (scheduled injection)', '有故障（排定注入）')}
          {'　'}
          <span style={{ color: C.ok }}>■</span> {u('healthy', '健康')}
        </div>
      </Card>

      {/* ── 每台機組明細表 ── */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
          {u('Per-turbine detail', '各機組明細')}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'right', color: C.sub, fontSize: 11 }}>
                <th style={{ textAlign: 'left', padding: '6px 8px' }}>{u('Turbine', '機組')}</th>
                <th style={{ padding: '6px 8px' }}>{u('Cap. factor', '容量因數')}</th>
                <th style={{ padding: '6px 8px' }}>{u('Energy (kWh)', '發電量')}</th>
                <th style={{ padding: '6px 8px' }}>{u('Worst damage', '最嚴重損傷')}</th>
                <th style={{ padding: '6px 8px' }}>{u('RUL (h)', '剩餘壽命')}</th>
                <th style={{ padding: '6px 8px' }}>{u('Faults', '故障數')}</th>
              </tr>
            </thead>
            <tbody style={{ fontFamily: 'JetBrains Mono, monospace' }}>
              {rows.map((r) => (
                <tr key={r.turbineId} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ padding: '6px 8px', textAlign: 'left' }}>
                    <span style={{ color: C.text }}>{r.turbineId}</span>{' '}
                    {r.faulted && (
                      <StatusPill tone={r.scheduledNotTriggered ? 'amber' : 'warn'} size="sm">
                        {r.scheduledNotTriggered ? u('scheduled', '排定未觸發') : u('faulted', '故障')}
                      </StatusPill>
                    )}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text }}>{(r.capacityFactor * 100).toFixed(1)}%</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text }}>{Math.round(r.energyKwh).toLocaleString()}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text }}>{r.worstDamage !== null ? fmtDamage(r.worstDamage) : '—'}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text }}>{r.rulHours !== null ? Math.round(r.rulHours).toLocaleString() : '—'}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: r.faultEvents > 0 ? C.warn : C.text }}>{r.faultEvents}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {summary.eventsByTimeWindow && (
          <div style={{ fontSize: 11, color: C.faint, marginTop: 8 }}>
            {u(
              'Fault counts are matched by scenario time window (not session-isolated); overlapping scenarios may share counts. Faulted/healthy grouping uses the injection schedule.',
              '故障數走情境時間窗（非 session 隔離），時間窗重疊的情境可能共用計數；有故障/健康分群以注入排程判定。',
            )}
          </div>
        )}
      </Card>
    </div>
  );
};

export default ScenarioCompareView;

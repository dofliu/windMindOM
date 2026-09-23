/**
 * ScenarioCompareAcrossView — A2「跨情境比較」摘要並排（WMOM-20260922-04, DEC-20260720-02）。
 *
 * 消費 A2 Part 1 `GET /api/scenarios/compare?ids=1,2,3`，把使用者從「過去情境」清單挑選的
 * 2–5 個情境的**風場層 rollup**（而非個別機組——不同情境機組組成可能不同，逐機組比較無意義）
 * 摘要並排：headline 卡片 → 指標選擇 → 跨情境長條圖 → 全指標並排表。與 A1
 * （`ScenarioCompareView`，同情境內跨機組）對稱：A1 比較「機組 vs 機組」，本頁比較「情境 vs 情境」。
 *
 * 相對時間對齊的時序疊圖（第二個頁籤，A2 Part 3，WMOM-20260923-03）重用既有單情境端點
 * （見 `ScenarioCompareTimelineView`），非新後端端點；差異圖（決策記錄 A2 完整範圍的最後一塊）需要
 * 先解決多序列時間點不完全對齊的插值/分桶問題，仍不在本頁範圍，留給下一階段。
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
import { Btn, Card } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { windProfileLabel } from '../utils/windProfiles';
import {
  farmMetricValue,
  scenarioCompareBars,
  scenarioLabel,
  type FarmCompareMetricKey,
  type ScenarioSummary,
} from '../utils/scenarioCompare';
import ScenarioCompareTimelineView from './ScenarioCompareTimelineView';
import type { SavedScenario } from './ScenarioDetail';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

type CompareTab = 'summary' | 'timeline';

interface Props {
  /** 挑選比較的情境 id（2–5 個，比照後端 MIN/MAX_COMPARE_SCENARIOS，順序即並排順序）。 */
  ids: number[];
  /** 「過去情境」清單的完整物件（含 `config.sim_start`/`turbine_count`），供「時序疊圖」頁籤的相對
   *  時間對齊使用；預設空陣列——只影響時序疊圖頁籤，摘要並排頁籤不受影響（仍走 `ids` + `/compare`）。 */
  savedScenarios?: SavedScenario[];
  lang?: 'en' | 'zh';
  onBack: () => void;
}

interface MetricDef {
  key: FarmCompareMetricKey;
  en: string;
  zh: string;
  unit: string;
  fmt: (v: number) => string;
}

/** 損傷值量級極小（~1e-3 或更小）→ 極小用科學記號，其餘固定小數（比照 ScenarioCompareView）。 */
function fmtDamage(v: number): string {
  if (v === 0) return '0';
  return Math.abs(v) < 1e-3 ? v.toExponential(2) : v.toFixed(4);
}

const ScenarioCompareAcrossView: React.FC<Props> = ({ ids, savedScenarios = [], lang = 'zh', onBack }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [scenarios, setScenarios] = useState<ScenarioSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<FarmCompareMetricKey>('avgCapacityFactor');
  const [tab, setTab] = useState<CompareTab>('summary');

  const idsKey = ids.join(',');

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    authFetch(`${API_BASE}/api/scenarios/compare?ids=${idsKey}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      // 只有仍是最新 request 才套用（比照 ScenarioCompareView 對 abort 的防呆）。
      .then((res: { scenarios: ScenarioSummary[] }) => {
        if (!ctrl.signal.aborted) setScenarios(res.scenarios);
      })
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setError(u('Failed to load scenario comparison.', '載入跨情境比較失敗。'));
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [idsKey]);

  // 固定 5 色循環（既有 chart 事件色票，本就為區分類別而設，MAX_COMPARE_SCENARIOS 上限恰好 5）——
  // 依情境在陣列中的 index 指派，指標切換時同一情境顏色不變，方便來回比對。
  const palette = useMemo(
    () => [C.chartFault, C.chartWind, C.chartOperator, C.chartState, C.chartGrid],
    [C],
  );
  const colorFor = (index: number) => palette[index % palette.length];

  const METRICS: MetricDef[] = useMemo(
    () => [
      { key: 'avgCapacityFactor', en: 'Avg capacity factor', zh: '平均容量因數', unit: '%', fmt: (v) => (v * 100).toFixed(1) },
      { key: 'totalEnergyKwh', en: 'Total energy', zh: '總發電量', unit: 'kWh', fmt: (v) => Math.round(v).toLocaleString() },
      { key: 'avgProductionRate', en: 'Avg production rate', zh: '平均生產佔比', unit: '%', fmt: (v) => (v * 100).toFixed(1) },
      { key: 'totalFaultEvents', en: 'Total fault events', zh: '總故障事件', unit: '', fmt: (v) => String(v) },
      { key: 'worstDamage', en: 'Worst damage', zh: '最嚴重損傷', unit: '', fmt: fmtDamage },
      { key: 'minRulHours', en: 'Shortest remaining life', zh: '最短剩餘壽命', unit: 'h', fmt: (v) => Math.round(v).toLocaleString() },
    ],
    [],
  );

  const activeMetric = METRICS.find((m) => m.key === metric) ?? METRICS[0];
  const bars = useMemo(
    () => (scenarios ? scenarioCompareBars(scenarios, metric) : []),
    [scenarios, metric],
  );

  const fmtCell = (v: number | null, m: MetricDef): string =>
    v === null ? '—' : `${m.fmt(v)}${m.unit ? ` ${m.unit}` : ''}`;

  // 名稱查表：時序疊圖頁籤沿用摘要並排已抓到的 ScenarioSummary 命名邏輯（同一情境同一名稱，
  // 不因頁籤切換而不一致）；找不到（理論上不會，兩者共用同一批 ids）時回退 #id。
  const labelFor = (scenarioId: number): string => {
    const s = scenarios?.find((x) => x.scenarioId === scenarioId);
    return s ? scenarioLabel(s) : `#${scenarioId}`;
  };

  const idsKeyForTimeline = ids.join(',');
  // 找不到對應 metadata 的情境（`savedScenarios` 未含該 id，理論上不會發生——`ScenarioPage` 傳的
  // `savedScenarios` 恆是 `ids` 的來源清單本身）在此靜默過濾掉，不傳給
  // `ScenarioCompareTimelineView`（該元件把收到的 `scenarios` 視為已完整、不重複防呆）。
  const timelineScenarios = useMemo(
    () => ids.map((id) => savedScenarios.find((s) => s.id === id)).filter((s): s is SavedScenario => Boolean(s)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [idsKeyForTimeline, savedScenarios],
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: C.text }}>
          {u('Compare scenarios', '跨情境比較')}{' '}
          <span style={{ color: C.faint, fontWeight: 400, fontSize: 13 }}>
            ({ids.length} {u('scenarios', '個情境')})
          </span>
        </div>
        <Btn variant="secondary" onClick={onBack} ariaLabel={u('Back to scenario list', '返回情境列表')}>
          ← {u('Back', '返回')}
        </Btn>
      </div>

      {loading && (
        <Card>
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {u('Loading comparison…', '載入比較資料…')}
          </div>
        </Card>
      )}
      {!loading && (error || !scenarios) && (
        <Card>
          <div style={{ fontSize: 13, color: C.warn, padding: '24px 0', textAlign: 'center' }}>
            {error ?? u('No comparison available.', '無比較資料。')}
          </div>
        </Card>
      )}
      {!loading && scenarios && (
        <>
          {/* ── 頁籤：摘要並排 / 時序疊圖（A2 Part 3）── */}
          <div
            style={{
              display: 'flex',
              gap: 4,
              marginBottom: 14,
              padding: 4,
              background: C.panelMuted,
              borderRadius: 8,
              width: 'fit-content',
            }}
          >
            {([
              { key: 'summary' as const, en: 'Summary', zh: '摘要並排' },
              { key: 'timeline' as const, en: 'Timeline overlay', zh: '時序疊圖' },
            ]).map((t) => {
              const active = t.key === tab;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  aria-pressed={active}
                  style={{
                    padding: '6px 14px',
                    fontSize: 13,
                    borderRadius: 6,
                    border: 'none',
                    background: active ? C.accent : 'transparent',
                    color: active ? C.accentInk : C.sub,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  {u(t.en, t.zh)}
                </button>
              );
            })}
          </div>

          {tab === 'timeline' && (
            <ScenarioCompareTimelineView
              scenarios={timelineScenarios}
              labelFor={labelFor}
              colorFor={colorFor}
              lang={lang}
            />
          )}

          {tab === 'summary' && (
        <>
          {/* ── 情境 headline 卡片（依配色區分，指標切換保持一致）── */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 14,
            }}
          >
            {scenarios.map((s, i) => (
              <Card key={s.scenarioId} style={{ borderTop: `3px solid ${colorFor(i)}` }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {scenarioLabel(s)}
                </div>
                <div style={{ fontSize: 11, color: C.sub, marginTop: 4 }}>
                  {s.windProfile ? `${u('wind', '風況')} ${windProfileLabel(s.windProfile, lang)}` : u('(no wind profile)', '（無風況）')}
                  {s.durationHours != null ? ` · ${s.durationHours}h` : ''}
                </div>
              </Card>
            ))}
          </div>

          {/* ── 指標選擇 + 跨情境長條圖 ── */}
          <Card style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
              {u('Compare scenarios by', '依指標比較情境')}
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

            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={bars} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: C.sub, fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fill: C.sub, fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.text }}
                    formatter={(v: number) => [activeMetric.fmt(v), u(activeMetric.en, activeMetric.zh)]}
                  />
                  <Bar dataKey="value" name={u(activeMetric.en, activeMetric.zh)} isAnimationActive={false}>
                    {bars.map((b, i) => (
                      <Cell key={b.scenarioId} fill={colorFor(i)} fillOpacity={b.missing ? 0.25 : 1} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* ── 全指標並排表 ── */}
          <Card>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
              {u('All metrics, side by side', '全指標並排')}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'right', color: C.sub, fontSize: 11 }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>{u('Metric', '指標')}</th>
                    {scenarios.map((s, i) => (
                      <th key={s.scenarioId} style={{ padding: '6px 8px', color: colorFor(i) }}>
                        {scenarioLabel(s)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                  {METRICS.map((m) => (
                    <tr key={m.key} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: '6px 8px', textAlign: 'left', color: C.sub, fontFamily: 'inherit' }}>
                        {u(m.en, m.zh)}
                      </td>
                      {scenarios.map((s) => (
                        <td key={s.scenarioId} style={{ padding: '6px 8px', textAlign: 'right', color: C.text }}>
                          {fmtCell(farmMetricValue(s.farm, m.key), m)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {scenarios.some((s) => s.eventsByTimeWindow) && (
              <div style={{ fontSize: 11, color: C.faint, marginTop: 8 }}>
                {u(
                  'Fault counts are matched by scenario time window (not session-isolated); overlapping scenarios may share counts.',
                  '故障數走情境時間窗（非 session 隔離），時間窗重疊的情境可能共用計數。',
                )}
              </div>
            )}
          </Card>
        </>
          )}
        </>
      )}
    </div>
  );
};

export default ScenarioCompareAcrossView;

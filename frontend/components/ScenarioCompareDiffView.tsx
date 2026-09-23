/**
 * ScenarioCompareDiffView — A2 Part 4「跨情境差異圖」（DEC-20260720-02，補充決策見 decision_log
 * DEC-20260923-01 caveat：差異圖是否需要後端聚合，留給本階段依實作探勘判斷）。
 *
 * 從選取的情境中挑一個當 baseline，其餘情境逐點算「compare − baseline」疊在同一張圖上比較，
 * y=0 為參考線（等於 baseline 本身）。多情境序列的取樣時間點通常不完全對齊（見
 * `utils/scenarioTimeline.ts` 分桶重採樣說明），本頁判定純前端分桶重採樣即可、不需要新後端端點
 * ——資料來源與 A2 Part 3（`ScenarioCompareTimelineView`）相同，皆是既有單情境端點
 * `GET /api/scenarios/{id}/turbines/{turbineId}/history`。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, Field, Select } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { fetchScenarioHistory, type RawScenarioData } from '../utils/scenarioHistoryFetch';
import {
  buildDiffSeries,
  buildTimelinePoints,
  formatElapsed,
  pickBinMs,
  type TimelinePoint,
} from '../utils/scenarioTimeline';
import { HISTORY_LIMIT, METRICS, POWER_TAG } from './ScenarioCompareTimelineView';
import type { SavedScenario } from './ScenarioDetail';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface Props {
  /** 選取比較的情境（依 A2 並排順序），需含 `config.sim_start`/`turbine_count`。 */
  scenarios: SavedScenario[];
  labelFor: (scenarioId: number) => string;
  colorFor: (index: number) => string;
  lang?: 'en' | 'zh';
}

const ScenarioCompareDiffView: React.FC<Props> = ({ scenarios, labelFor, colorFor, lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const turbineCount = useMemo(() => {
    if (scenarios.length === 0) return 3;
    return Math.min(...scenarios.map((s) => s.turbine_count ?? 3));
  }, [scenarios]);
  const turbineOptions = useMemo(
    () => Array.from({ length: turbineCount }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`),
    [turbineCount],
  );

  const [turbineId, setTurbineId] = useState('WT001');
  const [tag, setTag] = useState(POWER_TAG);
  const [baselineId, setBaselineId] = useState<number | null>(scenarios[0]?.id ?? null);
  const [rawByScenario, setRawByScenario] = useState<Record<number, RawScenarioData>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (turbineOptions.length > 0 && !turbineOptions.includes(turbineId)) {
      setTurbineId(turbineOptions[0]);
    }
  }, [turbineOptions, turbineId]);

  // 選取情境變動（新增/移除）時，若原本的 baseline 已不在清單內，回退第一個。
  useEffect(() => {
    if (scenarios.length > 0 && !scenarios.some((s) => s.id === baselineId)) {
      setBaselineId(scenarios[0].id);
    }
  }, [scenarios, baselineId]);

  const scenariosKey = scenarios.map((s) => s.id).join(',');

  useEffect(() => {
    if (scenarios.length === 0) {
      setRawByScenario({});
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    Promise.all(
      scenarios.map((s) =>
        fetchScenarioHistory(API_BASE, s.id, turbineId, s.config?.sim_start, HISTORY_LIMIT, ctrl.signal).then(
          (data) => [s.id, data] as const,
        ),
      ),
    )
      .then((entries) => {
        if (!ctrl.signal.aborted) setRawByScenario(Object.fromEntries(entries));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenariosKey, turbineId]);

  const seriesByScenario = useMemo(() => {
    const out: Record<number, TimelinePoint[]> = {};
    for (const [id, data] of Object.entries(rawByScenario) as [string, RawScenarioData][]) {
      out[Number(id)] = buildTimelinePoints(data.rows, tag, data.baseMs);
    }
    return out;
  }, [rawByScenario, tag]);

  // 桶寬取所有選取情境中最粗的取樣間隔（見 scenarioTimeline.ts pickBinMs 說明），與 baseline 選擇
  // 無關——不論哪個情境當 baseline，桶寬本身只跟取樣密度有關。
  const binMs = useMemo(() => pickBinMs(Object.values(seriesByScenario)), [seriesByScenario]);

  const baselineSeries = baselineId !== null ? seriesByScenario[baselineId] ?? [] : [];
  const compareScenarios = scenarios.filter((s) => s.id !== baselineId);

  const diffByScenario = useMemo(() => {
    const out: Record<number, TimelinePoint[]> = {};
    if (baselineSeries.length === 0) return out;
    for (const s of compareScenarios) {
      const series = seriesByScenario[s.id];
      if (series && series.length > 0) out[s.id] = buildDiffSeries(baselineSeries, series, binMs);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seriesByScenario, baselineId, binMs]);

  const failedNames = scenarios.filter((s) => rawByScenario[s.id]?.failed).map((s) => labelFor(s.id));
  // 注意：`diffByScenario[s.id]` 的長度是「桶的數量」，即使兩情境完全不重疊，聯集後的每個桶
  // 仍會有一筆 `value: null` 紀錄——必須檢查「至少一個桶兩邊都有值」，否則長度判斷會誤判成
  // 「有資料」而畫出一條全是缺口、看起來像錯誤的空線。
  const hasAnyDiff = compareScenarios.some((s) => (diffByScenario[s.id] ?? []).some((p) => p.value !== null));
  const baselineHasNoData =
    baselineId !== null && !loading && Object.keys(rawByScenario).length > 0 && baselineSeries.length === 0;

  return (
    <div>
      <Card style={{ marginBottom: 14 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 10,
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {u('Difference vs baseline', '差異圖　相對 baseline')}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Field label={u('Baseline', 'Baseline 情境')}>
              <Select
                value={baselineId !== null ? String(baselineId) : ''}
                onChange={(v) => setBaselineId(Number(v))}
                options={scenarios.map((s) => ({ value: String(s.id), label: labelFor(s.id) }))}
                ariaLabel={u('Baseline scenario', 'Baseline 情境')}
              />
            </Field>
            <Field label={u('Turbine', '風機')}>
              <Select
                value={turbineId}
                onChange={setTurbineId}
                options={turbineOptions.map((t) => ({ value: t, label: t }))}
                ariaLabel={u('Turbine', '風機')}
              />
            </Field>
            <Field label={u('Metric', '指標')}>
              <Select
                value={tag}
                onChange={setTag}
                options={METRICS.map((m) => ({ value: m.key, label: u(m.en, m.zh) }))}
                ariaLabel={u('Metric', '指標')}
              />
            </Field>
          </div>
        </div>

        {failedNames.length > 0 && (
          <div
            style={{
              marginBottom: 10,
              fontSize: 12,
              color: C.warn,
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: '8px 12px',
            }}
          >
            {u(
              `${failedNames.join(', ')} — failed to load (possibly a transient error); try again later.`,
              `${failedNames.join('、')} — 載入失敗（可能是暫時性問題），稍後再試。`,
            )}
          </div>
        )}
        {baselineHasNoData && (
          <div
            style={{
              marginBottom: 10,
              fontSize: 12,
              color: C.warn,
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: '8px 12px',
            }}
          >
            {u(
              `${labelFor(baselineId as number)} (baseline) has no data for this turbine — cannot compute a difference.`,
              `${labelFor(baselineId as number)}（baseline）此機組沒有資料，無法算出差異。`,
            )}
          </div>
        )}

        {/* ── 純 DOM 圖例（同 Part 3，不含 baseline 本身——baseline 是參考線 y=0，不是一條差異線）── */}
        {compareScenarios.length > 0 && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
            {compareScenarios.map((s) => {
              const i = scenarios.findIndex((x) => x.id === s.id);
              return (
                <div
                  key={s.id}
                  data-testid={`diff-legend-${s.id}`}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: C.sub }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: 2, background: colorFor(i), flexShrink: 0 }} />
                  {labelFor(s.id)}
                </div>
              );
            })}
          </div>
        )}

        {loading && (
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {u('Loading…', '載入中…')}
          </div>
        )}
        {!loading && !hasAnyDiff && !baselineHasNoData && (
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {u('No overlapping data to compare for this turbine.', '選取的情境中，此機組沒有可比較的重疊資料。')}
          </div>
        )}
        {!loading && hasAnyDiff && (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="t"
                domain={['dataMin', 'dataMax']}
                tickFormatter={(v) => formatElapsed(v as number)}
                stroke={C.sub}
                fontSize={11}
              />
              <YAxis stroke={C.sub} fontSize={11} />
              <ReferenceLine y={0} stroke={C.border} strokeDasharray="4 4" />
              <Tooltip
                contentStyle={{
                  backgroundColor: C.panel,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  color: C.text,
                }}
                labelFormatter={(v) => u('Elapsed ', '經過 ') + formatElapsed(v as number)}
                formatter={(value: number, name: string) => [
                  value != null ? Number(value).toFixed(2) : '—',
                  name,
                ]}
              />
              {compareScenarios.map((s) => {
                const i = scenarios.findIndex((x) => x.id === s.id);
                return (
                  <Line
                    key={s.id}
                    data={diffByScenario[s.id] ?? []}
                    dataKey="value"
                    name={labelFor(s.id)}
                    stroke={colorFor(i)}
                    strokeWidth={1.8}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
        <div style={{ fontSize: 11, color: C.faint, marginTop: 8 }}>
          {u(
            `Each series is "compare − baseline" (baseline itself is the y=0 reference line). Values are resampled into ${Math.round(binMs / 1000)}s buckets (the coarsest sampling interval among the selected scenarios) before subtracting, since the raw sample points rarely land on exactly the same timestamp across scenarios.`,
            `每條線是「該情境 − baseline」（baseline 本身即為 y=0 參考線）。相減前會先把資料分桶重採樣成約 ${Math.round(binMs / 1000)} 秒一桶（取選取情境中最粗的取樣間隔），因為不同情境的原始取樣點通常不會剛好落在同一個時間點上。`,
          )}
          {' '}
          {u(
            'A gap in a line means that bucket has data on only one side (baseline or that scenario), so no difference could be computed there — not that the difference is zero.',
            '線上的缺口代表該桶只有一邊（baseline 或該情境）有資料，算不出差異——不是差異剛好等於 0。',
          )}
        </div>
      </Card>
    </div>
  );
};

export default ScenarioCompareDiffView;

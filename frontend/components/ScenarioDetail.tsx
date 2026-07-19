/**
 * ScenarioDetail — 調閱單一已保存情境（WMOM-20260719-02 前端，DEC-20260719-01）。
 *
 * 讀 `GET /api/scenarios/{id}/turbines/{tid}/history`（session 隔離）→ 呈現該情境某機組的
 * 「發電量 vs 風速」雙軸趨勢 + 故障事件標記與清單。這正是使用者要的「回頭把過去情境調出來
 * 觀察分析」：資料走 session_id 與 Live/其他歷史隔離；事件走情境時間窗（後端回傳
 * `events_by_time_window` 旗標提醒可能混入時間窗重疊的其他情境）。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine as RawReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Btn, Card, Field, Select, Stat, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { rightAxisTags } from '../utils/chartAxes';

// recharts 3.x 未在 type 上露出 React 內建 `key`，比照 HistoryPage 以寬鬆型別轉一次。
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReferenceLine: React.FC<any> = RawReferenceLine as unknown as React.FC<any>;

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

const POWER_TAG = 'WTUR_TotPwrAt';
const WIND_TAG = 'WMET_WSpeedNac';
const TAGS = [POWER_TAG, WIND_TAG];
const TAG_LABEL: Record<string, { en: string; zh: string }> = {
  [POWER_TAG]: { en: 'Power (kW)', zh: '發電量 (kW)' },
  [WIND_TAG]: { en: 'Wind (m/s)', zh: '風速 (m/s)' },
};

export interface ScenarioConfig {
  kind?: string; // 後端以 config_json.kind === 'scenario' 標記情境 session
  name?: string;
  wind_profile?: string;
  duration_hours?: number;
  time_step?: number;
  total_readings?: number;
  faults_injected?: number;
  sim_start?: string;
  sim_end?: string;
  status?: string;
  fault_schedule?: Array<{ scenario_id: string; turbine_id: string; offset_seconds: number }>;
}

export interface SavedScenario {
  id: number;
  started_at: string;
  ended_at?: string | null;
  turbine_count?: number;
  config?: ScenarioConfig;
}

interface HistPoint {
  timestamp: string;
  scada?: Record<string, number>;
  scada_json?: string;
}

interface HistEvent {
  id: number;
  timestamp: string;
  turbine_id?: string | null;
  event_type: string;
  title: string;
  detail?: string | null;
  _time?: number;
}

interface Props {
  scenario: SavedScenario;
  lang?: 'en' | 'zh';
  onBack: () => void;
}

const ScenarioDetail: React.FC<Props> = ({ scenario, lang = 'zh', onBack }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const cfg = scenario.config ?? {};

  const turbineCount = scenario.turbine_count ?? 3;
  const turbineOptions = useMemo(
    () => Array.from({ length: turbineCount }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`),
    [turbineCount],
  );
  const [turbineId, setTurbineId] = useState(turbineOptions[0] ?? 'WT001');
  const [points, setPoints] = useState<Record<string, number | string | null>[]>([]);
  const [events, setEvents] = useState<HistEvent[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    authFetch(`${API_BASE}/api/scenarios/${scenario.id}/turbines/${turbineId}/history?limit=3000`, {
      signal: ctrl.signal,
    })
      .then(r => (r.ok ? r.json() : { readings: [], events: [] }))
      .then(res => {
        const rows: HistPoint[] = Array.isArray(res.readings) ? [...res.readings].reverse() : [];
        const mapped = rows.map(row => {
          let scada = row.scada || {};
          if (!row.scada && row.scada_json) {
            try {
              scada = JSON.parse(row.scada_json);
            } catch {
              scada = {};
            }
          }
          const p: Record<string, number | string | null> = {
            _time: row.timestamp ? new Date(row.timestamp).getTime() : 0,
          };
          for (const t of TAGS) p[t] = scada?.[t] ?? null;
          return p;
        });
        setPoints(mapped);
        setEvents(Array.isArray(res.events) ? res.events : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [scenario.id, turbineId]);

  const rightTags = useMemo(() => rightAxisTags(TAGS, points), [points]);
  const faultEvents = useMemo(
    () =>
      events
        .filter(e => e.event_type === 'fault')
        .map(e => ({ ...e, _time: e.timestamp ? new Date(e.timestamp).getTime() : 0 }))
        .filter(e => (e._time ?? 0) > 0),
    [events],
  );

  const tagLabel = (t: string) => u(TAG_LABEL[t]?.en ?? t, TAG_LABEL[t]?.zh ?? t);
  const lineColor = (t: string) => (t === POWER_TAG ? C.accent : C.info);
  const fmtTime = (ms: number) => new Date(ms).toLocaleString();

  return (
    <div>
      {/* ── 情境詮釋資料 + 返回 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text }}>
              {cfg.name || u('(unnamed scenario)', '（未命名情境）')}
            </div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
              {u('Generated', '產生於')} {new Date(scenario.started_at).toLocaleString()}
              {cfg.wind_profile ? ` · ${u('wind', '風況')} ${cfg.wind_profile}` : ''}
              {cfg.status === 'error' && (
                <StatusPill tone="warn" size="sm">
                  {u('generation failed', '生成失敗')}
                </StatusPill>
              )}
            </div>
          </div>
          <Btn variant="secondary" onClick={onBack} ariaLabel={u('Back to scenario list', '返回情境列表')}>
            ← {u('Back', '返回')}
          </Btn>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
            gap: 14,
            marginTop: 14,
          }}
        >
          <Stat label={u('Duration', '時長')} value={`${cfg.duration_hours ?? '—'}h`} size={20} />
          <Stat label={u('Resolution', '解析度')} value={`${cfg.time_step ?? '—'}s`} size={20} />
          <Stat label={u('Readings', '資料筆數')} value={(cfg.total_readings ?? 0).toLocaleString()} highlight size={20} />
          <Stat label={u('Faults injected', '注入故障數')} value={cfg.faults_injected ?? 0} size={20} />
        </div>
      </Card>

      {/* ── 發電量 vs 風速 趨勢（含故障事件標記）── */}
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
            {u('Power vs wind · with fault markers', '發電量 vs 風速　含故障標記')}
          </div>
          <Field label={u('Turbine', '風機')}>
            <Select
              value={turbineId}
              onChange={setTurbineId}
              options={turbineOptions.map(t => ({ value: t, label: t }))}
              ariaLabel={u('Turbine', '風機')}
            />
          </Field>
        </div>

        {points.length === 0 ? (
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {loading ? u('Loading…', '載入中…') : u('No data for this turbine in the scenario.', '此情境中該機組沒有資料。')}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={points}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
              <XAxis
                dataKey="_time"
                tickFormatter={v => new Date(v as number).toLocaleTimeString()}
                stroke={C.sub}
                fontSize={11}
              />
              <YAxis yAxisId="left" stroke={C.sub} fontSize={11} />
              {rightTags.size > 0 && (
                <YAxis yAxisId="right" orientation="right" stroke={C.sub} fontSize={11} />
              )}
              <Tooltip
                contentStyle={{
                  backgroundColor: C.panel,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  color: C.text,
                }}
                labelFormatter={v => fmtTime(v as number)}
                formatter={(value: number, name: string) => [
                  value != null ? Number(value).toFixed(2) : '—',
                  tagLabel(name),
                ]}
              />
              <Legend formatter={value => tagLabel(value as string)} wrapperStyle={{ fontSize: 11 }} />
              {faultEvents.map(e => (
                <ReferenceLine
                  key={`fault-${e.id}`}
                  yAxisId="left"
                  x={e._time}
                  stroke={C.warn}
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  ifOverflow="extendDomain"
                  label={{ value: u('FAULT', '故障'), position: 'top', fill: C.warn, fontSize: 10 }}
                />
              ))}
              {TAGS.map(t => (
                <Line
                  key={t}
                  yAxisId={rightTags.has(t) ? 'right' : 'left'}
                  type="monotone"
                  dataKey={t}
                  stroke={lineColor(t)}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* ── 故障事件清單 ── */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: C.text }}>
          {u('Fault events', '故障事件')}{' '}
          <span style={{ color: C.faint, fontWeight: 400 }}>({faultEvents.length})</span>
        </div>
        {faultEvents.length === 0 ? (
          <div style={{ fontSize: 13, color: C.faint }}>
            {u('No fault events in this scenario window.', '此情境時間窗內沒有故障事件。')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {faultEvents.map(e => (
              <div
                key={e.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '170px 90px 1fr',
                  gap: 10,
                  alignItems: 'baseline',
                  padding: '8px 12px',
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  fontSize: 13,
                }}
              >
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>
                  {new Date(e.timestamp).toLocaleString()}
                </span>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: C.text }}>
                  {e.turbine_id ?? '—'}
                </span>
                <span style={{ color: C.text }}>{e.title}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

export default ScenarioDetail;

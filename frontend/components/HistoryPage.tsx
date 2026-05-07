/**
 * HistoryPage — A · Calm Operator 改版。
 *
 * 版面：
 *   - PageHeader：歷史資料 + 「搜尋 SCADA 標籤・事件標記・CSV 匯出」+ Compare tab
 *   - 查詢條件卡（4 欄）：風機 / 時間範圍 / 標籤 / 事件篩選
 *   - 折線圖（含事件 ReferenceLine 與 ReferenceArea）
 *   - 事件清單 + 事件詳情
 *   - 最近 20 筆資料表
 *
 * **API 不動**：`/api/turbines/:id/history`、`/api/i18n/tags`、`/api/export/history`。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea as RawReferenceArea,
  ReferenceLine as RawReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

// recharts 3.x type definitions do not surface the `key` React-builtin on
// ReferenceArea / ReferenceLine; cast to a permissive component so we can
// pass `key` while iterating without losing render correctness.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReferenceArea: React.FC<any> = RawReferenceArea as unknown as React.FC<any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReferenceLine: React.FC<any> = RawReferenceLine as unknown as React.FC<any>;
import type { TurbineData } from '../types';
import EventComparisonView from './EventComparisonView';
import {
  Btn,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  StatusPill,
  type PillTone,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

const TAG_PRESETS: Record<string, string[]> = {
  startup: ['WTUR_TurSt', 'WROT_RotSpd', 'WTUR_TotPwrAt', 'WGEN_GnVtgMs', 'WCNV_CnvGnFrq'],
  thermal: ['WGEN_GnStaTmp1', 'WGEN_GnBrgTmp1', 'WCNV_CnvCabinTmp', 'WGDC_TrfCoreTmp'],
  vibration: ['WNAC_VibMsNacXDir', 'WNAC_VibMsNacYDir', 'WYAW_YwBrkHyPrs', 'WROT_RotSpd'],
  pitch: ['WROT_PtAngValBl1', 'WROT_PtAngValBl2', 'WROT_PtAngValBl3', 'WTUR_TotPwrAt'],
};

const EVENT_TYPES = ['grid', 'fault', 'operator', 'wind', 'state'] as const;
type EventType = typeof EVENT_TYPES[number];

interface HistoryPageProps {
  turbines: TurbineData[];
  lang?: 'en' | 'zh';
}

interface HistoryRow {
  timestamp: string;
  scada?: Record<string, number>;
  scada_json?: string;
}

interface HistoryEvent {
  id: number;
  timestamp: string;
  end_timestamp?: string | null;
  turbine_id?: string | null;
  event_type: string;
  source: string;
  title: string;
  detail?: string | null;
  payload?: Record<string, unknown>;
  _time?: number;
  _endTime?: number;
}

const toDateTimeLocal = (value: Date) => {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
};

const eventTone = (et: string): PillTone => {
  if (et === 'fault') return 'warn';
  if (et === 'grid') return 'amber';
  if (et === 'wind') return 'info';
  if (et === 'operator') return 'ok';
  if (et === 'state') return 'accent';
  return 'muted';
};

// Use raw hex for chart event lines (per handover §7 — chart event hex 例外允許)
const EVENT_HEX: Record<string, { light: string; dark: string }> = {
  fault: { light: '#C97B5A', dark: '#FF8E72' },
  grid: { light: '#B8A053', dark: '#FFB347' },
  wind: { light: '#5A7A98', dark: '#7AB8E8' },
  operator: { light: '#5C8A5F', dark: '#3DDC97' },
  state: { light: '#8B7AB8', dark: '#B49DE8' },
};

const HistoryPage: React.FC<HistoryPageProps> = ({ turbines, lang = 'zh' }) => {
  const { C } = useTheme();
  const tr = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const eventColor = (et: string) =>
    (EVENT_HEX[et]?.[C.isDark ? 'dark' : 'light']) || C.faint;

  const [tab, setTab] = useState<'single' | 'compare'>('single');
  const [selectedTurbineId, setSelectedTurbineId] = useState('WT001');
  const [activeTags, setActiveTags] = useState<string[]>(TAG_PRESETS.startup);
  const [limit, setLimit] = useState(300);
  const [chartData, setChartData] = useState<Record<string, number | string | null>[]>([]);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [focusWindowSec, setFocusWindowSec] = useState<number>(0);
  const [eventSearch, setEventSearch] = useState('');
  const [rangeStart, setRangeStart] = useState(() =>
    toDateTimeLocal(new Date(Date.now() - 2 * 60 * 60 * 1000)),
  );
  const [rangeEnd, setRangeEnd] = useState(() => toDateTimeLocal(new Date()));
  const [enabledEventTypes, setEnabledEventTypes] = useState<Record<EventType, boolean>>({
    grid: true,
    fault: true,
    operator: true,
    wind: true,
    state: true,
  });
  const [tagLabels, setTagLabels] = useState<Record<string, string>>({});
  const [customTags, setCustomTags] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!turbines.length) return;
    setSelectedTurbineId(prev => prev || `WT${String(turbines[0].id).padStart(3, '0')}`);
  }, [turbines]);

  useEffect(() => {
    fetch(`${API_BASE}/api/i18n/tags?lang=${lang}`)
      .then(r => r.json())
      .then(setTagLabels)
      .catch(() => {});
  }, [lang]);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    const params = new URLSearchParams({ limit: String(limit) });
    if (rangeStart) params.set('start', new Date(rangeStart).toISOString());
    if (rangeEnd) params.set('end', new Date(rangeEnd).toISOString());

    fetch(`${API_BASE}/api/turbines/${selectedTurbineId}/history?${params.toString()}`, {
      signal: ctrl.signal,
    })
      .then(r => r.json())
      .then(res => {
        const rows: HistoryRow[] = Array.isArray(res.data) ? [...res.data].reverse() : [];
        const eventRows: HistoryEvent[] = Array.isArray(res.events) ? [...res.events].reverse() : [];
        const mapped = rows.map(row => {
          let scada = row.scada || {};
          if (!row.scada && row.scada_json) {
            try {
              scada = JSON.parse(row.scada_json);
            } catch {
              scada = {};
            }
          }
          const point: Record<string, number | string | null> = {
            timestamp: row.timestamp,
            _time: row.timestamp ? new Date(row.timestamp).getTime() : 0,
          };
          for (const tag of activeTags) {
            point[tag] = scada?.[tag] ?? null;
          }
          return point;
        });
        setChartData(mapped);
        setEvents(eventRows);
        setSelectedEventId(prev =>
          eventRows.some(e => e.id === prev) ? prev : eventRows[0]?.id ?? null,
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    return () => ctrl.abort();
  }, [selectedTurbineId, activeTags, limit, rangeStart, rangeEnd]);

  const visibleEvents = useMemo(
    () =>
      events
        .filter(e => enabledEventTypes[(e.event_type as EventType)] ?? false)
        .map(e => ({
          ...e,
          _time: e.timestamp ? new Date(e.timestamp).getTime() : 0,
          _endTime: e.end_timestamp ? new Date(e.end_timestamp).getTime() : undefined,
        }))
        .filter(e => (e._time ?? 0) > 0)
        .filter(e => {
          const q = eventSearch.trim().toLowerCase();
          if (!q) return true;
          const blob = `${e.title} ${e.detail ?? ''} ${e.source} ${e.event_type} ${e.turbine_id ?? ''}`.toLowerCase();
          return blob.includes(q);
        }),
    [events, enabledEventTypes, eventSearch],
  );

  const selectedEvent = useMemo(
    () => visibleEvents.find(e => e.id === selectedEventId) || visibleEvents[0] || null,
    [visibleEvents, selectedEventId],
  );

  const focusedChartData = useMemo(() => {
    if (!selectedEvent || focusWindowSec <= 0) return chartData;
    const center = selectedEvent._time ?? 0;
    const half = focusWindowSec * 1000;
    return chartData.filter(p => {
      const t = Number(p._time ?? 0);
      return t >= center - half && t <= center + half;
    });
  }, [chartData, selectedEvent, focusWindowSec]);

  const focusedEvents = useMemo(() => {
    if (!selectedEvent || focusWindowSec <= 0) return visibleEvents;
    const center = selectedEvent._time ?? 0;
    const half = focusWindowSec * 1000;
    return visibleEvents.filter(e => {
      const start = e._time ?? 0;
      const end = e._endTime ?? start;
      return end >= center - half && start <= center + half;
    });
  }, [visibleEvents, selectedEvent, focusWindowSec]);

  const previewRows = useMemo(() => focusedChartData.slice(-20).reverse(), [focusedChartData]);

  const applyPreset = (id: keyof typeof TAG_PRESETS) => setActiveTags(TAG_PRESETS[id]);
  const applyCustomTags = () => {
    const tags = customTags.split(',').map(t => t.trim()).filter(Boolean);
    if (tags.length) setActiveTags(tags);
  };

  const exportCsv = (focusedOnly: boolean) => {
    const params = new URLSearchParams({
      turbine_id: selectedTurbineId,
      limit: String(limit),
      format: 'csv',
    });
    const center = selectedEvent?._time ?? 0;
    if (focusedOnly && selectedEvent && focusWindowSec > 0) {
      params.set('start', new Date(center - focusWindowSec * 1000).toISOString());
      params.set('end', new Date(center + focusWindowSec * 1000).toISOString());
    } else {
      if (rangeStart) params.set('start', new Date(rangeStart).toISOString());
      if (rangeEnd) params.set('end', new Date(rangeEnd).toISOString());
    }
    window.open(`${API_BASE}/api/export/history?${params.toString()}`, '_blank');
  };

  const toggleEvent = (et: EventType) => setEnabledEventTypes(prev => ({ ...prev, [et]: !prev[et] }));

  const getLabel = (tag: string) => tagLabels[tag] || tag;
  const eventTypeLabel = (et: string) => {
    if (lang === 'zh') {
      if (et === 'grid') return '電網';
      if (et === 'fault') return '故障';
      if (et === 'operator') return '操作';
      if (et === 'wind') return '風況';
      if (et === 'state') return '狀態';
    }
    return et;
  };

  // Line colors derived from theme
  const lineColors = [C.accent, C.amber, C.ok, C.warn, C.info, C.chartState, C.accent, C.amber];

  return (
    <div>
      <PageHeader
        title={tr('History', '歷史資料')}
        sub={tr(
          'Search SCADA tags · marked events · CSV export',
          '搜尋 SCADA 標籤・事件標記・CSV 匯出',
        )}
        actions={
          <>
            <Btn ariaLabel={tr('Download CSV (range)', '下載 CSV (區間)')} onClick={() => exportCsv(false)}>
              {tr('CSV (range)', '匯出區間')}
            </Btn>
            <Btn ariaLabel={tr('Download CSV (focus)', '下載 CSV (聚焦)')} onClick={() => exportCsv(true)}>
              {tr('CSV (focus)', '匯出聚焦')}
            </Btn>
          </>
        }
      />

      {/* Tab */}
      <div
        style={{
          display: 'inline-flex',
          background: C.panel,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          marginBottom: 14,
          overflow: 'hidden',
        }}
      >
        {(['single', 'compare'] as const).map(t => {
          const active = tab === t;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              aria-pressed={active}
              style={{
                padding: '6px 14px',
                fontSize: 13,
                background: active ? C.accent : 'transparent',
                color: active ? C.accentInk : C.sub,
                border: 'none',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: active ? 600 : 500,
              }}
            >
              {t === 'single' ? tr('Single turbine', '單機歷史') : tr('Multi compare', '多機比較')}
            </button>
          );
        })}
      </div>

      {tab === 'compare' ? (
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 14, padding: 14 }}>
          <EventComparisonView turbines={turbines} lang={lang} />
        </div>
      ) : (
        <>
          {/* Filter row */}
          <Card style={{ marginBottom: 14 }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 12,
              }}
            >
              <Field label={tr('Turbine', '風機')}>
                <Select
                  value={selectedTurbineId}
                  onChange={setSelectedTurbineId}
                  options={turbines.map(t => {
                    const tid = `WT${String(t.id).padStart(3, '0')}`;
                    return { value: tid, label: `${tid} · ${t.name}` };
                  })}
                  ariaLabel={tr('Turbine', '風機')}
                  fullWidth
                />
              </Field>
              <Field label={tr('Samples', '筆數')}>
                <Select
                  value={String(limit)}
                  onChange={v => setLimit(Number(v))}
                  options={[120, 300, 600, 1200, 3600].map(n => ({ value: String(n), label: String(n) }))}
                  ariaLabel={tr('Samples', '筆數')}
                  fullWidth
                />
              </Field>
              <Field label={tr('Start', '開始時間')}>
                <Input
                  type="datetime-local"
                  value={rangeStart}
                  onChange={setRangeStart}
                  fullWidth
                  monospace
                  ariaLabel={tr('Start', '開始時間')}
                />
              </Field>
              <Field label={tr('End', '結束時間')}>
                <Input
                  type="datetime-local"
                  value={rangeEnd}
                  onChange={setRangeEnd}
                  fullWidth
                  monospace
                  ariaLabel={tr('End', '結束時間')}
                />
              </Field>
            </div>

            {/* Tag presets + custom + event toggles */}
            <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
                  {tr('Tag presets', '標籤預設')}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {Object.keys(TAG_PRESETS).map(k => (
                    <button
                      key={k}
                      onClick={() => applyPreset(k as keyof typeof TAG_PRESETS)}
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
                      {k}
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 240px', minWidth: 240 }}>
                  <Input
                    value={customTags}
                    onChange={setCustomTags}
                    placeholder={tr(
                      'Custom tags (comma separated)',
                      '自訂標籤，以逗號分隔',
                    )}
                    fullWidth
                    monospace
                    ariaLabel={tr('Custom tags', '自訂標籤')}
                  />
                </div>
                <Btn onClick={applyCustomTags}>{tr('Apply', '套用')}</Btn>
              </div>

              <div>
                <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
                  {tr('Event filters', '事件篩選')}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {EVENT_TYPES.map(et => {
                    const enabled = enabledEventTypes[et];
                    const col = eventColor(et);
                    return (
                      <button
                        key={et}
                        onClick={() => toggleEvent(et)}
                        aria-pressed={enabled}
                        style={{
                          padding: '4px 10px',
                          fontSize: 12,
                          borderRadius: 6,
                          border: `1px solid ${enabled ? col : C.border}`,
                          background: enabled ? `${col}22` : C.panelMuted,
                          color: enabled ? col : C.sub,
                          cursor: 'pointer',
                          fontFamily: 'inherit',
                          fontWeight: enabled ? 600 : 500,
                        }}
                      >
                        {eventTypeLabel(et)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <Field label={tr('Event search', '事件搜尋')}>
                  <Input
                    value={eventSearch}
                    onChange={setEventSearch}
                    placeholder={tr('Search title / detail / type', '標題 / 描述 / 類型')}
                    width={260}
                    ariaLabel={tr('Event search', '事件搜尋')}
                  />
                </Field>
                <Field label={tr('Focus window', '聚焦視窗')}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {[0, 30, 120].map(v => {
                      const active = focusWindowSec === v;
                      return (
                        <button
                          key={v}
                          onClick={() => setFocusWindowSec(v)}
                          aria-pressed={active}
                          style={{
                            padding: '6px 12px',
                            fontSize: 12,
                            borderRadius: 6,
                            border: `1px solid ${active ? C.accent : C.border}`,
                            background: active ? C.accentSoft : C.panel,
                            color: active ? C.accent : C.sub,
                            cursor: 'pointer',
                            fontFamily: 'inherit',
                            fontWeight: active ? 600 : 500,
                          }}
                        >
                          {v === 0 ? tr('All', '全部') : `${v}s`}
                        </button>
                      );
                    })}
                  </div>
                </Field>
                <div style={{ flex: 1, fontSize: 12, color: C.sub, textAlign: 'right' }}>
                  {loading
                    ? tr('Loading…', '載入中…')
                    : `${focusedChartData.length} ${tr('rows', '筆資料')}`}
                </div>
              </div>
            </div>
          </Card>

          {/* Chart */}
          <Card style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: C.text }}>
              {tr('Power output · with events', '功率輸出　含事件標記')}
            </div>
            <ResponsiveContainer width="100%" height={420}>
              <LineChart data={focusedChartData}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis
                  dataKey="_time"
                  tickFormatter={v => new Date(v as number).toLocaleTimeString()}
                  stroke={C.sub}
                  fontSize={11}
                />
                <YAxis stroke={C.sub} fontSize={11} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: C.panel,
                    border: `1px solid ${C.border}`,
                    borderRadius: 8,
                    color: C.text,
                  }}
                  labelFormatter={v => new Date(v as number).toLocaleString()}
                  formatter={(value: number, name: string) => [
                    value != null ? Number(value).toFixed(2) : '—',
                    getLabel(name),
                  ]}
                />
                <Legend formatter={value => getLabel(value as string)} wrapperStyle={{ fontSize: 11 }} />
                {focusedEvents
                  .filter(e => (e._endTime ?? 0) > (e._time ?? 0) && (e.event_type === 'grid' || e.event_type === 'wind'))
                  .map(e => (
                    <ReferenceArea
                      key={`band-${e.id}`}
                      x1={e._time}
                      x2={e._endTime}
                      fill={eventColor(e.event_type)}
                      fillOpacity={selectedEvent?.id === e.id ? 0.16 : 0.08}
                      strokeOpacity={0}
                    />
                  ))}
                {focusedEvents.map((e, i) => (
                  <ReferenceLine
                    key={`${e.id}-${e.timestamp}`}
                    x={e._time}
                    stroke={eventColor(e.event_type)}
                    strokeDasharray="4 4"
                    strokeOpacity={selectedEvent?.id === e.id ? 1 : 0.7}
                    strokeWidth={selectedEvent?.id === e.id ? 3 : 1.5}
                    ifOverflow="extendDomain"
                    label={{
                      value: i % 2 === 0 ? eventTypeLabel(e.event_type).toUpperCase() : '',
                      position: 'top',
                      fill: C.sub,
                      fontSize: 10,
                    }}
                  />
                ))}
                {activeTags.map((tag, i) => (
                  <Line
                    key={tag}
                    type="monotone"
                    dataKey={tag}
                    stroke={lineColors[i % lineColors.length]}
                    strokeWidth={1.8}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <div style={{ marginTop: 8, fontSize: 11, color: C.faint }}>
              {tr('Showing', '目前顯示')}: {activeTags.map(getLabel).join(' · ')}
            </div>
          </Card>

          {/* Event log + detail */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 0.8fr)',
              gap: 16,
              marginBottom: 14,
            }}
          >
            <Card>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: C.text }}>
                {tr('Event log', '事件紀錄')}
              </div>
              {focusedEvents.length === 0 ? (
                <div style={{ fontSize: 12, color: C.sub }}>
                  {tr('No events in current range.', '目前區間沒有事件。')}
                </div>
              ) : (
                <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {focusedEvents
                    .slice()
                    .reverse()
                    .map(e => {
                      const active = selectedEvent?.id === e.id;
                      return (
                        <button
                          key={e.id}
                          type="button"
                          onClick={() => setSelectedEventId(e.id)}
                          style={{
                            textAlign: 'left',
                            padding: '8px 12px',
                            border: `1px solid ${active ? C.accent : C.border}`,
                            background: active ? C.accentSoft : C.panel,
                            borderRadius: 8,
                            cursor: 'pointer',
                            fontFamily: 'inherit',
                            display: 'grid',
                            gridTemplateColumns: '160px 1fr auto',
                            gap: 10,
                            alignItems: 'baseline',
                            fontSize: 13,
                          }}
                        >
                          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>
                            {new Date(e.timestamp).toLocaleString()}
                          </span>
                          <span style={{ color: active ? C.accent : C.text, fontWeight: active ? 600 : 500 }}>
                            {e.title}
                          </span>
                          <StatusPill tone={eventTone(e.event_type)}>
                            {eventTypeLabel(e.event_type)}
                          </StatusPill>
                        </button>
                      );
                    })}
                </div>
              )}
            </Card>

            <Card>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: C.text }}>
                {tr('Event details', '事件詳情')}
              </div>
              {selectedEvent ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, justifyContent: 'space-between' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>
                        {selectedEvent.title}
                      </div>
                      <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                        {[eventTypeLabel(selectedEvent.event_type), selectedEvent.source, selectedEvent.turbine_id || 'FARM'].join(' · ')}
                      </div>
                    </div>
                    <StatusPill tone={eventTone(selectedEvent.event_type)}>
                      {eventTypeLabel(selectedEvent.event_type)}
                    </StatusPill>
                  </div>
                  <div style={{ fontSize: 11, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>
                    {new Date(selectedEvent.timestamp).toLocaleString()}
                    {selectedEvent.end_timestamp
                      ? ` → ${new Date(selectedEvent.end_timestamp).toLocaleString()}`
                      : ''}
                  </div>
                  <div style={{ fontSize: 13, color: C.text }}>
                    {selectedEvent.detail || tr('No additional detail.', '沒有額外描述。')}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {[30, 120].map(v => (
                      <Btn key={v} size="sm" onClick={() => setFocusWindowSec(v)}>
                        {tr(`Focus ±${v}s`, `聚焦前後 ${v} 秒`)}
                      </Btn>
                    ))}
                    <Btn size="sm" variant="ghost" onClick={() => setFocusWindowSec(0)}>
                      {tr('Show all', '顯示全部')}
                    </Btn>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>Payload</div>
                    <pre
                      style={{
                        background: C.panelMuted,
                        border: `1px solid ${C.border}`,
                        borderRadius: 8,
                        padding: 10,
                        fontSize: 11,
                        color: C.text,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        maxHeight: 220,
                        overflowY: 'auto',
                        margin: 0,
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {JSON.stringify(selectedEvent.payload ?? {}, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 12, color: C.sub }}>
                  {tr('Select an event from the list.', '請從左側選擇事件。')}
                </div>
              )}
            </Card>
          </div>

          {/* Last 20 rows */}
          <Card padding={0}>
            <div
              style={{
                padding: '14px 18px',
                borderBottom: `1px solid ${C.border}`,
                fontSize: 14,
                fontWeight: 600,
                color: C.text,
              }}
            >
              {tr('Latest 20 rows', '最近 20 筆')}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: C.panelMuted }}>
                    <th
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
                      {tr('Timestamp', '時間')}
                    </th>
                    {activeTags.map(tag => (
                      <th
                        key={tag}
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
                        {getLabel(tag)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, i) => (
                    <tr key={`${row.timestamp}-${i}`} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td
                        style={{
                          padding: '10px 14px',
                          fontFamily: 'JetBrains Mono, monospace',
                          color: C.sub,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {String(row.timestamp)}
                      </td>
                      {activeTags.map(tag => (
                        <td
                          key={tag}
                          style={{
                            padding: '10px 14px',
                            fontFamily: 'JetBrains Mono, monospace',
                            color: C.text,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {row[tag] != null ? Number(row[tag]).toFixed(2) : '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};

export default HistoryPage;

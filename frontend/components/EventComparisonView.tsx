/**
 * EventComparisonView — A · Calm Operator 改版（功能不動）。
 * 多風機事件比較：選風機 + 範圍 + 類型 → 顯示摘要、全場事件、合併時間線。
 */

import React, { useEffect, useMemo, useState } from 'react';
import type { TurbineData } from '../types';
import { Btn, Card, Field, Input, Select, StatusPill, type PillTone } from './ui';
import { useTheme } from '../theme/ThemeProvider';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface ComparisonEvent {
  id: number;
  timestamp: string;
  end_timestamp?: string | null;
  turbine_id?: string | null;
  event_type: string;
  source: string;
  title: string;
  detail?: string | null;
  severity?: string;
  _turbine_id?: string;
}

interface Props {
  turbines: TurbineData[];
  lang?: 'en' | 'zh';
}

const eventTone = (et: string): PillTone => {
  if (et === 'fault' || et === 'fault_lifecycle') return 'warn';
  if (et === 'grid') return 'amber';
  if (et === 'wind') return 'info';
  if (et === 'operator') return 'ok';
  if (et === 'state') return 'accent';
  return 'muted';
};

const sevTone = (s?: string): PillTone => {
  if (s === 'critical') return 'warn';
  if (s === 'warning') return 'amber';
  return 'muted';
};

const toDateTimeLocal = (v: Date) => {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${v.getFullYear()}-${pad(v.getMonth() + 1)}-${pad(v.getDate())}T${pad(v.getHours())}:${pad(v.getMinutes())}`;
};

const EventComparisonView: React.FC<Props> = ({ turbines, lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const allTurbineIds = useMemo(
    () => turbines.map(t => `WT${String(t.id).padStart(3, '0')}`),
    [turbines],
  );

  const [selectedIds, setSelectedIds] = useState<string[]>(() => allTurbineIds.slice(0, 4));
  const [rangeStart, setRangeStart] = useState(() =>
    toDateTimeLocal(new Date(Date.now() - 2 * 60 * 60 * 1000)),
  );
  const [rangeEnd, setRangeEnd] = useState(() => toDateTimeLocal(new Date()));
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [timeline, setTimeline] = useState<ComparisonEvent[]>([]);
  const [summary, setSummary] = useState<Record<string, { total: number; by_type: Record<string, number> }>>({});
  const [farmEvents, setFarmEvents] = useState<ComparisonEvent[]>([]);

  useEffect(() => {
    if (selectedIds.length === 0) return;
    setLoading(true);
    const params = new URLSearchParams({ turbine_ids: selectedIds.join(','), limit: '500' });
    if (rangeStart) params.set('start', new Date(rangeStart).toISOString());
    if (rangeEnd) params.set('end', new Date(rangeEnd).toISOString());
    if (eventTypeFilter) params.set('event_type', eventTypeFilter);

    fetch(`${API_BASE}/api/maintenance/events/compare?${params.toString()}`)
      .then(r => r.json())
      .then(data => {
        setTimeline(data.timeline || []);
        setSummary(data.summary || {});
        setFarmEvents(data.farm_events || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedIds, rangeStart, rangeEnd, eventTypeFilter]);

  const toggleTurbine = (tid: string) => {
    setSelectedIds(prev => (prev.includes(tid) ? prev.filter(id => id !== tid) : [...prev, tid]));
  };

  const exportEvents = () => {
    const params = new URLSearchParams({ format: 'csv', limit: '5000' });
    if (rangeStart) params.set('start', new Date(rangeStart).toISOString());
    if (rangeEnd) params.set('end', new Date(rangeEnd).toISOString());
    if (eventTypeFilter) params.set('event_type', eventTypeFilter);
    window.open(`${API_BASE}/api/export/events?${params.toString()}`, '_blank');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Turbine selector */}
      <Card>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 10,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {u('Select turbines', '選擇風機')}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <Btn size="sm" onClick={() => setSelectedIds([...allTurbineIds])}>
              {u('All', '全選')}
            </Btn>
            <Btn size="sm" variant="ghost" onClick={() => setSelectedIds([])}>
              {u('None', '清除')}
            </Btn>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {allTurbineIds.map(tid => {
            const active = selectedIds.includes(tid);
            return (
              <button
                key={tid}
                onClick={() => toggleTurbine(tid)}
                aria-pressed={active}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  borderRadius: 6,
                  border: `1px solid ${active ? C.accent : C.border}`,
                  background: active ? C.accentSoft : C.panelMuted,
                  color: active ? C.accent : C.sub,
                  cursor: 'pointer',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontWeight: active ? 600 : 500,
                }}
              >
                {tid}
              </button>
            );
          })}
        </div>
      </Card>

      {/* Filters */}
      <Card>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
            alignItems: 'flex-end',
          }}
        >
          <Field label={u('Start', '開始時間')}>
            <Input
              type="datetime-local"
              value={rangeStart}
              onChange={setRangeStart}
              fullWidth
              monospace
            />
          </Field>
          <Field label={u('End', '結束時間')}>
            <Input type="datetime-local" value={rangeEnd} onChange={setRangeEnd} fullWidth monospace />
          </Field>
          <Field label={u('Event type', '事件類型')}>
            <Select
              value={eventTypeFilter}
              onChange={setEventTypeFilter}
              options={[
                { value: '', label: u('All', '全部') },
                { value: 'fault', label: u('Fault', '故障') },
                { value: 'fault_lifecycle', label: u('Fault lifecycle', '故障生命週期') },
                { value: 'grid', label: u('Grid', '電網') },
                { value: 'state', label: u('State', '狀態') },
                { value: 'operator', label: u('Operator', '操作') },
                { value: 'wind', label: u('Wind', '風況') },
              ]}
              fullWidth
            />
          </Field>
          <div>
            <Btn variant="primary" onClick={exportEvents} fullWidth>
              {u('Export CSV', '匯出 CSV')}
            </Btn>
          </div>
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: C.sub }}>
          {loading
            ? u('Loading…', '載入中…')
            : `${timeline.length} ${u('events', '事件')} · ${selectedIds.length} ${u('turbines', '台')}`}
        </div>
      </Card>

      {/* Summary grid */}
      {selectedIds.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
            {u('Per-turbine summary', '單機摘要')}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 10,
            }}
          >
            {selectedIds.map(tid => {
              const s = summary[tid] || { total: 0, by_type: {} };
              return (
                <Card key={tid} tone="muted" padding={12}>
                  <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13, color: C.accent, fontWeight: 600 }}>
                    {tid}
                  </div>
                  <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 24, color: C.text, marginTop: 4 }}>
                    {s.total}
                  </div>
                  <div style={{ fontSize: 11, color: C.sub }}>{u('events', '事件')}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                    {Object.entries(s.by_type).map(([type, count]) => (
                      <StatusPill key={type} tone={eventTone(type)} size="sm">
                        {type}: {count as number}
                      </StatusPill>
                    ))}
                  </div>
                </Card>
              );
            })}
          </div>
        </Card>
      )}

      {/* Farm-wide events */}
      {farmEvents.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.amber, marginBottom: 10 }}>
            {u('Farm-wide events', '全場事件')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 200, overflowY: 'auto' }}>
            {farmEvents.slice(0, 30).map((ev, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 0',
                  borderBottom: i < farmEvents.length - 1 ? `1px solid ${C.border}` : undefined,
                  fontSize: 12,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    fontFamily: 'JetBrains Mono, monospace',
                    width: 160,
                    flexShrink: 0,
                  }}
                >
                  {new Date(ev.timestamp).toLocaleString()}
                </span>
                <StatusPill tone={eventTone(ev.event_type)}>{ev.event_type}</StatusPill>
                <span style={{ color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {ev.title}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Timeline */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
          {u('Event timeline', '事件時間線')}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 500, overflowY: 'auto' }}>
          {timeline.length === 0 && !loading && (
            <div style={{ color: C.sub, fontSize: 12, padding: 24, textAlign: 'center' }}>
              {u('No events found.', '未找到事件。')}
            </div>
          )}
          {timeline.map((ev, i) => (
            <div
              key={i}
              style={{
                display: 'grid',
                gridTemplateColumns: '160px 60px auto auto 1fr',
                gap: 10,
                padding: '8px 0',
                borderBottom: i < timeline.length - 1 ? `1px solid ${C.border}` : undefined,
                fontSize: 12,
                alignItems: 'baseline',
              }}
            >
              <span style={{ color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>
                {new Date(ev.timestamp).toLocaleString()}
              </span>
              <span style={{ color: C.accent, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                {ev._turbine_id || ev.turbine_id || '—'}
              </span>
              <StatusPill tone={eventTone(ev.event_type)}>{ev.event_type}</StatusPill>
              {ev.severity ? (
                <StatusPill tone={sevTone(ev.severity)}>{ev.severity}</StatusPill>
              ) : (
                <span />
              )}
              <span style={{ color: C.text, minWidth: 0 }}>
                {ev.title}
                {ev.detail && (
                  <span style={{ marginLeft: 6, fontSize: 11, color: C.sub }}>{ev.detail}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default EventComparisonView;

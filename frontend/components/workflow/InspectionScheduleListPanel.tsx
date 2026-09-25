/**
 * InspectionScheduleListPanel — 定檢計畫列表（WMOM-20260925-05）。
 *
 * 功能：
 *   - turbine selector（all / 各風機）— server-side filter
 *   - active_only toggle — server-side filter
 *   - 每筆 schedule 一張 card row：標題 + 風機 + 週期 + 下次到期時間 + active/暫停 pill
 *   - 點 row → onSelect → 開編輯 modal
 *
 * 視覺沿用 InventoryListPanel（filter row + counter + button-row list）。
 */

import React from 'react';
import { Btn, Card, Field, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type { InspectionScheduleResponse } from '../../services/inspectionScheduleService';
import { fmtDateTime, recurrenceLabel } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  items: InspectionScheduleResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  turbineOptions: { value: string; label: string }[];
  turbineId: string | 'all';
  onTurbineIdChange: (id: string | 'all') => void;
  activeOnly: boolean;
  onActiveOnlyChange: (v: boolean) => void;
  onSelect: (s: InspectionScheduleResponse) => void;
  onRefresh: () => void;
  lang: Lang;
}

const InspectionScheduleListPanel: React.FC<Props> = ({
  items,
  total,
  loading,
  error,
  turbineOptions,
  turbineId,
  onTurbineIdChange,
  activeOnly,
  onActiveOnlyChange,
  onSelect,
  onRefresh,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const options = [{ value: 'all', label: ui('All turbines', '全部風機') }, ...turbineOptions];

  return (
    <Card>
      {/* Filter row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(160px, 220px) auto auto',
          gap: 12,
          alignItems: 'end',
          marginBottom: 14,
        }}
      >
        <Field label={ui('Turbine', '風機')}>
          <Select
            value={turbineId}
            options={options}
            onChange={v => onTurbineIdChange(v as string | 'all')}
            ariaLabel={ui('Filter by turbine', '依風機過濾')}
            fullWidth
          />
        </Field>
        <Btn
          variant={activeOnly ? 'primary' : 'ghost'}
          onClick={() => onActiveOnlyChange(!activeOnly)}
          ariaLabel={ui('Toggle active-only filter', '切換僅顯示啟用中')}
          ariaPressed={activeOnly}
        >
          {activeOnly ? ui('Active only', '僅啟用中') : ui('All (incl. paused)', '全部（含暫停）')}
        </Btn>
        <Btn onClick={onRefresh} loading={loading} ariaLabel={ui('Refresh list', '重新整理列表')}>
          {loading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
        </Btn>
      </div>

      {/* Counter */}
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
        {ui(
          `Showing ${items.length} of ${total} inspection schedules`,
          `顯示 ${items.length} / ${total} 個定檢計畫`,
        )}
      </div>

      {error && (
        <Card tone="warn" padding={12} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
        </Card>
      )}

      {items.length === 0 && !loading && !error && (
        <Card tone="muted" padding={24}>
          <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
            {ui(
              'No inspection schedules match the current filter.',
              '目前沒有符合條件的定檢計畫。',
            )}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(s => (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s)}
            aria-label={`${ui('Open inspection schedule', '開啟定檢計畫')} ${s.title}`}
            style={{
              textAlign: 'left',
              background: C.panelMuted,
              border: `1px solid ${s.active ? C.border : C.warn}`,
              borderLeft: `4px solid ${s.active ? 'transparent' : C.warn}`,
              borderRadius: 12,
              padding: '12px 14px',
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'background 160ms ease',
              display: 'grid',
              gridTemplateColumns: 'minmax(180px, 1.4fr) minmax(140px, 1fr) auto',
              gap: 12,
              alignItems: 'center',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = C.panel;
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = C.panelMuted;
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{s.title}</div>
              <div
                style={{
                  fontSize: 12,
                  color: C.sub,
                  marginTop: 2,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {s.turbine_id}
              </div>
              <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>
                {recurrenceLabel(s.recurrence, lang)}
                {s.recurrence === 'custom_days' && s.interval_days != null && (
                  <> ({s.interval_days} {ui('days', '天')})</>
                )}
              </div>
            </div>

            <div style={{ fontSize: 12, color: C.text }}>
              <div style={{ color: C.sub, fontSize: 11 }}>{ui('Next due', '下次到期')}</div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                {fmtDateTime(s.next_due_at)}
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 4,
                alignItems: 'flex-end',
              }}
            >
              <StatusPill tone={s.active ? 'ok' : 'warn'} size="sm">
                {s.active ? ui('Active', '啟用中') : ui('Paused', '已暫停')}
              </StatusPill>
              {s.last_spawned_at && (
                <div style={{ fontSize: 10, color: C.faint }}>
                  {ui('Last spawned', '最近派工')} {fmtDateTime(s.last_spawned_at)}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
    </Card>
  );
};

export default InspectionScheduleListPanel;

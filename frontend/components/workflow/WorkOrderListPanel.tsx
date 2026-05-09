/**
 * WorkOrderListPanel — 工單列表 + status filter + business_key/title search。
 *
 * 功能（WMOM-20260504-19）：
 *   - status filter（all / 7 個 status）
 *   - search input（business_key / title / turbine_id 子字串 client filter）
 *   - 每筆工單一張 Card，點擊 onSelect → 開 detail modal
 *   - empty state / loading / error
 */

import React from 'react';
import {
  Btn,
  Card,
  Field,
  Input,
  Select,
  StatusPill,
} from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  WorkOrderStatusValues,
  type WorkOrderResponse,
  type WorkOrderStatus,
} from '../../services/workOrderService';
import {
  fmtDateTime,
  priorityLabel,
  priorityTone,
  statusLabel,
  statusTone,
  typeLabel,
} from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  items: WorkOrderResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  status: WorkOrderStatus | 'all';
  onStatusChange: (s: WorkOrderStatus | 'all') => void;
  search: string;
  onSearchChange: (v: string) => void;
  onSelect: (wo: WorkOrderResponse) => void;
  onRefresh: () => void;
  lang: Lang;
}

const WorkOrderListPanel: React.FC<Props> = ({
  items,
  total,
  loading,
  error,
  status,
  onStatusChange,
  search,
  onSearchChange,
  onSelect,
  onRefresh,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const statusOptions = [
    { value: 'all', label: ui('All status', '全部狀態') },
    ...WorkOrderStatusValues.map(s => ({
      value: s,
      label: statusLabel(s, lang),
    })),
  ];

  return (
    <Card>
      {/* Filter row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(160px, 220px) 1fr auto',
          gap: 12,
          alignItems: 'end',
          marginBottom: 14,
        }}
      >
        <Field label={ui('Status', '狀態')}>
          <Select
            value={status}
            options={statusOptions}
            onChange={v => onStatusChange(v as WorkOrderStatus | 'all')}
            ariaLabel={ui('Filter by status', '依狀態過濾')}
            fullWidth
          />
        </Field>
        <Field label={ui('Search (key / title / turbine)', '搜尋（編號 / 標題 / 風機）')}>
          <Input
            value={search}
            onChange={onSearchChange}
            placeholder={ui('e.g. WO-, gearbox, WTG01', '例：WO-、齒輪箱、WTG01')}
            fullWidth
            ariaLabel={ui('Search work orders', '搜尋工單')}
          />
        </Field>
        <Btn onClick={onRefresh} ariaLabel={ui('Refresh list', '重新整理列表')}>
          {loading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
        </Btn>
      </div>

      {/* Counter */}
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
        {ui(
          `Showing ${items.length} of ${total} work orders`,
          `顯示 ${items.length} / ${total} 筆工單`,
        )}
      </div>

      {/* Error */}
      {error && (
        <Card tone="warn" padding={12} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: C.warn }}>
            ⚠ {error}
          </div>
        </Card>
      )}

      {/* List */}
      {items.length === 0 && !loading && !error && (
        <Card tone="muted" padding={24}>
          <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
            {ui('No work orders match the current filter.', '目前沒有符合條件的工單。')}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(wo => (
          <button
            key={wo.id}
            type="button"
            onClick={() => onSelect(wo)}
            aria-label={`${ui('Open work order', '開啟工單')} ${wo.business_key}`}
            style={{
              textAlign: 'left',
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              padding: '12px 14px',
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'border-color 160ms ease, background 160ms ease',
              display: 'grid',
              gridTemplateColumns: 'minmax(180px, 1.2fr) 2fr auto',
              gap: 12,
              alignItems: 'center',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = C.accent;
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = C.border;
            }}
          >
            {/* Left col：business_key + turbine + type */}
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 13,
                  fontWeight: 600,
                  color: C.text,
                }}
              >
                {wo.business_key}
              </div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                {wo.turbine_id} · {typeLabel(wo.type, lang)}
              </div>
            </div>

            {/* Middle col：title + meta */}
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 14,
                  color: C.text,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {wo.title}
              </div>
              <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>
                {ui('Updated', '更新於')} {fmtDateTime(wo.updated_at)}
                {wo.estimated_hours != null && (
                  <>
                    {' · '}
                    {ui('Est.', '預估')} {wo.estimated_hours}h
                  </>
                )}
              </div>
            </div>

            {/* Right col：pills */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <StatusPill tone={priorityTone(wo.priority)} size="sm">
                {priorityLabel(wo.priority, lang)}
              </StatusPill>
              <StatusPill tone={statusTone(wo.status)} size="md">
                {statusLabel(wo.status, lang)}
              </StatusPill>
            </div>
          </button>
        ))}
      </div>
    </Card>
  );
};

export default WorkOrderListPanel;

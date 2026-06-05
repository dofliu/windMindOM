/**
 * MaterialRequestListPanel — 領料單列表 + status filter + business_key/work_order search。
 *
 * 功能（WMOM-20260509-06）：
 *   - status filter（all / 9 個 MR status）
 *   - search input（business_key / work_order_id 子字串 client filter）
 *   - 每筆 MR 一張 card row，點擊 onSelect → 開 detail modal
 *   - empty state / loading / error
 *
 * 設計沿用 WorkOrderListPanel 視覺與佈局。
 */

import React from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  MaterialRequestStatusValues,
  type MaterialRequestResponse,
  type MaterialRequestStatus,
} from '../../services/materialService';
import { fmtDateTime, mrStatusLabel, mrStatusTone } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  items: MaterialRequestResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  status: MaterialRequestStatus | 'all';
  onStatusChange: (s: MaterialRequestStatus | 'all') => void;
  search: string;
  onSearchChange: (v: string) => void;
  onSelect: (mr: MaterialRequestResponse) => void;
  onRefresh: () => void;
  lang: Lang;
}

const MaterialRequestListPanel: React.FC<Props> = ({
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
    ...MaterialRequestStatusValues.map(s => ({
      value: s,
      label: mrStatusLabel(s, lang),
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
            onChange={v => onStatusChange(v as MaterialRequestStatus | 'all')}
            ariaLabel={ui('Filter by status', '依狀態過濾')}
            fullWidth
          />
        </Field>
        <Field label={ui('Search (key / work order)', '搜尋（領料編號 / 工單）')}>
          <Input
            value={search}
            onChange={onSearchChange}
            placeholder={ui('e.g. MR-, work order UUID prefix', '例：MR-、工單 UUID 前綴')}
            fullWidth
            ariaLabel={ui('Search material requests', '搜尋領料單')}
          />
        </Field>
        <Btn onClick={onRefresh} loading={loading} ariaLabel={ui('Refresh list', '重新整理列表')}>
          {loading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
        </Btn>
      </div>

      {/* Counter */}
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
        {ui(
          `Showing ${items.length} of ${total} material requests`,
          `顯示 ${items.length} / ${total} 筆領料單`,
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
              'No material requests match the current filter.',
              '目前沒有符合條件的領料單。',
            )}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(mr => {
          const itemCount = mr.items.length;
          const totalEstimatedQty = mr.items.reduce(
            (sum, it) => sum + it.estimated_qty,
            0,
          );
          return (
            <button
              key={mr.id}
              type="button"
              onClick={() => onSelect(mr)}
              aria-label={`${ui('Open material request', '開啟領料單')} ${mr.business_key}`}
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
              {/* Left col：business_key + work_order linkage */}
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 13,
                    fontWeight: 600,
                    color: C.text,
                  }}
                >
                  {mr.business_key}
                </div>
                <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                  {mr.work_order_id
                    ? `${ui('WO', '工單')} …${mr.work_order_id.slice(-8)}`
                    : ui('(no linked work order)', '（無關聯工單）')}
                </div>
              </div>

              {/* Middle col：items summary + timestamps */}
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, color: C.text }}>
                  {ui(
                    `${itemCount} item${itemCount === 1 ? '' : 's'} · est. total qty ${totalEstimatedQty}`,
                    `${itemCount} 項料件 · 預估總量 ${totalEstimatedQty}`,
                  )}
                </div>
                <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>
                  {ui('Updated', '更新於')} {fmtDateTime(mr.updated_at)}
                </div>
              </div>

              {/* Right col：status pill */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <StatusPill tone={mrStatusTone(mr.status)} size="md">
                  {mrStatusLabel(mr.status, lang)}
                </StatusPill>
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
};

export default MaterialRequestListPanel;

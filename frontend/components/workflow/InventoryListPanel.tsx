/**
 * InventoryListPanel — 庫存料件列表（WMOM-20260509-07，A7）。
 *
 * 功能：
 *   - warehouse selector（all / 各倉）— server-side filter
 *   - below_safety_only toggle — server-side filter
 *   - search input（sku / name 子字串 client-side）
 *   - 每筆 item 一張 card row：SKU + name + 三欄 stock + safety_stock + LOW pill
 *   - 點 row → onSelect → 開 detail drawer
 *
 * 視覺沿用 MaterialRequestListPanel / WorkOrderListPanel。
 */

import React from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type {
  InventoryItemResponse,
  WarehouseResponse,
} from '../../services/inventoryService';
import { fmtDateTime } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  items: InventoryItemResponse[];
  total: number;
  loading: boolean;
  error: string | null;
  warehouses: WarehouseResponse[];
  warehouseId: string | 'all';
  onWarehouseChange: (id: string | 'all') => void;
  belowSafetyOnly: boolean;
  onBelowSafetyChange: (v: boolean) => void;
  search: string;
  onSearchChange: (v: string) => void;
  onSelect: (it: InventoryItemResponse) => void;
  onRefresh: () => void;
  lang: Lang;
}

const InventoryListPanel: React.FC<Props> = ({
  items,
  total,
  loading,
  error,
  warehouses,
  warehouseId,
  onWarehouseChange,
  belowSafetyOnly,
  onBelowSafetyChange,
  search,
  onSearchChange,
  onSelect,
  onRefresh,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const warehouseOptions = [
    { value: 'all', label: ui('All warehouses', '全部倉') },
    ...warehouses.map(w => ({
      value: w.id,
      label: w.is_default ? `★ ${w.name}` : w.name,
    })),
  ];

  return (
    <Card>
      {/* Filter row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(160px, 220px) auto minmax(160px, 1fr) auto',
          gap: 12,
          alignItems: 'end',
          marginBottom: 14,
        }}
      >
        <Field label={ui('Warehouse', '倉別')}>
          <Select
            value={warehouseId}
            options={warehouseOptions}
            onChange={v => onWarehouseChange(v as string | 'all')}
            ariaLabel={ui('Filter by warehouse', '依倉別過濾')}
            fullWidth
          />
        </Field>
        <Btn
          variant={belowSafetyOnly ? 'warn' : 'ghost'}
          onClick={() => onBelowSafetyChange(!belowSafetyOnly)}
          ariaLabel={ui('Toggle low-stock filter', '切換低於安全庫存過濾')}
          ariaPressed={belowSafetyOnly}
        >
          {belowSafetyOnly
            ? ui('Showing low stock only', '只顯示低於安全庫存')
            : ui('All stock', '全部')}
        </Btn>
        <Field label={ui('Search (SKU / name)', '搜尋（料號 / 名稱）')}>
          <Input
            value={search}
            onChange={onSearchChange}
            placeholder={ui('e.g. BRG-, gearbox bearing', '例：BRG-、齒輪箱軸承')}
            fullWidth
            ariaLabel={ui('Search inventory items', '搜尋料件')}
          />
        </Field>
        <Btn onClick={onRefresh} loading={loading} ariaLabel={ui('Refresh list', '重新整理列表')}>
          {loading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
        </Btn>
      </div>

      {/* Counter */}
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
        {ui(
          `Showing ${items.length} of ${total} inventory items`,
          `顯示 ${items.length} / ${total} 個料件`,
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
              'No inventory items match the current filter.',
              '目前沒有符合條件的料件。',
            )}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(it => {
          const totalAvailable = it.total_available;
          const isLow = it.below_safety;
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => onSelect(it)}
              aria-label={`${ui('Open inventory item', '開啟料件')} ${it.sku}`}
              style={{
                textAlign: 'left',
                background: C.panelMuted,
                border: `1px solid ${isLow ? C.warn : C.border}`,
                borderLeft: `4px solid ${isLow ? C.warn : 'transparent'}`,
                borderRadius: 12,
                padding: '12px 14px',
                cursor: 'pointer',
                fontFamily: 'inherit',
                transition: 'background 160ms ease',
                display: 'grid',
                gridTemplateColumns: 'minmax(180px, 1.4fr) minmax(160px, 1fr) auto',
                gap: 12,
                alignItems: 'center',
              }}
              onMouseEnter={e => {
                // 只動 background，不動 borderColor — 否則 hover 時 shorthand
                // borderColor 會把低庫存 row 的 4px warn borderLeft 蓋成 accent，
                // 弱化安全庫存警示視覺（code review 2026-05-18 Must-fix #2）。
                (e.currentTarget as HTMLButtonElement).style.background = C.panel;
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.background = C.panelMuted;
              }}
            >
              {/* Left col：SKU + name + unit */}
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 13,
                    fontWeight: 600,
                    color: C.text,
                  }}
                >
                  {it.sku}
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: C.sub,
                    marginTop: 2,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {it.name}
                </div>
                <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>
                  {ui('Unit', '單位')}: {it.unit}
                  {it.last_used_at && (
                    <>
                      {' · '}
                      {ui('Last used', '最後出庫')} {fmtDateTime(it.last_used_at)}
                    </>
                  )}
                </div>
              </div>

              {/* Middle col：3 stock cells */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                  fontSize: 12,
                }}
              >
                <StockCell label={ui('New', '全新')} qty={it.stock_new} />
                <StockCell label={ui('Used', '良品')} qty={it.stock_used} />
                <StockCell
                  label={ui('Repair', '維修中')}
                  qty={it.stock_repairing}
                />
              </div>

              {/* Right col：safety pill + total available */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  alignItems: 'flex-end',
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Safety', '安全')}: {it.safety_stock}
                </div>
                <div style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>
                  {ui('Available', '可用')}: {totalAvailable}
                </div>
                {isLow && (
                  <StatusPill tone="warn" size="sm">
                    {ui('LOW', '低於安全')}
                  </StatusPill>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
};

interface StockCellProps {
  label: string;
  qty: number;
}

const StockCell: React.FC<StockCellProps> = ({ label, qty }) => {
  const { C } = useTheme();
  return (
    <div
      style={{
        background: C.panel,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '4px 8px',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 10, color: C.faint, textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: C.text, fontWeight: 600 }}>{qty}</div>
    </div>
  );
};

export default InventoryListPanel;

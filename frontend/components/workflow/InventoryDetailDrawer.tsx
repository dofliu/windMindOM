/**
 * InventoryDetailDrawer — 料件詳情側邊 drawer + audit log（WMOM-20260509-07，A7）。
 *
 * 功能：
 *   - 右側 480px 滑出 drawer 顯示完整料件資料：identity / stocks / safety / unit_cost / timeline
 *   - 「Adjust stock」按鈕開 `InventoryAdjustmentDialog`（覆蓋 z=300，drawer z=180）
 *   - audit log（`GET /inventory/{id}/adjustments`）反序顯示；
 *     drawer 開啟時 lazy load；adjust 成功後 reload
 *
 * 視覺：右側 fixed drawer（與其他全螢幕 modal 不同，讓 user 可同時看左側 list context）。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Btn, Card, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type {
  AdjustInventoryPayload,
  AdjustInventoryResult,
  AdjustmentLogResponse,
  InventoryItemResponse,
} from '../../services/inventoryService';
import { fmtDateTime, stockKindLabel } from './statusUtils';
import InventoryAdjustmentDialog from './InventoryAdjustmentDialog';

type Lang = 'en' | 'zh';

interface Props {
  item: InventoryItemResponse;
  onAdjust: (
    itemId: string,
    req: AdjustInventoryPayload,
  ) => Promise<AdjustInventoryResult>;
  loadAdjustments: (itemId: string) => Promise<AdjustmentLogResponse[]>;
  onClose: () => void;
  lang: Lang;
}

const InventoryDetailDrawer: React.FC<Props> = ({
  item,
  onAdjust,
  loadAdjustments,
  onClose,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [logs, setLogs] = useState<AdjustmentLogResponse[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [showAdjustDialog, setShowAdjustDialog] = useState(false);

  const refreshLogs = useCallback(async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const next = await loadAdjustments(item.id);
      setLogs(next);
    } catch (e) {
      setLogsError(e instanceof Error ? e.message : String(e));
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  }, [item.id, loadAdjustments]);

  useEffect(() => {
    void refreshLogs();
  }, [refreshLogs]);

  const adjustForItem = useCallback(
    (req: AdjustInventoryPayload) => onAdjust(item.id, req),
    [item.id, onAdjust],
  );

  return (
    <>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={ui('Inventory item detail', '料件詳情')}
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 180,
          display: 'flex',
          justifyContent: 'flex-end',
        }}
      >
        <div
          onClick={e => e.stopPropagation()}
          style={{
            width: 'min(480px, 100vw)',
            height: '100%',
            background: C.bg,
            borderLeft: `1px solid ${C.border}`,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '16px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 14,
                  fontWeight: 600,
                  color: C.accent,
                }}
              >
                {item.sku}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: C.text,
                  marginTop: 2,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {item.name}
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label={ui('Close drawer', '關閉抽屜')}
              style={{
                background: 'transparent',
                border: 'none',
                color: C.sub,
                fontSize: 20,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: 16,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            {/* Stocks block */}
            <Card padding={14}>
              <div
                style={{
                  fontSize: 11,
                  color: C.sub,
                  textTransform: 'uppercase',
                  marginBottom: 6,
                }}
              >
                {ui('Stock breakdown', '庫存分項')}
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                }}
              >
                <StockTile
                  label={ui('New', '全新')}
                  qty={item.stock_new}
                />
                <StockTile
                  label={ui('Used', '良品')}
                  qty={item.stock_used}
                />
                <StockTile
                  label={ui('Repairing', '維修中')}
                  qty={item.stock_repairing}
                />
              </div>
              <div
                style={{
                  marginTop: 10,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 12,
                  color: C.sub,
                }}
              >
                <span>
                  {ui('Total available', '可用總計')}:{' '}
                  <strong style={{ color: C.text }}>{item.total_available}</strong>
                </span>
                <span>
                  {ui('Safety stock', '安全庫存')}: {item.safety_stock}
                </span>
                {item.below_safety && (
                  <StatusPill tone="warn" size="sm">
                    {ui('LOW', '低於安全')}
                  </StatusPill>
                )}
              </div>
            </Card>

            {/* Metadata block */}
            <Card padding={14}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '120px 1fr',
                  rowGap: 6,
                  columnGap: 10,
                  fontSize: 12,
                }}
              >
                <span style={{ color: C.sub }}>{ui('Unit', '單位')}</span>
                <span style={{ color: C.text }}>{item.unit}</span>
                <span style={{ color: C.sub }}>
                  {ui('Unit cost', '單位成本')}
                </span>
                <span
                  style={{
                    color: C.text,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                >
                  {item.unit_cost}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Description', '描述')}
                </span>
                <span style={{ color: C.text }}>
                  {item.description || ui('(none)', '（無）')}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Warehouse ID', '倉別 ID')}
                </span>
                <span
                  style={{
                    color: C.text,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                >
                  …{item.warehouse_id.slice(-8)}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Last received', '最後入庫')}
                </span>
                <span style={{ color: C.text }}>
                  {fmtDateTime(item.last_received_at)}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Last used', '最後出庫')}
                </span>
                <span style={{ color: C.text }}>
                  {fmtDateTime(item.last_used_at)}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Created', '建立時間')}
                </span>
                <span style={{ color: C.text }}>
                  {fmtDateTime(item.created_at)}
                </span>
                <span style={{ color: C.sub }}>
                  {ui('Updated', '更新時間')}
                </span>
                <span style={{ color: C.text }}>
                  {fmtDateTime(item.updated_at)}
                </span>
              </div>
            </Card>

            {/* Audit log */}
            <Card padding={14}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Adjustment log', '異動紀錄')} ({logs.length})
                </div>
                <Btn
                  size="sm"
                  variant="ghost"
                  onClick={() => void refreshLogs()}
                  ariaLabel={ui('Refresh adjustment log', '重新整理異動紀錄')}
                >
                  {logsLoading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
                </Btn>
              </div>

              {logsError && (
                <Card tone="warn" padding={10} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, color: C.warn }}>⚠ {logsError}</div>
                </Card>
              )}

              {!logsLoading && logs.length === 0 && !logsError && (
                <div
                  style={{
                    fontSize: 12,
                    color: C.faint,
                    textAlign: 'center',
                    padding: 12,
                  }}
                >
                  {ui('No adjustments yet.', '尚無異動紀錄。')}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {logs.map(log => (
                  <AuditRow key={log.id} log={log} lang={lang} />
                ))}
              </div>
            </Card>
          </div>

          {/* Footer */}
          <div
            style={{
              padding: '12px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <Btn
              variant="primary"
              onClick={() => setShowAdjustDialog(true)}
              ariaLabel={ui('Open adjust stock dialog', '開啟調整庫存對話框')}
            >
              + {ui('Adjust stock', '調整庫存')}
            </Btn>
          </div>
        </div>
      </div>

      {showAdjustDialog && (
        <InventoryAdjustmentDialog
          item={item}
          onAdjust={adjustForItem}
          onClose={() => setShowAdjustDialog(false)}
          onAdjusted={() => {
            void refreshLogs();
          }}
          lang={lang}
        />
      )}
    </>
  );
};

interface StockTileProps {
  label: string;
  qty: number;
}

const StockTile: React.FC<StockTileProps> = ({ label, qty }) => {
  const { C } = useTheme();
  return (
    <div
      style={{
        background: C.panelMuted,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '8px 10px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          fontSize: 10,
          color: C.faint,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: C.text }}>{qty}</div>
    </div>
  );
};

interface AuditRowProps {
  log: AdjustmentLogResponse;
  lang: Lang;
}

const AuditRow: React.FC<AuditRowProps> = ({ log, lang }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const sign = log.delta > 0 ? '+' : '';
  const positive = log.delta > 0;
  return (
    <div
      style={{
        background: C.panelMuted,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '8px 10px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 13,
            fontWeight: 600,
            color: positive ? C.ok : C.warn,
          }}
        >
          {sign}
          {log.delta} {stockKindLabel(log.delta_kind, lang)}
        </span>
        <span style={{ fontSize: 11, color: C.faint }}>
          {fmtDateTime(log.occurred_at)}
        </span>
      </div>
      <div style={{ fontSize: 12, color: C.text }}>{log.reason}</div>
      {log.note && (
        <div style={{ fontSize: 11, color: C.sub }}>
          {ui('Note', '備註')}: {log.note}
        </div>
      )}
      <div
        style={{
          fontSize: 10,
          color: C.faint,
          fontFamily: 'JetBrains Mono, monospace',
        }}
      >
        {ui('Actor', '操作者')}{' '}
        {log.actor_id ? `…${log.actor_id.slice(-8)}` : ui('system', '系統')}
      </div>
    </div>
  );
};

export default InventoryDetailDrawer;

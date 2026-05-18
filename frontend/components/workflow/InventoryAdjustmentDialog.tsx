/**
 * InventoryAdjustmentDialog — 手動 +/- stock 調整對話框（WMOM-20260509-07，A7）。
 *
 * 功能：
 *   - 顯示目前 SKU + name + 三欄現有 stock 給 context
 *   - 選 delta_kind（new / used / repairing）
 *   - 整數 delta input（允許負，扣到負數 backend 回 409）
 *   - reason 必填（給 audit log 用）
 *   - 選填 note
 *   - 預覽：「{label} {old}{sign}{abs} = {new}」幫 user 確認方向
 *   - 提交呼 `useInventory.adjust`；成功 patch list + 觸發 onAdjusted callback
 *
 * 視覺：modal 覆蓋（與 ApprovalActionDialog / DispatchModal 同 pattern）。
 */

import React, { useState } from 'react';
import { Btn, Card, Field, Input, Select } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import {
  StockKindValues,
  type AdjustInventoryPayload,
  type AdjustInventoryResult,
  type InventoryItemResponse,
  type StockKind,
} from '../../services/inventoryService';
import { stockKindLabel } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  item: InventoryItemResponse;
  onAdjust: (req: AdjustInventoryPayload) => Promise<AdjustInventoryResult>;
  onClose: () => void;
  /** 調整成功後 caller 可選擇 refresh audit log / 顯示 toast 等。 */
  onAdjusted?: (result: AdjustInventoryResult) => void;
  lang: Lang;
}

const InventoryAdjustmentDialog: React.FC<Props> = ({
  item,
  onAdjust,
  onClose,
  onAdjusted,
  lang,
}) => {
  const { C } = useTheme();
  const { currentUser } = useCurrentUser();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [deltaKind, setDeltaKind] = useState<StockKind>('new');
  const [deltaRaw, setDeltaRaw] = useState<string>('1');
  const [reason, setReason] = useState<string>('');
  const [note, setNote] = useState<string>('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deltaParsed = Number.parseInt(deltaRaw, 10);
  const deltaValid = Number.isFinite(deltaParsed) && deltaParsed !== 0;
  const reasonValid = reason.trim().length > 0;
  const canSubmit = deltaValid && reasonValid && !submitting;

  const currentQty =
    deltaKind === 'new'
      ? item.stock_new
      : deltaKind === 'used'
        ? item.stock_used
        : item.stock_repairing;
  const previewNext = deltaValid ? currentQty + deltaParsed : currentQty;
  const previewNegative = previewNext < 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await onAdjust({
        delta_kind: deltaKind,
        delta: deltaParsed,
        reason: reason.trim(),
        actor_id: currentUser.id,
        note: note.trim() || undefined,
      });
      onAdjusted?.(result);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ui('Adjust inventory', '調整庫存')}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        zIndex: 300, // 高於 detail drawer
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 520 }}
      >
        <Card padding={0}>
          <div
            style={{
              padding: '16px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div style={{ minWidth: 0 }}>
              <h3
                style={{
                  margin: 0,
                  fontFamily: '"DM Serif Display", serif',
                  fontSize: 20,
                  fontWeight: 400,
                  color: C.text,
                }}
              >
                {ui('Adjust stock', '調整庫存')}
              </h3>
              <div
                style={{
                  fontSize: 12,
                  color: C.sub,
                  marginTop: 4,
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              >
                {item.sku} · {item.name}
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label={ui('Close', '關閉')}
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

          <div
            style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            {/* 目前 stock 三欄回顧 */}
            <Card tone="muted" padding={12}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                  fontSize: 12,
                }}
              >
                {(['new', 'used', 'repairing'] as const).map(k => {
                  const qty =
                    k === 'new'
                      ? item.stock_new
                      : k === 'used'
                        ? item.stock_used
                        : item.stock_repairing;
                  return (
                    <div key={k} style={{ textAlign: 'center' }}>
                      <div
                        style={{
                          fontSize: 10,
                          color: C.faint,
                          textTransform: 'uppercase',
                        }}
                      >
                        {stockKindLabel(k, lang)}
                      </div>
                      <div
                        style={{ fontSize: 14, color: C.text, fontWeight: 600 }}
                      >
                        {qty}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Field label={ui('Stock kind', '庫存類別')}>
              <Select
                value={deltaKind}
                options={StockKindValues.map(k => ({
                  value: k,
                  label: stockKindLabel(k, lang),
                }))}
                onChange={v => setDeltaKind(v as StockKind)}
                ariaLabel={ui('Choose stock kind', '選擇庫存類別')}
                fullWidth
              />
            </Field>

            <Field
              label={ui('Delta (+/-)', '異動量（正=加，負=扣）')}
              hint={ui(
                'Integer, non-zero. Negative deltas are allowed but a deficit (resulting in stock < 0) will be rejected with 409.',
                '整數，不可為 0。可填負數扣庫，但若扣到負數會被後端 409 拒絕。',
              )}
            >
              <Input
                type="number"
                value={deltaRaw}
                onChange={setDeltaRaw}
                step={1}
                ariaLabel={ui('Delta value', '異動量數值')}
                fullWidth
              />
            </Field>

            {/* preview */}
            <Card tone={previewNegative ? 'warn' : 'accent'} padding={12}>
              <div style={{ fontSize: 12, color: C.sub }}>
                {ui('Preview', '預覽')}
              </div>
              <div
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 14,
                  color: previewNegative ? C.warn : C.text,
                  fontWeight: 600,
                  marginTop: 4,
                }}
              >
                {stockKindLabel(deltaKind, lang)}: {currentQty}{' '}
                {deltaValid && deltaParsed >= 0 ? '+' : ''}
                {deltaValid ? deltaParsed : 0} = {previewNext}
              </div>
              {previewNegative && (
                <div style={{ fontSize: 11, color: C.warn, marginTop: 4 }}>
                  ⚠{' '}
                  {ui(
                    'Stock would become negative — backend will return 409 Insufficient Stock.',
                    '庫存將為負數 — 後端會回 409 Insufficient Stock。',
                  )}
                </div>
              )}
            </Card>

            <Field
              label={ui('Reason (required)', '原因（必填）')}
              hint={ui(
                'Written into audit log; e.g. "盤盈", "良品歸還", "盤虧".',
                '寫入 audit log；如「盤盈」、「良品歸還」、「盤虧」。',
              )}
            >
              <Input
                value={reason}
                onChange={setReason}
                placeholder={ui('e.g. inventory count surplus', '例：盤盈')}
                fullWidth
                ariaLabel={ui('Adjustment reason', '異動原因')}
              />
            </Field>

            <Field label={ui('Note (optional)', '備註（選填）')}>
              <Input
                value={note}
                onChange={setNote}
                placeholder={ui('Extra context if any', '額外備註')}
                fullWidth
                ariaLabel={ui('Adjustment note', '異動備註')}
              />
            </Field>

            {error && (
              <Card tone="warn" padding={10}>
                <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
              </Card>
            )}
          </div>

          <div
            style={{
              padding: '12px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <Btn
              variant="ghost"
              onClick={onClose}
              ariaLabel={ui('Cancel', '取消')}
            >
              {ui('Cancel', '取消')}
            </Btn>
            <Btn
              variant="primary"
              onClick={handleSubmit}
              disabled={!canSubmit}
              loading={submitting}
              ariaLabel={ui('Submit adjustment', '送出異動')}
            >
              {submitting
                ? ui('Submitting…', '送出中…')
                : ui('Submit adjustment', '送出異動')}
            </Btn>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default InventoryAdjustmentDialog;

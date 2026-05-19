/**
 * MaterialRequestDetailModal — 領料單詳情 + 6 個 transition 控制（WMOM-20260509-06）。
 *
 * 提供 transitions：
 *   - submit_for_approval（DRAFT → AWAITING_APPROVAL，自動建 3 階 chain）
 *   - dispatch（APPROVED → DISPATCHED；通常 backend 簽核完自動觸發，這裡給 ops 手動補）
 *   - receive（DISPATCHED → RECEIVED + 填 actual_qty）
 *   - close（RECEIVED / USED → CLOSED）
 *   - cancel（DRAFT / AWAITING_APPROVAL / APPROVED → CANCELLED）
 *   - createReturn（建退料記錄 + atomic 加回 stock，不改 MR status）
 *
 * 核准（approve / reject）走 approval tab，不在此 modal。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  ReturnReasonValues,
  StockKindValues,
  type CreateMaterialReturnPayload,
  type MaterialRequestResponse,
  type ReturnReason,
  type StockKind,
} from '../../services/materialService';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import {
  fmtDateTime,
  mrStatusLabel,
  mrStatusTone,
  returnReasonLabel,
  stockKindLabel,
} from './statusUtils';

type Lang = 'en' | 'zh';

type ActionForm =
  | null
  | 'submit'
  | 'dispatch'
  | 'receive'
  | 'close'
  | 'cancel'
  | 'return';

interface Props {
  materialRequest: MaterialRequestResponse;
  onSubmitForApproval: (
    id: string,
    actorId: string,
  ) => Promise<MaterialRequestResponse>;
  onDispatch: (id: string, actorId: string) => Promise<MaterialRequestResponse>;
  onReceive: (
    id: string,
    actorId: string,
    actualQuantities: Record<string, number>,
  ) => Promise<MaterialRequestResponse>;
  onClose: (id: string, actorId: string) => Promise<MaterialRequestResponse>;
  onCancel: (
    id: string,
    actorId: string,
    reason: string,
  ) => Promise<MaterialRequestResponse>;
  onCreateReturn: (id: string, payload: CreateMaterialReturnPayload) => Promise<void>;
  onCloseModal: () => void;
  lang: Lang;
}

const MaterialRequestDetailModal: React.FC<Props> = ({
  materialRequest: initialMR,
  onSubmitForApproval,
  onDispatch,
  onReceive,
  onClose,
  onCancel,
  onCreateReturn,
  onCloseModal,
  lang,
}) => {
  const { C } = useTheme();
  const { currentUser } = useCurrentUser();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [mr, setMR] = useState<MaterialRequestResponse>(initialMR);
  useEffect(() => setMR(initialMR), [initialMR]);

  const [activeForm, setActiveForm] = useState<ActionForm>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form fields
  const [cancelReason, setCancelReason] = useState('');
  const [actualQuantities, setActualQuantities] = useState<Record<string, string>>(
    {},
  );
  // return form
  const [returnItemId, setReturnItemId] = useState<string>('');
  const [returnQty, setReturnQty] = useState<string>('1');
  const [returnReason, setReturnReason] = useState<ReturnReason>('surplus');
  const [returnToKind, setReturnToKind] = useState<StockKind>('new');
  const [returnNote, setReturnNote] = useState('');

  const resetForms = () => {
    setActiveForm(null);
    setError(null);
    setCancelReason('');
    setActualQuantities({});
    setReturnItemId('');
    setReturnQty('1');
    setReturnReason('surplus');
    setReturnToKind('new');
    setReturnNote('');
  };

  const runMutation = async (fn: () => Promise<MaterialRequestResponse>) => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await fn();
      setMR(updated);
      resetForms();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  // 開 receive form 時自動以 estimated_qty 預填
  useEffect(() => {
    if (activeForm === 'receive') {
      const next: Record<string, string> = {};
      for (const it of mr.items) {
        next[it.id] = String(it.estimated_qty);
      }
      setActualQuantities(next);
    }
  }, [activeForm, mr.items]);

  // ── status-driven visibility ──
  const status = mr.status;
  const canSubmit = status === 'draft';
  const canDispatchManual = status === 'approved';
  const canReceive = status === 'dispatched';
  const canClose = status === 'received' || status === 'used';
  const canCancel =
    status === 'draft' || status === 'awaiting_approval' || status === 'approved';
  // 退料只在已出庫之後且未結案前合理
  const canReturn =
    status === 'dispatched' || status === 'received' || status === 'used';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ui('Material request detail', '領料單詳情')}
      onClick={onCloseModal}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 200,
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 880,
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card
          padding={0}
          style={{
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            maxHeight: '92vh',
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
              gap: 12,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <h2
                style={{
                  margin: 0,
                  fontFamily: '"DM Serif Display", serif',
                  fontSize: 24,
                  fontWeight: 400,
                  color: C.text,
                }}
              >
                {ui('Material request', '領料單')}
              </h2>
              <div
                style={{
                  fontSize: 12,
                  color: C.sub,
                  marginTop: 4,
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                <span
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    color: C.accent,
                  }}
                >
                  {mr.business_key}
                </span>
                <StatusPill tone={mrStatusTone(mr.status)} size="md">
                  {mrStatusLabel(mr.status, lang)}
                </StatusPill>
                {mr.work_order_id && (
                  <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                    {ui('WO', '工單')} …{mr.work_order_id.slice(-8)}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={onCloseModal}
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

          {/* Body */}
          <div
            style={{
              padding: 20,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            {/* Timeline grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 10,
              }}
            >
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Requested', '申請時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.requested_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Submitted', '送簽時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.submitted_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Approved', '通過時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.approved_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Dispatched', '出庫時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.dispatched_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Received', '簽收時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.received_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Closed', '結案時間')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                  }}
                >
                  {fmtDateTime(mr.closed_at)}
                </div>
              </Card>
            </div>

            {/* Items table */}
            <div>
              <div
                style={{
                  fontSize: 12,
                  color: C.sub,
                  marginBottom: 6,
                  textTransform: 'uppercase',
                }}
              >
                {ui('Items', '料件明細')}
              </div>
              <Card tone="muted" padding={0}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 2fr 1fr 1fr 1fr',
                    padding: '8px 12px',
                    borderBottom: `1px solid ${C.border}`,
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  <div>{ui('SKU', '料號')}</div>
                  <div>{ui('Name', '料件名')}</div>
                  <div>{ui('Stock kind', '庫存類型')}</div>
                  <div>{ui('Est. qty', '預估量')}</div>
                  <div>{ui('Actual qty', '實領量')}</div>
                </div>
                {mr.items.map(it => (
                  <div
                    key={it.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 2fr 1fr 1fr 1fr',
                      padding: '8px 12px',
                      borderTop: `1px solid ${C.border}`,
                      fontSize: 12,
                      color: C.text,
                      alignItems: 'center',
                    }}
                  >
                    <div
                      style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}
                      title={it.item_id}
                    >
                      {it.sku ?? `…${it.item_id.slice(-8)}`}
                    </div>
                    <div
                      style={{
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={it.name ?? undefined}
                    >
                      {it.name ?? '—'}
                    </div>
                    <div>{stockKindLabel(it.stock_kind, lang)}</div>
                    <div>
                      {it.estimated_qty}
                      {it.unit ? ` ${it.unit}` : ''}
                    </div>
                    <div>
                      {it.actual_qty ?? '—'}
                      {it.actual_qty !== null && it.unit ? ` ${it.unit}` : ''}
                    </div>
                  </div>
                ))}
              </Card>
            </div>

            {/* Cancel / reject reason (if any) */}
            {mr.cancel_reason && (
              <Card tone="warn" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Cancel reason', '取消原因')}
                </div>
                <div style={{ fontSize: 13, color: C.text, marginTop: 4 }}>
                  {mr.cancel_reason}
                </div>
              </Card>
            )}
            {mr.reject_reason && (
              <Card tone="warn" padding={12}>
                <div
                  style={{
                    fontSize: 11,
                    color: C.sub,
                    textTransform: 'uppercase',
                  }}
                >
                  {ui('Reject reason', '駁回原因')}
                </div>
                <div style={{ fontSize: 13, color: C.text, marginTop: 4 }}>
                  {mr.reject_reason}
                </div>
              </Card>
            )}

            {/* Action form */}
            {activeForm && (
              <Card tone="muted" padding={14}>
                {activeForm === 'submit' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 13, color: C.text }}>
                      {ui(
                        'Submit this draft to start the 3-step approval chain (employee → leader → treasury).',
                        '送出後啟動 3 階簽核 chain（員工 → 組長 → 總務）。',
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Cancel', '取消')}>
                        {ui('Cancel', '取消')}
                      </Btn>
                      <Btn
                        variant="primary"
                        disabled={submitting}
                        onClick={() =>
                          runMutation(() => onSubmitForApproval(mr.id, currentUser.id))
                        }
                        ariaLabel={ui('Confirm submit', '確認送簽')}
                      >
                        {submitting ? ui('Submitting…', '送簽中…') : ui('Confirm', '確認')}
                      </Btn>
                    </div>
                  </div>
                )}

                {activeForm === 'dispatch' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 13, color: C.text }}>
                      {ui(
                        'Manually dispatch (deduct stock + write cost ledger). Normally triggered automatically after the last approval step.',
                        '手動派發出庫（扣 stock + 寫成本帳）。一般情況下，最後一階簽核完成會自動派發。',
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Cancel', '取消')}>
                        {ui('Cancel', '取消')}
                      </Btn>
                      <Btn
                        variant="primary"
                        disabled={submitting}
                        onClick={() => runMutation(() => onDispatch(mr.id, currentUser.id))}
                        ariaLabel={ui('Confirm dispatch', '確認派發')}
                      >
                        {submitting ? ui('Dispatching…', '派發中…') : ui('Confirm', '確認')}
                      </Btn>
                    </div>
                  </div>
                )}

                {activeForm === 'receive' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ fontSize: 13, color: C.text }}>
                      {ui(
                        'Fill actual received quantity for each item.',
                        '填寫每項料件的實際領取數量。',
                      )}
                    </div>
                    {mr.items.map(it => (
                      <Field
                        key={it.id}
                        label={
                          <>
                            <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                              {it.sku ?? `…${it.item_id.slice(-8)}`}
                            </span>
                            {it.name ? ` · ${it.name}` : ''}{' '}
                            ({ui('est.', '預估')} {it.estimated_qty}
                            {it.unit ? ` ${it.unit}` : ''})
                          </>
                        }
                      >
                        <Input
                          type="number"
                          min={0}
                          value={actualQuantities[it.id] ?? ''}
                          onChange={v =>
                            setActualQuantities(prev => ({ ...prev, [it.id]: v }))
                          }
                          fullWidth
                          ariaLabel={`actual_qty ${it.item_id}`}
                        />
                      </Field>
                    ))}
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Cancel', '取消')}>
                        {ui('Cancel', '取消')}
                      </Btn>
                      <Btn
                        variant="primary"
                        disabled={submitting}
                        onClick={() => {
                          const parsed: Record<string, number> = {};
                          let hasInvalid = false;
                          for (const it of mr.items) {
                            const raw = actualQuantities[it.id];
                            const n = parseInt(raw ?? '', 10);
                            if (Number.isNaN(n) || n < 0) {
                              hasInvalid = true;
                              break;
                            }
                            parsed[it.id] = n;
                          }
                          if (hasInvalid) {
                            setError(
                              ui(
                                'Each actual_qty must be a non-negative integer.',
                                '每項實際數量必須是非負整數。',
                              ),
                            );
                            return;
                          }
                          runMutation(() => onReceive(mr.id, currentUser.id, parsed));
                        }}
                        ariaLabel={ui('Confirm receive', '確認簽收')}
                      >
                        {submitting ? ui('Receiving…', '簽收中…') : ui('Confirm', '確認')}
                      </Btn>
                    </div>
                  </div>
                )}

                {activeForm === 'close' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 13, color: C.text }}>
                      {ui(
                        'Close this material request. After close, no further state transitions are allowed.',
                        '結案此領料單。結案後不可再轉狀態。',
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Cancel', '取消')}>
                        {ui('Cancel', '取消')}
                      </Btn>
                      <Btn
                        variant="primary"
                        disabled={submitting}
                        onClick={() => runMutation(() => onClose(mr.id, currentUser.id))}
                        ariaLabel={ui('Confirm close', '確認結案')}
                      >
                        {submitting ? ui('Closing…', '結案中…') : ui('Confirm', '確認')}
                      </Btn>
                    </div>
                  </div>
                )}

                {activeForm === 'cancel' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <Field label={ui('Cancel reason', '取消原因')} fullWidth>
                      <Input
                        value={cancelReason}
                        onChange={setCancelReason}
                        placeholder={ui(
                          'e.g. duplicate request',
                          '例：重複申請',
                        )}
                        fullWidth
                        ariaLabel={ui('Cancel reason', '取消原因')}
                      />
                    </Field>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Back', '返回')}>
                        {ui('Back', '返回')}
                      </Btn>
                      <Btn
                        variant="warn"
                        disabled={submitting || !cancelReason.trim()}
                        onClick={() =>
                          runMutation(() =>
                            onCancel(mr.id, currentUser.id, cancelReason.trim()),
                          )
                        }
                        ariaLabel={ui('Confirm cancel', '確認取消')}
                      >
                        {submitting ? ui('Cancelling…', '取消中…') : ui('Cancel request', '取消領料單')}
                      </Btn>
                    </div>
                  </div>
                )}

                {activeForm === 'return' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <Field label={ui('Item to return', '退料項目')} fullWidth>
                      <Select
                        value={returnItemId}
                        options={[
                          { value: '', label: ui('— Select item —', '— 選擇項目 —') },
                          ...mr.items.map(it => {
                            const id = it.sku ?? `…${it.item_id.slice(-8)}`;
                            const namePart = it.name ? ` · ${it.name}` : '';
                            const unitPart = it.unit ? ` ${it.unit}` : '';
                            return {
                              value: it.item_id,
                              label: `${id}${namePart} · ${ui('est.', '預估')} ${it.estimated_qty}${unitPart}`,
                            };
                          }),
                        ]}
                        onChange={setReturnItemId}
                        ariaLabel={ui('Item to return', '退料項目')}
                        fullWidth
                      />
                    </Field>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr 1fr',
                        gap: 8,
                      }}
                    >
                      <Field label={ui('Qty', '數量')}>
                        <Input
                          type="number"
                          min={1}
                          value={returnQty}
                          onChange={setReturnQty}
                          fullWidth
                          ariaLabel={ui('Return qty', '退料數量')}
                        />
                      </Field>
                      <Field label={ui('Reason', '原因')}>
                        <Select
                          value={returnReason}
                          options={ReturnReasonValues.map(r => ({
                            value: r,
                            label: returnReasonLabel(r, lang),
                          }))}
                          onChange={v => setReturnReason(v as ReturnReason)}
                          ariaLabel={ui('Return reason', '退料原因')}
                          fullWidth
                        />
                      </Field>
                      <Field label={ui('Return to', '入哪欄')}>
                        <Select
                          value={returnToKind}
                          options={StockKindValues.map(k => ({
                            value: k,
                            label: stockKindLabel(k, lang),
                          }))}
                          onChange={v => setReturnToKind(v as StockKind)}
                          ariaLabel={ui('Return to stock kind', '退回庫存類型')}
                          fullWidth
                        />
                      </Field>
                    </div>
                    <Field label={ui('Note (optional)', '備註（選填）')} fullWidth>
                      <Input
                        value={returnNote}
                        onChange={setReturnNote}
                        placeholder={ui('e.g. wrong sku', '例：拿錯料件')}
                        fullWidth
                        ariaLabel={ui('Return note', '退料備註')}
                      />
                    </Field>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <Btn onClick={resetForms} ariaLabel={ui('Back', '返回')}>
                        {ui('Back', '返回')}
                      </Btn>
                      <Btn
                        variant="primary"
                        disabled={
                          submitting ||
                          !returnItemId ||
                          !returnQty ||
                          parseInt(returnQty, 10) < 1
                        }
                        onClick={async () => {
                          setSubmitting(true);
                          setError(null);
                          try {
                            await onCreateReturn(mr.id, {
                              item_id: returnItemId,
                              qty: parseInt(returnQty, 10),
                              reason: returnReason,
                              return_to_kind: returnToKind,
                              returned_by: currentUser.id,
                              note: returnNote.trim() || null,
                            });
                            resetForms();
                          } catch (e) {
                            setError(e instanceof Error ? e.message : String(e));
                          } finally {
                            setSubmitting(false);
                          }
                        }}
                        ariaLabel={ui('Confirm return', '確認退料')}
                      >
                        {submitting ? ui('Returning…', '退料中…') : ui('Confirm return', '確認退料')}
                      </Btn>
                    </div>
                  </div>
                )}
              </Card>
            )}

            {error && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
              </Card>
            )}
          </div>

          {/* Footer：action buttons */}
          <div
            style={{
              padding: '14px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 8,
              flexShrink: 0,
              flexWrap: 'wrap',
            }}
          >
            <Btn onClick={onCloseModal} ariaLabel={ui('Close', '關閉')}>
              {ui('Close', '關閉')}
            </Btn>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {canCancel && (
                <Btn
                  variant="warn"
                  size="sm"
                  onClick={() => setActiveForm('cancel')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Cancel request', '取消領料單')}
                >
                  {ui('Cancel', '取消')}
                </Btn>
              )}
              {canReturn && (
                <Btn
                  size="sm"
                  onClick={() => setActiveForm('return')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Create return', '建退料')}
                >
                  + {ui('Return', '退料')}
                </Btn>
              )}
              {canSubmit && (
                <Btn
                  variant="primary"
                  size="sm"
                  onClick={() => setActiveForm('submit')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Submit for approval', '送出簽核')}
                >
                  {ui('Submit for approval', '送出簽核')}
                </Btn>
              )}
              {canDispatchManual && (
                <Btn
                  size="sm"
                  onClick={() => setActiveForm('dispatch')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Dispatch', '派發')}
                >
                  {ui('Dispatch', '派發')}
                </Btn>
              )}
              {canReceive && (
                <Btn
                  variant="primary"
                  size="sm"
                  onClick={() => setActiveForm('receive')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Receive', '簽收')}
                >
                  {ui('Receive', '簽收')}
                </Btn>
              )}
              {canClose && (
                <Btn
                  variant="primary"
                  size="sm"
                  onClick={() => setActiveForm('close')}
                  disabled={!!activeForm}
                  ariaLabel={ui('Close request', '結案')}
                >
                  {ui('Close', '結案')}
                </Btn>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default MaterialRequestDetailModal;

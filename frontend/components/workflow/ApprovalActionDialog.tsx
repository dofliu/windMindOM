/**
 * ApprovalActionDialog — 簽核 / 駁回對話框（WMOM-20260504-20）。
 *
 * 兩個模式：
 *   - approve：comment 選填，按鈕 primary
 *   - reject：reason 必填（>=1 char），按鈕 danger
 *
 * 上方顯示工單摘要（business_key / title / turbine / priority）讓 reviewer 確認
 * 在簽哪一張，避免簽錯（DN-02 風險點）。
 */

import React, { useState } from 'react';
import { Btn, Card, Field, Input, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type {
  ApprovalResultResponse,
  PendingSignoffItem,
  WorkOrderResponse,
} from '../../services/workOrderService';
import {
  priorityLabel,
  priorityTone,
  signoffLevelLabel,
  statusLabel,
  statusTone,
  subjectTypeLabel,
  typeLabel,
} from './statusUtils';

type Lang = 'en' | 'zh';
export type ApprovalMode = 'approve' | 'reject';

interface Props {
  mode: ApprovalMode;
  pending: PendingSignoffItem;
  /** 對應的 work_order detail；material_request subject 或 cache miss 時為 null */
  workOrder: WorkOrderResponse | null;
  onClose: () => void;
  /** 成功 callback；dialog 內處理 try/catch 把 error 顯示在底部 */
  onApprove: (stepId: string, comment: string | null) => Promise<ApprovalResultResponse>;
  onReject: (stepId: string, reason: string) => Promise<ApprovalResultResponse>;
  lang: Lang;
}

const ApprovalActionDialog: React.FC<Props> = ({
  mode,
  pending,
  workOrder,
  onClose,
  onApprove,
  onReject,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [comment, setComment] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const { step, chain } = pending;
  const isReject = mode === 'reject';
  const canSubmit = isReject ? reason.trim().length > 0 : true;

  const handleSubmit = async () => {
    setError(null);
    setWarning(null);
    setSubmitting(true);
    try {
      const result = isReject
        ? await onReject(step.id, reason.trim())
        : await onApprove(step.id, comment.trim() || null);
      if (result.subject_transition_error) {
        // chain 已 approve / reject 但工單 transition 失敗 → 只警告，不算錯誤
        setWarning(result.subject_transition_error);
      } else {
        onClose();
      }
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
      aria-label={isReject ? ui('Reject approval', '駁回簽核') : ui('Approve step', '通過此階')}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 220,
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 560 }}
      >
        <Card padding={0} style={{ overflow: 'hidden' }}>
          {/* Header */}
          <div
            style={{
              padding: '16px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <h2
              style={{
                margin: 0,
                fontFamily: '"DM Serif Display", serif',
                fontSize: 22,
                fontWeight: 400,
                color: C.text,
              }}
            >
              {isReject
                ? ui('Reject approval', '駁回簽核')
                : ui('Approve step', '通過此階')}
            </h2>
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

          <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Subject summary */}
            <Card tone="muted" padding={12}>
              <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
                {ui('Subject', '簽核對象')}
              </div>
              {workOrder ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div
                    style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: 13,
                      color: C.accent,
                    }}
                  >
                    {workOrder.business_key} · {workOrder.turbine_id}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
                    {workOrder.title}
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <StatusPill tone={priorityTone(workOrder.priority)} size="sm">
                      {priorityLabel(workOrder.priority, lang)}
                    </StatusPill>
                    <StatusPill tone={statusTone(workOrder.status)} size="sm">
                      {statusLabel(workOrder.status, lang)}
                    </StatusPill>
                    <span style={{ fontSize: 11, color: C.sub }}>
                      · {typeLabel(workOrder.type, lang)}
                    </span>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 13, color: C.faint }}>
                  {subjectTypeLabel(chain.subject_type, lang)} ·{' '}
                  <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                    {chain.subject_id.slice(-8)}
                  </span>
                </div>
              )}
            </Card>

            {/* Step / chain context */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 8,
                fontSize: 12,
                color: C.sub,
              }}
            >
              <div>
                <strong>{ui('Level', '層級')}:</strong> {signoffLevelLabel(step.level, lang)}
              </div>
              <div>
                <strong>{ui('Step', '階段')}:</strong> {step.sequence + 1} / {chain.levels.length}
              </div>
            </div>

            {/* Approve / Reject input */}
            {isReject ? (
              <Field label={`${ui('Reject reason', '駁回原因')} *`} fullWidth>
                <textarea
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  rows={4}
                  placeholder={ui(
                    'Explain why this work is being sent back to in_progress...',
                    '請說明為何要把工單退回 IN_PROGRESS...',
                  )}
                  aria-label={ui('Reject reason', '駁回原因')}
                  style={{
                    background: C.panel,
                    border: `1px solid ${C.border}`,
                    borderRadius: 8,
                    padding: '8px 12px',
                    fontSize: 13,
                    color: C.text,
                    fontFamily: 'inherit',
                    width: '100%',
                    resize: 'vertical',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </Field>
            ) : (
              <Field
                label={`${ui('Approval comment', '簽核備註')} (${ui('optional', '選填')})`}
                fullWidth
              >
                <Input
                  value={comment}
                  onChange={setComment}
                  placeholder={ui('Optional note for the audit log', '寫入稽核紀錄的選填備註')}
                  fullWidth
                  ariaLabel={ui('Approval comment', '簽核備註')}
                />
              </Field>
            )}

            {error && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
              </Card>
            )}

            {warning && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>
                  {ui(
                    'Chain status committed but work order transition failed:',
                    'Chain 已落地，但工單 transition 失敗：',
                  )}{' '}
                  {warning}
                </div>
                <div style={{ fontSize: 11, color: C.faint, marginTop: 4 }}>
                  {ui(
                    'Notify ops to backfill the work order state.',
                    '請通知 ops 補正工單狀態。',
                  )}
                </div>
              </Card>
            )}
          </div>

          <div
            style={{
              padding: '14px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <Btn onClick={onClose} ariaLabel={ui('Cancel', '取消')}>
              {ui('Cancel', '取消')}
            </Btn>
            <Btn
              variant={isReject ? 'danger' : 'primary'}
              onClick={handleSubmit}
              disabled={submitting || !canSubmit}
              ariaLabel={
                isReject
                  ? ui('Confirm reject', '確認駁回')
                  : ui('Confirm approve', '確認通過')
              }
            >
              {submitting
                ? ui('Submitting…', '送出中…')
                : isReject
                  ? ui('Reject', '駁回')
                  : ui('Approve', '通過')}
            </Btn>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default ApprovalActionDialog;

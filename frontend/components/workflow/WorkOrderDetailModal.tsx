/**
 * WorkOrderDetailModal — workflow 版本的工單詳情 + 狀態 transition 控制。
 *
 * ⚠ 與 components/WorkOrderDetailModal.tsx（legacy mock 版）區分：
 *   - 此檔對應 backend WorkOrderResponse schema
 *   - 提供 7 個 transition 按鈕（dispatch / start-work / update-progress / finish /
 *     reject / cancel / reopen），approve 走 /api/workflow/approvals/{step_id}/approve
 *     的 -20 流程，本 modal 只 disable 顯示「待簽核」
 *
 * 設計：依 work_order.status 顯示對應 action button；點擊後 collapsible inline form
 * 收集必填欄位（reason / hours / followup_kind...）→ 提交 → patch local + 收 form。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  DEV_ACTOR_ID,
  FollowupKindValues,
  type FollowupKind,
  type WorkOrderResponse,
} from '../../services/workOrderService';
import {
  followupLabel,
  fmtDateTime,
  priorityLabel,
  priorityTone,
  statusLabel,
  statusTone,
  typeLabel,
} from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  workOrder: WorkOrderResponse;
  /** 觸發狀態變更的 callbacks（呼叫 hook 的 mutation） */
  onDispatch: (id: string) => Promise<WorkOrderResponse>;
  onStartWork: (id: string, requireWeatherWindow: boolean) => Promise<WorkOrderResponse>;
  onUpdateProgress: (id: string, note: string) => Promise<WorkOrderResponse>;
  onFinish: (
    id: string,
    payload: {
      actual_hours: number;
      followup_kind: FollowupKind;
      work_summary: string | null;
      unfinished_items: string | null;
      followup_note: string | null;
    },
  ) => Promise<WorkOrderResponse>;
  onReject: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onCancel: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onReopen: (id: string, reason: string) => Promise<WorkOrderResponse>;
  onClose: () => void;
  lang: Lang;
}

type ActionForm =
  | null
  | 'dispatch'
  | 'start_work'
  | 'progress'
  | 'finish'
  | 'reject'
  | 'cancel'
  | 'reopen';

const WorkOrderDetailModal: React.FC<Props> = ({
  workOrder: initialWO,
  onDispatch,
  onStartWork,
  onUpdateProgress,
  onFinish,
  onReject,
  onCancel,
  onReopen,
  onClose,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  // 局部 state — transition 後直接更新顯示，不用等父層 list 推
  const [wo, setWO] = useState<WorkOrderResponse>(initialWO);
  useEffect(() => setWO(initialWO), [initialWO]);

  const [activeForm, setActiveForm] = useState<ActionForm>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form fields
  const [requireWeather, setRequireWeather] = useState(false);
  const [progressNote, setProgressNote] = useState('');
  const [actualHours, setActualHours] = useState('');
  const [followupKind, setFollowupKind] = useState<FollowupKind>('none');
  const [workSummary, setWorkSummary] = useState('');
  const [unfinishedItems, setUnfinishedItems] = useState('');
  const [followupNote, setFollowupNote] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [cancelReason, setCancelReason] = useState('');
  const [reopenReason, setReopenReason] = useState('');

  const resetForms = () => {
    setActiveForm(null);
    setError(null);
    setProgressNote('');
    setActualHours('');
    setFollowupKind('none');
    setWorkSummary('');
    setUnfinishedItems('');
    setFollowupNote('');
    setRejectReason('');
    setCancelReason('');
    setReopenReason('');
    setRequireWeather(false);
  };

  const runMutation = async (fn: () => Promise<WorkOrderResponse>) => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await fn();
      setWO(updated);
      resetForms();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  // ── action button visibility based on status ──
  const status = wo.status;
  const canDispatch = status === 'draft';
  const canStartWork = status === 'dispatched' || status === 'reopened';
  const canUpdateProgress = status === 'in_progress';
  const canFinish = status === 'in_progress';
  const canReject = status === 'awaiting_signoff';
  const canCancel = status === 'draft' || status === 'dispatched' || status === 'in_progress';
  const canReopen = status === 'closed';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ui('Work order detail', '工單詳情')}
      onClick={onClose}
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
        style={{ width: '100%', maxWidth: 920, maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        <Card
          padding={0}
          style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', maxHeight: '92vh' }}
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
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {wo.title}
              </h2>
              <div style={{ fontSize: 12, color: C.sub, marginTop: 4, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: C.accent }}>
                  {wo.business_key}
                </span>
                <span>·</span>
                <span>{wo.turbine_id}</span>
                <span>·</span>
                <span>{typeLabel(wo.type, lang)}</span>
                <StatusPill tone={priorityTone(wo.priority)} size="sm">
                  {priorityLabel(wo.priority, lang)}
                </StatusPill>
                <StatusPill tone={statusTone(wo.status)} size="md">
                  {statusLabel(wo.status, lang)}
                </StatusPill>
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
            {/* Detail grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 10,
              }}
            >
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>
                  {ui('Created', '建立時間')}
                </div>
                <div style={{ fontWeight: 600, color: C.text, fontSize: 13, marginTop: 4 }}>
                  {fmtDateTime(wo.created_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>
                  {ui('Updated', '最後更新')}
                </div>
                <div style={{ fontWeight: 600, color: C.text, fontSize: 13, marginTop: 4 }}>
                  {fmtDateTime(wo.updated_at)}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>
                  {ui('Crew / Est. hours', '工班 / 預估工時')}
                </div>
                <div style={{ fontWeight: 600, color: C.text, fontSize: 13, marginTop: 4 }}>
                  {wo.crew_size}p · {wo.estimated_hours != null ? `${wo.estimated_hours}h` : '—'}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>
                  {ui('Source alarm', '來源警報')}
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    color: C.text,
                    fontSize: 13,
                    marginTop: 4,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                >
                  {wo.source_alarm_code ?? '—'}
                </div>
              </Card>
            </div>

            {/* Description */}
            <Card tone="muted">
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                {ui('Description', '說明')}
              </div>
              <pre
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: C.sub,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              >
                {wo.description}
              </pre>
            </Card>

            {/* Progress notes */}
            {wo.progress_notes.length > 0 && (
              <Card tone="muted">
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  {ui('Progress log', '進度記錄')}
                  <span style={{ marginLeft: 6, fontSize: 11, color: C.faint }}>
                    ({wo.progress_notes.length})
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
                  {wo.progress_notes.map((p, i) => (
                    <div
                      key={i}
                      style={{
                        background: C.panel,
                        border: `1px solid ${C.border}`,
                        borderRadius: 8,
                        padding: '8px 10px',
                      }}
                    >
                      <div style={{ fontSize: 11, color: C.faint }}>
                        {fmtDateTime(p.timestamp)}
                      </div>
                      <div style={{ fontSize: 13, color: C.text, marginTop: 4 }}>
                        {p.note}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Closed-state metadata */}
            {(wo.status === 'awaiting_signoff' || wo.status === 'closed' || wo.status === 'reopened') && (
              <Card tone="muted">
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  {ui('Completion summary', '完工摘要')}
                </div>
                <div style={{ fontSize: 12, color: C.sub, display: 'grid', gap: 4 }}>
                  <div>
                    {ui('Finished at', '完工時間')}: {fmtDateTime(wo.finished_at)}
                  </div>
                  <div>
                    {ui('Actual hours', '實際工時')}:{' '}
                    {wo.actual_hours != null ? `${wo.actual_hours}h` : '—'}
                  </div>
                  <div>
                    {ui('Follow-up', '後續處理')}: {followupLabel(wo.followup_kind, lang)}
                  </div>
                  {wo.work_summary && (
                    <div>
                      {ui('Summary', '工作摘要')}: {wo.work_summary}
                    </div>
                  )}
                  {wo.unfinished_items && (
                    <div>
                      {ui('Unfinished items', '未完事項')}: {wo.unfinished_items}
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* Cancel / reject reasons */}
            {wo.cancel_reason && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>
                  <strong>{ui('Cancelled', '已取消')}:</strong> {wo.cancel_reason}
                </div>
              </Card>
            )}
            {wo.reject_reason && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>
                  <strong>{ui('Rejected', '駁回原因')}:</strong> {wo.reject_reason}
                </div>
              </Card>
            )}
            {wo.reopen_reason && (
              <Card tone="accent" padding={12}>
                <div style={{ fontSize: 12, color: C.accent }}>
                  <strong>{ui('Reopened', '重開原因')}:</strong> {wo.reopen_reason}
                </div>
              </Card>
            )}

            {/* Pending signoff hint */}
            {wo.status === 'awaiting_signoff' && (
              <Card tone="accent" padding={12}>
                <div style={{ fontSize: 12, color: C.accent }}>
                  {ui(
                    '⏳ Pending signoff. Approve via /admin/workflow/approval (WMOM-20).',
                    '⏳ 等待簽核中。請至 /admin/workflow/approval 處理（WMOM-20 上線）。',
                  )}
                </div>
              </Card>
            )}

            {/* Inline forms */}
            {error && (
              <Card tone="warn" padding={12}>
                <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
              </Card>
            )}

            {activeForm === 'dispatch' && (
              <Card>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  {ui('Dispatch work order', '派工')}
                </div>
                <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
                  {ui(
                    `Will dispatch as actor ${DEV_ACTOR_ID} (dev placeholder).`,
                    `將以 actor ${DEV_ACTOR_ID} 身分派工（dev 占位）。`,
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="primary"
                    onClick={() => runMutation(() => onDispatch(wo.id))}
                    disabled={submitting}
                    ariaLabel={ui('Confirm dispatch', '確認派工')}
                  >
                    {submitting ? ui('Dispatching…', '派工中…') : ui('Confirm dispatch', '確認派工')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'start_work' && (
              <Card>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  {ui('Start work', '開始作業')}
                </div>
                <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: C.sub, marginBottom: 10 }}>
                  <input
                    type="checkbox"
                    checked={requireWeather}
                    onChange={e => setRequireWeather(e.target.checked)}
                  />
                  {ui(
                    'Require weather window (offshore)',
                    '需檢查氣象窗（離岸風場）',
                  )}
                </label>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="primary"
                    onClick={() => runMutation(() => onStartWork(wo.id, requireWeather))}
                    disabled={submitting}
                    ariaLabel={ui('Start work', '開始作業')}
                  >
                    {submitting ? ui('Starting…', '啟動中…') : ui('Start work', '開始作業')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'progress' && (
              <Card>
                <Field label={ui('Progress note', '進度記錄')} fullWidth>
                  <textarea
                    value={progressNote}
                    onChange={e => setProgressNote(e.target.value)}
                    rows={3}
                    aria-label={ui('Progress note', '進度記錄')}
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
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="primary"
                    onClick={() => runMutation(() => onUpdateProgress(wo.id, progressNote.trim()))}
                    disabled={submitting || progressNote.trim().length === 0}
                    ariaLabel={ui('Add note', '新增記錄')}
                  >
                    {submitting ? ui('Saving…', '儲存中…') : ui('Add note', '新增記錄')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'finish' && (
              <Card>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 8 }}>
                  {ui('Finish work order', '完成工單')}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
                  <Field label={`${ui('Actual hours', '實際工時')} *`}>
                    <Input
                      type="number"
                      step="0.5"
                      value={actualHours}
                      onChange={setActualHours}
                      min={0}
                      placeholder="3.5"
                      fullWidth
                      ariaLabel={ui('Actual hours', '實際工時')}
                    />
                  </Field>
                  <Field label={`${ui('Follow-up kind', '後續處理')} *`}>
                    <Select
                      value={followupKind}
                      options={FollowupKindValues.map(v => ({
                        value: v,
                        label: followupLabel(v, lang),
                      }))}
                      onChange={v => setFollowupKind(v as FollowupKind)}
                      fullWidth
                      ariaLabel={ui('Follow-up kind', '後續處理')}
                    />
                  </Field>
                </div>
                <Field
                  label={`${ui('Work summary', '工作摘要')} (${ui('optional', '選填')})`}
                  fullWidth
                >
                  <textarea
                    value={workSummary}
                    onChange={e => setWorkSummary(e.target.value)}
                    rows={2}
                    aria-label={ui('Work summary', '工作摘要')}
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
                      marginTop: 4,
                    }}
                  />
                </Field>
                {followupKind === 'followup_needed' && (
                  <>
                    <Field
                      label={`${ui('Unfinished items', '未完事項')} (${ui('optional', '選填')})`}
                      fullWidth
                    >
                      <textarea
                        value={unfinishedItems}
                        onChange={e => setUnfinishedItems(e.target.value)}
                        rows={2}
                        aria-label={ui('Unfinished items', '未完事項')}
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
                          marginTop: 4,
                        }}
                      />
                    </Field>
                    <Field
                      label={`${ui('Follow-up note', '追蹤備註')} (${ui('optional', '選填')})`}
                      fullWidth
                    >
                      <Input
                        value={followupNote}
                        onChange={setFollowupNote}
                        placeholder={ui('Schedule next inspection in 30 days', '30 天後排定下次檢查')}
                        fullWidth
                        ariaLabel={ui('Follow-up note', '追蹤備註')}
                      />
                    </Field>
                  </>
                )}
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="primary"
                    onClick={() => {
                      const hours = Number(actualHours);
                      if (!actualHours || Number.isNaN(hours) || hours < 0) {
                        setError(ui('Actual hours required (>= 0).', '實際工時必填，需 >= 0。'));
                        return;
                      }
                      runMutation(() =>
                        onFinish(wo.id, {
                          actual_hours: hours,
                          followup_kind: followupKind,
                          work_summary: workSummary.trim() || null,
                          unfinished_items: unfinishedItems.trim() || null,
                          followup_note: followupNote.trim() || null,
                        }),
                      );
                    }}
                    disabled={submitting}
                    ariaLabel={ui('Finish', '完成')}
                  >
                    {submitting ? ui('Finishing…', '結束中…') : ui('Finish', '完成')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'reject' && (
              <Card>
                <Field label={`${ui('Reject reason', '駁回原因')} *`} fullWidth>
                  <textarea
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    rows={3}
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
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="danger"
                    onClick={() => runMutation(() => onReject(wo.id, rejectReason.trim()))}
                    disabled={submitting || rejectReason.trim().length === 0}
                    ariaLabel={ui('Reject', '駁回')}
                  >
                    {submitting ? ui('Rejecting…', '駁回中…') : ui('Reject', '駁回')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'cancel' && (
              <Card>
                <Field label={`${ui('Cancel reason', '取消原因')} *`} fullWidth>
                  <textarea
                    value={cancelReason}
                    onChange={e => setCancelReason(e.target.value)}
                    rows={3}
                    aria-label={ui('Cancel reason', '取消原因')}
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
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                  <Btn onClick={resetForms}>{ui('Back', '返回')}</Btn>
                  <Btn
                    variant="danger"
                    onClick={() => runMutation(() => onCancel(wo.id, cancelReason.trim()))}
                    disabled={submitting || cancelReason.trim().length === 0}
                    ariaLabel={ui('Cancel work order', '取消工單')}
                  >
                    {submitting ? ui('Cancelling…', '取消中…') : ui('Cancel work order', '取消工單')}
                  </Btn>
                </div>
              </Card>
            )}

            {activeForm === 'reopen' && (
              <Card>
                <Field label={`${ui('Reopen reason', '重開原因')} *`} fullWidth>
                  <textarea
                    value={reopenReason}
                    onChange={e => setReopenReason(e.target.value)}
                    rows={3}
                    aria-label={ui('Reopen reason', '重開原因')}
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
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                  <Btn onClick={resetForms}>{ui('Cancel', '取消')}</Btn>
                  <Btn
                    variant="primary"
                    onClick={() => runMutation(() => onReopen(wo.id, reopenReason.trim()))}
                    disabled={submitting || reopenReason.trim().length === 0}
                    ariaLabel={ui('Reopen', '重開')}
                  >
                    {submitting ? ui('Reopening…', '重開中…') : ui('Reopen', '重開')}
                  </Btn>
                </div>
              </Card>
            )}
          </div>

          {/* Action footer */}
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
            <Btn onClick={onClose} ariaLabel={ui('Close', '關閉')}>
              {ui('Close', '關閉')}
            </Btn>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {canDispatch && (
                <Btn
                  variant="primary"
                  onClick={() => setActiveForm('dispatch')}
                  ariaLabel={ui('Dispatch', '派工')}
                >
                  {ui('Dispatch', '派工')}
                </Btn>
              )}
              {canStartWork && (
                <Btn
                  variant="primary"
                  onClick={() => setActiveForm('start_work')}
                  ariaLabel={ui('Start work', '開始作業')}
                >
                  {ui('Start work', '開始作業')}
                </Btn>
              )}
              {canUpdateProgress && (
                <Btn
                  onClick={() => setActiveForm('progress')}
                  ariaLabel={ui('Add progress', '新增進度')}
                >
                  {ui('Add progress', '新增進度')}
                </Btn>
              )}
              {canFinish && (
                <Btn
                  variant="primary"
                  onClick={() => setActiveForm('finish')}
                  ariaLabel={ui('Finish', '完工')}
                >
                  {ui('Finish', '完工')}
                </Btn>
              )}
              {canReject && (
                <Btn
                  variant="warn"
                  onClick={() => setActiveForm('reject')}
                  ariaLabel={ui('Reject', '駁回')}
                >
                  {ui('Reject', '駁回')}
                </Btn>
              )}
              {canCancel && (
                <Btn
                  variant="danger"
                  onClick={() => setActiveForm('cancel')}
                  ariaLabel={ui('Cancel', '取消工單')}
                >
                  {ui('Cancel', '取消工單')}
                </Btn>
              )}
              {canReopen && (
                <Btn
                  onClick={() => setActiveForm('reopen')}
                  ariaLabel={ui('Reopen', '重開')}
                >
                  {ui('Reopen', '重開')}
                </Btn>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default WorkOrderDetailModal;

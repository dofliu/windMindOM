/**
 * InspectionScheduleDetailModal — 檢視 / 編輯定檢計畫（WMOM-20260925-05）。
 *
 * 功能：
 *   - 顯示風機 / 下次到期時間 / 最近派工紀錄（唯讀，`turbine_id`/`next_due_at`
 *     不在 `UpdateInspectionScheduleRequest` schema 內，後端不支援改）
 *   - 編輯標題 / 說明 / 週期 / 自訂天數 → Save 呼叫 `PATCH .../{id}`
 *   - Active/Paused 切換 → 呼叫 `POST .../activate` 或 `.../deactivate`
 *     （獨立於 Save，比照 `CurtailModal` 先例：狀態切換即時生效，不需按 Save）
 */

import React, { useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  RecurrenceValues,
  type InspectionScheduleResponse,
  type Recurrence,
  type UpdateInspectionSchedulePayload,
} from '../../services/inspectionScheduleService';
import { fmtDateTime, recurrenceLabel } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  schedule: InspectionScheduleResponse;
  onClose: () => void;
  onUpdate: (
    id: string,
    req: UpdateInspectionSchedulePayload,
  ) => Promise<InspectionScheduleResponse>;
  onActivate: (id: string) => Promise<InspectionScheduleResponse>;
  onDeactivate: (id: string) => Promise<InspectionScheduleResponse>;
  lang: Lang;
}

const InspectionScheduleDetailModal: React.FC<Props> = ({
  schedule,
  onClose,
  onUpdate,
  onActivate,
  onDeactivate,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [current, setCurrent] = useState(schedule);
  const [title, setTitle] = useState(schedule.title);
  const [description, setDescription] = useState(schedule.description);
  const [recurrence, setRecurrence] = useState<Recurrence>(schedule.recurrence);
  const [intervalDays, setIntervalDays] = useState(
    schedule.interval_days != null ? String(schedule.interval_days) : '45',
  );
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState('');

  const canSave =
    title.trim() !== '' &&
    (recurrence !== 'custom_days' ||
      (Number.isFinite(parseInt(intervalDays, 10)) && parseInt(intervalDays, 10) > 0));

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      const updated = await onUpdate(current.id, {
        title: title.trim(),
        description: description.trim(),
        recurrence,
        interval_days: recurrence === 'custom_days' ? parseInt(intervalDays, 10) : null,
      });
      setCurrent(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async () => {
    setToggling(true);
    setError('');
    try {
      const updated = current.active
        ? await onDeactivate(current.id)
        : await onActivate(current.id);
      setCurrent(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setToggling(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ui('Inspection schedule detail', '定檢計畫詳情')}
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
      <Card
        padding={0}
        onClick={undefined}
        style={{ width: '100%', maxWidth: 460, overflow: 'hidden' }}
      >
        <div onClick={e => e.stopPropagation()}>
          <div
            style={{
              padding: '14px 18px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div>
              <h2
                style={{
                  margin: 0,
                  fontFamily: '"DM Serif Display", serif',
                  fontSize: 20,
                  fontWeight: 400,
                  color: C.text,
                }}
              >
                {ui('Inspection schedule', '定檢計畫')}
              </h2>
              <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>{current.turbine_id}</div>
            </div>
            <button
              onClick={onClose}
              aria-label={ui('Close', '關閉')}
              style={{
                background: 'transparent',
                border: 'none',
                color: C.sub,
                fontSize: 18,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>

          <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ fontSize: 12, color: C.sub }}>
                {ui('Next due', '下次到期')}:{' '}
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: C.text }}>
                  {fmtDateTime(current.next_due_at)}
                </span>
              </div>
              <StatusPill tone={current.active ? 'ok' : 'warn'} size="sm">
                {current.active ? ui('Active', '啟用中') : ui('Paused', '已暫停')}
              </StatusPill>
            </div>

            {current.last_spawned_at && (
              <div style={{ fontSize: 11, color: C.faint }}>
                {ui('Last spawned work order', '最近派工工單')}{' '}
                {fmtDateTime(current.last_spawned_at)}
              </div>
            )}

            <Field label={ui('Title', '標題')}>
              <Input
                value={title}
                onChange={setTitle}
                fullWidth
                ariaLabel={ui('Title', '標題')}
              />
            </Field>

            <Field label={ui('Description', '說明')}>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={3}
                aria-label={ui('Description', '說明')}
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

            <Field label={ui('Recurrence', '週期')}>
              <Select
                value={recurrence}
                options={RecurrenceValues.map(r => ({
                  value: r,
                  label: recurrenceLabel(r, lang),
                }))}
                onChange={v => setRecurrence(v as Recurrence)}
                ariaLabel={ui('Recurrence', '週期')}
                fullWidth
              />
            </Field>

            {recurrence === 'custom_days' && (
              <Field label={ui('Interval (days)', '自訂天數')}>
                <Input
                  type="number"
                  min={1}
                  value={intervalDays}
                  onChange={setIntervalDays}
                  fullWidth
                  ariaLabel={ui('Interval (days)', '自訂天數')}
                />
              </Field>
            )}

            {error && (
              <div
                style={{
                  background: C.warnSoft,
                  border: `1px solid ${C.warn}`,
                  borderRadius: 8,
                  padding: '8px 12px',
                  color: C.warn,
                  fontSize: 12,
                }}
              >
                ⚠ {error}
              </div>
            )}
          </div>

          <div
            style={{
              padding: '14px 18px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 8,
            }}
          >
            <Btn
              variant={current.active ? 'warn' : 'secondary'}
              onClick={handleToggleActive}
              disabled={toggling}
              ariaLabel={current.active ? ui('Pause schedule', '暫停計畫') : ui('Resume schedule', '恢復計畫')}
            >
              {toggling
                ? ui('Working…', '處理中…')
                : current.active
                  ? ui('Pause', '暫停')
                  : ui('Resume', '恢復')}
            </Btn>
            <Btn
              variant="primary"
              onClick={handleSave}
              disabled={saving || !canSave}
              ariaLabel={ui('Save changes', '儲存變更')}
            >
              {saving ? ui('Saving…', '儲存中…') : ui('Save changes', '儲存變更')}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default InspectionScheduleDetailModal;

/**
 * CreateInspectionScheduleModal — 建立定檢計畫（WMOM-20260925-05）。
 *
 * 單頁表單（比照 CurtailModal 的簡潔 modal 風格，不需要 CreateMaterialRequestWizard
 * 那種多步驟——欄位少、無需分步）：風機 + 標題 + 說明 + 週期 + 自訂天數（僅
 * `recurrence=custom_days` 顯示）。`first_due_at` 不在表單提供，交給後端預設
 * 「現在起算一個週期後」（見 repository docstring），避免時區轉換的額外複雜度。
 *
 * 提交後呼叫 `onSubmit`，呼叫端（WorkflowPage）決定要 close modal + refresh list
 * （比照 `CreateWorkOrderWizard` 慣例，本 modal 本身不自己 `onClose()`）。
 */

import React, { useState } from 'react';
import { Btn, Card, Field, Input, Select } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  RecurrenceValues,
  type CreateInspectionSchedulePayload,
  type Recurrence,
} from '../../services/inspectionScheduleService';
import { recurrenceLabel } from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  turbineOptions: { value: string; label: string }[];
  preselectTurbineId?: string;
  onClose: () => void;
  onSubmit: (req: Omit<CreateInspectionSchedulePayload, 'farm_id'>) => Promise<void>;
  lang: Lang;
}

const CreateInspectionScheduleModal: React.FC<Props> = ({
  turbineOptions,
  preselectTurbineId,
  onClose,
  onSubmit,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [turbineId, setTurbineId] = useState(
    preselectTurbineId ?? turbineOptions[0]?.value ?? '',
  );
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [recurrence, setRecurrence] = useState<Recurrence>('quarterly');
  const [intervalDays, setIntervalDays] = useState('45');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // 驗證 turbineId 確實是 turbineOptions 之一（非只檢查非空字串）——防
  // `preselectTurbineId` 帶入一個已不在目前風場清單內的過期值（例如風機在使用者從
  // TurbineDetail 點擊安排檢查、到本 modal 開啟之間的空檔被移出風場），送出會打一支
  // 後端 422 卻在前端顯示成看似可送出的啟用態按鈕（code review should-fix）。
  const canSubmit =
    turbineOptions.some(o => o.value === turbineId) &&
    title.trim() !== '' &&
    (recurrence !== 'custom_days' ||
      (Number.isFinite(parseInt(intervalDays, 10)) && parseInt(intervalDays, 10) > 0));

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError('');
    try {
      await onSubmit({
        turbine_id: turbineId.trim(),
        title: title.trim(),
        description: description.trim(),
        recurrence,
        interval_days: recurrence === 'custom_days' ? parseInt(intervalDays, 10) : null,
      });
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
      aria-label={ui('Create inspection schedule', '建立定檢計畫')}
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
            <h2
              style={{
                margin: 0,
                fontFamily: '"DM Serif Display", serif',
                fontSize: 20,
                fontWeight: 400,
                color: C.text,
              }}
            >
              {ui('Create inspection schedule', '建立定檢計畫')}
            </h2>
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
            <Field label={ui('Turbine', '風機')}>
              <Select
                value={turbineId}
                options={turbineOptions}
                onChange={v => setTurbineId(v as string)}
                ariaLabel={ui('Turbine', '風機')}
                fullWidth
              />
            </Field>

            <Field label={ui('Title', '標題')}>
              <Input
                value={title}
                onChange={setTitle}
                placeholder={ui('e.g. Quarterly gearbox inspection', '例：齒輪箱季度定檢')}
                fullWidth
                ariaLabel={ui('Title', '標題')}
              />
            </Field>

            <Field label={ui('Description', '說明')}>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={3}
                placeholder={ui('Optional details...', '選填說明...')}
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
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <Btn onClick={onClose} ariaLabel={ui('Cancel', '取消')}>
              {ui('Cancel', '取消')}
            </Btn>
            <Btn
              variant="primary"
              onClick={handleSubmit}
              disabled={submitting || !canSubmit}
              ariaLabel={ui('Create schedule', '建立計畫')}
            >
              {submitting ? ui('Creating…', '建立中…') : ui('Create schedule', '建立計畫')}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default CreateInspectionScheduleModal;

/**
 * CreateWorkOrderWizard — 3 步建立工單精靈。
 *
 * Step 1：選風機（從 active farm 的 turbines 列表）
 * Step 2：工單細節（type / priority / title / description / source_alarm_code 選填）
 * Step 3：派工 + 工時（assignee_id 選填、crew_size、estimated_hours 選填）
 *
 * 提交後呼叫 onSubmit (CreateWorkOrderRequest)，呼叫端決定要 close modal + refresh list。
 */

import React, { useMemo, useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  PriorityValues,
  WorkOrderTypeValues,
  type CreateWorkOrderRequest,
  type Priority,
  type WorkOrderType,
} from '../../services/workOrderService';
import { priorityLabel, priorityTone, typeLabel } from './statusUtils';
import {
  type TurbineData,
  TurbineStatus,
} from '../../types';
import { turbineStatusTone } from '../ui';

type Lang = 'en' | 'zh';

interface Props {
  farmId: string;
  turbines: TurbineData[];
  /** 預先帶入的風機 id（從 turbine detail 跳來時用）。 */
  preselectTurbineId?: string;
  onClose: () => void;
  /** 成功 submit 後 callback；wizard 內部會 try/catch 把 error 顯示在 step 3 */
  onSubmit: (req: CreateWorkOrderRequest) => Promise<void>;
  lang: Lang;
}

const CreateWorkOrderWizard: React.FC<Props> = ({
  farmId,
  turbines,
  preselectTurbineId,
  onClose,
  onSubmit,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1：風機
  const [turbineId, setTurbineId] = useState<string>(preselectTurbineId ?? '');

  // Step 2：工單細節
  const [type, setType] = useState<WorkOrderType>('corrective');
  const [priority, setPriority] = useState<Priority>('normal');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [sourceAlarmCode, setSourceAlarmCode] = useState('');

  // Step 3：派工 + 工時
  const [assigneeId, setAssigneeId] = useState('');
  const [crewSize, setCrewSize] = useState(1);
  const [estimatedHours, setEstimatedHours] = useState('');

  const canNext1 = turbineId.trim() !== '';
  const canNext2 = title.trim().length > 0 && description.trim().length > 0;
  const canSubmit = !submitting;

  const sortedTurbines = useMemo(
    () => [...turbines].sort((a, b) => a.name.localeCompare(b.name)),
    [turbines],
  );

  const buildRequest = (): CreateWorkOrderRequest => ({
    farm_id: farmId,
    turbine_id: turbineId.trim(),
    type,
    title: title.trim(),
    description: description.trim(),
    priority,
    source_alarm_code: sourceAlarmCode.trim() || null,
    assignee_id: assigneeId.trim() || null,
    crew_size: crewSize,
    estimated_hours: estimatedHours.trim() === '' ? null : Number(estimatedHours),
  });

  const handleSubmit = async () => {
    setError(null);
    const req = buildRequest();
    if (req.estimated_hours != null && Number.isNaN(req.estimated_hours)) {
      setError(ui('Estimated hours must be a number.', '預估工時必須是數字。'));
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(req);
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
      aria-label={ui('Create work order', '建立工單')}
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
        style={{ width: '100%', maxWidth: 720, maxHeight: '90vh', display: 'flex' }}
      >
        <Card padding={0} style={{ width: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', maxHeight: '90vh' }}>
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
            <div>
              <h2
                style={{
                  margin: 0,
                  fontFamily: '"DM Serif Display", serif',
                  fontSize: 24,
                  fontWeight: 400,
                  color: C.text,
                }}
              >
                {ui('Create work order', '建立工單')}
              </h2>
              <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
                {ui(`Step ${step} of 3`, `第 ${step} 步 / 共 3 步`)}
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
            {step === 1 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Select target turbine', '選擇目標風機')}
                </h3>
                {sortedTurbines.length === 0 ? (
                  <Card tone="muted" padding={20}>
                    <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
                      {ui('No turbines available in active farm.', '目前風場沒有可選的風機。')}
                    </div>
                  </Card>
                ) : (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: 8,
                      maxHeight: 360,
                      overflowY: 'auto',
                      padding: 2,
                    }}
                  >
                    {sortedTurbines.map(t => {
                      const tid = t.name; // backend turbine_id 用 name string
                      const active = turbineId === tid;
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setTurbineId(tid)}
                          aria-pressed={active}
                          style={{
                            padding: 12,
                            textAlign: 'left',
                            borderRadius: 10,
                            border: `2px solid ${active ? C.accent : C.border}`,
                            background: active ? C.accentSoft : C.panel,
                            cursor: 'pointer',
                            fontFamily: 'inherit',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: C.text, fontSize: 14 }}>
                            {t.name}
                          </div>
                          <div style={{ marginTop: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
                            <StatusPill tone={turbineStatusTone(t.status)} size="sm">
                              {t.status}
                            </StatusPill>
                            {t.status === TurbineStatus.FAULT && (
                              <span style={{ fontSize: 11, color: C.warn }}>⚠</span>
                            )}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 11, color: C.sub }}>
                            {t.powerOutput.toFixed(2)} MW · {t.windSpeed.toFixed(1)} m/s
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {step === 2 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Work order details', '工單細節')}
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                  <Field label={ui('Type', '類型')}>
                    <Select
                      value={type}
                      options={WorkOrderTypeValues.map(v => ({
                        value: v,
                        label: typeLabel(v, lang),
                      }))}
                      onChange={v => setType(v as WorkOrderType)}
                      fullWidth
                      ariaLabel={ui('Work order type', '工單類型')}
                    />
                  </Field>
                  <Field label={ui('Priority', '優先級')}>
                    <Select
                      value={priority}
                      options={PriorityValues.map(v => ({
                        value: v,
                        label: priorityLabel(v, lang),
                      }))}
                      onChange={v => setPriority(v as Priority)}
                      fullWidth
                      ariaLabel={ui('Priority', '優先級')}
                    />
                  </Field>
                </div>
                <Field
                  label={`${ui('Title', '標題')} *`}
                  fullWidth
                >
                  <Input
                    value={title}
                    onChange={setTitle}
                    placeholder={ui('e.g. Gearbox bearing replacement', '例：齒輪箱軸承更換')}
                    fullWidth
                    ariaLabel={ui('Title', '標題')}
                  />
                </Field>
                <Field
                  label={`${ui('Description', '說明')} *`}
                  fullWidth
                >
                  <textarea
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    rows={4}
                    placeholder={ui('Detailed maintenance work description...', '詳細維護工作說明...')}
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
                <Field
                  label={`${ui('Source alarm code', '來源警報碼')} (${ui('optional', '選填')})`}
                  hint={ui(
                    'If created from an alarm, fill the alarm code (Z72 / Bachmann tag).',
                    '若由警報觸發，填入警報碼（Z72 / Bachmann tag）。',
                  )}
                >
                  <Input
                    value={sourceAlarmCode}
                    onChange={setSourceAlarmCode}
                    placeholder="e.g. ALM_GEN_TEMP_HIGH"
                    fullWidth
                    monospace
                    ariaLabel={ui('Source alarm code', '來源警報碼')}
                  />
                </Field>
              </>
            )}

            {step === 3 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Assignment & estimated effort', '派工與工時預估')}
                </h3>
                <Field
                  label={`${ui('Assignee user UUID', '派工人員 UUID')} (${ui('optional', '選填')})`}
                  hint={ui(
                    'Leave blank for unassigned DRAFT. Auth integration lands in M5+.',
                    '空白即為未指派 DRAFT；認證整合於 M5+ 上線。',
                  )}
                >
                  <Input
                    value={assigneeId}
                    onChange={setAssigneeId}
                    placeholder="00000000-0000-0000-0000-000000000000"
                    fullWidth
                    monospace
                    ariaLabel={ui('Assignee UUID', '派工人員 UUID')}
                  />
                </Field>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                  <Field label={ui('Crew size', '工班人數')}>
                    <Input
                      type="number"
                      value={crewSize}
                      onChange={v => setCrewSize(Math.max(1, Math.min(20, parseInt(v) || 1)))}
                      min={1}
                      max={20}
                      fullWidth
                      ariaLabel={ui('Crew size', '工班人數')}
                    />
                  </Field>
                  <Field
                    label={`${ui('Estimated hours', '預估工時')} (${ui('optional', '選填')})`}
                  >
                    <Input
                      type="number"
                      step="0.5"
                      value={estimatedHours}
                      onChange={setEstimatedHours}
                      placeholder="4.0"
                      min={0}
                      fullWidth
                      ariaLabel={ui('Estimated hours', '預估工時')}
                    />
                  </Field>
                </div>

                {/* Summary card */}
                <Card tone="muted" padding={12}>
                  <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>
                    {ui('Review', '檢閱')}
                  </div>
                  <div style={{ fontSize: 13, color: C.text, display: 'grid', gap: 4 }}>
                    <div>
                      <strong>{ui('Turbine', '風機')}:</strong> {turbineId || '—'}
                    </div>
                    <div>
                      <strong>{ui('Type / Priority', '類型 / 優先級')}:</strong>{' '}
                      {typeLabel(type, lang)} ·{' '}
                      <StatusPill tone={priorityTone(priority)} size="sm">
                        {priorityLabel(priority, lang)}
                      </StatusPill>
                    </div>
                    <div>
                      <strong>{ui('Title', '標題')}:</strong> {title || '—'}
                    </div>
                  </div>
                </Card>

                {error && (
                  <Card tone="warn" padding={12}>
                    <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
                  </Card>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div
            style={{
              padding: '14px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <Btn onClick={onClose} ariaLabel={ui('Cancel', '取消')}>
              {ui('Cancel', '取消')}
            </Btn>
            <div style={{ display: 'flex', gap: 8 }}>
              {step > 1 && (
                <Btn
                  onClick={() => setStep(s => (s > 1 ? ((s - 1) as 1 | 2 | 3) : s))}
                  ariaLabel={ui('Back', '上一步')}
                >
                  {ui('Back', '上一步')}
                </Btn>
              )}
              {step < 3 && (
                <Btn
                  variant="primary"
                  onClick={() => setStep(s => (s < 3 ? ((s + 1) as 1 | 2 | 3) : s))}
                  disabled={(step === 1 && !canNext1) || (step === 2 && !canNext2)}
                  ariaLabel={ui('Next', '下一步')}
                >
                  {ui('Next', '下一步')}
                </Btn>
              )}
              {step === 3 && (
                <Btn
                  variant="primary"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  ariaLabel={ui('Create work order', '建立工單')}
                >
                  {submitting
                    ? ui('Creating…', '建立中…')
                    : ui('Create work order', '建立工單')}
                </Btn>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default CreateWorkOrderWizard;

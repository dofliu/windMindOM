/**
 * DayWorkFormPanel — 個人「工作日誌」頁（WMOM-20260926-01，`WMOM-20260505-21` 前端）。
 *
 * 功能：
 *   - 日期選擇（預設今天，Asia/Taipei 曆日）→ 查該日日誌（未建立過顯示空狀態，
 *     非錯誤——`get-or-create` 由「新增活動」表單送出時才自動觸發，不預先建立空日誌）
 *   - 該日已記錄活動清單（唯讀）
 *   - 新增活動表單：kind 選擇 + kind-specific 欄位（`completed_wo` 從本人工單清單選、
 *     其餘為文字輸入，`item_id`/`wo_id` 無 FK 目錄可選，`item_id` 維持自由輸入 UUID，
 *     見後端 review 記錄的刻意鬆耦合設計）
 *   - 最近日誌歷史（僅本人，唯讀列表；跨角色瀏覽範圍見 `WMOM-20260926-01` 第 3 項，
 *     本次不處理）
 *
 * 視覺沿用 InspectionScheduleListPanel（filter row + counter + card list）。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  ActivityKindValues,
  type ActivityKind,
  type AppendActivityPayload,
  type DayWorkFormResponse,
} from '../../services/dayWorkFormService';
import { activityKindLabel, fmtDate, fmtDateTime } from './statusUtils';

type Lang = 'en' | 'zh';

interface WorkOrderOption {
  id: string;
  label: string;
}

interface Props {
  workDate: string;
  onWorkDateChange: (d: string) => void;
  form: DayWorkFormResponse | null;
  loading: boolean;
  error: string | null;
  history: DayWorkFormResponse[];
  historyLoading: boolean;
  historyError: string | null;
  /** `completed_wo` 選單來源——呼叫端已過濾成本人（`assignee_id`）的工單。 */
  workOrderOptions: WorkOrderOption[];
  onAppendActivity: (
    req: Omit<AppendActivityPayload, 'employee_id'>,
  ) => Promise<DayWorkFormResponse>;
  lang: Lang;
}

/** 依 `kind` 判斷必填欄位是否齊全（鏡射 domain `ACTIVITY_REQUIRED_FIELDS`，前端提早擋送出）。 */
function canSubmitActivity(
  kind: ActivityKind,
  fields: { woId: string; itemId: string; result: string; area: string; topic: string },
): boolean {
  switch (kind) {
    case 'completed_wo':
      return fields.woId.trim() !== '';
    case 'inspection_item':
      return fields.itemId.trim() !== '' && fields.result.trim() !== '';
    case 'patrol':
      return fields.area.trim() !== '';
    case 'training':
      return fields.topic.trim() !== '';
  }
}

const DayWorkFormPanel: React.FC<Props> = ({
  workDate,
  onWorkDateChange,
  form,
  loading,
  error,
  history,
  historyLoading,
  historyError,
  workOrderOptions,
  onAppendActivity,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [kind, setKind] = useState<ActivityKind>('completed_wo');
  const [woId, setWoId] = useState(workOrderOptions[0]?.id ?? '');
  const [itemId, setItemId] = useState('');
  const [result, setResult] = useState('');
  const [area, setArea] = useState('');
  const [topic, setTopic] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // `workOrderOptions` 常是父層另一個 hook 非同步載入完成才有值——mount 當下可能還是
  // 空陣列，`useState` 初值抓不到，等它有資料後補選第一筆（只在目前為空時補，不覆蓋
  // 使用者已手動選的值）。
  useEffect(() => {
    if (!woId && workOrderOptions.length > 0) {
      setWoId(workOrderOptions[0].id);
    }
  }, [workOrderOptions, woId]);

  const canSubmit = canSubmitActivity(kind, { woId, itemId, result, area, topic });

  const resetFields = () => {
    setItemId('');
    setResult('');
    setArea('');
    setTopic('');
    setNote('');
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      await onAppendActivity({
        kind,
        wo_id: kind === 'completed_wo' ? woId : undefined,
        item_id: kind === 'inspection_item' ? itemId.trim() : undefined,
        result: kind === 'inspection_item' ? result.trim() : undefined,
        area: kind === 'patrol' ? area.trim() : undefined,
        topic: kind === 'training' ? topic.trim() : undefined,
        note: note.trim(),
      });
      resetFields();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(160px, 220px) auto',
            gap: 12,
            alignItems: 'end',
            marginBottom: 14,
          }}
        >
          <Field label={ui('Date', '日期')}>
            <Input
              type="date"
              value={workDate}
              onChange={onWorkDateChange}
              fullWidth
              ariaLabel={ui('Work date', '工作日期')}
            />
          </Field>
        </div>

        {error && (
          <Card tone="warn" padding={12} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
          </Card>
        )}

        {loading && (
          <div style={{ fontSize: 12, color: C.faint, marginBottom: 10 }}>
            {ui('Loading…', '載入中…')}
          </div>
        )}

        {!loading && !error && !form && (
          <Card tone="muted" padding={20}>
            <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
              {ui(
                'No log for this date yet. Add your first activity below to start one.',
                '這天尚未建立日誌，於下方新增第一筆活動即可自動建立。',
              )}
            </div>
          </Card>
        )}

        {!loading && form && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 4 }}>
            <div style={{ fontSize: 12, color: C.sub }}>
              {ui(
                `${form.activities.length} activity(ies) logged`,
                `已記錄 ${form.activities.length} 筆活動`,
              )}
            </div>
            {form.activities.length === 0 && (
              <div style={{ fontSize: 12, color: C.faint }}>
                {ui('No activities yet.', '尚無活動記錄。')}
              </div>
            )}
            {form.activities.map(a => (
              <div
                key={a.id}
                style={{
                  background: C.panelMuted,
                  border: `1px solid ${C.border}`,
                  borderRadius: 10,
                  padding: '10px 14px',
                  display: 'grid',
                  gridTemplateColumns: 'minmax(140px, 1fr) minmax(160px, 2fr) auto',
                  gap: 12,
                  alignItems: 'center',
                }}
              >
                <StatusPill tone="info" size="sm">
                  {activityKindLabel(a.kind, lang)}
                </StatusPill>
                <div style={{ fontSize: 12, color: C.text, minWidth: 0 }}>
                  {a.kind === 'completed_wo' && a.wo_id}
                  {a.kind === 'inspection_item' && `${a.item_id} — ${a.result}`}
                  {a.kind === 'patrol' && a.area}
                  {a.kind === 'training' && a.topic}
                  {a.note && (
                    <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>{a.note}</div>
                  )}
                </div>
                <div style={{ fontSize: 11, color: C.faint, fontFamily: 'JetBrains Mono, monospace' }}>
                  {fmtDateTime(a.logged_at)}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>
          {ui('Add activity', '新增活動')}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label={ui('Kind', '活動類型')}>
            <Select
              value={kind}
              options={ActivityKindValues.map(k => ({ value: k, label: activityKindLabel(k, lang) }))}
              onChange={v => setKind(v as ActivityKind)}
              ariaLabel={ui('Activity kind', '活動類型')}
              fullWidth
            />
          </Field>

          {kind === 'completed_wo' && (
            <Field
              label={ui('Work order', '工單')}
              hint={
                workOrderOptions.length === 0
                  ? ui('No work orders assigned to you.', '目前沒有指派給你的工單。')
                  : undefined
              }
            >
              <Select
                value={woId}
                options={workOrderOptions.map(o => ({ value: o.id, label: o.label }))}
                onChange={setWoId}
                ariaLabel={ui('Work order', '工單')}
                fullWidth
              />
            </Field>
          )}

          {kind === 'inspection_item' && (
            <>
              <Field label={ui('Inspection item ID', '定檢項目 ID')}>
                <Input
                  value={itemId}
                  onChange={setItemId}
                  placeholder={ui('Item UUID', '項目 UUID')}
                  fullWidth
                  ariaLabel={ui('Inspection item ID', '定檢項目 ID')}
                />
              </Field>
              <Field label={ui('Result', '結果')}>
                <Input
                  value={result}
                  onChange={setResult}
                  placeholder={ui('e.g. pass / fail / note', '例：正常 / 異常 / 備註')}
                  fullWidth
                  ariaLabel={ui('Result', '結果')}
                />
              </Field>
            </>
          )}

          {kind === 'patrol' && (
            <Field label={ui('Area', '巡視區域')}>
              <Input
                value={area}
                onChange={setArea}
                placeholder={ui('e.g. Turbine hall B', '例：B 棟機艙')}
                fullWidth
                ariaLabel={ui('Area', '巡視區域')}
              />
            </Field>
          )}

          {kind === 'training' && (
            <Field label={ui('Topic', '訓練主題')}>
              <Input
                value={topic}
                onChange={setTopic}
                placeholder={ui('e.g. Fire safety refresher', '例：消防安全複訓')}
                fullWidth
                ariaLabel={ui('Topic', '訓練主題')}
              />
            </Field>
          )}

          <Field label={ui('Note (optional)', '備註（選填）')}>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              aria-label={ui('Note', '備註')}
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

          {submitError && (
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
              ⚠ {submitError}
            </div>
          )}

          <div>
            <Btn
              variant="primary"
              onClick={handleSubmit}
              disabled={submitting || !canSubmit}
              ariaLabel={ui('Add activity', '新增活動')}
            >
              {submitting ? ui('Adding…', '新增中…') : ui('Add activity', '新增活動')}
            </Btn>
          </div>
        </div>
      </Card>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 12 }}>
          {ui('Recent logs (yours)', '最近日誌（本人）')}
        </div>
        {historyError && (
          <div style={{ fontSize: 12, color: C.warn, marginBottom: 8 }}>⚠ {historyError}</div>
        )}
        {historyLoading && (
          <div style={{ fontSize: 12, color: C.faint }}>{ui('Loading…', '載入中…')}</div>
        )}
        {!historyLoading && !historyError && history.length === 0 && (
          <div style={{ fontSize: 12, color: C.faint }}>{ui('No logs yet.', '尚無日誌記錄。')}</div>
        )}
        {!historyLoading && history.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {history.map(h => (
              <div
                key={h.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 12,
                  padding: '6px 10px',
                  background: C.panelMuted,
                  borderRadius: 8,
                }}
              >
                <span style={{ color: C.text, fontFamily: 'JetBrains Mono, monospace' }}>
                  {fmtDate(h.work_date)}
                </span>
                <span style={{ color: C.sub }}>
                  {ui(`${h.activities.length} activity(ies)`, `${h.activities.length} 筆活動`)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

export default DayWorkFormPanel;

/**
 * PendingApprovalPanel — 「我這層的待簽」列表（WMOM-20260504-20）。
 *
 * 功能：
 *   - level Selector（員工 / 組長 / 主管 / 總務）— 預設 leader（最常見的工單簽核角色）
 *   - subject_type filter（all / work_order / material_request）— 為 M4 領料單預留
 *   - 每筆 row 顯示：subject summary（工單 title / business_key / turbine / priority）+
 *     step level + chain progress + approve/reject 兩顆按鈕
 *   - 點 approve / reject 開 ApprovalActionDialog
 */

import React from 'react';
import { Btn, Card, Field, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  SignoffLevelValues,
  SignoffSubjectTypeValues,
  type PendingSignoffItem,
  type SignoffLevel,
  type SignoffSubjectType,
  type WorkOrderResponse,
} from '../../services/workOrderService';
import {
  fmtDateTime,
  priorityLabel,
  priorityTone,
  signoffLevelLabel,
  statusLabel,
  statusTone,
  subjectTypeLabel,
} from './statusUtils';

type Lang = 'en' | 'zh';

interface Props {
  items: PendingSignoffItem[];
  total: number;
  loading: boolean;
  error: string | null;
  level: SignoffLevel;
  onLevelChange: (l: SignoffLevel) => void;
  subjectType: SignoffSubjectType | 'all';
  onSubjectTypeChange: (t: SignoffSubjectType | 'all') => void;
  workOrderCache: Map<string, WorkOrderResponse>;
  onApproveClick: (pending: PendingSignoffItem) => void;
  onRejectClick: (pending: PendingSignoffItem) => void;
  onRefresh: () => void;
  lang: Lang;
}

const PendingApprovalPanel: React.FC<Props> = ({
  items,
  total,
  loading,
  error,
  level,
  onLevelChange,
  subjectType,
  onSubjectTypeChange,
  workOrderCache,
  onApproveClick,
  onRejectClick,
  onRefresh,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const levelOptions = SignoffLevelValues.map(v => ({
    value: v,
    label: signoffLevelLabel(v, lang),
  }));
  const subjectTypeOptions = [
    { value: 'all', label: ui('All subjects', '全部對象') },
    ...SignoffSubjectTypeValues.map(v => ({
      value: v,
      label: subjectTypeLabel(v, lang),
    })),
  ];

  return (
    <Card>
      {/* Filter row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(160px, 200px) minmax(160px, 200px) 1fr auto',
          gap: 12,
          alignItems: 'end',
          marginBottom: 14,
        }}
      >
        <Field label={ui('Acting as level', '我的簽核層級')}>
          <Select
            value={level}
            options={levelOptions}
            onChange={v => onLevelChange(v as SignoffLevel)}
            ariaLabel={ui('Acting as level', '我的簽核層級')}
            fullWidth
          />
        </Field>
        <Field label={ui('Subject type', '對象類型')}>
          <Select
            value={subjectType}
            options={subjectTypeOptions}
            onChange={v => onSubjectTypeChange(v as SignoffSubjectType | 'all')}
            ariaLabel={ui('Subject type filter', '對象類型過濾')}
            fullWidth
          />
        </Field>
        <div />
        <Btn onClick={onRefresh} ariaLabel={ui('Refresh pending list', '重新整理待簽列表')}>
          {loading ? ui('Loading…', '載入中…') : ui('Refresh', '重新整理')}
        </Btn>
      </div>

      <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
        {ui(
          `Showing ${items.length} of ${total} pending steps for ${signoffLevelLabel(level, 'en')}`,
          `顯示 ${items.length} / ${total} 筆 ${signoffLevelLabel(level, 'zh')} 待簽`,
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
              `No pending approvals at ${signoffLevelLabel(level, 'en')} level.`,
              `${signoffLevelLabel(level, 'zh')}層目前沒有待簽項目。`,
            )}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(item => {
          const { step, chain } = item;
          const wo =
            chain.subject_type === 'work_order'
              ? workOrderCache.get(chain.subject_id) ?? null
              : null;
          const subjectId8 = chain.subject_id.slice(-8);
          return (
            <div
              key={step.id}
              style={{
                background: C.panelMuted,
                border: `1px solid ${C.border}`,
                borderRadius: 12,
                padding: '12px 14px',
                display: 'grid',
                gridTemplateColumns: 'minmax(160px, 1fr) 2fr auto',
                gap: 12,
                alignItems: 'center',
              }}
            >
              {/* Left col：subject summary */}
              <div style={{ minWidth: 0 }}>
                {wo ? (
                  <>
                    <div
                      style={{
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: 12,
                        fontWeight: 600,
                        color: C.text,
                      }}
                    >
                      {wo.business_key}
                    </div>
                    <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                      {wo.turbine_id}
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: 12, color: C.sub }}>
                      {subjectTypeLabel(chain.subject_type, lang)}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: C.faint,
                        fontFamily: 'JetBrains Mono, monospace',
                        marginTop: 2,
                      }}
                    >
                      …{subjectId8}
                    </div>
                  </>
                )}
              </div>

              {/* Middle col：title + meta */}
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 14,
                    color: C.text,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {wo?.title ?? subjectTypeLabel(chain.subject_type, lang)}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: C.faint,
                    marginTop: 4,
                    display: 'flex',
                    gap: 8,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                  }}
                >
                  <StatusPill tone="info" size="sm">
                    {signoffLevelLabel(step.level, lang)} · {step.sequence + 1}/{chain.levels.length}
                  </StatusPill>
                  {wo && (
                    <>
                      <StatusPill tone={priorityTone(wo.priority)} size="sm">
                        {priorityLabel(wo.priority, lang)}
                      </StatusPill>
                      <StatusPill tone={statusTone(wo.status)} size="sm">
                        {statusLabel(wo.status, lang)}
                      </StatusPill>
                    </>
                  )}
                  <span>
                    {ui('Started', '開啟於')} {fmtDateTime(chain.started_at)}
                  </span>
                </div>
              </div>

              {/* Right col：actions */}
              <div style={{ display: 'flex', gap: 6 }}>
                <Btn
                  variant="warn"
                  size="sm"
                  onClick={() => onRejectClick(item)}
                  ariaLabel={ui('Reject', '駁回')}
                >
                  {ui('Reject', '駁回')}
                </Btn>
                <Btn
                  variant="primary"
                  size="sm"
                  onClick={() => onApproveClick(item)}
                  ariaLabel={ui('Approve', '通過')}
                >
                  {ui('Approve', '通過')}
                </Btn>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default PendingApprovalPanel;

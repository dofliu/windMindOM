/**
 * 工單 / 優先級 / 類型 enum → label + pill tone 的 mapping。
 * 全部走 ui/StatusPill 提供的 PillTone（不可硬寫 hex）。
 */

import type { PillTone } from '../ui';
import type {
  Priority,
  WorkOrderStatus,
  WorkOrderType,
  FollowupKind,
  SignoffLevel,
  SignoffStatus,
  SignoffSubjectType,
} from '../../services/workOrderService';

type Lang = 'en' | 'zh';

export function statusLabel(s: WorkOrderStatus, lang: Lang): string {
  const map: Record<WorkOrderStatus, [string, string]> = {
    draft: ['DRAFT', '草稿'],
    dispatched: ['DISPATCHED', '已派工'],
    in_progress: ['IN PROGRESS', '進行中'],
    awaiting_signoff: ['AWAITING SIGNOFF', '待簽核'],
    closed: ['CLOSED', '已結案'],
    cancelled: ['CANCELLED', '已取消'],
    reopened: ['REOPENED', '重開'],
  };
  const [en, zh] = map[s];
  return lang === 'zh' ? zh : en;
}

export function statusTone(s: WorkOrderStatus): PillTone {
  switch (s) {
    case 'draft':
      return 'muted';
    case 'dispatched':
      return 'info';
    case 'in_progress':
      return 'amber';
    case 'awaiting_signoff':
      return 'accent';
    case 'closed':
      return 'ok';
    case 'cancelled':
      return 'muted';
    case 'reopened':
      return 'warn';
  }
}

export function priorityLabel(p: Priority, lang: Lang): string {
  const map: Record<Priority, [string, string]> = {
    low: ['LOW', '低'],
    normal: ['NORMAL', '一般'],
    high: ['HIGH', '高'],
    critical: ['CRITICAL', '緊急'],
  };
  const [en, zh] = map[p];
  return lang === 'zh' ? zh : en;
}

export function priorityTone(p: Priority): PillTone {
  switch (p) {
    case 'low':
      return 'muted';
    case 'normal':
      return 'info';
    case 'high':
      return 'amber';
    case 'critical':
      return 'danger';
  }
}

export function typeLabel(t: WorkOrderType, lang: Lang): string {
  const map: Record<WorkOrderType, [string, string]> = {
    corrective: ['Corrective', '故障維修'],
    preventive: ['Preventive', '預防保養'],
    inspection: ['Inspection', '定檢'],
    commissioning: ['Commissioning', '試運轉'],
  };
  const [en, zh] = map[t];
  return lang === 'zh' ? zh : en;
}

export function followupLabel(f: FollowupKind, lang: Lang): string {
  const map: Record<FollowupKind, [string, string]> = {
    none: ['No follow-up', '無後續'],
    followup_needed: ['Follow-up needed', '需追蹤'],
  };
  const [en, zh] = map[f];
  return lang === 'zh' ? zh : en;
}

/** 短日期格式：YYYY-MM-DD HH:mm（給列表 / detail 用，不顯秒） */
export function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

// ─── Signoff label / tone（WMOM-20） ─────────────────────────────────────

export function signoffLevelLabel(l: SignoffLevel, lang: Lang): string {
  const map: Record<SignoffLevel, [string, string]> = {
    employee: ['Employee', '員工'],
    leader: ['Leader', '組長'],
    supervisor: ['Supervisor', '主管'],
    treasury: ['Treasury', '總務'],
  };
  const [en, zh] = map[l];
  return lang === 'zh' ? zh : en;
}

export function signoffStatusLabel(s: SignoffStatus, lang: Lang): string {
  const map: Record<SignoffStatus, [string, string]> = {
    pending: ['Pending', '待簽'],
    approved: ['Approved', '已通過'],
    rejected: ['Rejected', '已駁回'],
    skipped: ['Skipped', '已跳過'],
  };
  const [en, zh] = map[s];
  return lang === 'zh' ? zh : en;
}

export function signoffStatusTone(s: SignoffStatus): PillTone {
  switch (s) {
    case 'pending':
      return 'amber';
    case 'approved':
      return 'ok';
    case 'rejected':
      return 'warn';
    case 'skipped':
      return 'muted';
  }
}

export function subjectTypeLabel(t: SignoffSubjectType, lang: Lang): string {
  const map: Record<SignoffSubjectType, [string, string]> = {
    work_order: ['Work order', '工單'],
    material_request: ['Material request', '領料單'],
  };
  const [en, zh] = map[t];
  return lang === 'zh' ? zh : en;
}

/** 短日期：YYYY-MM-DD */
export function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

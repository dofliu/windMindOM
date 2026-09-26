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
import type {
  MaterialRequestStatus,
  ReturnReason,
  StockKind,
} from '../../services/materialService';
import type { Recurrence } from '../../services/inspectionScheduleService';
import type { ActivityKind } from '../../services/dayWorkFormService';

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

/** 短日期格式：YYYY-MM-DD HH:mm（明確 Asia/Taipei，避免不同 browser timezone 漂移）
 *  Backend 統一存 UTC tz-aware datetime，UI 一律 Asia/Taipei（CLAUDE.md §B）。 */
export function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const lookup = (k: string) => parts.find(p => p.type === k)?.value ?? '00';
  return `${lookup('year')}-${lookup('month')}-${lookup('day')} ${lookup('hour')}:${lookup('minute')}`;
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

/**
 * 短日期：YYYY-MM-DD（明確 Asia/Taipei）。
 *
 * review nice-to-have：也安全用於 bare `date`（無時間，如 `day_work_form`
 * 的 `work_date`）——`new Date('2026-09-20')` 解析成該日 UTC 00:00，轉
 * Asia/Taipei（+8，全年無 DST）只會往後跳非跨界，同一曆日不變。這個安全性
 * **僅因 Asia/Taipei 是正 UTC 偏移**才成立；未來若複製這個手法給負偏移時區
 * （例如美洲），bare date 會被反向跨日，需改用不經過 `Date`/時區轉換的
 * 專屬 helper，不能照抄本函式。
 */
export function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(d);
  const lookup = (k: string) => parts.find(p => p.type === k)?.value ?? '00';
  return `${lookup('year')}-${lookup('month')}-${lookup('day')}`;
}

// ─── Material Request label / tone（WMOM-20260509-06） ──────────────────

export function mrStatusLabel(s: MaterialRequestStatus, lang: Lang): string {
  const map: Record<MaterialRequestStatus, [string, string]> = {
    draft: ['DRAFT', '草稿'],
    awaiting_approval: ['AWAITING APPROVAL', '待簽核'],
    approved: ['APPROVED', '已通過'],
    dispatched: ['DISPATCHED', '已出庫'],
    received: ['RECEIVED', '已簽收'],
    used: ['USED', '已使用'],
    closed: ['CLOSED', '已結案'],
    cancelled: ['CANCELLED', '已取消'],
    rejected: ['REJECTED', '已駁回'],
  };
  const [en, zh] = map[s];
  return lang === 'zh' ? zh : en;
}

export function mrStatusTone(s: MaterialRequestStatus): PillTone {
  // 進度感：muted → amber → info → accent → accent → ok → ok（從建到結案）
  switch (s) {
    case 'draft':
      return 'muted';
    case 'awaiting_approval':
      return 'amber';
    case 'approved':
      return 'info';
    case 'dispatched':
      return 'accent';
    case 'received':
      return 'accent';
    case 'used':
      return 'ok';
    case 'closed':
      return 'ok';
    case 'cancelled':
      return 'muted';
    case 'rejected':
      return 'warn';
  }
}

export function stockKindLabel(k: StockKind, lang: Lang): string {
  const map: Record<StockKind, [string, string]> = {
    new: ['New', '全新'],
    used: ['Used', '良品'],
    repairing: ['Repairing', '維修中'],
  };
  const [en, zh] = map[k];
  return lang === 'zh' ? zh : en;
}

export function returnReasonLabel(r: ReturnReason, lang: Lang): string {
  const map: Record<ReturnReason, [string, string]> = {
    surplus: ['Surplus', '用剩'],
    wrong_part: ['Wrong part', '拿錯料件'],
    failed_install: ['Failed install', '試裝失敗'],
    other: ['Other', '其他'],
  };
  const [en, zh] = map[r];
  return lang === 'zh' ? zh : en;
}

// ─── Inspection Schedule label（WMOM-20260925-05） ───────────────────────

export function recurrenceLabel(r: Recurrence, lang: Lang): string {
  const map: Record<Recurrence, [string, string]> = {
    monthly: ['Monthly (~30d)', '每月（約 30 天）'],
    quarterly: ['Quarterly (~91d)', '每季（約 91 天）'],
    semi_annual: ['Semi-annual (~182d)', '每半年（約 182 天）'],
    annual: ['Annual (~365d)', '每年（約 365 天）'],
    custom_days: ['Custom', '自訂天數'],
  };
  const [en, zh] = map[r];
  return lang === 'zh' ? zh : en;
}

// ─── Day Work Form（WMOM-20260926-01） ───────────────────────────────────

export function activityKindLabel(k: ActivityKind, lang: Lang): string {
  const map: Record<ActivityKind, [string, string]> = {
    completed_wo: ['Completed work order', '完成工單'],
    inspection_item: ['Completed inspection item', '完成定檢項'],
    patrol: ['Patrol', '巡視'],
    training: ['Training', '訓練'],
  };
  const [en, zh] = map[k];
  return lang === 'zh' ? zh : en;
}

/** 今天的曆日（Asia/Taipei，非 UTC——見 `day_work_form.py` domain docstring 建議）。 */
export function todayAsiaTaipei(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const lookup = (t: string) => parts.find(p => p.type === t)?.value ?? '01';
  return `${lookup('year')}-${lookup('month')}-${lookup('day')}`;
}


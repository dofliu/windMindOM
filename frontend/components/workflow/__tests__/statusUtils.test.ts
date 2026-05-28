/**
 * statusUtils 純函式回歸測試。
 *
 * statusUtils 是 workflow UI（orders / approval / material / inventory tab）共用的
 * enum → label / enum → tone mapping 與 Asia/Taipei 日期格式化層；任何 label 文案、
 * tone 配色、時區行為的非預期改動都會直接污染畫面。本檔把這些純函式鎖成回歸基準。
 *
 * 守護點：
 * - 每個 label 函式 en/zh 雙語對應完整：用 service 匯出的 *Values runtime 陣列窮舉，
 *   期望值用 `Record<Enum, ...>` 型別 → 新增 enum 值卻漏補期望字串時 tsc 立刻紅
 *   （compile-time 窮舉），改文案則 runtime 立刻紅（迫使刻意更新）。
 * - 每個 tone 函式對所有 enum 值都回傳明確 tone（switch 無漏 case → 不回 undefined）。
 * - fmtDateTime / fmtDate 守 WMOM-20260509-06 code review Must-fix #1：明確
 *   Asia/Taipei（UTC+8、不隨 test runner timezone 漂移）+ null / invalid 邊界。
 */

import { describe, it, expect } from 'vitest';
import {
  WorkOrderStatusValues,
  WorkOrderTypeValues,
  PriorityValues,
  FollowupKindValues,
  SignoffLevelValues,
  SignoffStatusValues,
  SignoffSubjectTypeValues,
  type WorkOrderStatus,
  type WorkOrderType,
  type Priority,
  type FollowupKind,
  type SignoffLevel,
  type SignoffStatus,
  type SignoffSubjectType,
} from '../../../services/workOrderService';
import {
  MaterialRequestStatusValues,
  StockKindValues,
  ReturnReasonValues,
  type MaterialRequestStatus,
  type StockKind,
  type ReturnReason,
} from '../../../services/materialService';
import type { PillTone } from '../../ui';
import {
  statusLabel,
  statusTone,
  priorityLabel,
  priorityTone,
  typeLabel,
  followupLabel,
  fmtDateTime,
  fmtDate,
  signoffLevelLabel,
  signoffStatusLabel,
  signoffStatusTone,
  subjectTypeLabel,
  mrStatusLabel,
  mrStatusTone,
  stockKindLabel,
  returnReasonLabel,
} from '../statusUtils';

// ─── 期望值表（[en, zh]）。Record 型別保證 compile-time 窮舉。 ───────────────

const WO_STATUS: Record<WorkOrderStatus, [string, string]> = {
  draft: ['DRAFT', '草稿'],
  dispatched: ['DISPATCHED', '已派工'],
  in_progress: ['IN PROGRESS', '進行中'],
  awaiting_signoff: ['AWAITING SIGNOFF', '待簽核'],
  closed: ['CLOSED', '已結案'],
  cancelled: ['CANCELLED', '已取消'],
  reopened: ['REOPENED', '重開'],
};

const WO_STATUS_TONE: Record<WorkOrderStatus, PillTone> = {
  draft: 'muted',
  dispatched: 'info',
  in_progress: 'amber',
  awaiting_signoff: 'accent',
  closed: 'ok',
  cancelled: 'muted',
  reopened: 'warn',
};

const PRIORITY: Record<Priority, [string, string]> = {
  low: ['LOW', '低'],
  normal: ['NORMAL', '一般'],
  high: ['HIGH', '高'],
  critical: ['CRITICAL', '緊急'],
};

const PRIORITY_TONE: Record<Priority, PillTone> = {
  low: 'muted',
  normal: 'info',
  high: 'amber',
  critical: 'danger',
};

const WO_TYPE: Record<WorkOrderType, [string, string]> = {
  corrective: ['Corrective', '故障維修'],
  preventive: ['Preventive', '預防保養'],
  inspection: ['Inspection', '定檢'],
  commissioning: ['Commissioning', '試運轉'],
};

const FOLLOWUP: Record<FollowupKind, [string, string]> = {
  none: ['No follow-up', '無後續'],
  followup_needed: ['Follow-up needed', '需追蹤'],
};

const SIGNOFF_LEVEL: Record<SignoffLevel, [string, string]> = {
  employee: ['Employee', '員工'],
  leader: ['Leader', '組長'],
  supervisor: ['Supervisor', '主管'],
  treasury: ['Treasury', '總務'],
};

const SIGNOFF_STATUS: Record<SignoffStatus, [string, string]> = {
  pending: ['Pending', '待簽'],
  approved: ['Approved', '已通過'],
  rejected: ['Rejected', '已駁回'],
  skipped: ['Skipped', '已跳過'],
};

const SIGNOFF_STATUS_TONE: Record<SignoffStatus, PillTone> = {
  pending: 'amber',
  approved: 'ok',
  rejected: 'warn',
  skipped: 'muted',
};

const SUBJECT_TYPE: Record<SignoffSubjectType, [string, string]> = {
  work_order: ['Work order', '工單'],
  material_request: ['Material request', '領料單'],
};

const MR_STATUS: Record<MaterialRequestStatus, [string, string]> = {
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

const MR_STATUS_TONE: Record<MaterialRequestStatus, PillTone> = {
  draft: 'muted',
  awaiting_approval: 'amber',
  approved: 'info',
  dispatched: 'accent',
  received: 'accent',
  used: 'ok',
  closed: 'ok',
  cancelled: 'muted',
  rejected: 'warn',
};

const STOCK_KIND: Record<StockKind, [string, string]> = {
  new: ['New', '全新'],
  used: ['Used', '良品'],
  repairing: ['Repairing', '維修中'],
};

const RETURN_REASON: Record<ReturnReason, [string, string]> = {
  surplus: ['Surplus', '用剩'],
  wrong_part: ['Wrong part', '拿錯料件'],
  failed_install: ['Failed install', '試裝失敗'],
  other: ['Other', '其他'],
};

describe('statusUtils / label 函式（en + zh 雙語窮舉）', () => {
  it('statusLabel 涵蓋所有 WorkOrderStatus', () => {
    for (const s of WorkOrderStatusValues) {
      expect(statusLabel(s, 'en')).toBe(WO_STATUS[s][0]);
      expect(statusLabel(s, 'zh')).toBe(WO_STATUS[s][1]);
    }
  });

  it('priorityLabel 涵蓋所有 Priority', () => {
    for (const p of PriorityValues) {
      expect(priorityLabel(p, 'en')).toBe(PRIORITY[p][0]);
      expect(priorityLabel(p, 'zh')).toBe(PRIORITY[p][1]);
    }
  });

  it('typeLabel 涵蓋所有 WorkOrderType', () => {
    for (const t of WorkOrderTypeValues) {
      expect(typeLabel(t, 'en')).toBe(WO_TYPE[t][0]);
      expect(typeLabel(t, 'zh')).toBe(WO_TYPE[t][1]);
    }
  });

  it('followupLabel 涵蓋所有 FollowupKind', () => {
    for (const f of FollowupKindValues) {
      expect(followupLabel(f, 'en')).toBe(FOLLOWUP[f][0]);
      expect(followupLabel(f, 'zh')).toBe(FOLLOWUP[f][1]);
    }
  });

  it('signoffLevelLabel 涵蓋所有 SignoffLevel', () => {
    for (const l of SignoffLevelValues) {
      expect(signoffLevelLabel(l, 'en')).toBe(SIGNOFF_LEVEL[l][0]);
      expect(signoffLevelLabel(l, 'zh')).toBe(SIGNOFF_LEVEL[l][1]);
    }
  });

  it('signoffStatusLabel 涵蓋所有 SignoffStatus', () => {
    for (const s of SignoffStatusValues) {
      expect(signoffStatusLabel(s, 'en')).toBe(SIGNOFF_STATUS[s][0]);
      expect(signoffStatusLabel(s, 'zh')).toBe(SIGNOFF_STATUS[s][1]);
    }
  });

  it('subjectTypeLabel 涵蓋所有 SignoffSubjectType', () => {
    for (const t of SignoffSubjectTypeValues) {
      expect(subjectTypeLabel(t, 'en')).toBe(SUBJECT_TYPE[t][0]);
      expect(subjectTypeLabel(t, 'zh')).toBe(SUBJECT_TYPE[t][1]);
    }
  });

  it('mrStatusLabel 涵蓋所有 MaterialRequestStatus', () => {
    for (const s of MaterialRequestStatusValues) {
      expect(mrStatusLabel(s, 'en')).toBe(MR_STATUS[s][0]);
      expect(mrStatusLabel(s, 'zh')).toBe(MR_STATUS[s][1]);
    }
  });

  it('stockKindLabel 涵蓋所有 StockKind', () => {
    for (const k of StockKindValues) {
      expect(stockKindLabel(k, 'en')).toBe(STOCK_KIND[k][0]);
      expect(stockKindLabel(k, 'zh')).toBe(STOCK_KIND[k][1]);
    }
  });

  it('returnReasonLabel 涵蓋所有 ReturnReason', () => {
    for (const r of ReturnReasonValues) {
      expect(returnReasonLabel(r, 'en')).toBe(RETURN_REASON[r][0]);
      expect(returnReasonLabel(r, 'zh')).toBe(RETURN_REASON[r][1]);
    }
  });

  it('未知 lang 值退回 en（非 zh 即 en）', () => {
    // statusUtils 以 `lang === 'zh' ? zh : en` 判斷，任何非 'zh' 值都應拿到 en。
    expect(statusLabel('closed', 'en')).toBe('CLOSED');
    expect(mrStatusLabel('used', 'en')).toBe('USED');
    // 用雙重 cast 餵一個型別外的 lang，真正打到 fallback 分支（非 'zh' → en）。
    const unknownLang = 'fr' as unknown as 'en';
    expect(statusLabel('closed', unknownLang)).toBe('CLOSED');
    expect(mrStatusLabel('used', unknownLang)).toBe('USED');
  });
});

describe('statusUtils / tone 函式（窮舉，無漏 case）', () => {
  it('statusTone 對所有 WorkOrderStatus 回傳明確 tone', () => {
    for (const s of WorkOrderStatusValues) {
      expect(statusTone(s)).toBe(WO_STATUS_TONE[s]);
    }
  });

  it('priorityTone 對所有 Priority 回傳明確 tone', () => {
    for (const p of PriorityValues) {
      expect(priorityTone(p)).toBe(PRIORITY_TONE[p]);
    }
  });

  it('signoffStatusTone 對所有 SignoffStatus 回傳明確 tone', () => {
    for (const s of SignoffStatusValues) {
      expect(signoffStatusTone(s)).toBe(SIGNOFF_STATUS_TONE[s]);
    }
  });

  it('mrStatusTone 對所有 MaterialRequestStatus 回傳明確 tone', () => {
    for (const s of MaterialRequestStatusValues) {
      expect(mrStatusTone(s)).toBe(MR_STATUS_TONE[s]);
    }
  });
});

describe('statusUtils / 日期格式化（明確 Asia/Taipei = UTC+8）', () => {
  // Asia/Taipei 全年 UTC+8、無 DST → 下列轉換不隨季節 / runner timezone 改變。

  it('fmtDateTime：UTC 時刻轉成 Taipei（+8）牆鐘時間', () => {
    // 18:30Z + 8h = 隔日 02:30 → 同時驗「日期跨午夜進位」確實套了時區。
    expect(fmtDateTime('2026-01-15T18:30:00Z')).toBe('2026-01-16 02:30');
    // 同日（不跨午夜）的一般情況。
    expect(fmtDateTime('2026-03-09T01:05:00Z')).toBe('2026-03-09 09:05');
  });

  it('fmtDateTime：null → 「—」，無法解析 → 原樣回傳', () => {
    // 注意：無法解析時 source 刻意回傳「原始字串」（非 '—'），讓壞資料外顯而非被隱藏。
    // 此為目前 source 的 fallback 設計，鎖住以防非預期改動；非最終 UI 文案決策。
    expect(fmtDateTime(null)).toBe('—');
    expect(fmtDateTime('not-a-date')).toBe('not-a-date');
  });

  it('fmtDate：UTC 時刻轉 Taipei 後只取日期（跨午夜進位）', () => {
    expect(fmtDate('2026-01-15T18:30:00Z')).toBe('2026-01-16');
    expect(fmtDate('2026-03-09T01:05:00Z')).toBe('2026-03-09');
  });

  it('fmtDate：null → 「—」，無法解析 → 原樣回傳', () => {
    expect(fmtDate(null)).toBe('—');
    expect(fmtDate('garbage')).toBe('garbage');
  });
});

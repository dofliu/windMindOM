/**
 * statusUtils 純函式回歸測試（WMOM-20260528-01）。
 *
 * 守 workflow UI 的 enum → label / pill tone / 日期格式 對映。這些函式渲染
 * M3-M4 工單 / 領料 / 庫存 / 簽核畫面上每一個狀態 pill 與時間欄位，是 demo
 * 直接被客戶看到的顯示邏輯。本檔鎖定：
 *   - 每個 enum 值的雙語 label（漏一個 case → map/switch 與型別不一致時抓得到）
 *   - 每個 tone 對映（避免改色時誤動）
 *   - fmtDateTime / fmtDate 的 Asia/Taipei 轉換 + null / 無效輸入
 *     （守 WMOM-20260509-06 code review Must#1：明確 Asia/Taipei，不隨 browser 漂移）
 *   - mrStatusTone 進度感漸進色（守 WMOM-20260509-06 should-fix #2）
 *
 * 純函式：statusUtils 只有 `import type`（編譯期抹除），無 runtime 相依，毋須 jsdom / context。
 */

import { describe, it, expect } from 'vitest';
import {
  PriorityValues,
  WorkOrderStatusValues,
  WorkOrderTypeValues,
  FollowupKindValues,
  SignoffLevelValues,
  SignoffStatusValues,
  SignoffSubjectTypeValues,
} from '../../../services/workOrderService';
import {
  MaterialRequestStatusValues,
  ReturnReasonValues,
  StockKindValues,
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
  signoffLevelLabel,
  signoffStatusLabel,
  signoffStatusTone,
  subjectTypeLabel,
  fmtDate,
  mrStatusLabel,
  mrStatusTone,
  stockKindLabel,
  returnReasonLabel,
} from '../statusUtils';

// 直接引用 service 的 canonical `*Values` 常量做 exhaustive 來源：source enum 新增值時
// 自動流進下方 loop，若 label/tone 漏掉該 case（runtime 回 undefined）測試立刻紅，
// 不會像手寫陣列那樣「假裝覆蓋完整」。
const ALL_WO_STATUS = WorkOrderStatusValues;
const ALL_PRIORITY = PriorityValues;
const ALL_WO_TYPE = WorkOrderTypeValues;
const ALL_FOLLOWUP = FollowupKindValues;
const ALL_SIGNOFF_LEVEL = SignoffLevelValues;
const ALL_SIGNOFF_STATUS = SignoffStatusValues;
const ALL_SUBJECT_TYPE = SignoffSubjectTypeValues;
const ALL_MR_STATUS = MaterialRequestStatusValues;
const ALL_STOCK_KIND = StockKindValues;
const ALL_RETURN_REASON = ReturnReasonValues;

const VALID_TONES: PillTone[] = ['muted', 'info', 'amber', 'accent', 'ok', 'warn', 'danger'];

describe('statusLabel — 工單狀態雙語 label', () => {
  it('每個值回傳正確 en / zh', () => {
    expect(statusLabel('draft', 'en')).toBe('DRAFT');
    expect(statusLabel('draft', 'zh')).toBe('草稿');
    expect(statusLabel('dispatched', 'en')).toBe('DISPATCHED');
    expect(statusLabel('dispatched', 'zh')).toBe('已派工');
    expect(statusLabel('in_progress', 'en')).toBe('IN PROGRESS');
    expect(statusLabel('in_progress', 'zh')).toBe('進行中');
    expect(statusLabel('awaiting_signoff', 'en')).toBe('AWAITING SIGNOFF');
    expect(statusLabel('awaiting_signoff', 'zh')).toBe('待簽核');
    expect(statusLabel('closed', 'en')).toBe('CLOSED');
    expect(statusLabel('closed', 'zh')).toBe('已結案');
    expect(statusLabel('cancelled', 'en')).toBe('CANCELLED');
    expect(statusLabel('cancelled', 'zh')).toBe('已取消');
    expect(statusLabel('reopened', 'en')).toBe('REOPENED');
    expect(statusLabel('reopened', 'zh')).toBe('重開');
  });

  it('所有值在兩種語言都回傳非空字串', () => {
    for (const s of ALL_WO_STATUS) {
      expect(statusLabel(s, 'en')).toBeTruthy();
      expect(statusLabel(s, 'zh')).toBeTruthy();
    }
  });
});

describe('statusTone — 工單狀態 pill tone', () => {
  it('每個值回傳正確 tone', () => {
    expect(statusTone('draft')).toBe('muted');
    expect(statusTone('dispatched')).toBe('info');
    expect(statusTone('in_progress')).toBe('amber');
    expect(statusTone('awaiting_signoff')).toBe('accent');
    expect(statusTone('closed')).toBe('ok');
    expect(statusTone('cancelled')).toBe('muted');
    expect(statusTone('reopened')).toBe('warn');
  });

  it('所有值回傳合法 PillTone', () => {
    for (const s of ALL_WO_STATUS) {
      expect(VALID_TONES).toContain(statusTone(s));
    }
  });
});

describe('priorityLabel / priorityTone — 優先級', () => {
  it('label 正確', () => {
    expect(priorityLabel('low', 'en')).toBe('LOW');
    expect(priorityLabel('low', 'zh')).toBe('低');
    expect(priorityLabel('normal', 'en')).toBe('NORMAL');
    expect(priorityLabel('normal', 'zh')).toBe('一般');
    expect(priorityLabel('high', 'en')).toBe('HIGH');
    expect(priorityLabel('high', 'zh')).toBe('高');
    expect(priorityLabel('critical', 'en')).toBe('CRITICAL');
    expect(priorityLabel('critical', 'zh')).toBe('緊急');
  });

  it('tone 正確（critical → danger 凸顯緊急）', () => {
    expect(priorityTone('low')).toBe('muted');
    expect(priorityTone('normal')).toBe('info');
    expect(priorityTone('high')).toBe('amber');
    expect(priorityTone('critical')).toBe('danger');
  });

  it('所有值 label 非空 + tone 合法', () => {
    for (const p of ALL_PRIORITY) {
      expect(priorityLabel(p, 'en')).toBeTruthy();
      expect(priorityLabel(p, 'zh')).toBeTruthy();
      expect(VALID_TONES).toContain(priorityTone(p));
    }
  });
});

describe('typeLabel — 工單類型', () => {
  it('label 正確', () => {
    expect(typeLabel('corrective', 'en')).toBe('Corrective');
    expect(typeLabel('corrective', 'zh')).toBe('故障維修');
    expect(typeLabel('preventive', 'en')).toBe('Preventive');
    expect(typeLabel('preventive', 'zh')).toBe('預防保養');
    expect(typeLabel('inspection', 'en')).toBe('Inspection');
    expect(typeLabel('inspection', 'zh')).toBe('定檢');
    expect(typeLabel('commissioning', 'en')).toBe('Commissioning');
    expect(typeLabel('commissioning', 'zh')).toBe('試運轉');
  });

  it('所有值在兩種語言都非空', () => {
    for (const t of ALL_WO_TYPE) {
      expect(typeLabel(t, 'en')).toBeTruthy();
      expect(typeLabel(t, 'zh')).toBeTruthy();
    }
  });
});

describe('followupLabel — 後續追蹤', () => {
  it('label 正確', () => {
    expect(followupLabel('none', 'en')).toBe('No follow-up');
    expect(followupLabel('none', 'zh')).toBe('無後續');
    expect(followupLabel('followup_needed', 'en')).toBe('Follow-up needed');
    expect(followupLabel('followup_needed', 'zh')).toBe('需追蹤');
  });

  it('所有值非空', () => {
    for (const f of ALL_FOLLOWUP) {
      expect(followupLabel(f, 'en')).toBeTruthy();
      expect(followupLabel(f, 'zh')).toBeTruthy();
    }
  });
});

describe('signoff 系列 — level / status label + tone', () => {
  it('signoffLevelLabel 正確', () => {
    expect(signoffLevelLabel('employee', 'en')).toBe('Employee');
    expect(signoffLevelLabel('employee', 'zh')).toBe('員工');
    expect(signoffLevelLabel('leader', 'en')).toBe('Leader');
    expect(signoffLevelLabel('leader', 'zh')).toBe('組長');
    expect(signoffLevelLabel('supervisor', 'en')).toBe('Supervisor');
    expect(signoffLevelLabel('supervisor', 'zh')).toBe('主管');
    expect(signoffLevelLabel('treasury', 'en')).toBe('Treasury');
    expect(signoffLevelLabel('treasury', 'zh')).toBe('總務');
  });

  it('signoffStatusLabel 正確', () => {
    expect(signoffStatusLabel('pending', 'en')).toBe('Pending');
    expect(signoffStatusLabel('pending', 'zh')).toBe('待簽');
    expect(signoffStatusLabel('approved', 'en')).toBe('Approved');
    expect(signoffStatusLabel('approved', 'zh')).toBe('已通過');
    expect(signoffStatusLabel('rejected', 'en')).toBe('Rejected');
    expect(signoffStatusLabel('rejected', 'zh')).toBe('已駁回');
    expect(signoffStatusLabel('skipped', 'en')).toBe('Skipped');
    expect(signoffStatusLabel('skipped', 'zh')).toBe('已跳過');
  });

  it('signoffStatusTone 正確（approved→ok / rejected→warn）', () => {
    expect(signoffStatusTone('pending')).toBe('amber');
    expect(signoffStatusTone('approved')).toBe('ok');
    expect(signoffStatusTone('rejected')).toBe('warn');
    expect(signoffStatusTone('skipped')).toBe('muted');
  });

  it('所有 level / status 值非空 + tone 合法', () => {
    for (const l of ALL_SIGNOFF_LEVEL) {
      expect(signoffLevelLabel(l, 'en')).toBeTruthy();
      expect(signoffLevelLabel(l, 'zh')).toBeTruthy();
    }
    for (const s of ALL_SIGNOFF_STATUS) {
      expect(signoffStatusLabel(s, 'en')).toBeTruthy();
      expect(signoffStatusLabel(s, 'zh')).toBeTruthy();
      expect(VALID_TONES).toContain(signoffStatusTone(s));
    }
  });
});

describe('subjectTypeLabel — 簽核主體類型', () => {
  it('label 正確', () => {
    expect(subjectTypeLabel('work_order', 'en')).toBe('Work order');
    expect(subjectTypeLabel('work_order', 'zh')).toBe('工單');
    expect(subjectTypeLabel('material_request', 'en')).toBe('Material request');
    expect(subjectTypeLabel('material_request', 'zh')).toBe('領料單');
  });

  it('所有值非空', () => {
    for (const t of ALL_SUBJECT_TYPE) {
      expect(subjectTypeLabel(t, 'en')).toBeTruthy();
      expect(subjectTypeLabel(t, 'zh')).toBeTruthy();
    }
  });
});

describe('mrStatusLabel / mrStatusTone — 領料單狀態', () => {
  it('label 正確（dispatched=已出庫，與工單的已派工區隔）', () => {
    expect(mrStatusLabel('draft', 'en')).toBe('DRAFT');
    expect(mrStatusLabel('draft', 'zh')).toBe('草稿');
    expect(mrStatusLabel('awaiting_approval', 'en')).toBe('AWAITING APPROVAL');
    expect(mrStatusLabel('awaiting_approval', 'zh')).toBe('待簽核');
    expect(mrStatusLabel('approved', 'en')).toBe('APPROVED');
    expect(mrStatusLabel('approved', 'zh')).toBe('已通過');
    expect(mrStatusLabel('dispatched', 'en')).toBe('DISPATCHED');
    expect(mrStatusLabel('dispatched', 'zh')).toBe('已出庫');
    expect(mrStatusLabel('received', 'en')).toBe('RECEIVED');
    expect(mrStatusLabel('received', 'zh')).toBe('已簽收');
    expect(mrStatusLabel('used', 'en')).toBe('USED');
    expect(mrStatusLabel('used', 'zh')).toBe('已使用');
    expect(mrStatusLabel('closed', 'en')).toBe('CLOSED');
    expect(mrStatusLabel('closed', 'zh')).toBe('已結案');
    expect(mrStatusLabel('cancelled', 'en')).toBe('CANCELLED');
    expect(mrStatusLabel('cancelled', 'zh')).toBe('已取消');
    expect(mrStatusLabel('rejected', 'en')).toBe('REJECTED');
    expect(mrStatusLabel('rejected', 'zh')).toBe('已駁回');
  });

  it('tone 進度感漸進：建→簽→出→收→用→結（muted→amber→info→accent→accent→ok→ok）', () => {
    expect(mrStatusTone('draft')).toBe('muted');
    expect(mrStatusTone('awaiting_approval')).toBe('amber');
    expect(mrStatusTone('approved')).toBe('info');
    expect(mrStatusTone('dispatched')).toBe('accent');
    expect(mrStatusTone('received')).toBe('accent');
    expect(mrStatusTone('used')).toBe('ok');
    expect(mrStatusTone('closed')).toBe('ok');
    expect(mrStatusTone('cancelled')).toBe('muted');
    expect(mrStatusTone('rejected')).toBe('warn');
  });

  it('所有值 label 非空 + tone 合法', () => {
    for (const s of ALL_MR_STATUS) {
      expect(mrStatusLabel(s, 'en')).toBeTruthy();
      expect(mrStatusLabel(s, 'zh')).toBeTruthy();
      expect(VALID_TONES).toContain(mrStatusTone(s));
    }
  });
});

describe('stockKindLabel / returnReasonLabel', () => {
  it('stockKindLabel 正確', () => {
    expect(stockKindLabel('new', 'en')).toBe('New');
    expect(stockKindLabel('new', 'zh')).toBe('全新');
    expect(stockKindLabel('used', 'en')).toBe('Used');
    expect(stockKindLabel('used', 'zh')).toBe('良品');
    expect(stockKindLabel('repairing', 'en')).toBe('Repairing');
    expect(stockKindLabel('repairing', 'zh')).toBe('維修中');
  });

  it('returnReasonLabel 正確', () => {
    expect(returnReasonLabel('surplus', 'en')).toBe('Surplus');
    expect(returnReasonLabel('surplus', 'zh')).toBe('用剩');
    expect(returnReasonLabel('wrong_part', 'en')).toBe('Wrong part');
    expect(returnReasonLabel('wrong_part', 'zh')).toBe('拿錯料件');
    expect(returnReasonLabel('failed_install', 'en')).toBe('Failed install');
    expect(returnReasonLabel('failed_install', 'zh')).toBe('試裝失敗');
    expect(returnReasonLabel('other', 'en')).toBe('Other');
    expect(returnReasonLabel('other', 'zh')).toBe('其他');
  });

  it('所有值非空', () => {
    for (const k of ALL_STOCK_KIND) {
      expect(stockKindLabel(k, 'en')).toBeTruthy();
      expect(stockKindLabel(k, 'zh')).toBeTruthy();
    }
    for (const r of ALL_RETURN_REASON) {
      expect(returnReasonLabel(r, 'en')).toBeTruthy();
      expect(returnReasonLabel(r, 'zh')).toBeTruthy();
    }
  });
});

describe('fmtDateTime — UTC → Asia/Taipei（+8）YYYY-MM-DD HH:mm', () => {
  it('UTC 00:00 → Taipei 08:00 同日', () => {
    expect(fmtDateTime('2026-05-28T00:00:00Z')).toBe('2026-05-28 08:00');
  });

  it('+8 跨日：UTC 前一日 17:00 → Taipei 次日 01:00', () => {
    expect(fmtDateTime('2026-05-27T17:00:00Z')).toBe('2026-05-28 01:00');
  });

  it('午夜邊界：UTC 16:00 → Taipei 次日 00:00（守 hourCycle h23，防 ICU 24:00 陷阱）', () => {
    expect(fmtDateTime('2026-05-27T16:00:00Z')).toBe('2026-05-28 00:00');
  });

  it('補零：UTC 01:05 → Taipei 09:05', () => {
    expect(fmtDateTime('2026-05-28T01:05:00Z')).toBe('2026-05-28 09:05');
  });

  it('null / 空字串 → 破折號', () => {
    expect(fmtDateTime(null)).toBe('—');
    expect(fmtDateTime('')).toBe('—');
  });

  it('無效字串 → 原樣回傳（不丟例外）', () => {
    expect(fmtDateTime('not-a-date')).toBe('not-a-date');
  });
});

describe('fmtDate — UTC → Asia/Taipei（+8）YYYY-MM-DD', () => {
  it('+8 跨日：UTC 前一日 17:00 → Taipei 次日日期', () => {
    expect(fmtDate('2026-05-27T17:00:00Z')).toBe('2026-05-28');
  });

  it('同日：UTC 02:00 → Taipei 10:00 同日', () => {
    expect(fmtDate('2026-05-28T02:00:00Z')).toBe('2026-05-28');
  });

  it('null / 空字串 → 破折號', () => {
    expect(fmtDate(null)).toBe('—');
    expect(fmtDate('')).toBe('—');
  });

  it('無效字串 → 原樣回傳', () => {
    expect(fmtDate('garbage')).toBe('garbage');
  });
});

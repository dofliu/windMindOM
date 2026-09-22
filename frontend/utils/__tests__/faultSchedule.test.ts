/**
 * toFaultScheduleEntries 純函式測試（WMOM-20260720-13(4)）。
 *
 * 這個 helper 存在的理由就是「同一份排程不要被映射兩次、形狀還不同」——先前 request body 用
 * `at_hour`、就地組的情境 config 用 `offset_seconds`，兩份各自演化正是 A1 那個 bug 的成因模式。
 * 故本測守住：**單一形狀 = 後端落地形狀**、換算正確、空排程回空陣列（而非 undefined）。
 */

import { describe, it, expect } from 'vitest';
import { toFaultScheduleEntries } from '../faultSchedule';

const FAULT = { scenarioId: 'hydraulic_leak', turbineId: 'WT002', atHour: 12, severityRate: 0.002 };

describe('toFaultScheduleEntries', () => {
  it('產出後端落地形狀：scenario_id / turbine_id / offset_seconds / severity_rate', () => {
    expect(toFaultScheduleEntries([FAULT])).toEqual([
      {
        scenario_id: 'hydraulic_leak',
        turbine_id: 'WT002',
        offset_seconds: 12 * 3600,
        severity_rate: 0.002,
      },
    ]);
  });

  it('不再產出 at_hour（後端優先吃 offset_seconds；兩種形狀並存才是漂移來源）', () => {
    const [entry] = toFaultScheduleEntries([FAULT]);
    expect(entry).not.toHaveProperty('at_hour');
  });

  it('at_hour → offset_seconds 以 3600 換算（0 小時 = 0 秒，非省略）', () => {
    expect(toFaultScheduleEntries([{ ...FAULT, atHour: 0 }])[0].offset_seconds).toBe(0);
    expect(toFaultScheduleEntries([{ ...FAULT, atHour: 1.5 }])[0].offset_seconds).toBe(5400);
  });

  it('空排程 → 空陣列（不是 undefined）：「刻意的純風況基準情境」與「沒帶排程」必須可區分', () => {
    const out = toFaultScheduleEntries([]);
    expect(out).toEqual([]);
    expect(out).not.toBeUndefined();
  });

  it('多列保留原序（後端自己會依 offset 排序，前端不預先重排以免與畫面不一致）', () => {
    const entries = toFaultScheduleEntries([
      { ...FAULT, turbineId: 'WT003', atHour: 20 },
      { ...FAULT, turbineId: 'WT001', atHour: 5 },
    ]);
    expect(entries.map(e => e.turbine_id)).toEqual(['WT003', 'WT001']);
  });
});

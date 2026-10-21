/**
 * scenarioEvents 純函式測試（WMOM-20261021-04）：情境趨勢圖只標警報成立 / 跳機與情境標記，
 * 不把 PLC 解除 / 資訊 / 狀態轉換也畫成「故障」線。
 */

import { describe, it, expect } from 'vitest';
import { isScenarioFaultMarker } from '../scenarioEvents';

describe('isScenarioFaultMarker', () => {
  it.each([
    ['plc', 'alarm_raised'],
    ['plc', 'trip'],
  ])('marks PLC %s %s', (source, kind) => {
    expect(isScenarioFaultMarker({ event_type: 'fault', source, payload: { kind, code: 240 } })).toBe(true);
  });

  it.each(['alarm_cleared', 'trip_cleared', 'restart_blocked', 'operator_reset', 'info'])(
    'skips PLC %s',
    (kind) => {
      expect(isScenarioFaultMarker({ event_type: 'fault', source: 'plc', payload: { kind } })).toBe(false);
    },
  );

  it('skips state transitions (a PLC stop is already marked by its trip event)', () => {
    expect(
      isScenarioFaultMarker({
        event_type: 'fault',
        source: 'simulator',
        payload: { fromState: 6, toState: 9, shutdownCause: 'plc:240' },
      }),
    ).toBe(false);
  });

  it('marks scenario injection / trip markers and legacy fault events', () => {
    expect(isScenarioFaultMarker({ event_type: 'fault', source: 'scenario', payload: { scenarioId: 'x' } })).toBe(true);
    expect(isScenarioFaultMarker({ event_type: 'fault', source: 'simulator' })).toBe(true);
  });

  it('ignores non-fault events', () => {
    expect(isScenarioFaultMarker({ event_type: 'state', source: 'simulator', payload: { fromState: 1, toState: 4 } })).toBe(false);
    expect(isScenarioFaultMarker({ event_type: 'grid', source: 'simulator' })).toBe(false);
  });
});

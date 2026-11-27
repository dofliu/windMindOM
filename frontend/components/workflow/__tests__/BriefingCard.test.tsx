/**
 * 出發前準備卡（WMOM-20261125-05）的畫面測試。
 *
 * 守住的事：
 *   - 六塊都顯示：本次事件、近 7 天、相關訊號與同場對照、手冊、過往工單、聲明
 *   - 偏高 / 偏低 / 相近 / 無法比較的標示
 *   - 同場其他機組同碼時特別標出（外部原因的線索）
 *   - 資料不完整時顯示警示與原因；事後補產生的卡片有標示
 *   - 卡上寫明不判定根因
 *   - 讀取：載入中 → 卡片；沒有卡片不顯示任何東西；讀取失敗顯示訊息；換工單會重讀
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import { BriefingCard, BriefingCardView, InspectionCardView } from '../BriefingCard';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import type {
  BriefingCard as CardData,
  BriefingResponse,
  BriefingSignal,
  InspectionBriefingCard,
} from '../../../services/briefingService';

afterEach(cleanup);

function signal(over: Partial<BriefingSignal>): BriefingSignal {
  return {
    name: 'Z72PLC__UI_Loc_WGEN_Analogue_GnBrgTmp1',
    label_zh: '發電機軸承溫度',
    label_en: 'Generator bearing temperature',
    unit: '°C',
    role: 'primary',
    turbine_mean: 42.75,
    farm_median: 32.46,
    farm_min: 31.9,
    farm_max: 33.1,
    peer_count: 4,
    deviation: 'high',
    recent_mean: 55.21,
    recent_farm_median: 32.5,
    baseline_mean: 32.33,
    change_from_baseline: 10.42,
    ...over,
  };
}

function card(over: Partial<CardData> = {}): CardData {
  return {
    card_version: '1.0',
    kind: 'fault_dispatch',
    work_order: {
      business_key: 'WO-FARMA-202611-001',
      turbine_id: 'WT002',
      type: 'corrective',
      priority: 'normal',
      source_alarm_code: 240,
    },
    data_cutoff: '2026-01-01T02:16:30.000000Z',
    generated_late: false,
    event: {
      ts: '2026-01-01T02:16:30.000000Z',
      code: 240,
      level: 'T1',
      text: 'Bearing 1 temperature very high',
      event_id: 'T_240',
      event_type: 'trip',
      turbine_state: 6,
      turbine_state_ts: '2026-01-01T02:16:20.000000Z',
    },
    recent_events: {
      window: { start: '2025-12-25T02:16:30.000000Z', end: '2026-01-01T02:16:30.000000Z' },
      same_code: { count: 1, first_ts: '2026-01-01T02:16:30.000000Z', last_ts: '2026-01-01T02:16:30.000000Z', recent: [] },
      other_codes: [{ code: 262, level: 'A', text: 'Bearing 1 temperature high', count: 2, last_ts: null }],
      farm_same_code: { window_minutes: 10, turbines: [] },
    },
    signals: {
      window: { start: '2026-01-01T01:16:30.000000Z', end: '2026-01-01T02:16:30.000000Z' },
      samples: 360,
      peers: 4,
      items: [
        signal({}),
        signal({ name: 'ws', label_zh: '機艙風速', label_en: 'Nacelle wind speed', unit: 'm/s', role: 'context', turbine_mean: 10.46, farm_median: 9.79, deviation: 'normal', baseline_mean: 10.51 }),
        signal({ name: 'pw', label_zh: '功率', label_en: 'Power', unit: 'kW', role: 'context', turbine_mean: null, farm_median: null, deviation: 'unknown', baseline_mean: null }),
        signal({ name: 'pr', label_zh: '煞車壓力', label_en: 'Brake pressure', unit: 'bar', role: 'related', turbine_mean: 120, farm_median: 205, deviation: 'low', baseline_mean: 204 }),
      ],
    },
    past_work_orders: [
      { business_key: 'WO-FARMA-202610-007', type: 'inspection', status: 'closed', source_alarm_code: 62, created_at: '2025-10-03T01:00:00+00:00', finished_at: null },
    ],
    manual: {
      status: 'ok',
      code: 240,
      level: 'T1',
      text: 'Bearing 1 temperature very high',
      cause: 'Bearing temperature 1 is very high',
      rectification: 'Check lubrication main bearing. Check cooling fan.',
      manual_page: 110,
      source: 'Z72 User Manual Appendix C',
    },
    inventory: { status: 'no_mapping', note: '' },
    data_quality: { flags: [], degraded: false },
    notes: [],
    ...over,
  };
}

function view(data: CardData, lang: 'zh' | 'en' = 'zh') {
  return render(
    <ThemeProvider>
      <BriefingCardView card={data} lang={lang} />
    </ThemeProvider>,
  );
}

describe('BriefingCardView', () => {
  it('shows the event, the recent history and the manual entry', () => {
    view(card());
    expect(screen.getByText('出發前準備卡')).toBeInTheDocument();
    expect(screen.getByText('T1 240')).toBeInTheDocument();
    expect(screen.getByText(/Bearing 1 temperature very high/)).toBeInTheDocument();
    expect(screen.getByText(/最後一筆讀值的機組狀態：發電中/)).toBeInTheDocument();
    expect(screen.getByText(/A 262 ×2/)).toBeInTheDocument();
    expect(screen.getByText('同一時間同場沒有其他機組同碼')).toBeInTheDocument();
    expect(screen.getByText('Bearing temperature 1 is very high')).toBeInTheDocument();
    expect(screen.getByText('Check lubrication main bearing. Check cooling fan.')).toBeInTheDocument();
    expect(screen.getByText(/Appendix C p\.110/)).toBeInTheDocument();
    // 過往工單的事件碼是數字，補到三位
    expect(screen.getByText(/WO-FARMA-202610-007 · inspection · closed · 062/)).toBeInTheDocument();
  });

  it('marks each signal against the rest of the farm', () => {
    view(card());
    expect(screen.getByText('發電機軸承溫度')).toBeInTheDocument();
    expect(screen.getByText('42.8')).toBeInTheDocument();
    expect(screen.getAllByText('55.2').length).toBeGreaterThan(0); // 最近 10 分鐘的平均
    expect(screen.getByText('32.5')).toBeInTheDocument();
    expect(screen.getByText('和同場 4 台發電中的機組比')).toBeInTheDocument();
    expect(screen.getByText('最近 10 分鐘')).toBeInTheDocument();
    expect(screen.getByText('偏高')).toBeInTheDocument();
    expect(screen.getByText('偏低')).toBeInTheDocument();
    expect(screen.getByText('相近')).toBeInTheDocument();
    expect(screen.getByText('無法比較')).toBeInTheDocument();
  });

  it('calls out the same code on other turbines', () => {
    const data = card();
    data.recent_events.farm_same_code.turbines = [
      { turbine_id: 'WT001', ts: '2026-01-01T02:16:00.000000Z' },
      { turbine_id: 'WT003', ts: '2026-01-01T02:16:10.000000Z' },
    ];
    view(data);
    expect(screen.getByText(/前後 10 分鐘內，同場另有 2 台同碼：WT001、WT003/)).toBeInTheDocument();
    expect(screen.queryByText('同一時間同場沒有其他機組同碼')).not.toBeInTheDocument();
  });

  it('warns when the data is incomplete and says why', () => {
    view(
      card({
        generated_late: true,
        data_quality: { flags: ['no_event_found', 'stale_data', 'events_truncated', 'something_new'], degraded: true },
        event: { turbine_state: null },
        manual: { status: 'no_alarm_code' },
        past_work_orders: [],
      }),
    );
    expect(screen.getByText('資料不完整，請保守判讀')).toBeInTheDocument();
    expect(screen.getByText('近 7 天找不到這筆警報事件')).toBeInTheDocument();
    expect(screen.getByText('最新讀值已經超過 5 分鐘')).toBeInTheDocument();
    expect(screen.getByText('事件太多，沒有全部看完')).toBeInTheDocument();
    expect(screen.getByText('something_new')).toBeInTheDocument();
    expect(screen.getByText(/事後補產生/)).toBeInTheDocument();
    expect(screen.getByText('沒有對應的警報事件')).toBeInTheDocument();
    expect(screen.getByText('這張工單沒有對應的手冊條目')).toBeInTheDocument();
    expect(screen.getByText('沒有')).toBeInTheDocument();
  });

  it('states that it does not determine the root cause, in both languages', () => {
    view(card());
    expect(screen.getByText(/不判定根因/)).toBeInTheDocument();
    expect(screen.getByText(/沒有列料件/)).toBeInTheDocument();
    cleanup();
    view(card(), 'en');
    expect(screen.getByText('Pre-departure briefing')).toBeInTheDocument();
    expect(screen.getByText(/does not determine the root cause/)).toBeInTheDocument();
    expect(screen.getByText('Generator bearing temperature')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });
});

describe('BriefingCard', () => {
  const response = (data: CardData): BriefingResponse => ({
    work_order_id: 'wo-1',
    business_key: data.work_order.business_key,
    turbine_id: 'WT002',
    created_at: '2026-01-01T02:16:31+00:00',
    data_cutoff: data.data_cutoff,
    card: data,
  });

  function mount(load: (id: string, farm: string) => Promise<BriefingResponse | null>, id = 'wo-1') {
    return render(
      <ThemeProvider>
        <BriefingCard workOrderId={id} farmId="farm-a" lang="zh" load={load} />
      </ThemeProvider>,
    );
  }

  it('loads the card for the work order', async () => {
    const load = vi.fn().mockResolvedValue(response(card()));
    mount(load);
    expect(screen.getByText('出發前準備卡載入中…')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('briefing-card')).toBeInTheDocument());
    expect(load).toHaveBeenCalledWith('wo-1', 'farm-a');
  });

  it('shows nothing when the work order has no card', async () => {
    const load = vi.fn().mockResolvedValue(null);
    const { container } = mount(load);
    await waitFor(() => expect(screen.queryByText('出發前準備卡載入中…')).not.toBeInTheDocument());
    expect(screen.queryByTestId('briefing-card')).not.toBeInTheDocument();
    expect(container.textContent).toBe('');
  });

  it('reports a failed load without breaking the page', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'));
    mount(load);
    await waitFor(() => expect(screen.getByText('出發前準備卡讀取失敗')).toBeInTheDocument());
  });

  it('reloads when the work order changes', async () => {
    const load = vi.fn().mockResolvedValue(response(card()));
    const { rerender } = mount(load);
    await waitFor(() => expect(screen.getByTestId('briefing-card')).toBeInTheDocument());
    rerender(
      <ThemeProvider>
        <BriefingCard workOrderId="wo-2" farmId="farm-a" lang="zh" load={load} />
      </ThemeProvider>,
    );
    await waitFor(() => expect(load).toHaveBeenCalledWith('wo-2', 'farm-a'));
    expect(load).toHaveBeenCalledTimes(2);
  });
});


// ─── 例行巡檢卡（WMOM-20261126-05）──────────────────────────────────────────

function inspectionCard(overrides: Partial<InspectionBriefingCard> = {}): InspectionBriefingCard {
  const base = card();
  return {
    card_version: '1.2',
    kind: 'routine_inspection',
    work_order: { ...base.work_order, type: 'inspection', source_alarm_code: null },
    data_cutoff: '2026-01-01T02:16:40Z',
    generated_late: false,
    checklist: {
      order_changed: true,
      items: [
        {
          id: 'transformer', label_zh: '變壓器', label_en: 'Transformer', default_position: 2, position: 1,
          attention: true, score: 5,
          evidence: [
            { type: 'signal', name: 'TrfCoreTmp', label_zh: '變壓器鐵芯溫度', label_en: 'Transformer core temp',
              unit: '°C', deviation: 'high', turbine_mean: 66.1, recent_mean: 67.9, farm_median: 34.2 },
            { type: 'events', code: 417, level: 'A', text: 'Transformer temperature high', event_type: 'alarm_raised',
              count: 2, last_ts: '2026-01-01T01:00:00Z' },
            { type: 'open_work_order', business_key: 'WO-9', source_alarm_code: 444, status: 'draft' },
          ],
          signals: ['TrfCoreTmp'],
        },
        {
          id: 'converter_cooling', label_zh: '變頻器與冷卻水系統', label_en: 'Converter and cooling water',
          default_position: 1, position: 2, attention: false, score: 0, evidence: [], signals: [],
        },
      ],
    },
    recent_events: { window: { start: '', end: '' }, by_code: [] },
    signals: base.signals,
    past_work_orders: [],
    data_quality: { flags: [], degraded: false },
    notes: [],
    ...overrides,
  };
}

describe('InspectionCardView', () => {
  it('lists the checklist in the card order with the evidence and the planned position', () => {
    render(
      <ThemeProvider>
        <InspectionCardView card={inspectionCard()} lang="zh" />
      </ThemeProvider>,
    );
    expect(screen.getByText('例行巡檢卡')).toBeInTheDocument();
    const first = screen.getByTestId('inspection-item-transformer');
    expect(first).toHaveTextContent('1. 變壓器');
    expect(first).toHaveTextContent('原訂第 2');
    expect(first).toHaveTextContent('注意');
    expect(first).toHaveTextContent('變壓器鐵芯溫度 偏高：66.1 °C（同場 34.2）');
    expect(first).toHaveTextContent('A 417 Transformer temperature high — 警報 ×2');
    expect(first).toHaveTextContent('未結案的故障維修工單 WO-9（444）');
    const second = screen.getByTestId('inspection-item-converter_cooling');
    expect(second).toHaveTextContent('2. 變頻器與冷卻水系統');
    expect(second).not.toHaveTextContent('注意');
    expect(screen.getByText(/不判定根因/)).toBeInTheDocument();
  });

  it('says when there is no evidence and does not treat it as missing data', () => {
    render(
      <ThemeProvider>
        <InspectionCardView
          card={inspectionCard({
            checklist: { order_changed: false, items: [] },
            data_quality: { flags: ['no_evidence', 'no_baseline'], degraded: false },
          })}
          lang="en"
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('No evidence found: the planned order is kept.')).toBeInTheDocument();
    expect(screen.queryByText(/Incomplete data/)).not.toBeInTheDocument();
  });

  it('is what BriefingCard shows for an inspection order', async () => {
    const data = inspectionCard();
    const load = vi.fn().mockResolvedValue({
      work_order_id: 'wo-3', business_key: 'WO-3', turbine_id: 'WT003', created_at: '', data_cutoff: data.data_cutoff,
      card: data,
    });
    render(
      <ThemeProvider>
        <BriefingCard workOrderId="wo-3" farmId="farm-a" lang="zh" load={load} />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('inspection-card')).toBeInTheDocument());
    expect(screen.queryByTestId('briefing-card')).not.toBeInTheDocument();
  });
});

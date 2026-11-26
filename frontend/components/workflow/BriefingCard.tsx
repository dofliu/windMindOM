/**
 * 出發前準備卡（WMOM-20261125-05）：故障出勤卡的畫面。
 *
 * 管理端的工單頁與現場工程師的「我的工單」共用。卡片由後端在工單建立當下產生，只整理看得到的資料
 * （讀值、PLC 事件、工單、手冊），不判定根因；資料有缺時卡上會標明。
 *
 * - `BriefingCardView`：純顯示，吃一張卡。
 * - `BriefingCard`：負責讀取（`load` 可以換掉，測試用）；沒有卡片時不顯示任何東西。
 */

import React, { useEffect, useState } from 'react';
import { Card, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  fetchBriefing,
  type BriefingCard as BriefingCardData,
  type BriefingResponse,
  type BriefingSignal,
} from '../../services/briefingService';

type Lang = 'en' | 'zh';

const FLAG_TEXT: Record<string, [string, string]> = {
  no_alarm_code: ['Work order has no alarm code', '工單沒有帶警報碼'],
  no_event_found: ['The alarm event was not found in the last 7 days', '近 7 天找不到這筆警報事件'],
  signals_unmapped: ['No related signal is known for this code', '這個警報碼沒有對應的量測'],
  signal_data_missing: ['No readings in the hour before the cut-off', '截止點前 1 小時沒有讀值'],
  stale_data: ['The latest reading is older than 5 minutes', '最新讀值已經超過 5 分鐘'],
  too_few_peers: ['Too few other turbines to compare with', '同場可比較的機組太少'],
  no_baseline: ['No earlier readings to compare with', '沒有更早的讀值可以比'],
  events_truncated: ['Too many events to scan them all', '事件太多，沒有全部看完'],
};

const STATE_NAME: Record<number, [string, string]> = {
  1: ['Shutdown', '停機'],
  2: ['Standby', '待機'],
  3: ['Wait restart', '等待重啟'],
  4: ['Pre-production', '起動中'],
  5: ['Synchronization', '併網中'],
  6: ['Production', '發電中'],
  7: ['Emergency stop', '緊急停機'],
  8: ['Restart', '重啟中'],
  9: ['Normal stop', '正常停機'],
};

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? '—' : value.toFixed(digits);
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

interface ViewProps {
  card: BriefingCardData;
  lang: Lang;
}

export const BriefingCardView: React.FC<ViewProps> = ({ card, lang }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string): string => (lang === 'zh' ? zh : en);
  const section: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: C.text, margin: '14px 0 6px' };
  const cell: React.CSSProperties = { padding: '4px 8px', fontSize: 12, color: C.text, textAlign: 'right' };
  const head: React.CSSProperties = { ...cell, color: C.sub, fontWeight: 600 };

  const deviationPill = (item: BriefingSignal): React.ReactNode => {
    if (item.deviation === 'high') return <StatusPill tone="warn">{ui('High', '偏高')}</StatusPill>;
    if (item.deviation === 'low') return <StatusPill tone="warn">{ui('Low', '偏低')}</StatusPill>;
    if (item.deviation === 'normal') return <StatusPill tone="ok">{ui('In line', '相近')}</StatusPill>;
    return <StatusPill tone="muted">{ui('No comparison', '無法比較')}</StatusPill>;
  };

  const state = card.event.turbine_state;
  const farmSame = card.recent_events.farm_same_code.turbines;
  const manual = card.manual;

  return (
    <Card>
      <div data-testid="briefing-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
            {ui('Pre-departure briefing', '出發前準備卡')}
          </div>
          <div style={{ fontSize: 11, color: C.faint }}>
            {ui('Data up to', '資料截止')} {fmtTime(card.data_cutoff)}
            {card.generated_late ? ui(' (generated later)', '（事後補產生）') : ''}
          </div>
        </div>

        {card.data_quality.degraded && (
          <div style={{ marginTop: 8 }}>
            <Card tone="warn" padding={10}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.warn }}>
                {ui('Incomplete data — read with care', '資料不完整，請保守判讀')}
              </div>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12, color: C.text }}>
                {card.data_quality.flags.map(flag => (
                  <li key={flag}>{FLAG_TEXT[flag] ? ui(FLAG_TEXT[flag][0], FLAG_TEXT[flag][1]) : flag}</li>
                ))}
              </ul>
            </Card>
          </div>
        )}

        <div style={section}>{ui('This event', '本次事件')}</div>
        <div style={{ fontSize: 13, color: C.text }}>
          {card.event.code !== undefined ? (
            <>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                {card.event.level} {String(card.event.code).padStart(3, '0')}
              </span>{' '}
              {card.event.text}
              <div style={{ fontSize: 12, color: C.sub, marginTop: 2 }}>{fmtTime(card.event.ts)}</div>
            </>
          ) : (
            <span style={{ color: C.sub }}>{ui('No alarm event on record', '沒有對應的警報事件')}</span>
          )}
          <div style={{ fontSize: 12, color: C.sub, marginTop: 2 }}>
            {ui('Turbine state in the last reading: ', '最後一筆讀值的機組狀態：')}
            {state !== null && STATE_NAME[state] ? ui(STATE_NAME[state][0], STATE_NAME[state][1]) : '—'}
            {state !== null && card.event.turbine_state_ts
              ? ui(` (${fmtTime(card.event.turbine_state_ts)})`, `（${fmtTime(card.event.turbine_state_ts)}）`)
              : ''}
          </div>
        </div>

        <div style={section}>{ui('Last 7 days', '近 7 天的事件')}</div>
        <div style={{ fontSize: 12, color: C.text }}>
          {ui('Same code on this turbine: ', '這台機組同碼：')}
          <strong>{card.recent_events.same_code.count}</strong> {ui('time(s)', '次')}
          {card.recent_events.other_codes.length > 0 && (
            <div style={{ marginTop: 4 }}>
              {ui('Other codes: ', '其他碼：')}
              {card.recent_events.other_codes
                .map(o => `${o.level} ${String(o.code).padStart(3, '0')} ×${o.count}`)
                .join('、')}
            </div>
          )}
          <div style={{ marginTop: 4 }}>
            {farmSame.length > 0 ? (
              <span style={{ color: C.warn, fontWeight: 600 }}>
                {ui(
                  `Same code on ${farmSame.length} other turbine(s) within ${card.recent_events.farm_same_code.window_minutes} min: `,
                  `前後 ${card.recent_events.farm_same_code.window_minutes} 分鐘內，同場另有 ${farmSame.length} 台同碼：`,
                )}
                {farmSame.map(t => t.turbine_id).join('、')}
              </span>
            ) : (
              <span style={{ color: C.sub }}>
                {ui('No other turbine raised this code at the same time', '同一時間同場沒有其他機組同碼')}
              </span>
            )}
          </div>
        </div>

        <div style={section}>
          {ui('Related signals (hour before cut-off)', '相關訊號（截止點前 1 小時的平均）')}
        </div>
        <div style={{ fontSize: 11, color: C.faint, marginBottom: 4 }}>
          {ui(
            `Compared with ${card.signals.peers} producing turbine(s) on the farm`,
            `和同場 ${card.signals.peers} 台發電中的機組比`,
          )}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead>
              <tr>
                <th scope="col" style={{ ...head, textAlign: 'left' }}>{ui('Signal', '訊號')}</th>
                <th scope="col" style={head}>{ui('This turbine', '本機')}</th>
                <th scope="col" style={head}>{ui('Last 10 min', '最近 10 分鐘')}</th>
                <th scope="col" style={head}>{ui('Last reading', '最後一筆')}</th>
                <th scope="col" style={head}>{ui('Farm median', '同場中位數')}</th>
                <th scope="col" style={head}>{ui('Earlier (6 h)', '自己前 6 小時')}</th>
                <th scope="col" style={head}>{ui('vs. farm', '與同場比')}</th>
              </tr>
            </thead>
            <tbody>
              {card.signals.items.map(item => (
                <tr key={item.name} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ ...cell, textAlign: 'left', fontWeight: item.role === 'primary' ? 700 : 400 }}>
                    {lang === 'zh' ? item.label_zh : item.label_en}
                    {item.unit ? <span style={{ color: C.faint }}> ({item.unit})</span> : null}
                  </td>
                  <td style={cell}>{fmt(item.turbine_mean)}</td>
                  <td style={cell}>{fmt(item.recent_mean)}</td>
                  <td style={cell}>{fmt(item.last_value)}</td>
                  <td style={cell}>{fmt(item.farm_median)}</td>
                  <td style={cell}>{fmt(item.baseline_mean)}</td>
                  <td style={cell}>{deviationPill(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={section}>{ui('Manual', '手冊')}</div>
        {manual.status === 'ok' ? (
          <div style={{ fontSize: 12, color: C.text }}>
            <div>
              <span style={{ color: C.sub }}>{ui('Listed cause: ', '手冊列的原因：')}</span>
              {manual.cause ?? '—'}
            </div>
            <div style={{ marginTop: 2 }}>
              <span style={{ color: C.sub }}>{ui('Listed rectification: ', '手冊列的處置：')}</span>
              {manual.rectification ?? '—'}
            </div>
            <div style={{ marginTop: 2, color: C.faint }}>
              {manual.source}
              {manual.manual_page ? ` p.${manual.manual_page}` : ''}
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: C.sub }}>
            {ui('No manual entry for this work order', '這張工單沒有對應的手冊條目')}
          </div>
        )}

        <div style={section}>{ui('Earlier work orders on this turbine', '這台機組以前的工單')}</div>
        {card.past_work_orders.length === 0 ? (
          <div style={{ fontSize: 12, color: C.sub }}>{ui('None', '沒有')}</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: C.text }}>
            {card.past_work_orders.map(order => (
              <li key={order.business_key}>
                {order.business_key} · {order.type} · {order.status}
                {order.source_alarm_code !== null ? ` · ${String(order.source_alarm_code).padStart(3, '0')}` : ''}
                {' · '}
                {fmtTime(order.created_at)}
              </li>
            ))}
          </ul>
        )}

        <div style={{ marginTop: 12, fontSize: 11, color: C.faint }}>
          {ui(
            'This card only organises observable data; it does not determine the root cause.',
            '本卡只整理看得到的資料，不判定根因。',
          )}{' '}
          {card.inventory.status === 'no_mapping'
            ? ui('No parts list: there is no alarm-to-part mapping yet.', '沒有列料件：目前沒有警報碼對料件的對應表。')
            : ''}
        </div>
      </div>
    </Card>
  );
};

interface Props {
  workOrderId: string;
  farmId: string;
  lang: Lang;
  /** 讀取卡片的函式；預設打後端，測試時換掉。 */
  load?: (workOrderId: string, farmId: string) => Promise<BriefingResponse | null>;
}

export const BriefingCard: React.FC<Props> = ({ workOrderId, farmId, lang, load = fetchBriefing }) => {
  const { C } = useTheme();
  const [card, setCard] = useState<BriefingCardData | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'none' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setCard(null);
    load(workOrderId, farmId)
      .then(resp => {
        if (cancelled) return;
        setCard(resp ? resp.card : null);
        setState(resp ? 'ready' : 'none');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [workOrderId, farmId, load]);

  if (state === 'loading') {
    return (
      <div style={{ fontSize: 12, color: C.sub }}>
        {lang === 'zh' ? '出發前準備卡載入中…' : 'Loading briefing…'}
      </div>
    );
  }
  if (state === 'error') {
    return (
      <div style={{ fontSize: 12, color: C.warn }}>
        {lang === 'zh' ? '出發前準備卡讀取失敗' : 'Failed to load the briefing'}
      </div>
    );
  }
  if (state === 'none' || card === null) return null;
  return <BriefingCardView card={card} lang={lang} />;
};

export default BriefingCard;

/**
 * ScenarioDetail — 調閱單一已保存情境（WMOM-20260719-02 前端，DEC-20260719-01）。
 *
 * 情境詮釋資料 + 頁籤容器：「趨勢」（單機發電量 vs 風速趨勢 + 故障標記，ScenarioTrendView）與
 * 「機組比較」（跨機組比較、有故障 vs 健康，ScenarioCompareView，A1 / DEC-20260720-02）。兩頁籤各
 * 自消費對應端點；本元件只負責詮釋資料 header + 頁籤切換，與兩個子視圖對稱解耦。
 *
 * 頁籤採 **keep-alive**（WMOM-20260720-13(2)）：造訪過的頁籤保持掛載、只切 `display`。原本用
 * `{tab === 'trend' && <ScenarioTrendView/>}` 條件式渲染，切頁籤會 unmount 子元件 → 所選機組
 * （`turbineId`）連同已抓的 history 一起銷毀，切回趨勢頁重設回 WT001 並重打一次 API——正打在 A1
 * 主打的「比較↔趨勢來回」動線上。
 */

import React, { useState } from 'react';
import { Btn, Card, Stat, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { windProfileLabel } from '../utils/windProfiles';
import ScenarioCompareView from './ScenarioCompareView';
import ScenarioTrendView from './ScenarioTrendView';
import type { FaultScheduleEntry } from '../utils/faultSchedule';

type DetailTab = 'trend' | 'compare';

export interface ScenarioConfig {
  kind?: string; // 後端以 config_json.kind === 'scenario' 標記情境 session
  name?: string;
  wind_profile?: string;
  duration_hours?: number;
  time_step?: number;
  total_readings?: number;
  faults_injected?: number;
  sim_start?: string;
  sim_end?: string;
  status?: string;
  fault_schedule?: FaultScheduleEntry[]; // 與送出端共用形狀，見 utils/faultSchedule
}

export interface SavedScenario {
  id: number;
  started_at: string;
  ended_at?: string | null;
  turbine_count?: number;
  config?: ScenarioConfig;
}

interface Props {
  scenario: SavedScenario;
  lang?: 'en' | 'zh';
  onBack: () => void;
}

const ScenarioDetail: React.FC<Props> = ({ scenario, lang = 'zh', onBack }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const cfg = scenario.config ?? {};

  const [tab, setTab] = useState<DetailTab>('trend');
  // 造訪過的頁籤才掛載，且掛載後不再卸除（keep-alive）。刻意「首次造訪才掛載」而非一開始就全掛：
  // 如此每個子視圖的第一次 mount 一定發生在**可見**狀態下——recharts `ResponsiveContainer` 於
  // mount 時量測容器尺寸，若在 `display:none` 下初次掛載會量到 0 而畫不出圖。之後轉成
  // `display:none` 不會觸發 ResizeObserver（規格：display:none 的元素不被觀察），已量到的尺寸
  // 因此保留，切回來即正確。
  const [visited, setVisited] = useState<Record<DetailTab, boolean>>({ trend: true, compare: false });
  const openTab = (next: DetailTab) => {
    setVisited(v => (v[next] ? v : { ...v, [next]: true }));
    setTab(next);
  };

  return (
    <div>
      {/* ── 情境詮釋資料 + 返回 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text }}>
              {cfg.name || u('(unnamed scenario)', '（未命名情境）')}
            </div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
              {u('Generated', '產生於')} {new Date(scenario.started_at).toLocaleString()}
              {cfg.wind_profile ? ` · ${u('wind', '風況')} ${windProfileLabel(cfg.wind_profile, lang)}` : ''}
              {cfg.status === 'error' && (
                <StatusPill tone="warn" size="sm">
                  {u('generation failed', '生成失敗')}
                </StatusPill>
              )}
            </div>
          </div>
          <Btn variant="secondary" onClick={onBack} ariaLabel={u('Back to scenario list', '返回情境列表')}>
            ← {u('Back', '返回')}
          </Btn>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
            gap: 14,
            marginTop: 14,
          }}
        >
          <Stat label={u('Duration', '時長')} value={`${cfg.duration_hours ?? '—'}h`} size={20} />
          <Stat label={u('Resolution', '解析度')} value={`${cfg.time_step ?? '—'}s`} size={20} />
          <Stat label={u('Readings', '資料筆數')} value={(cfg.total_readings ?? 0).toLocaleString()} highlight size={20} />
          <Stat label={u('Faults injected', '注入故障數')} value={cfg.faults_injected ?? 0} size={20} />
        </div>
      </Card>

      {/* ── 頁籤：趨勢（單機）｜機組比較（跨機組，A1）── */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          flexWrap: 'wrap',
          marginBottom: 14,
          padding: 4,
          background: C.panelMuted,
          borderRadius: 8,
        }}
      >
        {([
          { id: 'trend' as const, en: 'Trend', zh: '趨勢' },
          { id: 'compare' as const, en: 'Compare', zh: '機組比較' },
        ]).map(t => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => openTab(t.id)}
              aria-pressed={active}
              style={{
                padding: '6px 12px',
                fontSize: 12,
                borderRadius: 6,
                border: 'none',
                background: active ? C.accent : 'transparent',
                color: active ? C.accentInk : C.sub,
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: active ? 600 : 500,
              }}
            >
              {u(t.en, t.zh)}
            </button>
          );
        })}
      </div>

      {visited.trend && (
        <div style={{ display: tab === 'trend' ? 'block' : 'none' }}>
          <ScenarioTrendView scenario={scenario} lang={lang} />
        </div>
      )}
      {visited.compare && (
        <div style={{ display: tab === 'compare' ? 'block' : 'none' }}>
          <ScenarioCompareView scenario={scenario} lang={lang} />
        </div>
      )}
    </div>
  );
};

export default ScenarioDetail;

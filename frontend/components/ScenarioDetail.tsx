/**
 * ScenarioDetail — 調閱單一已保存情境（WMOM-20260719-02 前端，DEC-20260719-01）。
 *
 * 情境詮釋資料 + 頁籤容器：「趨勢」（單機發電量 vs 風速趨勢 + 故障標記，ScenarioTrendView）與
 * 「機組比較」（跨機組比較、有故障 vs 健康，ScenarioCompareView，A1 / DEC-20260720-02）。兩頁籤各
 * 自消費對應端點；本元件只負責詮釋資料 header + 頁籤切換，與兩個子視圖對稱解耦。
 */

import React, { useState } from 'react';
import { Btn, Card, Stat, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { windProfileLabel } from '../utils/windProfiles';
import ScenarioCompareView from './ScenarioCompareView';
import ScenarioTrendView from './ScenarioTrendView';

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
  fault_schedule?: Array<{ scenario_id: string; turbine_id: string; offset_seconds: number; severity_rate?: number }>;
}

export interface SavedScenario {
  id: number;
  started_at: string;
  ended_at?: string | null;
  turbine_count?: number;
  config?: ScenarioConfig;
}

/** PR C Phase 1 掛載請求（WMOM-20260926-03）：見 `ScenarioMountContext`。 */
export interface ScenarioMountRequest {
  scenarioId: number;
  scenarioName: string;
  target: 'overview' | 'turbine';
  /** `target === 'turbine'` 時帶入目前頁籤選取的機組（後端 `turbineId` 格式，如 `WT002`）。 */
  turbineWtId?: string;
}

interface Props {
  scenario: SavedScenario;
  lang?: 'en' | 'zh';
  onBack: () => void;
  /**
   * PR C Phase 1（WMOM-20260926-03）：把本情境掛載到 FarmOverview/TurbineDetail 做唯讀瀏覽。
   * 未提供時（如尚未整合掛載功能的呼叫端）不渲染按鈕，比照 `onNavigateInspection` 的
   * optional-prop fallback 慣例，避免舊呼叫端漏傳時整頁炸開。
   */
  onMount?: (request: ScenarioMountRequest) => void;
}

const ScenarioDetail: React.FC<Props> = ({ scenario, lang = 'zh', onBack, onMount }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const cfg = scenario.config ?? {};

  const [tab, setTab] = useState<DetailTab>('trend');
  // 選取機組提升到本層（controlled，WMOM-20260720-13 (2)）：ScenarioTrendView 原本自管 turbineId，
  // 但頁籤是條件式渲染（`{tab === 'trend' && <ScenarioTrendView/>}`）→ 切去「機組比較」再切回「趨勢」
  // 會 unmount 整個子元件，選取的機組連同 state 一起銷毀，回來又重設回 WT001（打在「比較↔趨勢來回」
  // 這條 A1 核心動線）。提升到這層、頁籤切換不影響本元件存續，選取值就能跨切換保留。
  const [turbineId, setTurbineId] = useState('WT001');

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

        {onMount && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
            <Btn
              size="sm"
              variant="secondary"
              onClick={() =>
                onMount({
                  scenarioId: scenario.id,
                  scenarioName: cfg.name || u('(unnamed scenario)', '（未命名情境）'),
                  target: 'overview',
                })
              }
              ariaLabel={u('View farm overview with this scenario', '以此情境瀏覽總覽')}
            >
              {u('View farm overview with this scenario', '以此情境瀏覽總覽')}
            </Btn>
            <Btn
              size="sm"
              variant="secondary"
              onClick={() =>
                onMount({
                  scenarioId: scenario.id,
                  scenarioName: cfg.name || u('(unnamed scenario)', '（未命名情境）'),
                  target: 'turbine',
                  turbineWtId: turbineId,
                })
              }
              ariaLabel={u('View turbine detail with this scenario', '以此情境瀏覽機組細節')}
            >
              {u('View turbine detail with this scenario', '以此情境瀏覽機組細節')}
            </Btn>
          </div>
        )}
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
              onClick={() => setTab(t.id)}
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

      {tab === 'trend' && (
        <ScenarioTrendView scenario={scenario} lang={lang} turbineId={turbineId} onTurbineIdChange={setTurbineId} />
      )}
      {tab === 'compare' && <ScenarioCompareView scenario={scenario} lang={lang} />}
    </div>
  );
};

export default ScenarioDetail;

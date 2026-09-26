/**
 * FarmOverview — A · Calm Operator 改版。
 *
 * 版面：
 *   1. PageHeader：「早安，營運團隊。」+ Farm + 12 機 + 日期
 *   2. Hero stat strip：4 等分卡片（Farm Power / Operating / Active Faults / Avg Wind）
 *   3. 24h 趨勢圖（時段切換 1H/6H/24H/7D，SVG 漸層折線）
 *   4. 風機卡片網格（4×3）
 *
 * 功能保留：原 SummaryView / TableView 改成 view-mode 切換按鈕（cards / summary / table），
 * 仍走同一資料來源；任何點擊風機都呼叫 onSelectTurbine 進入 detail。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { type TurbineData, TurbineStatus, type AppSettings, DataSourceType } from '../types';
import {
  Card,
  Btn,
  PageHeader,
  StatusPill,
  Stat,
  BigChart,
  MiniSparkline,
  turbineStatusTone,
  ScenarioMountBanner,
  type BigChartSeries,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { downloadBlob } from '../services/reportingService';
import { useScenarioMount } from '../contexts/ScenarioMountContext';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface FarmOverviewProps {
  turbines: TurbineData[];
  onSelectTurbine: (turbine: TurbineData) => void;
  settings: AppSettings;
  lang?: 'en' | 'zh';
  /** WMOM-20260507-02 sub-task f：PageHeader「+ 新報告」鈕 → 導向既有 `/admin/reports`（月報/年度預算齊全，不重造 modal）。 */
  onNavigateReports: () => void;
}

type TimeRange = '1H' | '6H' | '24H' | '7D';

const RANGE_TO_API: Record<TimeRange, string> = {
  '1H': '1h',
  '6H': '12h',
  '24H': '1d',
  '7D': '1d',
};

const RANGE_REFRESH_MS: Record<TimeRange, number> = {
  '1H': 5_000,
  '6H': 15_000,
  '24H': 30_000,
  '7D': 60_000,
};

interface TrendPoint {
  time: number;
  totalPower: number;
}

// Module-level cache to survive view-mode toggles
const _trendCache: Record<TimeRange, TrendPoint[]> = {
  '1H': [],
  '6H': [],
  '24H': [],
  '7D': [],
};
let _liveTrend: TrendPoint[] = [];
let _lastLiveAt = 0;
const MAX_LIVE_POINTS = 200;

const fmtPower = (mw: number): string => {
  if (Math.abs(mw) < 1) return `${(mw * 1000).toFixed(0)} kW`;
  return `${mw.toFixed(2)} MW`;
};

// ─── Hero strip ────────────────────────────────────────────────

const HeroStats: React.FC<{
  turbines: TurbineData[];
  tr: (en: string, zh: string) => string;
}> = ({ turbines, tr }) => {
  const { C } = useTheme();
  const total = turbines.reduce((s, t) => s + t.powerOutput, 0);
  const ops = turbines.filter(t => t.status === TurbineStatus.OPERATING).length;
  const flt = turbines.filter(t => t.status === TurbineStatus.FAULT).length;
  const rated = turbines.length * 2; // assume 2 MW per turbine for ratio display
  const avgWind = turbines.length
    ? turbines.reduce((s, t) => s + t.windSpeed, 0) / turbines.length
    : 0;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 14,
        marginBottom: 20,
      }}
    >
      <Card>
        <Stat
          label={tr('Farm Power', '風場功率')}
          value={total < 1 ? (total * 1000).toFixed(0) : total.toFixed(1)}
          unit={total < 1 ? 'kW' : 'MW'}
          hint={tr(`of ${rated.toFixed(1)} MW rated`, `額定 ${rated.toFixed(1)} MW`)}
          highlight
        />
      </Card>
      <Card>
        <Stat
          label={tr('Operating', '運轉中')}
          value={
            <>
              {ops}
              <span style={{ fontSize: 18, color: C.sub }}> / {turbines.length}</span>
            </>
          }
          hint={
            <span style={{ color: ops === turbines.length ? C.ok : C.sub }}>
              {ops === turbines.length ? tr('All healthy', '全部健康') : tr('Mixed status', '狀態混合')}
            </span>
          }
        />
      </Card>
      <Card tone={flt > 0 ? 'warn' : 'default'}>
        <Stat
          label={tr('Active Faults', '故障中')}
          value={flt}
          valueColor={flt > 0 ? C.warn : C.text}
          hint={flt > 0 ? tr('Needs attention →', '請關注 →') : tr('All clear', '一切順利')}
        />
      </Card>
      <Card>
        <Stat
          label={tr('Avg Wind', '平均風速')}
          value={avgWind.toFixed(1)}
          unit="m/s"
          hint={tr('Live SCADA average', 'SCADA 即時平均')}
        />
      </Card>
    </div>
  );
};

// ─── Trend card ────────────────────────────────────────────────

const TrendCard: React.FC<{
  turbines: TurbineData[];
  tr: (en: string, zh: string) => string;
  /**
   * 情境掛載中（PR C Phase 1，WMOM-20260926-03）：本卡片改走
   * `/api/turbines/farm-trend`（即時風場趨勢），與目前檢視的凍結情境快照無關——繼續抓取
   * 會把「唯讀回放」頁面混進真正即時的資料，比什麼都不顯示更誤導。掛載中一律停用抓取、
   * 改顯示提示文字。
   */
  disabled?: boolean;
}> = ({ turbines, tr, disabled }) => {
  const { C } = useTheme();
  const [range, setRange] = useState<TimeRange>('24H');
  const [apiData, setApiData] = useState<TrendPoint[]>(_trendCache[range]);
  const [liveData, setLiveData] = useState<TrendPoint[]>(_liveTrend);

  // Live accumulator for 1H mode
  useEffect(() => {
    if (disabled || range !== '1H' || !turbines.length) return;
    const now = Date.now();
    if (now - _lastLiveAt < 1800) return;
    _lastLiveAt = now;
    const totalPower = turbines.reduce((s, t) => s + t.powerOutput, 0);
    const next = [..._liveTrend, { time: now, totalPower: +totalPower.toFixed(2) }];
    _liveTrend = next.length > MAX_LIVE_POINTS ? next.slice(-MAX_LIVE_POINTS) : next;
    setLiveData(_liveTrend);
  }, [turbines, range, disabled]);

  // API fetch for longer ranges
  useEffect(() => {
    if (disabled || range === '1H') return;
    let cancelled = false;
    const fetchData = () => {
      authFetch(`${API_BASE}/api/turbines/farm-trend?range=${RANGE_TO_API[range]}&points=150`)
        .then(r => r.json())
        .then(res => {
          if (cancelled) return;
          if (res.data) {
            const mapped: TrendPoint[] = res.data.map((d: { timestamp: string; totalPower: number }) => ({
              time: d.timestamp ? new Date(d.timestamp).getTime() : 0,
              totalPower: d.totalPower,
            }));
            _trendCache[range] = mapped;
            setApiData(mapped);
          }
        })
        .catch(() => {
          /* ignore */
        });
    };
    fetchData();
    const id = setInterval(fetchData, RANGE_REFRESH_MS[range]);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [range, disabled]);

  const data = range === '1H' ? liveData : apiData;
  const series: BigChartSeries[] = useMemo(
    () => [
      {
        values: data.length > 0 ? data.map(d => d.totalPower) : [0],
        color: C.accent,
        fill: true,
      },
    ],
    [data, C.accent],
  );

  if (disabled) {
    return (
      <Card style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: C.text, marginBottom: 6 }}>
          {tr('Farm power trend', '風場功率趨勢')}
        </div>
        <div style={{ fontSize: 12, color: C.sub }}>
          {tr(
            'Not available in scenario view (shows live data, not this scenario). ' +
              'See the Trend tab on the scenario page for this scenario’s own history.',
            '情境唯讀檢視不提供本圖（本圖是即時資料，與所檢視情境無關）。' +
              '如需本情境的歷史趨勢，請至「情境模擬」頁該情境的「趨勢」頁籤查看。',
          )}
        </div>
      </Card>
    );
  }

  return (
    <Card style={{ marginBottom: 20 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 14,
          flexWrap: 'wrap',
          gap: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: C.text }}>
            {tr('Farm power · last ' + range, `風場功率　近 ${range}`)}
          </div>
          <div style={{ fontSize: 12, color: C.sub, marginTop: 2 }}>
            {tr('Hover the chart to inspect events', '滑入查看事件')}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['1H', '6H', '24H', '7D'] as TimeRange[]).map(r => {
            const active = range === r;
            return (
              <button
                key={r}
                onClick={() => setRange(r)}
                aria-pressed={active}
                aria-label={tr(`Range ${r}`, `時段 ${r}`)}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  borderRadius: 6,
                  background: active ? C.accent : 'transparent',
                  color: active ? C.accentInk : C.sub,
                  border: active ? 'none' : `1px solid ${C.border}`,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  fontWeight: active ? 600 : 500,
                }}
              >
                {r}
              </button>
            );
          })}
        </div>
      </div>
      {data.length === 0 ? (
        <div
          style={{
            height: 220,
            display: 'grid',
            placeItems: 'center',
            color: C.sub,
            fontSize: 13,
          }}
        >
          {tr('Collecting data…', '資料收集中…')}
        </div>
      ) : (
        <BigChart series={series} height={220} />
      )}
    </Card>
  );
};

// ─── Turbine card ──────────────────────────────────────────────

const TUR_STATE_SHORT: Record<number, string> = {
  1: 'STOP',
  2: 'STBY',
  3: 'WAIT',
  4: 'PREP',
  5: 'START',
  6: 'PROD',
  7: 'SHTDN',
  8: 'RSTR',
  9: 'NSTP',
};

interface TurbineCardProps {
  t: TurbineData;
  onClick: () => void;
  tr: (en: string, zh: string) => string;
  lang: 'en' | 'zh';
}

/**
 * React.memo 比較器：只比對卡片實際渲染的欄位 + lang。
 *
 * onClick / tr 每次父層 render 都是新 reference，但刻意不納入比較：
 *   - onClick 閉包捕捉的 turbine 物件即使過期，App 端 `liveTurbine` 仍以 id 反查
 *     最新資料，導航結果正確。
 *   - tr 是 lang 的純函式，故只需比 lang；同語言下舊 tr 輸出完全相同。
 * 效果：父層因非資料因素 re-render（檢視模式切換 / 健康輪詢 / modal 開關）時，
 * 資料未變的風機卡片可跳過 re-render，省去 14 張 SVG 重繪。
 */
function turbineCardEqual(prev: TurbineCardProps, next: TurbineCardProps): boolean {
  if (prev.lang !== next.lang) return false;
  const a = prev.t;
  const b = next.t;
  return (
    a.id === b.id &&
    a.name === b.name &&
    a.status === b.status &&
    a.turState === b.turState &&
    a.powerOutput === b.powerOutput &&
    a.windSpeed === b.windSpeed &&
    a.rotorSpeed === b.rotorSpeed &&
    a.temperature === b.temperature &&
    a.history === b.history
  );
}

const TCard: React.FC<TurbineCardProps> = React.memo(({ t, onClick, tr }) => {
  const { C } = useTheme();
  const tone = turbineStatusTone(t.status);
  const strokeColor =
    t.status === TurbineStatus.OPERATING
      ? C.ok
      : t.status === TurbineStatus.FAULT
        ? C.warn
        : t.status === TurbineStatus.IDLE
          ? C.amber
          : C.faint;

  // Sparkline values: prefer real history; fall back to deterministic synth
  const sparkValues =
    t.history && t.history.length > 4
      ? t.history.slice(-24).map(h => h.power)
      : Array.from({ length: 24 }).map(
          (_, i) => t.powerOutput * Math.max(0.4, 1 + Math.sin(i * 0.4 + t.id) * 0.18),
        );

  const statusLabel =
    t.status === TurbineStatus.OPERATING
      ? tr('OPERATING', '運轉中')
      : t.status === TurbineStatus.FAULT
        ? tr('FAULT', '故障')
        : t.status === TurbineStatus.IDLE
          ? tr('IDLE', '待機')
          : tr('OFFLINE', '離線');

  return (
    <Card padding={16} onClick={onClick}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: C.text }}>{t.name}</span>
          {t.turState && (
            <span
              style={{
                fontSize: 10,
                color: C.faint,
                fontFamily: 'JetBrains Mono, monospace',
              }}
            >
              {TUR_STATE_SHORT[t.turState] || `S${t.turState}`}
            </span>
          )}
        </div>
        <StatusPill tone={tone}>{statusLabel}</StatusPill>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span
          style={{
            fontFamily: '"DM Serif Display", serif',
            fontSize: 32,
            color: C.accent,
            fontWeight: 400,
            lineHeight: 1,
          }}
        >
          {t.powerOutput < 1 ? (t.powerOutput * 1000).toFixed(0) : t.powerOutput.toFixed(2)}
        </span>
        <span style={{ fontSize: 12, color: C.sub }}>{t.powerOutput < 1 ? 'kW' : 'MW'}</span>
      </div>
      <div style={{ marginTop: 8 }}>
        <MiniSparkline values={sparkValues} color={strokeColor} height={32} />
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11,
          color: C.sub,
          marginTop: 6,
          fontFamily: 'JetBrains Mono, monospace',
        }}
      >
        <span>{t.windSpeed.toFixed(1)} m/s</span>
        <span>{t.rotorSpeed.toFixed(1)} rpm</span>
        <span>{t.temperature.toFixed(0)}°C</span>
      </div>
    </Card>
  );
}, turbineCardEqual);

// ─── Compact tile (summary view) ───────────────────────────────

function compactTileEqual(prev: TurbineCardProps, next: TurbineCardProps): boolean {
  if (prev.lang !== next.lang) return false;
  const a = prev.t;
  const b = next.t;
  return (
    a.id === b.id &&
    a.name === b.name &&
    a.status === b.status &&
    a.powerOutput === b.powerOutput &&
    a.windSpeed === b.windSpeed
  );
}

const CompactTile: React.FC<TurbineCardProps> = React.memo(({ t, onClick, tr }) => {
  const { C } = useTheme();
  const tone = turbineStatusTone(t.status);
  const strokeColor =
    t.status === TurbineStatus.OPERATING ? C.ok : t.status === TurbineStatus.FAULT ? C.warn : C.amber;
  return (
    <Card
      padding={10}
      onClick={onClick}
      tone={t.status === TurbineStatus.FAULT ? 'warn' : 'default'}
      style={{ minHeight: 86 }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 4,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 12, color: C.text }}>{t.name}</span>
        <span
          aria-hidden
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: strokeColor,
          }}
        />
      </div>
      <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 18, color: C.text }}>
        {fmtPower(t.powerOutput)}
      </div>
      <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
        {t.windSpeed.toFixed(1)} m/s
      </div>
      {t.status === TurbineStatus.FAULT && (
        <div style={{ marginTop: 4 }}>
          <StatusPill tone={tone} size="sm">
            {tr('FAULT', '故障')}
          </StatusPill>
        </div>
      )}
    </Card>
  );
}, compactTileEqual);

// ─── Table view ────────────────────────────────────────────────

const TableView: React.FC<{
  turbines: TurbineData[];
  onSelect: (t: TurbineData) => void;
  tr: (en: string, zh: string) => string;
}> = ({ turbines, onSelect, tr }) => {
  const { C } = useTheme();
  const cols: { key: keyof TurbineData | 'name' | 'status'; label: string; align?: 'right' }[] = [
    { key: 'name', label: tr('Turbine', '風機') },
    { key: 'status', label: tr('Status', '狀態') },
    { key: 'powerOutput', label: tr('Power MW', '功率 MW'), align: 'right' },
    { key: 'windSpeed', label: tr('Wind m/s', '風速'), align: 'right' },
    { key: 'rotorSpeed', label: 'RPM', align: 'right' },
    { key: 'genStatorTemp1', label: tr('Gen °C', '發電機 °C'), align: 'right' },
    { key: 'vibrationX', label: tr('Vib X', '振動 X'), align: 'right' },
    { key: 'bladeAngle1', label: tr('Blade°', '葉片角'), align: 'right' },
    { key: 'cnvGenFreq', label: 'Hz', align: 'right' },
    { key: 'yawError', label: tr('Yaw°', '偏航°'), align: 'right' },
  ];
  return (
    <Card padding={0}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: C.panelMuted }}>
              {cols.map(c => (
                <th
                  key={c.key}
                  style={{
                    textAlign: c.align ?? 'left',
                    padding: '12px 14px',
                    fontSize: 11,
                    color: C.sub,
                    fontWeight: 500,
                    letterSpacing: 0.5,
                    textTransform: 'uppercase',
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {turbines.map(t => (
              <tr
                key={t.id}
                onClick={() => onSelect(t)}
                style={{
                  borderTop: `1px solid ${C.border}`,
                  cursor: 'pointer',
                  background: t.status === TurbineStatus.FAULT ? C.warnSoft : 'transparent',
                }}
              >
                <td style={{ padding: '12px 14px', fontWeight: 600 }}>{t.name}</td>
                <td style={{ padding: '12px 14px' }}>
                  <StatusPill tone={turbineStatusTone(t.status)}>
                    {t.status === TurbineStatus.OPERATING
                      ? tr('OPERATING', '運轉中')
                      : t.status === TurbineStatus.FAULT
                        ? tr('FAULT', '故障')
                        : t.status === TurbineStatus.IDLE
                          ? tr('IDLE', '待機')
                          : tr('OFFLINE', '離線')}
                  </StatusPill>
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.powerOutput.toFixed(2)}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.windSpeed.toFixed(1)}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.rotorSpeed.toFixed(1)}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.genStatorTemp1?.toFixed(1) ?? '—'}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.vibrationX?.toFixed(2) ?? '—'}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.bladeAngle1?.toFixed(1) ?? '—'}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.cnvGenFreq?.toFixed(1) ?? '—'}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                  {t.yawError?.toFixed(1) ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

// ─── View toggle ───────────────────────────────────────────────

type ViewMode = 'cards' | 'summary' | 'table';

const ViewToggle: React.FC<{
  mode: ViewMode;
  onChange: (m: ViewMode) => void;
  tr: (en: string, zh: string) => string;
}> = ({ mode, onChange, tr }) => {
  const { C } = useTheme();
  const items: { id: ViewMode; label: string }[] = [
    { id: 'cards', label: tr('Cards', '卡片') },
    { id: 'summary', label: tr('Summary', '摘要') },
    { id: 'table', label: tr('Table', '列表') },
  ];
  return (
    <div
      style={{
        display: 'inline-flex',
        background: C.panel,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {items.map(it => {
        const active = mode === it.id;
        return (
          <button
            key={it.id}
            onClick={() => onChange(it.id)}
            aria-pressed={active}
            style={{
              padding: '6px 12px',
              fontSize: 12,
              border: 'none',
              background: active ? C.accent : 'transparent',
              color: active ? C.accentInk : C.sub,
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontWeight: active ? 600 : 500,
            }}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
};

// ─── Main ──────────────────────────────────────────────────────

const FarmOverview: React.FC<FarmOverviewProps> = ({
  turbines,
  onSelectTurbine,
  settings,
  lang = 'zh',
  onNavigateReports,
}) => {
  const { C } = useTheme();
  const [mode, setMode] = useState<ViewMode>('cards');
  const [exporting, setExporting] = useState(false);
  const tr = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const scenarioMount = useScenarioMount();
  const mounted = scenarioMount.mounted;

  const dateLabel = lang === 'zh'
    ? new Date().toLocaleDateString('zh-TW')
    : new Date().toLocaleDateString();

  const isMock = settings.dataSource === DataSourceType.MOCK;

  /**
   * 匯出目前全風場快照（WMOM-20260507-02 sub-task a）：GET /api/export/snapshot
   * 回應直接以 Blob 觸發瀏覽器下載，不解析內容（保留後端原始 JSON 格式）。
   * 失敗僅 console.error（沿用本 issue「沒作用沒關係，開發階段」的決策，不彈 alert）。
   */
  const handleExportSnapshot = async (): Promise<void> => {
    setExporting(true);
    try {
      const resp = await authFetch(`${API_BASE}/api/export/snapshot`);
      if (!resp.ok) {
        throw new Error(`Export snapshot failed: HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const dateSuffix = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `farm-snapshot-${dateSuffix}.json`);
    } catch (e) {
      console.error('匯出風場快照失敗', e);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      {mounted && (
        <ScenarioMountBanner
          scenarioName={mounted.name}
          onExit={scenarioMount.unmount}
          lang={lang}
          loading={scenarioMount.loading}
          error={scenarioMount.error}
        />
      )}
      <PageHeader
        title={tr('Good morning, Operator.', '早安，營運團隊。')}
        sub={
          <span>
            {tr('Changhua Coastal · ', '彰化沿海　')}
            {turbines.length} {tr('turbines · ', '機・')}
            {dateLabel}
            {isMock && (
              <span style={{ marginLeft: 10 }}>
                <StatusPill tone="amber" size="sm">
                  MOCK
                </StatusPill>
              </span>
            )}
          </span>
        }
        actions={
          <>
            <ViewToggle mode={mode} onChange={setMode} tr={tr} />
            <Btn
              ariaLabel={tr('Export report', '匯出報告')}
              onClick={handleExportSnapshot}
              loading={exporting}
              disabled={!!mounted}
              title={
                mounted
                  ? tr(
                      'Exports live farm data, not this scenario — disabled in scenario view',
                      '匯出的是即時風場資料、非此情境——情境檢視中停用',
                    )
                  : undefined
              }
            >
              {tr('Export', '匯出')}
            </Btn>
            <Btn
              variant="primary"
              ariaLabel={tr('New report', '新報告')}
              onClick={onNavigateReports}
            >
              + {tr('New Report', '新報告')}
            </Btn>
          </>
        }
      />

      {/* Hero */}
      <HeroStats turbines={turbines} tr={tr} />

      {/* Trend */}
      <TrendCard turbines={turbines} tr={tr} disabled={!!mounted} />

      {/* Turbine list */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: C.text }}>
          {tr('Turbines', '風機列表')}
        </div>
        <div style={{ fontSize: 12, color: C.sub }}>
          {tr('Click a turbine to drill in', '點選風機進入詳情')}
        </div>
      </div>

      {mode === 'cards' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          {turbines.map(t => (
            <TCard key={t.id} t={t} onClick={() => onSelectTurbine(t)} tr={tr} lang={lang} />
          ))}
        </div>
      )}

      {mode === 'summary' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
            gap: 10,
          }}
        >
          {turbines.map(t => (
            <CompactTile key={t.id} t={t} onClick={() => onSelectTurbine(t)} tr={tr} lang={lang} />
          ))}
        </div>
      )}

      {mode === 'table' && <TableView turbines={turbines} onSelect={onSelectTurbine} tr={tr} />}
    </div>
  );
};

export default FarmOverview;

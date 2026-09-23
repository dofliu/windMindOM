/**
 * ScenarioCompareTimelineView — A2 Part 3「跨情境相對時間對齊時序疊圖」（DEC-20260720-02）。
 *
 * 消費既有單情境端點 `GET /api/scenarios/{id}/turbines/{turbineId}/history`（A1 的
 * `ScenarioTrendView` 已在用，非新後端端點）：每個選取情境各自抓一次該機組的原始讀數，換算成
 * 「相對 sim_start 的經過時間」（`utils/scenarioTimeline.buildTimelinePoints`）疊在同一張圖上比較
 * ——decision_log DEC-20260720-02 caveat 指出各情境 sim clock 皆從生成當下的 wall-clock 起算，
 * 絕對時間會重疊，故必須走相對時間對齊。
 *
 * 是 `ScenarioCompareAcrossView`（A2 摘要並排）的第二個頁籤；差異圖（同一 caveat 提到的 A2 完整
 * 範圍另一半）需要先解決多序列時間點不完全對齊的插值/分桶問題，刻意不在本次範圍，留給下一階段。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, Field, Select } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { buildTimelinePoints, formatElapsed, simStartMs, type TimelinePoint } from '../utils/scenarioTimeline';
import type { SavedScenario } from './ScenarioDetail';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

const POWER_TAG = 'WTUR_TotPwrAt';
const WIND_TAG = 'WMET_WSpeedNac';
const METRICS: { key: string; en: string; zh: string }[] = [
  { key: POWER_TAG, en: 'Power (kW)', zh: '發電量 (kW)' },
  { key: WIND_TAG, en: 'Wind (m/s)', zh: '風速 (m/s)' },
];

// 一次抓的上限，比照 ScenarioTrendView（HISTORY_LIMIT）——命中上限的長情境只拿到最新 N 筆，
// 較早的資料未載入，於 UI 明示（見 truncated）。
const HISTORY_LIMIT = 12000;

interface RawHistPoint {
  timestamp: string;
  scada?: Record<string, number>;
  scada_json?: string;
}

interface RawScenarioData {
  rows: RawHistPoint[];
  /** 對齊基準（epoch ms）：`config.sim_start` 有值即用它，否則退回本情境自己最早一筆讀數的時間。 */
  baseMs: number;
  truncated: boolean;
  /** 該情境缺 `config.sim_start`（未回填的舊情境）→ 改以自己最早一筆讀數當對齊基準，
   *  序列仍能疊圖看形狀，但無法跟其他情境對齊「情境開始後第幾秒」這個絕對意義。 */
  usedFallbackAlign: boolean;
  /** 該情境的 history 請求本身失敗（HTTP 非 2xx 或例外，如暫時性後端錯誤/網路問題），
   *  與「請求成功但這個機組真的沒有資料」是不同情況——前者值得使用者重試，後者不用。 */
  failed: boolean;
}

interface Props {
  /** 選取比較的情境（依 A2 並排順序），需含 `config.sim_start`/`turbine_count` 供對齊使用；
   *  呼叫端（`ScenarioCompareAcrossView`）負責把找不到對應 metadata 的情境先過濾掉——本元件
   *  收到的陣列視為已經是完整、可用的清單，不重複做這層防呆。 */
  scenarios: SavedScenario[];
  /** 顯示用名稱（scenarioId → label），沿用 A2 摘要並排已抓到的 `ScenarioSummary` 命名邏輯。 */
  labelFor: (scenarioId: number) => string;
  /** 與摘要並排共用的固定配色（依 index 指派，指標/頁籤切換顏色不變）。 */
  colorFor: (index: number) => string;
  lang?: 'en' | 'zh';
}

const ScenarioCompareTimelineView: React.FC<Props> = ({ scenarios, labelFor, colorFor, lang = 'zh' }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const turbineCount = useMemo(() => {
    if (scenarios.length === 0) return 3;
    return Math.min(...scenarios.map((s) => s.turbine_count ?? 3));
  }, [scenarios]);
  const turbineOptions = useMemo(
    () => Array.from({ length: turbineCount }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`),
    [turbineCount],
  );

  const [turbineId, setTurbineId] = useState('WT001');
  const [tag, setTag] = useState(POWER_TAG);
  const [rawByScenario, setRawByScenario] = useState<Record<number, RawScenarioData>>({});
  const [loading, setLoading] = useState(false);

  // 選取機組數變少（跨情境取最小共同機組數）時，先前選的 turbineId 可能已不在選項內——回退第一個。
  useEffect(() => {
    if (turbineOptions.length > 0 && !turbineOptions.includes(turbineId)) {
      setTurbineId(turbineOptions[0]);
    }
  }, [turbineOptions, turbineId]);

  const scenariosKey = scenarios.map((s) => s.id).join(',');

  // 只依 [情境選取, 機組] 重新抓資料——切換指標（tag）純粹是換一個欄位算圖，資料本身沒變，不必
  // 重打一次後端（見下方 seriesByScenario 用 useMemo 從已抓到的 rawByScenario 衍生）。
  useEffect(() => {
    if (scenarios.length === 0) {
      setRawByScenario({});
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    Promise.all(
      scenarios.map((s) =>
        authFetch(`${API_BASE}/api/scenarios/${s.id}/turbines/${turbineId}/history?limit=${HISTORY_LIMIT}`, {
          signal: ctrl.signal,
        })
          .then((r) => (r.ok ? r.json().then((res) => ({ res, failed: false })) : { res: { readings: [] }, failed: true }))
          .then(({ res, failed }) => {
            const raw: RawHistPoint[] = Array.isArray(res.readings) ? res.readings : [];
            const declaredBase = simStartMs(s.config?.sim_start);
            const usedFallbackAlign = declaredBase === null;
            // 退而求其次：無 sim_start 時用該情境自己最早一筆讀數當基準（raw 為 DESC，最後一筆最舊）。
            const fallbackBase = raw.length > 0 ? new Date(raw[raw.length - 1].timestamp).getTime() : 0;
            const data: RawScenarioData = {
              rows: raw,
              baseMs: declaredBase ?? fallbackBase,
              truncated: raw.length >= HISTORY_LIMIT,
              usedFallbackAlign,
              failed,
            };
            return [s.id, data] as const;
          })
          .catch(() => [s.id, { rows: [], baseMs: 0, truncated: false, usedFallbackAlign: false, failed: true }] as const),
      ),
    ).then((entries) => {
      if (!ctrl.signal.aborted) setRawByScenario(Object.fromEntries(entries));
    }).finally(() => {
      if (!ctrl.signal.aborted) setLoading(false);
    });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenariosKey, turbineId]);

  const seriesByScenario = useMemo(() => {
    const out: Record<number, TimelinePoint[]> = {};
    for (const [id, data] of Object.entries(rawByScenario) as [string, RawScenarioData][]) {
      out[Number(id)] = buildTimelinePoints(data.rows, tag, data.baseMs);
    }
    return out;
  }, [rawByScenario, tag]);

  const truncatedNames = scenarios.filter((s) => rawByScenario[s.id]?.truncated).map((s) => labelFor(s.id));
  const fallbackNames = scenarios.filter((s) => rawByScenario[s.id]?.usedFallbackAlign).map((s) => labelFor(s.id));
  const failedNames = scenarios.filter((s) => rawByScenario[s.id]?.failed).map((s) => labelFor(s.id));
  const hasAnyData = scenarios.some((s) => (seriesByScenario[s.id]?.length ?? 0) > 0);

  return (
    <div>
      <Card style={{ marginBottom: 14 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 10,
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {u('Timeline overlay · relative time', '時序疊圖　相對時間對齊')}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Field label={u('Turbine', '風機')}>
              <Select
                value={turbineId}
                onChange={setTurbineId}
                options={turbineOptions.map((t) => ({ value: t, label: t }))}
                ariaLabel={u('Turbine', '風機')}
              />
            </Field>
            <Field label={u('Metric', '指標')}>
              <Select
                value={tag}
                onChange={setTag}
                options={METRICS.map((m) => ({ value: m.key, label: u(m.en, m.zh) }))}
                ariaLabel={u('Metric', '指標')}
              />
            </Field>
          </div>
        </div>

        {failedNames.length > 0 && (
          <div
            style={{
              marginBottom: 10,
              fontSize: 12,
              color: C.warn,
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: '8px 12px',
            }}
          >
            {u(
              `${failedNames.join(', ')} — failed to load (possibly a transient error); try again later.`,
              `${failedNames.join('、')} — 載入失敗（可能是暫時性問題），稍後再試。`,
            )}
          </div>
        )}
        {fallbackNames.length > 0 && (
          <div
            style={{
              marginBottom: 10,
              fontSize: 12,
              color: C.amber,
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: '8px 12px',
            }}
          >
            {u(
              `${fallbackNames.join(', ')} — missing sim_start, aligned to this scenario's own first sample instead (not a true "time since scenario start").`,
              `${fallbackNames.join('、')} — 缺情境 sim_start，改以該情境自己最早一筆讀數對齊（並非真正的「情境開始後經過時間」）。`,
            )}
          </div>
        )}
        {truncatedNames.length > 0 && (
          <div
            style={{
              marginBottom: 10,
              fontSize: 12,
              color: C.amber,
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: '8px 12px',
            }}
          >
            {u(
              `${truncatedNames.join(', ')} — showing only the latest ${HISTORY_LIMIT.toLocaleString()} points; this scenario is longer, so earlier data is not loaded.`,
              `${truncatedNames.join('、')} — 僅顯示最近 ${HISTORY_LIMIT.toLocaleString()} 筆，此情境更長，較早的資料未載入。`,
            )}
          </div>
        )}

        {/* ── 純 DOM 圖例（獨立於 recharts 內建 Legend）──
             recharts <Legend> 在 jsdom（無 ResizeObserver、ResponsiveContainer 量到 0×0）測試環境下
             不會渲染內容，只能靠讀原始碼推論；這裡另外畫一份純文字色塊列表，讓「哪個顏色對應哪個
             情境」在瀏覽器與測試環境都同樣可驗證，也比 5 個情境擠在同一個 SVG legend 更好讀。 */}
        {scenarios.length > 0 && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
            {scenarios.map((s, i) => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: C.sub }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: colorFor(i), flexShrink: 0 }} />
                {labelFor(s.id)}
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {u('Loading…', '載入中…')}
          </div>
        )}
        {!loading && !hasAnyData && (
          <div style={{ fontSize: 13, color: C.faint, padding: '24px 0', textAlign: 'center' }}>
            {u('No data for this turbine in the selected scenarios.', '選取的情境中，此機組沒有資料。')}
          </div>
        )}
        {!loading && hasAnyData && (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="t"
                domain={['dataMin', 'dataMax']}
                tickFormatter={(v) => formatElapsed(v as number)}
                stroke={C.sub}
                fontSize={11}
              />
              <YAxis stroke={C.sub} fontSize={11} />
              {/* recharts 用精確數值比對（非「找最近的點」）在游標位置的 t 值上找每條線的對應點
                  （見 util/DataUtils.js `findEntryInArray`）。若選取的情境取樣間隔不同（例如
                  time_step 不同）或起點沒有剛好對齊在同一個相對時間刻度上，游標停在某個 tick 時，
                  其他情境很可能在該精確 t 值上沒有對應點——tooltip 會顯示「—」（見下方 formatter
                  的 null 防呆），不是資料缺漏或畫錯，是這個已知的 recharts 行為特性。已在下方
                  頁尾說明文字提醒使用者。 */}
              <Tooltip
                contentStyle={{
                  backgroundColor: C.panel,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  color: C.text,
                }}
                labelFormatter={(v) => u('Elapsed ', '經過 ') + formatElapsed(v as number)}
                formatter={(value: number, name: string) => [
                  value != null ? Number(value).toFixed(2) : '—',
                  name,
                ]}
              />
              {scenarios.map((s, i) => (
                <Line
                  key={s.id}
                  data={seriesByScenario[s.id] ?? []}
                  dataKey="value"
                  name={labelFor(s.id)}
                  stroke={colorFor(i)}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
        <div style={{ fontSize: 11, color: C.faint, marginTop: 8 }}>
          {u(
            "X axis is elapsed time since each scenario's own start, not wall-clock time — scenarios generated close together in time would otherwise overlap on an absolute time axis.",
            'X 軸為各情境「自己開始後」的經過時間，非絕對時鐘時間——短時間內連續生成的情境在絕對時間軸上會互相重疊。',
          )}
          {' '}
          {u(
            'If scenarios sample at different intervals, hovering may show a value for only some of them at a given point — that reflects the cursor landing between sample points for the others, not missing data.',
            '若情境取樣間隔不同，游標可能只顯示部分情境在該時刻的數值——是游標落在其他情境取樣點之間，非資料缺漏。',
          )}
        </div>
      </Card>
    </div>
  );
};

export default ScenarioCompareTimelineView;
